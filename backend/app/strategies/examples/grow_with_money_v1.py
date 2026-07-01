"""
grow_with_money_v1 — 成长100 + 资金流/市值选股策略

策略逻辑：
1. 以国证成长100（980080）成分股为股票池
2. 计算每只成分股过去 M 日的主力净流入总额（main_net_flow 累加）
3. 除以该股在截止日的总市值（market_cap），得到资金流/市值比率
4. 按比率降序排列，取前 N 只推荐

与原始 grow_with_money 的区别：
- grow_with_money: 按主力净流入总额排名（大市值股票占优）
- grow_with_money_v1: 按主力净流入/总市值比率排名（资金效率优先）

参数（通过 config 传入，默认值用于回测框架 UI 联动）：
- index_code: 指数代码，默认 "980080"（国证成长100）
- N: 推荐股票数量，默认 3
- M: 资金流回顾天数（交易日），默认 5

数据依赖：
REQUIRED_DATA = ["fund_flow", "index_constituents"]

注意：
- 市值来源于 daily 表中的 market_cap 字段（单位：亿元），由 DailyValuation 表合并
- 若某股票无市值数据，跳过该股票
"""

from collections import defaultdict

REQUIRED_DATA = ["fund_flow", "index_constituents"]

# ── 默认参数 ──────────────────────────────────────────────────
DEFAULT_INDEX_CODE = "980080"
DEFAULT_N = 3
DEFAULT_M = 5


def run(data):
    """入口函数，回测引擎调用

    data 结构（由 BacktestEngine 注入）：
        - cutoff_date: str  YYYYMMDD
        - stocks:       [{ts_code, symbol, name, ...}]
        - daily:        {ts_code: [{trade_date, close, market_cap, ...}]}
        - fund_flow:    [{trade_date, ts_code, main_net_flow, ...}]
        - index_constituents: [{index_code, ts_code, stock_name, ...}]
        - config:       {index_code, N, M, ...}
    """
    config = data.get("config", {})
    index_code = str(config.get("index_code", DEFAULT_INDEX_CODE))
    N = int(config.get("N", DEFAULT_N))
    M = int(config.get("M", DEFAULT_M))
    cutoff_date = data.get("cutoff_date", "")

    # ── 1. 获取指数成分股原始代码集合 ──────────────────────────
    constituents = data.get("index_constituents", [])
    target_raw_codes = set(
        c["ts_code"][:6] for c in constituents
        if c.get("index_code") == index_code
    )

    if not target_raw_codes:
        return []

    # ── 2. 构建 raw_code → ts_code 映射（优先使用引擎预计算） ──
    precomputed_raw_map = data.get("_raw_to_tscode")
    ts_code_to_name = data.get("_ts_code_to_name", {})
    if precomputed_raw_map:
        raw_to_tscode = precomputed_raw_map
    else:
        raw_to_tscode = {}
        for s in data.get("stocks", []):
            ts_code = s.get("ts_code", "")
            raw_code = ts_code.split(".")[0] if "." in ts_code else ts_code
            if raw_code in target_raw_codes:
                raw_to_tscode[raw_code] = ts_code
                ts_code_to_name[ts_code] = s.get("name", "")

    # ── 3. 按 M 日窗口聚合资金流（优先使用引擎预聚合） ──────────
    precomputed_flow = data.get("_flow_aggregated_m")
    precomputed_dates = data.get("_valid_dates")

    if precomputed_flow is not None and precomputed_dates is not None:
        flow_by_tscode = defaultdict(float, precomputed_flow)
        valid_dates = precomputed_dates  # 引擎提供升序排列
    else:
        fund_flows = data.get("fund_flow", [])
        # 升序排列（与引擎注入的 _valid_dates 顺序一致）
        trade_dates = sorted(set(
            r["trade_date"] for r in fund_flows
            if r.get("trade_date")
        ))
        cutoff_fmt = _to_date_fmt(cutoff_date)
        valid_dates = [d for d in trade_dates if d <= cutoff_fmt][-M:]

        flow_by_tscode = defaultdict(float)
        if valid_dates:
            date_set = set(valid_dates)
            for row in fund_flows:
                if row["trade_date"] in date_set:
                    flow_by_tscode[row["ts_code"]] += (
                        row.get("main_net_flow") or 0.0
                    )

    if not valid_dates:
        return []

    # ── 4. 获取截止日的市值数据 ────────────────────────────────
    # market_cap 单位：亿元（由 DailyValuation 表合并）
    daily_data = data.get("daily", {})
    market_cap_by_tscode = {}  # ts_code → 总市值（亿元）

    cutoff_date_fmt = _to_date_fmt(cutoff_date)
    for ts_code, rows in daily_data.items():
        for r in rows:
            if r.get("trade_date") == cutoff_date_fmt:
                mc = r.get("market_cap")
                if mc and mc > 0:
                    market_cap_by_tscode[ts_code] = mc
                break

    # ── 5. 构建推荐列表（资金流/市值比率） ──────────────────────
    recommendations = []
    skipped_no_cap = 0
    for raw_code in target_raw_codes:
        ts_code = raw_to_tscode.get(raw_code)
        if not ts_code:
            continue
        total_flow = flow_by_tscode.get(ts_code, 0.0)
        mc = market_cap_by_tscode.get(ts_code, 0)
        if mc <= 0:
            skipped_no_cap += 1
            continue

        flow_yi = total_flow / 1e8  # 元 → 亿元
        score = round(flow_yi / mc * 100, 4)  # 资金流占市值百分比

        recommendations.append({
            "ts_code": ts_code,
            "name": ts_code_to_name.get(ts_code, raw_code),
            "score": score,
            "signal": _describe(valid_dates, total_flow, mc, score),
        })

    recommendations.sort(key=lambda x: x["score"], reverse=True)
    return recommendations[:N]


def _to_date_fmt(cutoff_date: str) -> str:
    """将 YYYYMMDD 转为 YYYY-MM-DD"""
    if len(cutoff_date) == 8:
        return f"{cutoff_date[:4]}-{cutoff_date[4:6]}-{cutoff_date[6:8]}"
    return cutoff_date


def _describe(dates: list, total_flow: float, mc: float, score: float) -> str:
    """生成信号描述文本（dates 为升序排列）"""
    yi = total_flow / 1e8
    direction = "流入" if total_flow > 0 else "流出"
    m = len(dates)
    if m == 0:
        return f"{m}日主力净{direction}: {abs(yi):.2f}亿 / 市值: {mc:.0f}亿 比率: {score:.4f}%"
    first = dates[0]   # 最早的日期（升序第一项）
    last = dates[-1]   # 最近的日期（升序末项）
    return f"{first}~{last} 主力净{direction}: {abs(yi):.2f}亿 / 市值: {mc:.0f}亿 比率: {score:.4f}%"
