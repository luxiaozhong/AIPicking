"""
个股综合诊断策略 (Single-Stock Comprehensive Checkup)

从技术面和资金面对单只个股进行多维度评分：
  1. 趋势 (Trend)       0-25: 均线、MACD、ADX、布林带
  2. 动量 (Momentum)    0-25: RSI、价格位置、近期涨跌、KDJ
  3. 量能 (Volume)      0-20: 量比、量价关系、换手率、OBV
  4. 形态 (Pattern)     0-15: 背离、神奇九转、支撑阻力
  5. 资金流 (Flow)      0-15: 板块资金流向排名

用法：通过 config 传入 ts_code 指定目标个股
  {"config": {"ts_code": "000001.SZ"}}
未指定 ts_code 时扫描全市场返回 Top 3。
"""

import json
import pandas as pd
import numpy as np

# ── 参数 ─────────────────────────────────────────────────
TOP_PICKS = 3
MIN_HISTORY = 60

# 市值过滤
CAP_MIN = 30
CAP_MAX = 10000

# 均线
MA_SHORT = 5
MA_MID = 10
MA_LONG = 20
MA_BIG = 60

# RSI
RSI_PERIOD = 14

# KDJ
KDJ_N = 9

# 布林带
BOLL_PERIOD = 20
BOLL_STD = 2

# ADX
ADX_PERIOD = 14

# 量能
VOL_RATIO_PERIOD = 5

# 神奇九转
TD_SETUP_BARS = 9
TD_COUNTDOWN_BARS = 13

# 资金流
FLOW_LOOKBACK = 5

# 涨停
LIMIT_UP_PCT = 0.095


def check_td_sequential(df):
    """TD Sequential 下跌结构检测（底部反转信号）。"""
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

    # Setup: close[i] < close[i-4]
    setup_end = -1
    consecutive = 0
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

    # Countdown: close < low[2 天前]
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


# ── 资金流辅助函数（复用 Trend Upstart Flow 模式）─────────

def build_sector_flow_index(raw_data):
    """构建 sector_flow 查询索引和排名。"""
    index = {}
    for row in raw_data:
        key = (row["sector_type"], row["sector_name"])
        if key not in index:
            index[key] = []
        index[key].append(row)

    for key in index:
        index[key].sort(key=lambda r: r["trade_date"])

    sector_nets = {}
    for key, rows in index.items():
        recent = rows[-FLOW_LOOKBACK:] if len(rows) >= FLOW_LOOKBACK else rows
        sector_nets[key] = sum((r.get("net_inflow") or 0) for r in recent)

    ranking = sorted(sector_nets.items(), key=lambda x: x[1], reverse=True)
    return index, ranking


def find_stock_sectors(index, industry_l2, industry_l1, concepts_json):
    """查找个股匹配的所有 sector_flow 板块。"""
    matched = set()

    for term in [industry_l2, industry_l1]:
        if not term:
            continue
        key = ("concept", term)
        if key in index:
            matched.add(key)

    if not matched:
        for term in [industry_l2, industry_l1]:
            if not term:
                continue
            for (stype, sname) in index:
                if stype != "concept":
                    continue
                if term in sname or sname in term:
                    matched.add((stype, sname))

    tags = []
    if concepts_json:
        try:
            tags = json.loads(concepts_json)
        except (json.JSONDecodeError, TypeError):
            pass

    if isinstance(tags, list):
        for tag in tags:
            for check_type in ("industry", "concept"):
                key = (check_type, tag)
                if key in index:
                    matched.add(key)
            for (stype, sname) in index:
                if (stype, sname) in matched:
                    continue
                if tag in sname or sname in tag:
                    matched.add((stype, sname))

    return list(matched)


