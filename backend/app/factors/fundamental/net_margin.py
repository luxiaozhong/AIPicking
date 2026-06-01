"""
净利率因子 — 打分 + 筛选

净利率反映公司费用控制和最终盈利效率。
- 筛选模式：净利率低于阈值 → 剔除
- 打分模式：净利率越高分越多
"""

FACTOR_META = {
    "id": "fundamental_net_margin",
    "name": "净利率",
    "category": "基本面类",
    "factor_type": "fundamental",
    "description": "基于净利率打分/筛选。高净利率代表强盈利效率。",
    "params": [
        {"name": "min_margin", "label": "最低净利率(%)", "type": "float", "default": 5.0, "min": 0, "max": 100},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 10.0, "min": 0, "max": 20},
    ],
    "usage_modes": ["scoring", "screening"],
}


def compute(financial: dict, market_data: dict, params: dict) -> float:
    """
    计算净利率评分。

    Args:
        financial: 最新财报字段 dict（需要 net_margin）
        market_data: 未使用
        params: {'min_margin': float, 'max_score': float}

    Returns:
        -1: 筛选不通过
        正数: 加分值
    """
    margin = financial.get("net_margin")
    if margin is None:
        return -1

    min_margin = params.get("min_margin", 5.0)
    max_score = params.get("max_score", 10.0)

    if margin < min_margin:
        return -1

    # 线性映射：min_margin → 0, min_margin+25 → max_score
    score = min(max_score, (margin - min_margin) / 25.0 * max_score)
    return round(max(0.0, score), 2)
