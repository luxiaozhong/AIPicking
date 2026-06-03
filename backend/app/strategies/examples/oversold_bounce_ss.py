"""
超跌反弹策略 — 上证深证版 (Oversold Bounce SS)
捕捉放量急跌 → 缩量止跌 → 放量反弹的三阶段信号链。

原始逻辑来源：oversold_bounce.py（创业板+科创板版本）
适用范围：上证主板(600/601/603/605) + 深证主板(000/001/002/003)
技术指标：价格回撤、MA20偏离、恐慌放量、缩量止跌、放量反弹、收盘位置
"""

import pandas as pd
import numpy as np

# ── 参数（可通过 config 覆盖）──────────────────────────────
TOP_PICKS = 100
MIN_HISTORY = 60  # 最低交易日数（替代 list_date 过滤）

# 急跌参数
DRAWDOWN_PCT = 15.0        # 回撤幅度 %
LOOKBACK_DAYS = 20         # 找高点回溯天数
PANIC_VOL_RATIO = 2.0      # 恐慌放量：某日量 > 20日均量 × N
MA20_DEVIATION = 5.0       # MA20 偏离度：收盘价需低于 MA20 至少 N%

# 止跌参数
SHRINK_VOL_RATIO = 0.6     # 缩量标准：止跌日量 < 20日均量 × N
STABILIZE_WINDOW = 3       # 止跌日搜索窗口（在买入日前 N 天内找）
LOW_TOLERANCE = 0.04       # 止跌低点容差：最低价 ≥ 前日低 × (1 - N)

# 反弹参数
BOUNCE_VOL_RATIO = 1.2     # 反弹放量：买入日量 > 止跌日量 × N
CLOSE_UPPER_RATIO = 0.0    # 收盘在振幅上半区：0 = 不检查

# 大盘择时
MARKET_TIMING = True
MARKET_INDEX = "000001.SH"  # 上证指数（需带后缀）
MARKET_MA20_BELOW = 1.5    # 指数收盘需低于 MA20 至少 N%

# 市值过滤 (亿)
CAP_MIN = 20
CAP_MAX = 5000


# ═══════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════

def _calc_change(df, idx, days):
    """计算 N 日涨跌幅（基于收盘价）"""
    p = idx - days
    if p < 0:
        return None
    prev = df.iloc[p]["close"]
    curr = df.iloc[idx]["close"]
    if prev and prev > 0:
        return round((curr - prev) / prev * 100, 2)
    return None


def _is_market_oversold(daily, index_code, threshold):
    """检查参考指数是否处于超跌状态：收盘价低于 MA20 至少 threshold%"""
    if index_code not in daily:
        return True  # 无指数数据，默认通过

    rows = daily[index_code]
    if len(rows) < 20:
        return True

    df = pd.DataFrame(rows).sort_values("trade_date")
    df["ma20"] = df["close"].rolling(20).mean()

    latest = df.iloc[-1]
    ma20 = latest["ma20"]
    close = latest["close"]

    if pd.isna(ma20) or ma20 <= 0 or close is None or close <= 0:
        return True

    deviation = (ma20 - close) / ma20 * 100
    return deviation >= threshold


def _compute_turnover(vol, amount, close, float_shares):
    """
    估算换手率(%)。

    自适应 vol 单位：通过 amount/(close×vol) 比率判断：
      ratio≈1   → vol 单位「股」
      ratio≈100 → vol 单位「手」(1手=100股)
    """
    if not float_shares or float_shares <= 0:
        return 0.0
    if not (vol and vol > 0 and close and close > 0):
        return 0.0

    # 自适应单位归一化
    if amount and amount > 0:
        ratio = amount / (close * vol)
        if ratio > 50:  # vol 单位为「手」
            shares_traded = vol * 100
        else:
            shares_traded = vol
    else:
        shares_traded = vol  # 无 amount 回退到 vol（假设为股）

    if shares_traded > 0:
        turnover = shares_traded / float_shares * 100
        return min(round(turnover, 2), 100.0)  # 上限 100%，防止数据异常
    return 0.0


# ═══════════════════════════════════════════════════════════
# 核心检测函数
# ═══════════════════════════════════════════════════════════