def compute_flow_score(matched_sectors, ranking, index):
    """基于匹配板块在资金流排名中的位置计算得分（0-15）。"""
    if not matched_sectors or not ranking:
        return 0

    total = len(ranking)
    if total < 5:
        return 0

    rank_map = {key: i for i, (key, _) in enumerate(ranking)}

    best_score = 0
    for skey in matched_sectors:
        if skey not in rank_map:
            continue
        rank_idx = rank_map[skey]
        percentile = 1.0 - (rank_idx / total)

        if percentile >= 0.90:
            sector_score = 15
        elif percentile >= 0.75:
            sector_score = 12
        elif percentile >= 0.50:
            sector_score = 8
        elif percentile >= 0.25:
            sector_score = 4
        else:
            sector_score = 0

        if skey in index:
            rows = index[skey]
            consecutive = 0
            for r in reversed(rows):
                if (r.get("net_inflow") or 0) > 0:
                    consecutive += 1
                else:
                    break
            if consecutive >= 3:
                sector_score = min(sector_score + 2, 15)

        if sector_score > best_score:
            best_score = sector_score

    return best_score


def calc_adx(df, period=ADX_PERIOD):
    """计算 ADX 趋势强度。"""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)

    up = high - high.shift()
    down = low.shift() - low
    plus_dm = np.where((up > down) & (up > 0), up, 0)
    minus_dm = np.where((down > up) & (down > 0), down, 0)

    atr = pd.Series(tr).rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm).rolling(period).mean() / atr
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 0.0001)) * 100
    adx = dx.rolling(period).mean()

    return adx, plus_di, minus_di


def calc_kdj(df, n=KDJ_N):
    """计算 KDJ 指标。"""
    low_n = df["low"].rolling(n).min()
    high_n = df["high"].rolling(n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n + 0.0001) * 100

    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d

    return k, d, j


def compute_obv(df):
    """计算 OBV。"""
    obv = [0]
    for i in range(1, len(df)):
        if df.iloc[i]["close"] > df.iloc[i - 1]["close"]:
            obv.append(obv[-1] + df.iloc[i]["vol"])
        elif df.iloc[i]["close"] < df.iloc[i - 1]["close"]:
            obv.append(obv[-1] - df.iloc[i]["vol"])
        else:
            obv.append(obv[-1])
    return pd.Series(obv, index=df.index)


