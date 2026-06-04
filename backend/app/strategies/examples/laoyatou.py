"""
老鸭头策略 (Lao Ya Tou / Old Duck Head)
经典技术形态：上升趋势中的回调再启动形态，形似鸭头。

形态结构：
  鸭颈 — 前期均线多头排列（MA5>MA10>MA60），股价沿 MA5 上行
  鸭头顶 — 高位回落，MA5 下穿 MA10（死叉），但 MA60 支撑不破，缩量
  鸭嘴 — MA5 重新上穿 MA10（金叉）+ 放量，MACD 零轴附近金叉（鸭眼）
  买入点 — 鸭嘴形成当日或次日

参考：经典老鸭头技术指标，适用于日线级别。
"""

import pandas as pd
import numpy as np

# ── 参数 ─────────────────────────────────────────────────
TOP_PICKS = 10
MIN_HISTORY = 80  # 至少需要 80 个交易日数据

# 均线
MA_SHORT = 5
MA_MID = 10
MA_LONG = 60

# 鸭颈 — 前期多头确认
NECK_LOOKBACK = 30       # 向前查看多少天找多头排列
NECK_MIN_DAYS = 5        # 至少连续多少天多头排列才算有效鸭颈

# 鸭头顶 — 回调参数
HEAD_LOOKBACK = 30       # 找鸭头顶高点的回溯天数
PULLBACK_MAX_PCT = 20.0  # 从鸭头顶到鸭嘴的最大回调幅度 %
PULLBACK_MIN_PCT = 3.0   # 最小回调幅度 %（太浅不构成形态）
HEAD_MAX_DAYS = 25       # 从鸭头顶到鸭嘴最多间隔天数

# 鸭嘴 — 放量金叉
VOL_RATIO_MIN = 1.2      # 鸭嘴日量 / 近5日均量下限
VOL_RATIO_STRONG = 2.0   # 强放量阈值
SHRINK_VOL_MAX = 0.7     # 回调期缩量上限（回调期均量/鸭颈期均量）

# MACD（鸭眼）
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# 市值过滤 (亿)
CAP_MIN = 10
CAP_MAX = 5000