def check_oversold_bounce(df):
    """
    检测 df 的最后一天是否触发超跌反弹信号。

    三阶段信号链：
      阶段一：放量急跌（回撤≥阈值 + 低于MA20 + 窗口内曾恐慌放量）
      阶段二：缩量止跌（量萎缩 + 量递减 + 不再创新低）
      阶段三：放量反弹（今日放量 > 止跌日量 × 倍数 + 收盘位置）

    Returns:
        {"passed": bool, "score": int, "details": {...}, "breakdown": {...}}
    """
    result = {"passed": False, "score": 0, "details": {}, "breakdown": {}}
    filter_reasons = []

    if len(df) < MIN_HISTORY:
        result["details"]["error"] = f"数据不足：需要至少 {MIN_HISTORY} 个交易日，实际 {len(df)} 个"
        return result

    df = df.copy().sort_values("trade_date").reset_index(drop=True)

    # ── 计算指标 ──────────────────────────────────────────
    df["ma20"] = df["close"].rolling(20).mean()
    df["vol_ma20"] = df["vol"].rolling(20).mean()

    target_idx = len(df) - 1
    target_row = df.iloc[target_idx]
    price = target_row["close"]

    # ── 阶段一：急跌识别 ──────────────────────────────────
    lookback_start = max(0, target_idx - LOOKBACK_DAYS)
    window = df.iloc[lookback_start: target_idx + 1]
    peak_close = window["close"].max()

    # 1a. 回撤幅度
    drawdown_pct = (peak_close - price) / peak_close * 100 if peak_close > 0 else 0
    if drawdown_pct < DRAWDOWN_PCT:
        filter_reasons.append(f"回撤不足({drawdown_pct:.1f}%<{DRAWDOWN_PCT}%)")

    # 1b. MA20 偏离
    ma20 = target_row["ma20"]
    ma20_dist = 0.0  # 默认值
    if pd.isna(ma20) or ma20 <= 0:
        filter_reasons.append("无法计算MA20")
    else:
        ma20_dist = (ma20 - price) / ma20 * 100
        if ma20_dist < MA20_DEVIATION:
            filter_reasons.append(f"MA20偏离不足({ma20_dist:.1f}%<{MA20_DEVIATION}%)")

    # 1c. 恐慌放量：窗口内任意一天量 > 20日均量 × panic_vol_ratio
    has_panic_vol = False
    for _, row in window.iterrows():
        vm = row.get("vol_ma20")
        if pd.notna(vm) and vm > 0 and row["vol"] > vm * PANIC_VOL_RATIO:
            has_panic_vol = True
            break
    if not has_panic_vol:
        filter_reasons.append("窗口内无恐慌放量")

    # ── 阶段二：在买入日前 stabilize_window 天内找止跌日 ──
    stabilize_idx = None
    search_start = max(0, target_idx - STABILIZE_WINDOW)
    for s in range(target_idx - 1, search_start - 1, -1):
        if s < 1:
            continue
        sd = df.iloc[s]

        # 2a. 缩量：量 < 20日均量 × shrink_vol_ratio
        svm = sd.get("vol_ma20")
        if pd.isna(svm) or svm <= 0:
            continue
        if sd["vol"] >= svm * SHRINK_VOL_RATIO:
            continue

        # 2a-sanity. 数据完整性校验（非原始策略条件，适配本系统日线数据质量）：
        #   (1) amount 应与 close×vol 基本吻合 — 排除 amount 字段损坏
        #   (2) vol 不低于均量的 1% — 排除系统性异常日（如全板成交量骤降 200 倍）
        sd_close_v = sd.get("close") or 0
        sd_vol_v = sd.get("vol") or 0
        sd_amount = sd.get("amount") or 0
        if sd_amount > 0 and sd_close_v > 0 and sd_vol_v > 0:
            if sd_amount < sd_close_v * sd_vol_v * 0.1:
                continue
        if sd_vol_v < svm * 0.01:
            continue

        # 2b. 缩量递减：止跌日量 < 前日量
        prev1 = df.iloc[s - 1]
        if sd["vol"] >= prev1["vol"]:
            continue

        # 2c. 不再创新低：止跌日最低 >= 前日最低 × (1 - tolerance)
        if sd["low"] is None or prev1["low"] is None:
            continue
        if sd["low"] < prev1["low"] * (1 - LOW_TOLERANCE):
            continue

        stabilize_idx = s
        break

    if stabilize_idx is None:
        filter_reasons.append("未找到止跌日（缩量+缩量递减+不再创新低）")

    # ── 阶段三：反弹触发（target_date 对比止跌日）─────────
    close_position = 0.5
    if stabilize_idx is not None:
        stabilize_row = df.iloc[stabilize_idx]
        stab_vol = stabilize_row["vol"]
        today_vol = target_row["vol"]

        # 3a. 放量反弹
        if stab_vol is None or stab_vol <= 0:
            filter_reasons.append("止跌日量无效")
        elif today_vol is None or today_vol <= stab_vol * BOUNCE_VOL_RATIO:
            actual_ratio = today_vol / stab_vol if (stab_vol and today_vol) else 0
            filter_reasons.append(f"反弹未放量({actual_ratio:.1f}x<{BOUNCE_VOL_RATIO}x)")

        # 3b. 收盘强势位置（仅当 CLOSE_UPPER_RATIO > 0 时检查）
        if CLOSE_UPPER_RATIO > 0:
            if target_row["high"] is not None and target_row["low"] is not None and target_row["high"] > target_row["low"]:
                close_position = (price - target_row["low"]) / (target_row["high"] - target_row["low"])
                if close_position < CLOSE_UPPER_RATIO:
                    filter_reasons.append(f"收盘偏弱({close_position:.2f}<{CLOSE_UPPER_RATIO})")
            else:
                filter_reasons.append("日内无振幅数据")

    # ── 汇总详情 ──────────────────────────────────────────
    result["details"]["drawdown_pct"] = round(drawdown_pct, 2)
    result["details"]["peak_close"] = round(peak_close, 2)
    result["details"]["ma20_dist"] = round(ma20_dist, 2)
    result["details"]["has_panic_vol"] = has_panic_vol
    result["details"]["filter_reasons"] = filter_reasons

    if stabilize_idx is not None:
        sr = df.iloc[stabilize_idx]
        shrink_ratio = round(sr["vol"] / sr["vol_ma20"], 2) if sr.get("vol_ma20") and sr["vol_ma20"] > 0 else None
        stab_vol_val = sr["vol"] or 0
        today_vol_val = target_row["vol"] or 0
        bounce_ratio = round(today_vol_val / stab_vol_val, 1) if stab_vol_val > 0 else None

        result["details"]["stabilize_date"] = str(sr["trade_date"])
        result["details"]["stabilize_low"] = round(sr["low"], 2) if sr["low"] else None
        result["details"]["stabilize_close"] = round(sr["close"], 2) if sr["close"] else None
        result["details"]["shrink_vol_ratio_actual"] = shrink_ratio
        result["details"]["bounce_vol_ratio_actual"] = bounce_ratio
        result["details"]["close_position"] = round(close_position, 2)
    else:
        result["details"]["stabilize_date"] = None
        result["details"]["shrink_vol_ratio_actual"] = None
        result["details"]["bounce_vol_ratio_actual"] = None

    result["details"]["close"] = round(price, 2) if price else None
    result["details"]["ma20"] = round(ma20, 2)
    result["details"]["change_3d"] = _calc_change(df, target_idx, 3)
    result["details"]["change_5d"] = _calc_change(df, target_idx, 5)
    result["details"]["change_10d"] = _calc_change(df, target_idx, 10)

    # ── 判断通过 ──────────────────────────────────────────
    passed = len(filter_reasons) == 0
    result["passed"] = passed

    # ── 信号文字 ──────────────────────────────────────────
    if passed:
        shrink_str = f"缩量至{result['details']['shrink_vol_ratio_actual']}x均量"
        bounce_str = f"反弹放量{result['details']['bounce_vol_ratio_actual']}倍"
        parts = [
            f"回撤{drawdown_pct:.1f}%",
            "恐慌放量" if has_panic_vol else "",
            shrink_str,
            bounce_str,
        ]
        result["details"]["signal_text"] = " → ".join(p for p in parts if p)
    else:
        result["details"]["signal_text"] = "未达标:" + filter_reasons[0]

    # ── 打分（满分 100，不含换手率加分）──────────────────
    score = 0
    bd = {}

    if passed:
        # 回撤幅度 (0-30)
        if drawdown_pct >= 25:
            score += 30; bd["drawdown"] = 30
        elif drawdown_pct >= 20:
            score += 24; bd["drawdown"] = 24
        elif drawdown_pct >= 15:
            score += 18; bd["drawdown"] = 18
        else:
            score += 10; bd["drawdown"] = 10

        # MA20 偏离 (0-20)
        if ma20_dist >= 10:
            score += 20; bd["ma20_dev"] = 20
        elif ma20_dist >= 7:
            score += 15; bd["ma20_dev"] = 15
        elif ma20_dist >= 5:
            score += 10; bd["ma20_dev"] = 10
        else:
            score += 5; bd["ma20_dev"] = 5

        # 缩量程度 (0-20)
        shrink_val = result["details"].get("shrink_vol_ratio_actual")
        if shrink_val is not None:
            if shrink_val < 0.3:
                score += 20; bd["shrink"] = 20
            elif shrink_val < 0.5:
                score += 15; bd["shrink"] = 15
            elif shrink_val < SHRINK_VOL_RATIO:
                score += 10; bd["shrink"] = 10
            else:
                score += 5; bd["shrink"] = 5

        # 反弹放量强度 (0-20)
        bounce_val = result["details"].get("bounce_vol_ratio_actual")
        if bounce_val is not None:
            if bounce_val >= 2.5:
                score += 20; bd["bounce"] = 20
            elif bounce_val >= 2.0:
                score += 16; bd["bounce"] = 16
            elif bounce_val >= 1.5:
                score += 12; bd["bounce"] = 12
            else:
                score += 6; bd["bounce"] = 6

        # 收盘位置加分 (0-10)
        if CLOSE_UPPER_RATIO > 0:
            cp = result["details"].get("close_position", 0.5)
            if cp >= 0.8:
                score += 10; bd["close_pos"] = 10
            elif cp >= CLOSE_UPPER_RATIO:
                score += 5; bd["close_pos"] = 5
            else:
                bd["close_pos"] = 0
        else:
            bd["close_pos"] = 0
    else:
        bd = {"drawdown": 0, "ma20_dev": 0, "shrink": 0, "bounce": 0, "close_pos": 0}

    result["score"] = score
    result["breakdown"] = bd

    return result


