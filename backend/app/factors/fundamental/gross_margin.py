"""
毛利率因子 — 打分 + 筛选

毛利率反映公司产品或服务的基本盈利能力。
- 筛选模式：毛利率低于阈值 → 剔除
- 打分模式：毛利率越高分越多（高毛利通常意味着护城河）
"""

FACTOR_META = {
    "id": "fundamental_gross_margin",
    "name": "毛利率",
    "category": "基本面类",
    "factor_type": "fundamental",
    "description": "基于毛利率打分/筛选。高毛利率通常代表强定价权或品牌壁垒。",
    "params": [
        {"name": "min_margin", "label": "最低毛利率(%)", "type": "float", "default": 20.0, "min": 0, "max": 100},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 10.0, "min": 0, "max": 20},
    ],
    "usage_modes": ["scoring", "screening"],
}


def compute(financial: dict, market_data: dict, params: dict) -> float:
    """
    计算毛利率评分。

    Args:
        financial: 最新财报字段 dict（需要 gross_margin）
        market_data: 未使用
        params: {'min_margin': float, 'max_score': float}

    Returns:
        -1: 筛选不通过
        正数: 加分值
    """
    margin = financial.get("gross_margin")
    if margin is None:
        return -1

    min_margin = params.get("min_margin", 20.0)
    max_score = params.get("max_score", 10.0)

    if margin < min_margin:
        return -1

    # 线性映射：min_margin → 0, min_margin+40 → max_score
    score = min(max_score, (margin - min_margin) / 40.0 * max_score)
    return round(max(0.0, score), 2)