def check_laoyatou(df):
    """
    检测 df 的最后一天是否触发老鸭头买入信号。

    五阶段检测：
      1. 鸭颈确认：前期存在 MA5>MA10>MA60 多头排列
      2. 鸭头顶识别：找到近期高点，其后 MA5 下穿 MA10
      3. MA60 支撑：回调期间股价始终在 MA60 上方
      4. 鸭嘴金叉：最近 MA5 重新上穿 MA10 + 放量
      5. 鸭眼确认：MACD 零轴附近或上方运行

    Returns:
        {"passed": bool, "score": int (0-100), "details": {...}, "breakdown": {...}}
    """
    result = {"passed": False, "score": 0, "details": {}, "breakdown": {}}
    filter_reasons = []

    if len(df) < MIN_HISTORY:
        result["details"]["error"] = f"数据不足：需要至少 {MIN_HISTORY} 个交易日，实际 {len(df)} 个"
        return result

    df = df.copy().sort_values("trade_date").reset_index(drop=True)

    # ── 计算技术指标 ──────────────────────────────────────
    df["ma5"] = df["close"].rolling(MA_SHORT).mean()
    df["ma10"] = df["close"].rolling(MA_MID).mean()
    df["ma60"] = df["close"].rolling(MA_LONG).mean()
    df["vol_ma5"] = df["vol"].rolling(5).mean()
    df["vol_ma20"] = df["vol"].rolling(20).mean()

    # MACD
    ema12 = df["close"].ewm(span=MACD_FAST, adjust=False).mean()
    ema26 = df["close"].ewm(span=MACD_SLOW, adjust=False).mean()
    df["macd_dif"] = ema12 - ema26
    df["macd_dea"] = df["macd_dif"].ewm(span=MACD_SIGNAL, adjust=False).mean()
    df["macd_hist"] = 2 * (df["macd_dif"] - df["macd_dea"])

    df["pct_chg"] = df["close"].pct_change() * 100

    target_idx = len(df) - 1
    target_row = df.iloc[target_idx]
    price = target_row["close"]

    # ── 数据有效性检查 ────────────────────────────────────
    ma60_val = target_row["ma60"]
    if pd.isna(ma60_val) or ma60_val <= 0:
        result["details"]["error"] = "MA60 无法计算"
        return result

    # ═══════════════════════════════════════════════════════
    # 阶段一：鸭颈确认 — 前期多头排列
    # ═══════════════════════════════════════════════════════
    neck_start = max(0, target_idx - HEAD_LOOKBACK - NECK_LOOKBACK)
    neck_end = target_idx - 1  # 不包含今天

    neck_bullish_days = 0
    neck_max_consecutive = 0
    neck_consecutive = 0
    neck_volumes = []

    for i in range(neck_start, neck_end + 1):
        row = df.iloc[i]
        ma5_v = row["ma5"]
        ma10_v = row["ma10"]
        ma60_v = row["ma60"]

        if pd.isna(ma5_v) or pd.isna(ma10_v) or pd.isna(ma60_v):
            continue

        if ma5_v > ma10_v > ma60_v and row["close"] > ma5_v:
            neck_bullish_days += 1
            neck_consecutive += 1
            neck_max_consecutive = max(neck_max_consecutive, neck_consecutive)
            neck_volumes.append(row["vol"])
        else:
            neck_consecutive = 0

    neck_has_pattern = neck_max_consecutive >= NECK_MIN_DAYS
    neck_avg_vol = sum(neck_volumes) / len(neck_volumes) if neck_volumes else 0

    result["details"]["neck_bullish_days"] = neck_bullish_days
    result["details"]["neck_max_consecutive"] = neck_max_consecutive
    result["details"]["neck_has_pattern"] = neck_has_pattern

    if not neck_has_pattern:
        filter_reasons.append(f"鸭颈不成立：近{NECK_LOOKBACK + HEAD_LOOKBACK}天内最多连续{neck_max_consecutive}天多头排列，需≥{NECK_MIN_DAYS}天")

    # ═══════════════════════════════════════════════════════
    # 阶段二：鸭头顶识别
    # ═══════════════════════════════════════════════════════
    head_search_start = max(0, target_idx - HEAD_LOOKBACK)
    head_search_end = target_idx

    # 在回溯窗口内找最高收盘价作为鸭头顶
    head_peak_idx = head_search_start
    head_peak_price = df.iloc[head_search_start]["close"]
    for i in range(head_search_start, head_search_end + 1):
        if df.iloc[i]["close"] > head_peak_price:
            head_peak_price = df.iloc[i]["close"]
            head_peak_idx = i

    # 确认鸭头顶后存在 MA5 下穿 MA10（死叉）
    death_cross_idx = None
    for i in range(head_peak_idx + 1, target_idx + 1):
        curr = df.iloc[i]
        prev = df.iloc[i - 1]
        if (pd.notna(curr["ma5"]) and pd.notna(curr["ma10"])
                and pd.notna(prev["ma5"]) and pd.notna(prev["ma10"])):
            if prev["ma5"] >= prev["ma10"] and curr["ma5"] < curr["ma10"]:
                death_cross_idx = i
                break

    # 鸭头顶到今天的回调幅度
    pullback_pct = (head_peak_price - price) / head_peak_price * 100 if head_peak_price > 0 else 0
    head_to_now_days = target_idx - head_peak_idx

    result["details"]["head_peak_price"] = round(head_peak_price, 2)
    result["details"]["head_peak_date"] = str(df.iloc[head_peak_idx]["trade_date"])
    result["details"]["death_cross_idx"] = int(death_cross_idx) if death_cross_idx is not None else None
    result["details"]["pullback_pct"] = round(pullback_pct, 2)
    result["details"]["head_to_now_days"] = head_to_now_days

    if death_cross_idx is None:
        filter_reasons.append("未检测到鸭头顶后的死叉（MA5下穿MA10）")

    if pullback_pct < PULLBACK_MIN_PCT:
        filter_reasons.append(f"回调幅度过浅({pullback_pct:.1f}%<{PULLBACK_MIN_PCT}%)，不构成鸭头形态")
    if pullback_pct > PULLBACK_MAX_PCT:
        filter_reasons.append(f"回调幅度过深({pullback_pct:.1f}%>{PULLBACK_MAX_PCT}%)，形态破坏")

    if head_to_now_days > HEAD_MAX_DAYS:
        filter_reasons.append(f"鸭头顶距今{head_to_now_days}天，超过{HEAD_MAX_DAYS}天上限")

    # ═══════════════════════════════════════════════════════
    # 阶段三：MA60 支撑 — 回调期间不破 MA60
    # ═══════════════════════════════════════════════════════
    ma60_broken = False
    ma60_lowest_dist = float("inf")
    for i in range(head_peak_idx, target_idx + 1):
        row = df.iloc[i]
        mv = row["ma60"]
        if pd.isna(mv) or mv <= 0:
            continue
        dist = (row["close"] - mv) / mv * 100
        if dist < ma60_lowest_dist:
            ma60_lowest_dist = dist
        if row["low"] < mv:  # 盘中跌破 MA60 也算
            ma60_broken = True

    result["details"]["ma60_broken"] = ma60_broken
    result["details"]["ma60_lowest_dist"] = round(ma60_lowest_dist, 2)

    if ma60_broken:
        filter_reasons.append("回调期间跌破 MA60 支撑，形态破坏")

    # ═══════════════════════════════════════════════════════
    # 阶段四：鸭嘴 — MA5 重新上穿 MA10（金叉）+ 放量
    # ═══════════════════════════════════════════════════════
    golden_cross_today = False
    golden_cross_recent = False
    golden_cross_idx = None

    # 检测今天是否金叉
    if target_idx >= 1:
        prev = df.iloc[target_idx - 1]
        if (pd.notna(prev["ma5"]) and pd.notna(prev["ma10"])
                and pd.notna(target_row["ma5"]) and pd.notna(target_row["ma10"])):
            if prev["ma5"] <= prev["ma10"] and target_row["ma5"] > target_row["ma10"]:
                golden_cross_today = True
                golden_cross_idx = target_idx

    # 如果今天不是金叉，检查近 3 天内
    if not golden_cross_today:
        for i in range(max(0, target_idx - 3), target_idx):
            curr = df.iloc[i]
            prev = df.iloc[i - 1]
            if (pd.notna(curr["ma5"]) and pd.notna(curr["ma10"])
                    and pd.notna(prev["ma5"]) and pd.notna(prev["ma10"])):
                if prev["ma5"] <= prev["ma10"] and curr["ma5"] > curr["ma10"]:
                    golden_cross_recent = True
                    golden_cross_idx = i
                    break

    has_golden_cross = golden_cross_today or golden_cross_recent

    # 量能确认
    vol_ma5_val = target_row["vol_ma5"]
    today_vol = target_row["vol"]
    vol_ratio = today_vol / vol_ma5_val if vol_ma5_val > 0 and not pd.isna(vol_ma5_val) else 0

    # 回调期缩量检查
    if death_cross_idx is not None and golden_cross_idx is not None:
        pullback_start = min(death_cross_idx, golden_cross_idx)
        pullback_end = max(death_cross_idx, golden_cross_idx)
    elif death_cross_idx is not None:
        pullback_start = death_cross_idx
        pullback_end = target_idx
    else:
        pullback_start = head_peak_idx
        pullback_end = target_idx

    pullback_volumes = []
    for i in range(pullback_start, pullback_end + 1):
        v = df.iloc[i]["vol"]
        if v and v > 0:
            pullback_volumes.append(v)

    pullback_avg_vol = sum(pullback_volumes) / len(pullback_volumes) if pullback_volumes else 0
    shrink_ratio = pullback_avg_vol / neck_avg_vol if neck_avg_vol > 0 else 1.0

    vol_expand = vol_ratio >= VOL_RATIO_MIN
    vol_shrink = shrink_ratio <= SHRINK_VOL_MAX if neck_avg_vol > 0 else True

    result["details"]["golden_cross_today"] = golden_cross_today
    result["details"]["golden_cross_recent"] = golden_cross_recent
    result["details"]["golden_cross_idx"] = golden_cross_idx
    result["details"]["vol_ratio"] = round(vol_ratio, 2)
    result["details"]["vol_expand"] = vol_expand
    result["details"]["shrink_ratio"] = round(shrink_ratio, 2)
    result["details"]["vol_shrink"] = vol_shrink

    if not has_golden_cross:
        filter_reasons.append("未检测到鸭嘴金叉（MA5上穿MA10）")
    if not vol_expand:
        filter_reasons.append(f"鸭嘴日量能不足(量比{vol_ratio:.1f}x，需≥{VOL_RATIO_MIN}x)")

    # ═══════════════════════════════════════════════════════
    # 阶段五：鸭眼 — MACD 确认
    # ═══════════════════════════════════════════════════════
    dif_val = target_row["macd_dif"]
    dea_val = target_row["macd_dea"]

    # MACD 金叉（近期）
    macd_golden = False
    for i in range(max(0, target_idx - 5), target_idx + 1):
        if i >= 1:
            curr = df.iloc[i]
            prev = df.iloc[i - 1]
            if (pd.notna(curr["macd_dif"]) and pd.notna(curr["macd_dea"])
                    and pd.notna(prev["macd_dif"]) and pd.notna(prev["macd_dea"])):
                if prev["macd_dif"] <= prev["macd_dea"] and curr["macd_dif"] > curr["macd_dea"]:
                    macd_golden = True
                    break

    # MACD 在零轴上方
    macd_above_zero = dif_val > 0 and dea_val > 0 if pd.notna(dif_val) and pd.notna(dea_val) else False

    # MACD 红柱或绿柱缩短
    macd_hist_rising = False
    if target_idx >= 1:
        prev_hist = df.iloc[target_idx - 1]["macd_hist"]
        curr_hist = target_row["macd_hist"]
        if pd.notna(prev_hist) and pd.notna(curr_hist):
            macd_hist_rising = curr_hist > prev_hist

    macd_ok = macd_golden or macd_above_zero or macd_hist_rising

    result["details"]["macd_dif"] = round(dif_val, 4) if pd.notna(dif_val) else None
    result["details"]["macd_dea"] = round(dea_val, 4) if pd.notna(dea_val) else None
    result["details"]["macd_golden"] = macd_golden
    result["details"]["macd_above_zero"] = macd_above_zero
    result["details"]["macd_hist_rising"] = macd_hist_rising

    if not macd_ok:
        filter_reasons.append("MACD 未确认（需金叉/零轴上/红柱放大）")

    # ── 当前均线状态 ──────────────────────────────────────
    ma5_now = target_row["ma5"]
    ma10_now = target_row["ma10"]
    ma60_now = target_row["ma60"]

    result["details"]["ma5_now"] = round(ma5_now, 2) if pd.notna(ma5_now) else None
    result["details"]["ma10_now"] = round(ma10_now, 2) if pd.notna(ma10_now) else None
    result["details"]["ma60_now"] = round(ma60_now, 2) if pd.notna(ma60_now) else None
    result["details"]["close"] = round(price, 2) if price else None
    result["details"]["filter_reasons"] = filter_reasons

    # ═══════════════════════════════════════════════════════
    # 打分（满分 100）
    # ═══════════════════════════════════════════════════════
    score = 0
    bd = {}

    # 1. 鸭颈强度 (0-15)
    if neck_max_consecutive >= 15:
        score += 15; bd["neck"] = 15
    elif neck_max_consecutive >= 10:
        score += 12; bd["neck"] = 12
    elif neck_max_consecutive >= NECK_MIN_DAYS:
        score += 8; bd["neck"] = 8
    else:
        score += 4; bd["neck"] = 4

    # 2. 回调形态 (0-20)
    if PULLBACK_MIN_PCT <= pullback_pct <= 10:
        score += 20; bd["pullback"] = 20
    elif pullback_pct <= 15:
        score += 15; bd["pullback"] = 15
    elif pullback_pct <= PULLBACK_MAX_PCT:
        score += 10; bd["pullback"] = 10
    else:
        bd["pullback"] = 0

    # 3. MA60 支撑距离 (0-15)
    if ma60_lowest_dist > 5:
        score += 15; bd["ma60_support"] = 15
    elif ma60_lowest_dist > 2:
        score += 12; bd["ma60_support"] = 12
    elif ma60_lowest_dist > 0:
        score += 8; bd["ma60_support"] = 8
    else:
        score += 3; bd["ma60_support"] = 3

    # 4. 鸭嘴放量强度 (0-20)
    if golden_cross_today and vol_ratio >= VOL_RATIO_STRONG:
        score += 20; bd["duck_mouth"] = 20
    elif golden_cross_today and vol_expand:
        score += 16; bd["duck_mouth"] = 16
    elif golden_cross_recent and vol_expand:
        score += 12; bd["duck_mouth"] = 12
    elif golden_cross_recent:
        score += 8; bd["duck_mouth"] = 8
    else:
        bd["duck_mouth"] = 0

    # 5. 缩量回调 (0-10)
    if vol_shrink and shrink_ratio < 0.5:
        score += 10; bd["shrink"] = 10
    elif vol_shrink:
        score += 7; bd["shrink"] = 7
    elif shrink_ratio < 1.0:
        score += 4; bd["shrink"] = 4
    else:
        bd["shrink"] = 0

    # 6. MACD 鸭眼 (0-15)
    if macd_golden and macd_above_zero:
        score += 15; bd["macd"] = 15
    elif macd_golden:
        score += 12; bd["macd"] = 12
    elif macd_above_zero:
        score += 8; bd["macd"] = 8
    elif macd_hist_rising:
        score += 5; bd["macd"] = 5
    else:
        bd["macd"] = 0

    # 7. 当前均线状态 (0-5)
    if pd.notna(ma5_now) and pd.notna(ma10_now) and pd.notna(ma60_now):
        if ma5_now > ma10_now > ma60_now:
            score += 5; bd["ma_state"] = 5
        elif ma5_now > ma10_now:
            score += 3; bd["ma_state"] = 3
        else:
            bd["ma_state"] = 0
    else:
        bd["ma_state"] = 0

    result["score"] = score
    result["breakdown"] = bd

    # ── 通过判断 ──────────────────────────────────────────
    passed = len(filter_reasons) == 0
    result["passed"] = passed

    # ── 信号文字 ──────────────────────────────────────────
    if passed:
        parts = []
        parts.append(f"鸭头回调{pullback_pct:.1f}%")
        if golden_cross_today:
            parts.append("今日鸭嘴金叉")
        else:
            parts.append(f"近3日鸭嘴金叉")
        if vol_expand:
            parts.append(f"放量{vol_ratio:.1f}x")
        if macd_golden:
            parts.append("MACD金叉")
        elif macd_above_zero:
            parts.append("MACD零轴上")
        result["details"]["signal_text"] = " → ".join(parts)
    else:
        result["details"]["signal_text"] = "未达标:" + filter_reasons[0]

    return result


