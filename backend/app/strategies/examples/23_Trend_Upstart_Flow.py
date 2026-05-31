"""
趋势启动捕捉策略 — 资金流向增强版 (Trend Upstart Flow)
基于 Trend Upstart 核心逻辑 + sector_flow 板块资金流向打分

Mapping convention:
  sector_flow.sector_type='concept'  => 板块/行业（申万分类），匹配 stocks.industry_l2 / industry_l1
  sector_flow.sector_type='industry' => 题材/概念，匹配 stocks.concepts JSON 数组
"""

import json
import pandas as pd

# ── 趋势启动参数（与 Trend Upstart 一致） ──────────────────
TOP_PICKS = 5
MIN_HISTORY = 30

BIG_UP_PCT = 0.05
BIG_UP_DAYS = 3
BIG_UP_COUNT = 2
VOL_RATIO_MIN = 1.2
LIMIT_UP_PCT = 0.095
SHRINK_VOL_MAX = 0.8
RECENT_GAIN_MIN = -0.10
RECENT_GAIN_MAX = 0.20
MAX_DRAWDOWN = 0.15
LOOKBACK_LOW = 20

MA_SHORT = 5
MA_MID = 10
MA_LONG = 20

CAP_MIN = 300
CAP_MAX = 5000

# ── 资金流向评分参数 ──────────────────────────────────────
FLOW_LOOKBACK = 5       # 资金流向动量窗口（交易日）
FLOW_SCORE_MAX = 20     # 资金流向满分


def build_sector_flow_index(raw_data):
    """
    将 sector_flow 原始列表构建为查询索引。
    同时构建全板块 net_inflow 排名缓存。
    返回 (index, sector_ranking)
      index: {(sector_type, sector_name): [rows...]}
      sector_ranking: [(sector_type, sector_name, total_net_inflow), ...] 按 net_inflow 降序
    """
    index = {}
    for row in raw_data:
        key = (row["sector_type"], row["sector_name"])
        if key not in index:
            index[key] = []
        index[key].append(row)

    for key in index:
        index[key].sort(key=lambda r: r["trade_date"])

    # 构建全板块 5 日 net_inflow 排名
    sector_nets = {}
    for key, rows in index.items():
        recent = rows[-FLOW_LOOKBACK:] if len(rows) >= FLOW_LOOKBACK else rows
        sector_nets[key] = sum((r.get("net_inflow") or 0) for r in recent)

    ranking = sorted(sector_nets.items(), key=lambda x: x[1], reverse=True)

    return index, ranking


def find_stock_sectors(index, industry_l2, industry_l1, concepts_json):
    """
    查找个股匹配的所有 sector_flow 板块。
    返回匹配的 sector_key 列表 [(sector_type, sector_name), ...]。
    """
    matched = set()

    # 1. concept-type 精确匹配 industry_l2 / industry_l1
    for term in [industry_l2, industry_l1]:
        if not term:
            continue
        key = ("concept", term)
        if key in index:
            matched.add(key)

    # 2. concept-type 模糊匹配（双向包含）
    if not matched:
        for term in [industry_l2, industry_l1]:
            if not term:
                continue
            for (stype, sname) in index:
                if stype != "concept":
                    continue
                if term in sname or sname in term:
                    matched.add((stype, sname))

    # 3. 解析 concepts JSON，匹配 industry-type 和 concept-type
    tags = []
    if concepts_json:
        try:
            tags = json.loads(concepts_json)
        except (json.JSONDecodeError, TypeError):
            pass

    if isinstance(tags, list):
        for tag in tags:
            # 精确匹配 industry-type
            key = ("industry", tag)
            if key in index:
                matched.add(key)
            # 精确匹配 concept-type
            key = ("concept", tag)
            if key in index:
                matched.add(key)
            # 模糊匹配（双向包含）
            for (stype, sname) in index:
                if (stype, sname) in matched:
                    continue
                if tag in sname or sname in tag:
                    matched.add((stype, sname))

    return list(matched)