# ═══════════════════════════════════════════════════════════
# 策略入口
# ═══════════════════════════════════════════════════════════

def run(data):
    """
    AIpicking 策略接口 — 超跌反弹选股（上证深证版）。

    Args:
        data: {
            "cutoff_date": "20260525",
            "stocks": [{"ts_code": "600001.SH", "name": "浦发银行", "market": "上证主板",
                         "float_shares": 1200000000, "total_shares": 2000000000, ...}],
            "daily": {
                "600001.SH": [{"trade_date": "20260101", "open": 10.0, "high": 10.5,
                               "low": 9.8, "close": 10.2, "vol": 50000, ...}],
                ...
            },
            "config": {  # 可选参数覆盖
                "drawdown_pct": 18.0,
                "market_timing": False,
                "ts_code": ""  # 单股诊断模式
            }
        }

    Returns:
        [{"ts_code": "600001.SH", "name": "浦发银行", "score": 85,
          "signal": "回撤18.5%→恐慌放量→缩量至0.4x均量→反弹放量1.8倍 换手3.2%",
          "breakdown": {...}, "details": {...}}, ...]
    """
    cutoff_date = data.get("cutoff_date", "")
    stocks = data.get("stocks", [])
    daily = data.get("daily", {})
    config = data.get("config", {}) or {}

    # ── 参数覆盖 ──────────────────────────────────────────
    global DRAWDOWN_PCT, LOOKBACK_DAYS, PANIC_VOL_RATIO, MA20_DEVIATION
    global SHRINK_VOL_RATIO, STABILIZE_WINDOW, LOW_TOLERANCE
    global BOUNCE_VOL_RATIO, CLOSE_UPPER_RATIO
    global MARKET_TIMING, MARKET_INDEX, MARKET_MA20_BELOW
    global CAP_MIN, CAP_MAX

    DRAWDOWN_PCT       = float(config.get("drawdown_pct",       DRAWDOWN_PCT))
    LOOKBACK_DAYS      = int(config.get("lookback_days",        LOOKBACK_DAYS))
    PANIC_VOL_RATIO    = float(config.get("panic_vol_ratio",    PANIC_VOL_RATIO))
    MA20_DEVIATION     = float(config.get("ma20_deviation",     MA20_DEVIATION))
    SHRINK_VOL_RATIO   = float(config.get("shrink_vol_ratio",   SHRINK_VOL_RATIO))
    STABILIZE_WINDOW   = int(config.get("stabilize_window",     STABILIZE_WINDOW))
    LOW_TOLERANCE      = float(config.get("low_tolerance",      LOW_TOLERANCE))
    BOUNCE_VOL_RATIO   = float(config.get("bounce_vol_ratio",   BOUNCE_VOL_RATIO))
    CLOSE_UPPER_RATIO  = float(config.get("close_upper_ratio",  CLOSE_UPPER_RATIO))
    MARKET_TIMING      = bool(config.get("market_timing",       MARKET_TIMING))
    MARKET_INDEX       = str(config.get("market_index",         MARKET_INDEX))
    MARKET_MA20_BELOW  = float(config.get("market_ma20_below",  MARKET_MA20_BELOW))
    CAP_MIN            = float(config.get("cap_min",            CAP_MIN))
    CAP_MAX            = float(config.get("cap_max",            CAP_MAX))

    # 兼容短代码格式（如 "000001" → "000001.SH"）
    if MARKET_INDEX and not ("." in MARKET_INDEX):
        if MARKET_INDEX.startswith("000") or MARKET_INDEX.startswith("399"):
            MARKET_INDEX = MARKET_INDEX + ".SZ"
        elif MARKET_INDEX.startswith("6"):
            MARKET_INDEX = MARKET_INDEX + ".SH"

    target_ts_code = config.get("ts_code", "").strip()

    # ── 大盘择时 ──────────────────────────────────────────
    if MARKET_TIMING:
        if not _is_market_oversold(daily, MARKET_INDEX, MARKET_MA20_BELOW):
            return []  # 大盘不满足超跌条件，不产生任何信号

    # ── 股票查找表 ────────────────────────────────────────
    stock_lookup = {s["ts_code"]: s for s in stocks}

    recommendations = []

    for ts_code, rows in daily.items():
        if not rows:
            continue

        # ── 股票池过滤：上证主板(600/601/603/605) + 深证主板(000/001/002/003) ──
        if not (
            ts_code.startswith("600")
            or ts_code.startswith("601")
            or ts_code.startswith("603")
            or ts_code.startswith("605")
            or ts_code.startswith("000")
            or ts_code.startswith("001")
            or ts_code.startswith("002")
            or ts_code.startswith("003")
        ):
            continue

        stock = stock_lookup.get(ts_code, {})
        name = stock.get("name", ts_code)

        # ── ST 过滤 ───────────────────────────────────────
        if "ST" in name:
            continue

        # ── 市值过滤（单股诊断时跳过）────────────────────
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

        # ── 执行检测 ──────────────────────────────────────
        result = check_oversold_bounce(df)

        if not result["passed"] and not target_ts_code:
            continue

        # ── 换手率估算与加分 ──────────────────────────────
        float_shares = stock.get("float_shares", 0) or 0
        today_row = df.iloc[-1] if len(df) > 0 else None
        today_vol = today_row["vol"] if today_row is not None else 0
        today_amount = today_row.get("amount") if today_row is not None else 0
        today_close = today_row["close"] if today_row is not None else 0
        turnover_rate = _compute_turnover(today_vol, today_amount, today_close, float_shares)
        result["details"]["turnover_rate"] = round(turnover_rate, 2)

        # 换手率加分 (0-10)，叠加到基础分
        if turnover_rate >= 8:
            result["score"] += 10
        elif turnover_rate >= 5:
            result["score"] += 8
        elif turnover_rate >= 3:
            result["score"] += 6
        elif turnover_rate >= 1:
            result["score"] += 4
        else:
            result["score"] += 1

        # ── 构建输出 ──────────────────────────────────────
        signal_text = result["details"].get("signal_text", "超跌反弹")
        if turnover_rate > 0:
            signal_text += f" 换手{turnover_rate:.1f}%"

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