def run(data):
    """
    AIpicking 策略接口 — 老鸭头形态选股。

    Args:
        data: {
            "cutoff_date": "20260604",
            "stocks": [{"ts_code": "600001.SH", "name": "上证指数", "total_shares": ..., "float_shares": ...}],
            "daily": {
                "600001.SH": [{"trade_date": "20260101", "open": 10.0, "high": 10.5,
                               "low": 9.8, "close": 10.2, "vol": 50000, ...}],
                ...
            },
            "config": {  # 可选，单股诊断时含 ts_code
                "ts_code": ""  # 非空 = 单股诊断模式
            }
        }

    Returns:
        [{"ts_code": "600001.SH", "name": "...", "score": 85,
          "signal": "鸭头回调8.5%→今日鸭嘴金叉→放量1.5x→MACD金叉",
          "breakdown": {...}, "details": {...}}, ...]
    """
    cutoff_date = data.get("cutoff_date", "")
    stocks = data.get("stocks", [])
    daily = data.get("daily", {})
    config = data.get("config", {}) or {}

    target_ts_code = config.get("ts_code", "").strip() if config else ""

    stock_lookup = {s["ts_code"]: s for s in stocks}
    recommendations = []

    for ts_code, rows in daily.items():
        if not rows:
            continue

        stock = stock_lookup.get(ts_code, {})
        name = stock.get("name", ts_code)

        # ── 过滤条件（单股诊断模式跳过市值/ST 过滤）─────

        # ST 过滤
        if not target_ts_code and "ST" in name:
            continue

        # 市值过滤
        if not target_ts_code:
            total_shares = stock.get("total_shares", 0) or 0
            last_close = rows[-1]["close"] if rows else 0
            market_cap = total_shares * last_close / 1e8 if total_shares > 0 else 0
            if market_cap < CAP_MIN or market_cap > CAP_MAX:
                continue

        # ── 构建 DataFrame ─────────────────────────────────
        df = pd.DataFrame(rows)
        if len(df) < MIN_HISTORY:
            continue

        # ── 执行形态检测 ──────────────────────────────────
        result = check_laoyatou(df)

        if not result["passed"] and not target_ts_code:
            continue

        # ── 构建输出 ──────────────────────────────────────
        signal_text = result["details"].get("signal_text", "老鸭头")
        recommendations.append({
            "ts_code": ts_code,
            "name": name,
            "score": result["score"],
            "signal": signal_text,
            "breakdown": result.get("breakdown", {}),
            "details": result.get("details", {}),
        })

    # ── 按评分降序排列，返回 Top N ────────────────────────
    recommendations.sort(key=lambda x: x["score"], reverse=True)
    return recommendations[:TOP_PICKS]
