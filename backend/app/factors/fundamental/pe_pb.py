"""
PE/PB 估值因子 — 打分 + 筛选

PE（市盈率）和 PB（市净率）从 daily.market_cap + 财报数据实时计算。
- PE = 总市值(亿元) / 净利润(亿元)
- PB = 总市值(亿元) / 股东权益(亿元)
- 筛选模式：PE 超过阈值或为负 → 剔除
- 打分模式：PE 越低分越多（低估值加分）
"""

from typing import Optional

FACTOR_META = {
    "id": "fundamental_pe_pb",
    "name": "PE/PB 估值",
    "category": "基本面类",
    "factor_type": "fundamental",
    "description": "基于 PE（市盈率）和 PB（市净率）估值打分/筛选。低 PE/PB 加分。"
                   "数据来源：市值从日线行情获取，净利润和净资产从财报获取。",
    "params": [
        {"name": "max_pe", "label": "最高 PE（筛选）", "type": "float", "default": 50.0, "min": 0, "max": 500},
        {"name": "max_pb", "label": "最高 PB（筛选）", "type": "float", "default": 10.0, "min": 0, "max": 50},
        {"name": "pe_score_weight", "label": "PE 打分权重", "type": "float", "default": 0.7, "min": 0, "max": 1},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 15.0, "min": 0, "max": 30},
    ],
    "usage_modes": ["scoring", "screening"],
}


def _calc_pe(financial: dict, market_cap: float) -> Optional[float]:
    """从市值和净利润计算 PE(TTM)"""
    net_profit = financial.get("net_profit")  # 万元
    if not net_profit or net_profit <= 0 or not market_cap or market_cap <= 0:
        return None
    # market_cap: 元 → 亿元; net_profit: 万元 → 亿元
    mc_yi = market_cap / 1e8
    np_yi = net_profit / 1e4  # 万元 → 亿元
    return round(mc_yi / np_yi, 2)


def _calc_pb(financial: dict, market_cap: float) -> Optional[float]:
    """从市值和股东权益计算 PB"""
    equity = financial.get("shareholders_equity")  # 万元
    if not equity or equity <= 0 or not market_cap or market_cap <= 0:
        return None
    mc_yi = market_cap / 1e8
    eq_yi = equity / 1e4  # 万元 → 亿元
    return round(mc_yi / eq_yi, 2)


def compute(financial: dict, market_data: dict, params: dict) -> float:
    """
    计算 PE/PB 估值评分。

    Args:
        financial: 最新财报字段 dict（需要 net_profit, shareholders_equity）
        market_data: {'market_cap': float, 'close': float}
        params: {'max_pe': float, 'max_pb': float, 'pe_score_weight': float, 'max_score': float}

    Returns:
        -1: 筛选不通过（PE 为 None、超过阈值或为负）
        正数: 加分值（PE 越低分越多 + PB 越低分越多）
    """
    market_cap = market_data.get("market_cap", 0) if market_data else 0

    pe = _calc_pe(financial, market_cap)
    pb = _calc_pb(financial, market_cap)

    max_pe = params.get("max_pe", 50.0)
    max_pb = params.get("max_pb", 10.0)
    weight = params.get("pe_score_weight", 0.7)
    max_score = params.get("max_score", 15.0)

    # 筛选：PE 必须有效且不超过阈值
    if pe is None or pe <= 0 or pe > max_pe:
        return -1

    # 筛选：PB 如果有效，也不应超过阈值
    if pb is not None and pb > max_pb:
        return -1

    # 打分：PE 越低分越多
    # PE: 0~max_pe → max_score*weight ~ 0
    pe_score = max(0.0, (1.0 - pe / max_pe)) * max_score * weight

    # 打分：PB 越低分越多
    # PB: 0~max_pb → max_score*(1-weight) ~ 0
    if pb is not None and pb > 0:
        pb_score = max(0.0, (1.0 - pb / max_pb)) * max_score * (1.0 - weight)
    else:
        pb_score = 0.0

    return round(pe_score + pb_score, 2)