def compute_flow_score(matched_sectors, ranking, index):
    """
    基于匹配的板块在资金流向排名中的位置计算得分（0-20）。

    规则：
      - 取匹配板块中排名最靠前的
      - Top 10%  → 20 分
      - Top 25%  → 15 分
      - Top 50%  → 10 分
      - Top 75%  → 5 分
      - 其余     → 0 分
      - 持续性加成：板块连续 >= 3 日 net_inflow > 0，额外 +2
    """
    if not matched_sectors or not ranking:
        return 0

    total = len(ranking)
    if total < 5:
        return 0

    # 建立排名查找：sector_key -> rank_index
    rank_map = {key: i for i, (key, _) in enumerate(ranking)}

    best_score = 0
    for skey in matched_sectors:
        if skey not in rank_map:
            continue
        rank_idx = rank_map[skey]
        percentile = 1.0 - (rank_idx / total)

        if percentile >= 0.90:
            sector_score = 20
        elif percentile >= 0.75:
            sector_score = 15
        elif percentile >= 0.50:
            sector_score = 10
        elif percentile >= 0.25:
            sector_score = 5
        else:
            sector_score = 0

        # 持续性加成
        if skey in index:
            rows = index[skey]
            consecutive = 0
            for r in reversed(rows):
                if (r.get("net_inflow") or 0) > 0:
                    consecutive += 1
                else:
                    break
            if consecutive >= 3:
                sector_score += 2

        if sector_score > best_score:
            best_score = sector_score

    return min(best_score, FLOW_SCORE_MAX)


