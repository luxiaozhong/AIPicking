"""
grow_with_money_cy — 创业板个股 + 资金流选股策略

策略逻辑：
1. 以创业板个股（300/301 开头）为股票池
2. 计算每只股票过去 M 日的主力净流入总额（main_net_flow 累加）
3. 按资金流总额降序排列，取前 N 只推荐

参数（通过 config 传入，默认值用于回测框架 UI 联动）：
- N: 推荐股票数量，默认 5
- M: 资金流回顾天数（交易日），默认 5

数据依赖：
REQUIRED_DATA = ["fund_flow"]

注意：
- 股票池由 ts_code 前缀自动筛选，无需指数成分股数据
- 资金流数据已由引擎按 cutoff_date 截断，策略只需取最近 M 个交易日聚合
"""

import pandas as pd

REQUIRED_DATA = ["fund_flow"]

# ── 创业板股票代码前缀 ────────────────────────────────────────────
_STOCK_PREFIXES = ("300", "301")

# ── 默认参数 ──────────────────────────────────────────────────
DEFAULT_N = 5
DEFAULT_M = 5


def run(data):
    """入口函数，回测引擎调用

    data 结构（由 BacktestEngine 注入）：
        - cutoff_date: str  YYYYMMDD
        - stocks:       [{ts_code, symbol, name, ...}]
        - daily:        {ts_code: [{trade_date, close, vol, ...}]}
        - fund_flow:    [{trade_date, ts_code, main_net_flow, ...}]
        - config:       {N, M, ...}
    """
    config = data.get("config", {})
    N = int(config.get("N", DEFAULT_N))
    M = int(config.get("M", DEFAULT_M))
    cutoff_date = data.get("cutoff_date", "")

    # ── 1. 筛选创业板目标股票 ──────────────────────────────────
    ts_code_to_name = data.get("_ts_code_to_name", {})
    target_codes = set()
    for s in data.get("stocks", []):
        ts_code = s.get("ts_code", "")
        raw_code = ts_code.split(".")[0] if "." in ts_code else ts_code
        if raw_code.startswith(_STOCK_PREFIXES):
            target_codes.add(ts_code)
            if ts_code not in ts_code_to_name:
                ts_code_to_name[ts_code] = s.get("name", "")

    if not target_codes:
        return []

    # ── 2. 按 M 日窗口聚合资金流（优先使用引擎预聚合） ──────────
    from collections import defaultdict

    precomputed_flow = data.get("_flow_aggregated_m")
    precomputed_dates = data.get("_valid_dates")

    if precomputed_flow is not None and precomputed_dates is not None:
        flow_by_tscode = defaultdict(float, precomputed_flow)
        valid_dates = precomputed_dates
    else:
        fund_flows = data.get("fund_flow", [])
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

    # ── 3. 构建推荐列表 ──────────────────────────────────────
    recommendations = []
    for ts_code in target_codes:
        total_flow = flow_by_tscode.get(ts_code, 0.0)

        recommendations.append({
            "ts_code": ts_code,
            "name": ts_code_to_name.get(ts_code, ts_code),
            "score": round(total_flow / 1e8, 2),  # 转换为亿
            "signal": _describe(valid_dates, total_flow),
        })

    recommendations.sort(key=lambda x: x["score"], reverse=True)
    return recommendations[:N]


def _to_date_fmt(cutoff_date: str) -> str:
    """将 YYYYMMDD 转为 YYYY-MM-DD"""
    if len(cutoff_date) == 8:
        return f"{cutoff_date[:4]}-{cutoff_date[4:6]}-{cutoff_date[6:8]}"
    return cutoff_date  # 已经是 YYYY-MM-DD 格式


def _describe(dates: list, total_flow: float) -> str:
    """生成信号描述文本（dates 为升序排列）"""
    yi = total_flow / 1e8
    direction = "流入" if total_flow > 0 else "流出"
    m = len(dates)
    if m == 0:
        return f"{m}日主力净{direction}: {abs(yi):.2f}亿"
    first = dates[0]   # 最早的日期（升序第一项）
    last = dates[-1]   # 最近的日期（升序末项）
    return f"{first}~{last} 主力净{direction}: {abs(yi):.2f}亿"
