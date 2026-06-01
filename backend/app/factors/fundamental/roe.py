"""
ROE（净资产收益率）因子 — 打分 + 筛选

ROE 是衡量股东回报率的核心指标。
- 筛选模式：ROE 低于阈值 → 剔除
- 打分模式：ROE 越高分越多，线性映射
"""

FACTOR_META = {
    "id": "fundamental_roe",
    "name": "ROE（净资产收益率）",
    "category": "基本面类",
    "factor_type": "fundamental",
    "description": "基于 ROE 打分/筛选。ROE 越高代表股东回报率越高。",
    "params": [
        {"name": "min_roe", "label": "最低 ROE(%)", "type": "float", "default": 10.0, "min": 0, "max": 50},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 15.0, "min": 0, "max": 30},
    ],
    "usage_modes": ["scoring", "screening"],
}


def compute(financial: dict, market_data: dict, params: dict) -> float:
    """
    计算 ROE 评分。

    Args:
        financial: 最新财报字段 dict
        market_data: {'market_cap': float, 'close': float}
        params: {'min_roe': float, 'max_score': float}

    Returns:
        -1: 筛选不通过（ROE 为 None 或低于阈值）
        正数: 加分值（0 ~ max_score）
    """
    roe = financial.get("roe")
    if roe is None:
        return -1

    min_roe = params.get("min_roe", 10.0)
    max_score = params.get("max_score", 15.0)

    if roe < min_roe:
        return -1

    # 线性映射：min_roe → 0, min_roe+20 → max_score（封顶）
    score = min(max_score, (roe - min_roe) / 20.0 * max_score)
    return round(max(0.0, score), 2)