def checkup(df, sector_index=None, sector_ranking=None, stock_info=None):
    """
    对单只个股进行多维度综合诊断。
    返回 {"passed": bool, "score": int (0-100), "details": {}, "breakdown": {}}
    """
    result = {"passed": False, "score": 0, "details": {}, "breakdown": {}}

    if len(df) < MIN_HISTORY:
        return result

    df = df.copy()

    # ── 指标计算 ───────────────────────────────────────────
    df["ma5"] = df["close"].rolling(MA_SHORT).mean()
    df["ma10"] = df["close"].rolling(MA_MID).mean()
    df["ma20"] = df["close"].rolling(MA_LONG).mean()
    df["ma60"] = df["close"].rolling(MA_BIG).mean()
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

    k, d, j = calc_kdj(df)
    df["kdj_k"] = k
    df["kdj_d"] = d
    df["kdj_j"] = j

    df["boll_mid"] = df["close"].rolling(BOLL_PERIOD).mean()
    boll_std = df["close"].rolling(BOLL_PERIOD).std()
    df["boll_upper"] = df["boll_mid"] + BOLL_STD * boll_std
    df["boll_lower"] = df["boll_mid"] - BOLL_STD * boll_std

    adx, plus_di, minus_di = calc_adx(df)
    df["adx"] = adx
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    df["obv"] = compute_obv(df)
    df["pct_chg"] = df["close"].pct_change()

    latest = df.iloc[-1]
    price = latest["close"]

    # ── 涨停过滤 ───────────────────────────────────────────
    today_pct = latest["pct_chg"]
    if today_pct and abs(today_pct) >= LIMIT_UP_PCT:
        return result

    # ═══════════════════════════════════════════════════════
    # 维度 1: 趋势 (0-25)
    # ═══════════════════════════════════════════════════════
    trend_score = 0
    td = {}

    # 1a. 均线排列 (0-10)
    ma5 = latest["ma5"]
    ma10 = latest["ma10"]
    ma20 = latest["ma20"]
    ma60 = latest["ma60"]

    ma_values_ok = all(not pd.isna(v) for v in [ma5, ma10, ma20, ma60])

    if ma_values_ok:
        if ma5 > ma10 > ma20 > ma60 and price > ma5:
            td["ma_status"] = "强多头排列(MA5>MA10>MA20>MA60)"
            trend_score += 10
        elif ma5 > ma10 > ma20:
            td["ma_status"] = "多头排列(MA5>MA10>MA20)"
            trend_score += 8
        elif price > ma20 and ma5 > ma10:
            td["ma_status"] = "偏多(价格>MA20,MA5>MA10)"
            trend_score += 5
        elif price > ma20:
            td["ma_status"] = "震荡偏多(价格>MA20)"
            trend_score += 3
        elif price > ma60:
            td["ma_status"] = "偏弱(价格<MA20但>MA60)"
            trend_score += 1
        else:
            td["ma_status"] = "空头排列"
        td["ma5"] = round(ma5, 2)
        td["ma20"] = round(ma20, 2)
        td["ma60"] = round(ma60, 2) if not pd.isna(ma60) else 0
    else:
        td["ma_status"] = "数据不足"

    # 1b. MACD (0-8)
    dif = latest["macd_dif"]
    dea = latest["macd_dea"]
    hist = latest["macd_hist"]

    prev_dif = df.iloc[-2]["macd_dif"] if len(df) >= 2 else dif
    prev_dea = df.iloc[-2]["macd_dea"] if len(df) >= 2 else dea
    golden_cross = prev_dif < prev_dea and dif > dea
    death_cross = prev_dif > prev_dea and dif < dea

    if golden_cross and dif > 0:
        td["macd_signal"] = "零轴上金叉"
        trend_score += 8
    elif golden_cross:
        td["macd_signal"] = "金叉"
        trend_score += 6
    elif dif > dea and dif > 0:
        td["macd_signal"] = "零轴上多头"
        trend_score += 5
    elif dif > dea:
        td["macd_signal"] = "多头"
        trend_score += 3
    elif death_cross:
        td["macd_signal"] = "死叉"
        trend_score += 0
    else:
        td["macd_signal"] = "空头"
        trend_score += 0

    # 柱状图方向
    prev_hist = df.iloc[-2]["macd_hist"] if len(df) >= 2 else hist
    if hist > prev_hist and hist > 0:
        td["macd_hist_dir"] = "红柱放大"
        trend_score += 1
    elif hist > prev_hist:
        td["macd_hist_dir"] = "绿柱缩短"
        trend_score += 1

    td["macd_dif"] = round(dif, 4)
    td["macd_dea"] = round(dea, 4)

    # 1c. ADX 趋势强度 (0-4)
    adx_val = latest["adx"]
    plus_di_val = latest["plus_di"]
    minus_di_val = latest["minus_di"]

    if not pd.isna(adx_val):
        td["adx"] = round(adx_val, 1)
        if adx_val > 40 and plus_di_val > minus_di_val:
            td["adx_status"] = "强趋势上涨"
            trend_score += 4
        elif adx_val > 25 and plus_di_val > minus_di_val:
            td["adx_status"] = "趋势上涨"
            trend_score += 3
        elif adx_val > 25:
            td["adx_status"] = "趋势下跌"
            trend_score += 0
        elif adx_val > 20:
            td["adx_status"] = "弱趋势"
            trend_score += 1
        else:
            td["adx_status"] = "无明显趋势(盘整)"
            trend_score += 0
    else:
        td["adx_status"] = "数据不足"

    # 1d. 布林带位置 (0-3)
    boll_upper = latest["boll_upper"]
    boll_lower = latest["boll_lower"]
    boll_mid = latest["boll_mid"]

    if not pd.isna(boll_mid):
        td["boll_mid"] = round(boll_mid, 2)
        boll_width = (boll_upper - boll_lower) / boll_mid if boll_mid > 0 else 0
        boll_pos = (price - boll_lower) / (boll_upper - boll_lower + 0.0001)

        if boll_pos < 0.2:
            td["boll_position"] = "下轨超卖"
            trend_score += 3
        elif boll_pos < 0.4:
            td["boll_position"] = "下半区"
            trend_score += 2
        elif boll_pos < 0.8:
            td["boll_position"] = "中轨附近"
            trend_score += 1
        elif boll_pos <= 1.0:
            td["boll_position"] = "上轨附近"
            trend_score += 0
        else:
            td["boll_position"] = "突破上轨"
            trend_score += 2
    else:
        td["boll_position"] = "数据不足"

    trend_score = min(trend_score, 25)
    result["breakdown"]["trend"] = trend_score

    # ═══════════════════════════════════════════════════════
    # 维度 2: 动量 (0-25)
    # ═══════════════════════════════════════════════════════
    momentum_score = 0
    md = {}

    # 2a. RSI (0-8)
    rsi_val = latest["rsi"]
    if not pd.isna(rsi_val):
        md["rsi"] = round(rsi_val, 1)
        if 40 <= rsi_val <= 60:
            md["rsi_status"] = "中性偏强"
            momentum_score += 6
        elif 30 <= rsi_val < 40:
            md["rsi_status"] = "偏弱(接近超卖)"
            momentum_score += 8
        elif rsi_val < 30:
            md["rsi_status"] = "超卖"
            momentum_score += 4
        elif 60 < rsi_val <= 75:
            md["rsi_status"] = "偏强"
            momentum_score += 4
        elif rsi_val > 75:
            md["rsi_status"] = "超买"
            momentum_score += 0
    else:
        md["rsi_status"] = "数据不足"

    # 2b. 价格位置 (0-8)
    high_20 = df["close"].iloc[-20:].max()
    low_20 = df["close"].iloc[-20:].min()
    high_60 = df["close"].iloc[-60:].max() if len(df) >= 60 else high_20
    low_60 = df["close"].iloc[-60:].min() if len(df) >= 60 else low_20

    pos_20 = (price - low_20) / (high_20 - low_20 + 0.0001)
    pos_60 = (price - low_60) / (high_60 - low_60 + 0.0001)

    md["price_pos_20d"] = f"{pos_20*100:.0f}%"
    md["price_pos_60d"] = f"{pos_60*100:.0f}%"

    if pos_20 < 0.2 and pos_60 < 0.3:
        md["price_position"] = "低位(近20/60日低点)"
        momentum_score += 8
    elif pos_20 < 0.3:
        md["price_position"] = "偏低"
        momentum_score += 6
    elif pos_20 < 0.7:
        md["price_position"] = "中位"
        momentum_score += 4
    elif pos_20 < 0.85:
        md["price_position"] = "偏高"
        momentum_score += 2
    else:
        md["price_position"] = "高位(近20日高点)"
        momentum_score += 0

    # 2c. 近期涨跌 (0-5)
    if len(df) >= 6:
        ret_5d = (price / df.iloc[-6]["close"] - 1) if df.iloc[-6]["close"] > 0 else 0
    else:
        ret_5d = 0
    if len(df) >= 11:
        ret_10d = (price / df.iloc[-11]["close"] - 1) if df.iloc[-11]["close"] > 0 else 0
    else:
        ret_10d = 0

    md["ret_5d"] = f"{ret_5d*100:.2f}%"
    md["ret_10d"] = f"{ret_10d*100:.2f}%"

    if -0.03 <= ret_5d <= 0.03:
        md["recent_status"] = "横盘整理"
        momentum_score += 3
    elif ret_5d > 0.05:
        md["recent_status"] = "短期强势"
        momentum_score += 5
    elif ret_5d > 0:
        md["recent_status"] = "温和上涨"
        momentum_score += 4
    elif ret_5d > -0.05:
        md["recent_status"] = "小幅回调"
        momentum_score += 2
    else:
        md["recent_status"] = "短期弱势"
        momentum_score += 0

    # 2d. KDJ (0-4)
    k_val = latest["kdj_k"]
    d_val = latest["kdj_d"]
    j_val = latest["kdj_j"]

    if not pd.isna(k_val):
        md["kdj_k"] = round(k_val, 1)
        md["kdj_d"] = round(d_val, 1)
        md["kdj_j"] = round(j_val, 1)

        prev_k = df.iloc[-2]["kdj_k"] if len(df) >= 2 else k_val
        prev_d = df.iloc[-2]["kdj_d"] if len(df) >= 2 else d_val

        if prev_k < prev_d and k_val > d_val:
            md["kdj_signal"] = "金叉"
            momentum_score += 4
        elif j_val < 0:
            md["kdj_signal"] = "J值超卖"
            momentum_score += 4
        elif k_val < 20 and d_val < 20:
            md["kdj_signal"] = "超卖区"
            momentum_score += 3
        elif k_val > 80:
            md["kdj_signal"] = "超买区"
            momentum_score += 0
        elif k_val > d_val:
            md["kdj_signal"] = "多头"
            momentum_score += 2
        else:
            md["kdj_signal"] = "空头"
            momentum_score += 0
    else:
        md["kdj_signal"] = "数据不足"

    momentum_score = min(momentum_score, 25)
    result["breakdown"]["momentum"] = momentum_score

    # ═══════════════════════════════════════════════════════
    # 维度 3: 量能 (0-20)
    # ═══════════════════════════════════════════════════════
    volume_score = 0
    vd = {}

    # 3a. 量比 (0-8)
    vol_ma5 = latest["vol_ma5"]
    today_vol = latest["vol"]
    vol_ratio = today_vol / vol_ma5 if vol_ma5 > 0 and not pd.isna(vol_ma5) else 1

    vol_ma20_val = latest["vol_ma20"]
    vol_ratio_20 = today_vol / vol_ma20_val if vol_ma20_val > 0 and not pd.isna(vol_ma20_val) else 1

    vd["vol_ratio_vs5"] = round(vol_ratio, 2)
    vd["vol_ratio_vs20"] = round(vol_ratio_20, 2)

    if 1.2 <= vol_ratio <= 3.0:
        vd["vol_status"] = "温和放量"
        volume_score += 8
    elif vol_ratio > 3.0:
        vd["vol_status"] = "异常放量"
        volume_score += 4
    elif 0.5 <= vol_ratio < 0.8:
        vd["vol_status"] = "缩量"
        volume_score += 5
    elif vol_ratio < 0.5:
        vd["vol_status"] = "极度缩量"
        volume_score += 3
    else:
        vd["vol_status"] = "正常"
        volume_score += 6

    # 3b. 量价关系 (0-6)
    if len(df) >= 2:
        prev_vol = df.iloc[-2]["vol"]
        prev_pct = df.iloc[-2]["pct_chg"]
    else:
        prev_vol = today_vol
        prev_pct = 0

    vol_up = today_vol > prev_vol
    price_up = today_pct > 0

    if vol_up and price_up:
        vd["vol_price"] = "放量上涨(健康)"
        volume_score += 6
    elif not vol_up and not price_up:
        vd["vol_price"] = "缩量下跌"
        volume_score += 3
    elif vol_up and not price_up:
        vd["vol_price"] = "放量下跌(警示)"
        volume_score += 0
    else:
        vd["vol_price"] = "缩量上涨"
        volume_score += 4

    # 3c. 换手率评估 (0-3)
    vd["turnover_note"] = "数据不可用"
    volume_score += 1

    # 3d. OBV 背离 (0-3)
    obv_series = df["obv"]
    if len(df) >= 10:
        obv_recent = obv_series.iloc[-5:].mean()
        obv_prev = obv_series.iloc[-10:-5].mean()
        price_recent = df["close"].iloc[-5:].mean()
        price_prev = df["close"].iloc[-10:-5].mean()

        obv_up = obv_recent > obv_prev
        price_down = price_recent < price_prev

        if obv_up and price_down:
            vd["obv"] = "底背离(OBV升价格跌)"
            volume_score += 3
        elif obv_up:
            vd["obv"] = "OBV上升"
            volume_score += 2
        else:
            vd["obv"] = "OBV走平/下降"
            volume_score += 0
    else:
        vd["obv"] = "数据不足"

    volume_score = min(volume_score, 20)
    result["breakdown"]["volume"] = volume_score

    # ═══════════════════════════════════════════════════════
    # 维度 4: 形态 (0-15)
    # ═══════════════════════════════════════════════════════
    pattern_score = 0
    pd_detail = {}

    # 4a. MACD 底背离 (0-6)
    # 近 40 日内找两个局部低点
    window = 40
    n = len(df)
    window_start = max(0, n - window)

    swing_lows = []
    sw = 5
    for i in range(window_start + sw, n - sw):
        c = df.iloc[i]["close"]
        left_min = df.iloc[i - sw:i]["close"].min()
        right_min = df.iloc[i + 1:i + 1 + sw]["close"].min()
        if c <= left_min and c <= right_min:
            dif_val = df.iloc[i].get("macd_dif", 0)
            if not pd.isna(dif_val):
                swing_lows.append((i, c, dif_val))

    if len(swing_lows) >= 2:
        low2 = swing_lows[-1]
        for low1 in reversed(swing_lows[:-1]):
            if low2[0] - low1[0] >= 10:
                _, price1, dif1 = low1
                _, price2, dif2 = low2
                if price2 < price1 and dif2 > dif1:
                    pd_detail["divergence"] = "底背离(价格新低+DIF抬升)"
                    pattern_score += 6
                elif price2 > price1 and dif2 < dif1:
                    pd_detail["divergence"] = "顶背离(价格新高+DIF下降)"
                    pattern_score += 0
                else:
                    pd_detail["divergence"] = "无背离"
                break
    if "divergence" not in pd_detail:
        pd_detail["divergence"] = "无背离(低点不足)"

    # 4b. 神奇九转 (0-5)
    td_result = check_td_sequential(df)
    pd_detail["td_status"] = td_result["status"]
    if td_result["status"] == "cd13":
        pattern_score += 5
        pd_detail["td_signal"] = "买入结构13完成"
    elif td_result["status"] == "setup9":
        pattern_score += 3
        pd_detail["td_signal"] = "买入结构9完成"
    else:
        pd_detail["td_signal"] = "无信号"

    # 4c. 支撑/阻力 (0-4)
    recent_high = df["high"].iloc[-20:].max()
    recent_low = df["low"].iloc[-20:].min()

    pd_detail["resistance"] = round(recent_high, 2)
    pd_detail["support"] = round(recent_low, 2)

    dist_to_support = (price - recent_low) / price if price > 0 else 1
    dist_to_resist = (recent_high - price) / price if price > 0 else 0

    if dist_to_support < 0.03:
        pd_detail["sr_status"] = "接近支撑位"
        pattern_score += 4
    elif dist_to_support < 0.05:
        pd_detail["sr_status"] = "靠近支撑"
        pattern_score += 3
    elif dist_to_resist < 0.03 and price > recent_high * 0.98:
        pd_detail["sr_status"] = "接近阻力位"
        pattern_score += 1
    else:
        pd_detail["sr_status"] = "中间区域"
        pattern_score += 2

    pattern_score = min(pattern_score, 15)
    result["breakdown"]["pattern"] = pattern_score

    # ═══════════════════════════════════════════════════════
    # 维度 5: 资金流 (0-15)
    # ═══════════════════════════════════════════════════════
    flow_score = 0
    fd = {}

    if sector_index is not None and sector_ranking is not None and stock_info:
        industry_l2 = stock_info.get("industry_l2", "")
        industry_l1 = stock_info.get("industry_l1", "")
        concepts_str = stock_info.get("concepts", "")
        matched = find_stock_sectors(sector_index, industry_l2, industry_l1, concepts_str)
        flow_score = compute_flow_score(matched, sector_ranking, sector_index)
        fd["matched_sectors"] = len(matched)
        if matched:
            best = matched[0]
            fd["best_sector"] = f"{best[0]}:{best[1]}"
    else:
        fd["matched_sectors"] = 0

    result["breakdown"]["flow"] = flow_score

    # ═══════════════════════════════════════════════════════
    # 汇总打分
    # ═══════════════════════════════════════════════════════
    total_score = trend_score + momentum_score + volume_score + pattern_score + flow_score
    result["score"] = total_score
    result["passed"] = total_score >= 30

    # 合并所有 detail
    result["details"] = {**td, **md, **vd, **pd_detail, **fd}
    result["details"]["total_score"] = total_score

    # 构建信号描述
    signals = []
    if trend_score >= 18:
        signals.append("趋势向好")
    elif trend_score >= 10:
        signals.append("趋势中性")
    else:
        signals.append("趋势偏弱")

    if momentum_score >= 18:
        signals.append("动能充足")
    elif momentum_score >= 10:
        signals.append("动能一般")
    else:
        signals.append("动能不足")

    if volume_score >= 15:
        signals.append("量价健康")
    elif volume_score >= 8:
        signals.append("量能正常")

    if pattern_score >= 10:
        signals.append("形态积极")
    if flow_score >= 10:
        signals.append("资金共振")

    result["details"]["signal_text"] = ",".join(signals) if signals else "信号中性"

    return result