def check_trend_upstart(df):
    """
    检查 df 在最后一天是否出现"趋势启动"信号。
    返回 {"passed": bool, "score": int (0-100), "details": {}, "breakdown": {}}

    单股诊断模式下会计算所有指标，即使前置条件未满足也不会提前返回。
    """
    result = {"passed": False, "score": 0, "details": {}, "breakdown": {}}
    filter_reasons = []

    if len(df) < MIN_HISTORY:
        result["details"]["error"] = f"数据不足：需要至少 {MIN_HISTORY} 个交易日，实际 {len(df)} 个"
        return result

    df = df.copy()
    df["ma5"] = df["close"].rolling(MA_SHORT).mean()
    df["ma10"] = df["close"].rolling(MA_MID).mean()
    df["ma20"] = df["close"].rolling(MA_LONG).mean()
    df["vol_ma5"] = df["vol"].rolling(5).mean()
    df["vol_ma20"] = df["vol"].rolling(20).mean()

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd_dif"] = ema12 - ema26
    df["macd_dea"] = df["macd_dif"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = 2 * (df["macd_dif"] - df["macd_dea"])

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    df["pct_chg"] = df["close"].pct_change() * 100

    latest = df.iloc[-1]
    price = latest["close"]

    # ── 初始化所有打分相关变量 ──────────────────────────────
    shrink_limit = False
    vol_ratio = 0.0
    vol_expand = False
    recent_gain = 0.0
    max_dd = 0.0
    ma_bull = False
    ma_strict = False
    ma20_up = False
    macd_golden = False
    macd_zero = False

    # ── 1. 大阳线信号 ──────────────────────────────────────
    today_up = latest["pct_chg"]
    today_big = today_up > BIG_UP_PCT * 100

    recent_n = min(BIG_UP_DAYS, len(df) - 1)
    recent_bigs = sum(
        1 for i in range(1, recent_n + 1)
        if df.iloc[-i]["pct_chg"] > BIG_UP_PCT * 100
    )
    cluster_big = recent_bigs >= BIG_UP_COUNT

    big_signal = today_big or cluster_big
    result["details"]["today_up"] = round(today_up, 2)
    result["details"]["today_big"] = today_big
    result["details"]["recent_bigs"] = recent_bigs
    result["details"]["cluster_big"] = cluster_big

    if not big_signal:
        filter_reasons.append(f"无大阳线信号(今日涨幅{today_up:.1f}%,近{BIG_UP_DAYS}日{BIG_UP_COUNT}+大阳:{recent_bigs}次)")

    # ── 2. 量能确认 ────────────────────────────────────────
    vol_ma5 = latest["vol_ma5"]
    today_vol = latest["vol"]
    vol_ratio = today_vol / vol_ma5 if vol_ma5 > 0 and not pd.isna(vol_ma5) else 0

    vol_expand = vol_ratio > VOL_RATIO_MIN
    is_limit_up = today_up > LIMIT_UP_PCT * 100
    shrink_limit = (vol_ratio < SHRINK_VOL_MAX) and is_limit_up

    vol_ok = vol_expand or shrink_limit
    result["details"]["vol_ratio"] = round(vol_ratio, 2)
    result["details"]["vol_expand"] = vol_expand
    result["details"]["shrink_limit"] = shrink_limit

    if not vol_ok:
        filter_reasons.append(f"量能不足(量比{vol_ratio:.1f}x,需>{VOL_RATIO_MIN}x)")

    # ── 3. 近10日涨幅范围 ─────────────────────────────────
    lookback = min(10, len(df) - 1)
    close_10d_ago = df.iloc[-lookback - 1]["close"]
    recent_gain = (price / close_10d_ago - 1) if close_10d_ago > 0 else 0

    gain_ok = RECENT_GAIN_MIN <= recent_gain <= RECENT_GAIN_MAX
    result["details"]["recent_gain"] = f"{recent_gain*100:.2f}%"
    result["details"]["gain_ok"] = gain_ok

    if not gain_ok:
        direction = "涨幅过高" if recent_gain > RECENT_GAIN_MAX else "跌幅过大"
        filter_reasons.append(f"近10日{direction}({recent_gain*100:.1f}%)")

    # ── 4. 最大回撤 < 15% ──────────────────────────────────
    low_start = max(0, len(df) - LOOKBACK_LOW)
    segment = df.iloc[low_start:]
    low_idx = segment["close"].idxmin()
    low_price = segment.loc[low_idx, "close"]

    after_low = segment[segment.index >= low_idx]
    peak_after_low = 0
    max_dd = 0
    for _, row in after_low.iterrows():
        if row["close"] > peak_after_low:
            peak_after_low = row["close"]
        dd = (peak_after_low - row["close"]) / peak_after_low if peak_after_low > 0 else 0
        if dd > max_dd:
            max_dd = dd

    dd_ok = max_dd < MAX_DRAWDOWN
    result["details"]["low_price"] = round(low_price, 2)
    result["details"]["max_dd"] = f"{max_dd*100:.1f}%"
    result["details"]["dd_ok"] = dd_ok

    if not dd_ok:
        filter_reasons.append(f"回撤过大({max_dd*100:.1f}%,需<{MAX_DRAWDOWN*100:.0f}%)")

    # ── 5. 均线多头排列 ────────────────────────────────────
    ma5 = latest["ma5"]
    ma10_val = latest["ma10"]
    ma20 = latest["ma20"]

    ma_bull = ma5 > ma10_val and price > ma5
    ma_strict = ma5 > ma10_val > ma20
    ma20_up = ma20 > df.iloc[-2]["ma20"] if len(df) >= 2 else False

    result["details"]["ma5"] = round(ma5, 2)
    result["details"]["ma10"] = round(ma10_val, 2)
    result["details"]["ma20"] = round(ma20, 2)
    result["details"]["ma_bull"] = ma_bull
    result["details"]["ma_strict"] = ma_strict
    result["details"]["ma20_up"] = ma20_up

    if not ma_bull:
        filter_reasons.append(f"均线非多头(MA5={ma5:.2f},MA10={ma10_val:.2f},价格={price:.2f})")

    # ── 6. MACD（总是计算） ────────────────────────────────
    dif = latest["macd_dif"]
    dea = latest["macd_dea"]
    if len(df) >= 2:
        prev_dif = df.iloc[-2]["macd_dif"]
        prev_dea = df.iloc[-2]["macd_dea"]
        macd_golden = prev_dif < prev_dea and dif > dea
    macd_zero = dif > 0 and dea > 0

    result["details"]["macd_dif"] = round(dif, 4)
    result["details"]["macd_dea"] = round(dea, 4)
    result["details"]["macd_golden"] = macd_golden
    result["details"]["macd_zero"] = macd_zero

    # ── 7. RSI（总是计算） ─────────────────────────────────
    rsi = latest["rsi"]
    rsi_ok = rsi < 80
    result["details"]["rsi"] = round(rsi, 1)
    result["details"]["rsi_ok"] = rsi_ok

    # ── 打分（满分 100，总是完整计算）─────────────────────
    score = 0
    bd = {}

    if today_big and cluster_big:
        score += 25
        bd["big_signal"] = 25
    elif today_big:
        score += 18
        bd["big_signal"] = 18
    elif cluster_big:
        score += 15
        bd["big_signal"] = 15
    else:
        bd["big_signal"] = 0

    if shrink_limit:
        score += 20
        bd["volume"] = 20
    elif vol_ratio > 2.0:
        score += 18
        bd["volume"] = 18
    elif vol_expand:
        score += 14
        bd["volume"] = 14
    else:
        bd["volume"] = 0

    if abs(recent_gain) < 0.05:
        score += 10
        bd["recent_gain"] = 10
    elif abs(recent_gain) < 0.10:
        score += 7
        bd["recent_gain"] = 7
    elif recent_gain != 0:
        score += 4
        bd["recent_gain"] = 4
    else:
        bd["recent_gain"] = 0

    if max_dd < 0.05:
        score += 15
        bd["drawdown"] = 15
    elif max_dd < 0.10:
        score += 12
        bd["drawdown"] = 12
    elif max_dd > 0:
        score += 8
        bd["drawdown"] = 8
    else:
        bd["drawdown"] = 0

    if ma_strict and ma20_up:
        score += 15
        bd["ma"] = 15
    elif ma_bull and ma20_up:
        score += 12
        bd["ma"] = 12
    elif ma_bull:
        score += 8
        bd["ma"] = 8
    else:
        bd["ma"] = 0

    if macd_golden and macd_zero:
        score += 10
        bd["macd"] = 10
    elif macd_golden or macd_zero:
        score += 6
        bd["macd"] = 6
    else:
        bd["macd"] = 0

    if rsi_ok and rsi < 70:
        score += 5
        bd["rsi"] = 5
    elif rsi_ok:
        score += 3
        bd["rsi"] = 3
    else:
        bd["rsi"] = 0

    result["score"] = score
    result["breakdown"] = bd
    result["passed"] = score >= 40
    result["details"]["filter_reasons"] = filter_reasons

    # 构建信号描述
    signals = []
    if today_big:
        signals.append(f"当日涨{today_up:.1f}%")
    if cluster_big:
        signals.append(f"{BIG_UP_DAYS}日{BIG_UP_COUNT}阳")
    if shrink_limit:
        signals.append("缩量涨停")
    elif vol_ratio > 2.0:
        signals.append(f"爆量{vol_ratio:.1f}x")
    elif vol_expand:
        signals.append(f"放量{vol_ratio:.1f}x")
    if macd_golden:
        signals.append("MACD金叉")
    elif macd_zero:
        signals.append("MACD零轴上")
    if filter_reasons and not signals:
        signals.append("未达标:" + filter_reasons[0])
    result["details"]["signal_text"] = ", ".join(signals) if signals else "未达标"

    return result


def run(data):
    """
    AIpicking 策略接口。

    Args:
        data: {
            "cutoff_date": "20260525",
            "stocks": [{"ts_code": "...", "name": "...", "industry_l2": "...", ...}],
            "daily": {"600001.SH": [{"trade_date": "...", "close": ..., "vol": ..., ...}]},
            "daily_sector_flow": [{"trade_date": "...", "sector_type": "...", "sector_name": "...", ...}],
        }
    """
    cutoff_date = data["cutoff_date"]
    stocks = data["stocks"]
    daily = data["daily"]
    daily_sector_flow_raw = data.get("daily_sector_flow", [])
    target_ts_code = data.get("config", {}).get("ts_code", "").strip() if data.get("config") else ""

    stock_lookup = {s["ts_code"]: s for s in stocks}
    recommendations = []

    # 构建 sector_flow 索引和排名
    sector_index = None
    sector_ranking = None
    if daily_sector_flow_raw:
        sector_index, sector_ranking = build_sector_flow_index(daily_sector_flow_raw)

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

        result = check_trend_upstart(df)

        # 单股诊断时不过滤涨停，不跳过未通过的结果
        if not target_ts_code:
            today_up_pct = result["details"].get("today_up", 0)
            if today_up_pct >= 9.5:
                continue

        if not result["passed"] and not target_ts_code:
            continue

        # ── 资金流向打分（替代旧的 sector_heatmap） ────────
        flow_score = 0
        if sector_index and sector_ranking:
            industry_l2 = stock.get("industry_l2", "")
            industry_l1 = stock.get("industry_l1", "")
            concepts_str = stock.get("concepts", "")
            matched = find_stock_sectors(sector_index, industry_l2, industry_l1, concepts_str)
            flow_score = compute_flow_score(matched, sector_ranking, sector_index)
            result["score"] += flow_score
            result["breakdown"]["daily_sector_flow"] = flow_score

        if result["score"] < 40 and not target_ts_code:
            continue

        signal_text = result["details"].get("signal_text", "趋势启动")
        if flow_score >= 16:
            signal_text += " [资金共振强]"
        elif flow_score >= 10:
            signal_text += " [资金共振]"
        elif flow_score > 0:
            signal_text += " [资金关注]"

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
