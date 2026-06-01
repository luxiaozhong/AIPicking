"""
营收增长率因子 — 打分 + 筛选

营业收入同比增长率反映公司业务扩张速度。
- 筛选模式：增速低于阈值 → 剔除
- 打分模式：增速越高分越多，线性映射
"""

FACTOR_META = {
    "id": "fundamental_revenue_growth",
    "name": "营收增长率",
    "category": "基本面类",
    "factor_type": "fundamental",
    "description": "基于营业收入同比增长率打分/筛选。增速越高代表业务扩张越快。",
    "params": [
        {"name": "min_growth", "label": "最低增速(%)", "type": "float", "default": 5.0, "min": -100, "max": 500},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 10.0, "min": 0, "max": 25},
    ],
    "usage_modes": ["scoring", "screening"],
}


def compute(financial: dict, market_data: dict, params: dict) -> float:
    """
    计算营收增长率评分。

    Args:
        financial: 最新财报字段 dict（需要 revenue_yoy）
        market_data: 未使用
        params: {'min_growth': float, 'max_score': float}

    Returns:
        -1: 筛选不通过
        正数: 加分值
    """
    growth = financial.get("revenue_yoy")
    if growth is None:
        return -1

    min_growth = params.get("min_growth", 5.0)
    max_score = params.get("max_score", 10.0)

    if growth < min_growth:
        return -1

    # 线性映射：min_growth → 0, min_growth+30 → max_score
    score = min(max_score, (growth - min_growth) / 30.0 * max_score)
    return round(max(0.0, score), 2)
