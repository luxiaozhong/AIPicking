"""
底背离反弹策略 (Bottom Divergence Rebound)
基于 MACD 日线底背离检测 + 量能确认 + RSI 超卖辅助 + 神奇九转加分

核心逻辑：
  1. 股价近 40 日内两个低点：低点 2 < 低点 1（创新低）
  2. MACD DIF 低点 2 > DIF 低点 1（底背离：下跌动能衰竭）
  3. 量能确认：下跌缩量 + 背离后出现反弹阳线
  4. RSI 超卖区域加分（< 30）
  5. 处于下降趋势中（MA5 < MA20，确保是"抄底"而非"追涨"）
  6. 神奇九转：TD Setup 9 / Countdown 13 完成作为加分项
"""

import pandas as pd
import numpy as np

# ── 参数 ─────────────────────────────────────────────────
TOP_PICKS = 5
MIN_HISTORY = 60

# 市值过滤 (亿)
CAP_MIN = 100
CAP_MAX = 8000

# 背离检测
SWING_LOOKBACK = 5      # 寻找局部极值时的两侧窗口
DIVERGE_WINDOW = 40     # 背离检测窗口（日）
MIN_POINTS_GAP = 10     # 两个低点之间的最小间隔

# 量能确认
VOL_SHRINK_RATIO = 0.8  # 低点 2 附近均量 < 低点 1 附近均量 * 此值
REBOUND_MIN_PCT = 0.02  # 背离后最近反弹阳线最小涨幅

# RSI
RSI_PERIOD = 14
RSI_OVERSOLD = 30

# 均线
MA_SHORT = 5
MA_LONG = 20

# 涨停过滤
LIMIT_UP_PCT = 0.095

# 神奇九转
TD_SETUP_BARS = 9       # Setup 需要连续 9 根
TD_COUNTDOWN_BARS = 13  # Countdown 需要 13 次


def check_td_sequential(df):
    """
    TD Sequential 下跌结构检测（底部反转信号）。

    返回:
        {
            "setup_complete": bool,      # Setup 9 是否完成
            "countdown_complete": bool,  # Countdown 13 是否完成
            "setup_bars_ago": int,       # Setup 最后一天距今多少根 K 线
            "cd_bars_ago": int,          # Countdown 最后一天距今多少根 K 线
            "status": "none" | "setup9" | "cd13",
        }
    """
    result = {
        "setup_complete": False,
        "countdown_complete": False,
        "setup_bars_ago": -1,
        "cd_bars_ago": -1,
        "status": "none",
    }

    closes = df["close"].values
    lows = df["low"].values
    n = len(closes)

    if n < TD_SETUP_BARS + 4:
        return result

    # ── Setup 检测（从后往前扫，找最近的完成结构）───────
    # Setup 条件：close[i] < close[i-4]
    setup_end = -1
    consecutive = 0

    # 从最早可能的位置开始向后扫
    for i in range(4, n):
        if closes[i] < closes[i - 4]:
            consecutive += 1
            if consecutive >= TD_SETUP_BARS:
                setup_end = i
        else:
            consecutive = 0

    if setup_end < 0:
        return result

    result["setup_complete"] = True
    result["setup_bars_ago"] = n - 1 - setup_end

    # ── Countdown 检测（Setup 完成后）───────────────
    # Countdown 条件：close < low[2 天前]
    cd_count = 0
    cd_end = -1

    for i in range(setup_end + 1, n):
        if i >= 2 and closes[i] < lows[i - 2]:
            cd_count += 1
            if cd_count >= TD_COUNTDOWN_BARS:
                cd_end = i
                break

    if cd_end >= 0:
        result["countdown_complete"] = True
        result["cd_bars_ago"] = n - 1 - cd_end
        result["status"] = "cd13"
    else:
        result["status"] = "setup9"

    return result


def find_swing_lows(df, window=SWING_LOOKBACK):
    """
    在 df 中查找局部低点。返回 [(idx, close, macd_dif), ...] 列表。
    一个局部低点定义为：该日 close < 前后各 window 日的最低 close。
    """
    n = len(df)
    lows = []
    for i in range(window, n - window):
        close = df.iloc[i]["close"]
        left_min = df.iloc[i - window:i]["close"].min()
        right_min = df.iloc[i + 1:i + 1 + window]["close"].min()
        if close <= left_min and close <= right_min:
            dif = df.iloc[i].get("macd_dif", 0)
            if not pd.isna(dif):
                lows.append((i, close, dif))
    return lows