def run(data):
    """
    AIpicking 策略接口。

    Args:
        data: {
            "cutoff_date": "20260525",
            "stocks": [...],
            "daily": {...},
            "sector_flow": [...],
            "config": {"ts_code": "000001.SZ"},  # 可选：目标个股
        }
    """
    cutoff_date = data["cutoff_date"]
    stocks = data["stocks"]
    daily = data["daily"]
    sector_flow_raw = data.get("sector_flow", [])
    config = data.get("config", {})
    target_ts_code = config.get("ts_code", "").strip() if config else ""

    stock_lookup = {s["ts_code"]: s for s in stocks}

    # 构建资金流索引
    sector_index = None
    sector_ranking = None
    if sector_flow_raw:
        sector_index, sector_ranking = build_sector_flow_index(sector_flow_raw)

    recommendations = []

    # 确定要分析的股票列表
    if target_ts_code and target_ts_code in daily:
        target_codes = [target_ts_code]
    elif target_ts_code:
        # 指定的 ts_code 在 daily 中不存在
        target_codes = []
    else:
        # 未指定时扫描全市场
        target_codes = list(daily.keys())

    for ts_code in target_codes:
        rows = daily[ts_code]
        if not rows:
            continue

        df = pd.DataFrame(rows)
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        df = df.sort_values("trade_date")

        if len(df) < MIN_HISTORY:
            continue

        stock = stock_lookup.get(ts_code, {})
        name = stock.get("name", ts_code)

        # 市值过滤（全市场扫描时用）
        if not target_ts_code:
            total_shares = stock.get("total_shares", 0) or 0
            close_price = df.iloc[-1]["close"]
            market_cap = total_shares * close_price / 1e8 if total_shares > 0 else 0
            if market_cap < CAP_MIN or market_cap > CAP_MAX:
                continue

        # ST 过滤
        if "ST" in name:
            continue

        result = checkup(df, sector_index, sector_ranking, stock)
        if not result["passed"] and not target_ts_code:
            continue

        # 附加更多详情到 signal
        signal_text = result["details"].get("signal_text", "综合诊断")
        details = result["details"]

        recommendations.append({
            "ts_code": ts_code,
            "name": name,
            "score": result["score"],
            "signal": signal_text,
            "breakdown": result.get("breakdown", {}),
            "details": {
                "ma_status": details.get("ma_status", ""),
                "macd_signal": details.get("macd_signal", ""),
                "adx_status": details.get("adx_status", ""),
                "boll_position": details.get("boll_position", ""),
                "rsi": details.get("rsi", 0),
                "rsi_status": details.get("rsi_status", ""),
                "price_position": details.get("price_position", ""),
                "ret_5d": details.get("ret_5d", ""),
                "kdj_signal": details.get("kdj_signal", ""),
                "vol_ratio_vs5": details.get("vol_ratio_vs5", 0),
                "vol_status": details.get("vol_status", ""),
                "vol_price": details.get("vol_price", ""),
                "obv": details.get("obv", ""),
                "divergence": details.get("divergence", ""),
                "td_status": details.get("td_status", ""),
                "td_signal": details.get("td_signal", ""),
                "sr_status": details.get("sr_status", ""),
                "support": details.get("support", 0),
                "resistance": details.get("resistance", 0),
                "matched_sectors": details.get("matched_sectors", 0),
                "best_sector": details.get("best_sector", ""),
            },
        })

    recommendations.sort(key=lambda x: x["score"], reverse=True)
    return recommendations[:TOP_PICKS]