def check_divergence(df):
    """
    检测 df 最后一天是否存在底背离信号。
    返回 {"passed": bool, "score": int (0-100), "details": {}, "breakdown": {}}

    单股诊断模式下会计算所有指标，即使前置条件未满足也不会提前返回，
    以便用户看到完整的指标面板和过滤原因。
    """
    result = {"passed": False, "score": 0, "details": {}, "breakdown": {}}
    filter_reasons = []

    if len(df) < MIN_HISTORY:
        result["details"]["error"] = f"数据不足：需要至少 {MIN_HISTORY} 个交易日，实际 {len(df)} 个"
        return result

    df = df.copy()
    # ── 指标计算 ───────────────────────────────────────────
    df["ma5"] = df["close"].rolling(MA_SHORT).mean()
    df["ma20"] = df["close"].rolling(MA_LONG).mean()
    df["vol_ma5"] = df["vol"].rolling(5).mean()
    df["vol_ma20"] = df["vol"].rolling(20).mean()

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd_dif"] = ema12 - ema26
    df["macd_dea"] = df["macd_dif"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = 2 * (df["macd_dif"] - df["macd_dea"])

    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
    loss = (-delta.clip(upper=0)).rolling(RSI_PERIOD).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    df["pct_chg"] = df["close"].pct_change()

    latest = df.iloc[-1]
    price = latest["close"]

    # ── 初始化所有变量（避免后续引用未定义） ──────────────
    dif1, dif2 = 0.0, 0.0
    price1, price2 = price, price
    idx1, idx2 = len(df) - 1, len(df) - 1
    vol_near_l1, vol_near_l2 = 0.0, 0.0
    vol_shrink = False
    has_rebound = False
    rebound_candles = pd.DataFrame()
    dif_improve = 0.0
    price_new_low = False
    dif_higher_low = False
    divergence_detected = False

    # ── 趋势检查 ───────────────────────────────────────────
    ma5_val = latest["ma5"]
    ma20_val = latest["ma20"]
    if pd.isna(ma5_val) or pd.isna(ma20_val):
        result["details"]["error"] = "无法计算均线"
        return result
    in_downtrend = ma5_val < ma20_val
    result["details"]["ma5"] = round(ma5_val, 2)
    result["details"]["ma20"] = round(ma20_val, 2)
    result["details"]["in_downtrend"] = in_downtrend

    if not in_downtrend:
        filter_reasons.append(f"非下降趋势(MA5={ma5_val:.2f} >= MA20={ma20_val:.2f})")

    # ── 涨停检查 ───────────────────────────────────────────
    today_pct = latest["pct_chg"]
    result["details"]["today_pct"] = round(today_pct * 100, 2) if today_pct else 0
    is_limit_up = today_pct and abs(today_pct) >= LIMIT_UP_PCT
    if is_limit_up:
        filter_reasons.append(f"当日涨停({today_pct*100:.1f}%)，无法买入")

    # ── 底背离检测 ────────────────────────────────────────
    window_end = len(df) - 1
    window_start = max(0, window_end - DIVERGE_WINDOW)
    swing_lows = find_swing_lows(df.iloc[window_start:window_end + 1])
    swing_lows = [(i + window_start, c, d) for i, c, d in swing_lows]
    result["details"]["swing_lows_found"] = len(swing_lows)

    if len(swing_lows) >= 2:
        low2 = swing_lows[-1]
        low1_candidates = [s for s in swing_lows[:-1]
                           if (low2[0] - s[0]) >= MIN_POINTS_GAP]
        if low1_candidates:
            low1 = low1_candidates[-1]
            idx1, price1, dif1 = low1
            idx2, price2, dif2 = low2

            result["details"]["low1_idx"] = idx1
            result["details"]["low1_price"] = round(price1, 2)
            result["details"]["low1_dif"] = round(dif1, 4)
            result["details"]["low2_idx"] = idx2
            result["details"]["low2_price"] = round(price2, 2)
            result["details"]["low2_dif"] = round(dif2, 4)

            price_new_low = price2 < price1
            dif_higher_low = dif2 > dif1
            divergence_detected = price_new_low and dif_higher_low
            result["details"]["price_new_low"] = price_new_low
            result["details"]["dif_higher_low"] = dif_higher_low

            if not divergence_detected:
                reasons = []
                if not price_new_low:
                    reasons.append("价格未创新低")
                if not dif_higher_low:
                    reasons.append("DIF同步新低(无背离)")
                filter_reasons.append("; ".join(reasons))

            # ── 量能确认 ──────────────────────────────────────
            vol_near_l2 = df.iloc[max(0, idx2 - 2):idx2 + 1]["vol"].mean()
            vol_near_l1 = df.iloc[max(0, idx1 - 2):idx1 + 1]["vol"].mean()
            vol_shrink = vol_near_l2 < vol_near_l1 * VOL_SHRINK_RATIO
            result["details"]["vol_near_l1"] = round(vol_near_l1, 0)
            result["details"]["vol_near_l2"] = round(vol_near_l2, 0)
            result["details"]["vol_shrink"] = vol_shrink

            post_low = df.iloc[idx2:]
            rebound_candles = post_low[post_low["pct_chg"] > REBOUND_MIN_PCT]
            has_rebound = len(rebound_candles) > 0
            result["details"]["rebound_candles"] = len(rebound_candles)
            result["details"]["has_rebound"] = has_rebound

            if not (vol_shrink or has_rebound):
                filter_reasons.append("量能未确认(无缩量且无反弹阳线)")
        else:
            result["details"]["gap_ok"] = False
            filter_reasons.append(f"低点间距不足(需>{MIN_POINTS_GAP}日)")
    else:
        filter_reasons.append(f"近{DIVERGE_WINDOW}日内低点不足(找到{len(swing_lows)}个,需>=2)")

    # ── RSI 超卖（总是计算） ──────────────────────────────
    rsi_val = latest["rsi"]
    rsi_oversold = not pd.isna(rsi_val) and rsi_val < RSI_OVERSOLD
    result["details"]["rsi"] = round(rsi_val, 1) if not pd.isna(rsi_val) else 0
    result["details"]["rsi_oversold"] = rsi_oversold

    # ── 神奇九转（总是计算） ──────────────────────────────
    td = check_td_sequential(df)
    result["details"]["td_status"] = td["status"]
    if td["setup_complete"]:
        result["details"]["td_setup_bars_ago"] = td["setup_bars_ago"]
    if td["countdown_complete"]:
        result["details"]["td_cd_bars_ago"] = td["cd_bars_ago"]

    # ── MACD 柱状图方向 ──────────────────────────────────────
    if len(df) >= 2:
        prev_hist = df.iloc[-2]["macd_hist"]
        curr_hist = latest["macd_hist"]
        result["details"]["macd_hist_direction"] = "缩短" if abs(curr_hist) < abs(prev_hist) else "放大"
        result["details"]["macd_dif"] = round(latest["macd_dif"], 4)

    # ── 打分（满分 100，总是完整计算）─────────────────────
    score = 0
    bd = {}

    # 1. 背离强度（0-35）
    if divergence_detected:
        dif_improve = (dif2 - dif1) / (abs(dif1) + 0.001)
        if dif_improve > 0.5:
            score += 35
            bd["divergence"] = 35
        elif dif_improve > 0.3:
            score += 28
            bd["divergence"] = 28
        elif dif_improve > 0.15:
            score += 20
            bd["divergence"] = 20
        else:
            score += 12
            bd["divergence"] = 12
    else:
        bd["divergence"] = 0

    # 2. 价格偏离 MA20 幅度（0-20）
    if ma20_val > 0 and not pd.isna(ma20_val):
        deviation = (ma20_val - price) / ma20_val
        if deviation > 0.15:
            score += 20
            bd["deviation"] = 20
        elif deviation > 0.08:
            score += 14
            bd["deviation"] = 14
        elif deviation > 0.03:
            score += 8
            bd["deviation"] = 8
        else:
            score += 3
            bd["deviation"] = 3
        result["details"]["ma20_deviation"] = f"{deviation*100:.1f}%"

    # 3. 量能（0-25）
    if vol_shrink and has_rebound:
        score += 25
        bd["volume"] = 25
    elif vol_shrink:
        score += 15
        bd["volume"] = 15
    elif has_rebound:
        score += 12
        bd["volume"] = 12
    else:
        bd["volume"] = 0

    # 4. RSI 超卖（0-15）
    if rsi_oversold and not pd.isna(rsi_val) and rsi_val < 25:
        score += 15
        bd["rsi"] = 15
    elif rsi_oversold:
        score += 10
        bd["rsi"] = 10
    elif not pd.isna(rsi_val) and rsi_val < 40:
        score += 5
        bd["rsi"] = 5
    else:
        bd["rsi"] = 0

    # 5. 最近阳线强度（0-5）
    if has_rebound:
        best_rebound = rebound_candles["pct_chg"].max()
        if best_rebound > 0.04:
            score += 5
            bd["rebound_strength"] = 5
        elif best_rebound > 0.02:
            score += 3
            bd["rebound_strength"] = 3
        else:
            bd["rebound_strength"] = 0

    # 6. 神奇九转加分（0-15）
    if td["status"] == "cd13":
        score += 15
        bd["td_sequential"] = 15
    elif td["status"] == "setup9":
        score += 10
        bd["td_sequential"] = 10
    else:
        bd["td_sequential"] = 0

    result["score"] = score
    result["breakdown"] = bd
    result["passed"] = score >= 40
    result["details"]["filter_reasons"] = filter_reasons

    # 构建信号描述
    signals = []
    if divergence_detected:
        signals.append(f"DIF抬升{dif_improve:.0%}")
    if vol_shrink:
        signals.append("缩量")
    if has_rebound:
        signals.append("阳线确认")
    if rsi_oversold:
        signals.append(f"RSI超卖({rsi_val:.0f})")
    if td["status"] == "cd13":
        signals.append("九转13")
    elif td["status"] == "setup9":
        signals.append("九转9")
    if filter_reasons and not signals:
        signals.append("未达标:" + filter_reasons[0])
    result["details"]["signal_text"] = ",".join(signals) if signals else "未达标"

    return result


def run(data):
    """
    AIpicking 策略接口。

    Args:
        data: {
            "cutoff_date": "20260525",
            "stocks": [{"ts_code": "...", "name": "...", ...}],
            "daily": {"600001.SH": [{"trade_date": "...", "close": ..., ...}]},
        }

    Returns:
        [{"ts_code": "...", "name": "...", "score": 85, "signal": "..."}, ...]
    """
    cutoff_date = data["cutoff_date"]
    stocks = data["stocks"]
    daily = data["daily"]
    target_ts_code = data.get("config", {}).get("ts_code", "").strip() if data.get("config") else ""

    stock_lookup = {s["ts_code"]: s for s in stocks}
    recommendations = []

    for ts_code, rows in daily.items():
        if not rows:
            continue

        df = pd.DataFrame(rows)
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        df = df.sort_values("trade_date")

        if len(df) < MIN_HISTORY:
            continue

        stock = stock_lookup.get(ts_code, {})
        name = stock.get("name", ts_code)

        # 市值过滤（单股诊断时跳过）
        if not target_ts_code:
            total_shares = stock.get("total_shares", 0) or 0
            close_price = df.iloc[-1]["close"]
            market_cap = total_shares * close_price / 1e8 if total_shares > 0 else 0
            if market_cap < CAP_MIN or market_cap > CAP_MAX:
                continue

        # ST 过滤
        if "ST" in name:
            continue

        result = check_divergence(df)
        if not result["passed"] and not target_ts_code:
            continue

        signal_text = result["details"].get("signal_text", "底背离反弹")

        recommendations.append({
            "ts_code": ts_code,
            "name": name,
            "score": result["score"],
            "signal": signal_text,
            "breakdown": result.get("breakdown", {}),
            "details": result.get("details", {}),
        })

    recommendations.sort(key=lambda x: x["score"], reverse=True)
    return recommendations[:TOP_PICKS]
