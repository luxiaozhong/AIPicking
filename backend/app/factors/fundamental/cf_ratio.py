"""
现金流比率因子 — 打分 + 筛选

经营现金流 / 营业收入的比率，反映盈利质量。
- 筛选模式：比率低于阈值 → 剔除
- 打分模式：比率越高分越多（现金流充沛加分）
"""

FACTOR_META = {
    "id": "fundamental_cf_ratio",
    "name": "现金流比率",
    "category": "基本面类",
    "factor_type": "fundamental",
    "description": "经营现金流/营业收入比率。比率高说明盈利质量好、现金回收能力强。",
    "params": [
        {"name": "min_ratio", "label": "最低比率(%)", "type": "float", "default": 5.0, "min": -100, "max": 200},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 8.0, "min": 0, "max": 20},
    ],
    "usage_modes": ["scoring", "screening"],
}


def compute(financial: dict, market_data: dict, params: dict) -> float:
    """
    计算现金流比率评分。

    Args:
        financial: 最新财报字段 dict（需要 cf_operating, revenue）
        market_data: 未使用
        params: {'min_ratio': float, 'max_score': float}

    Returns:
        -1: 筛选不通过
        正数: 加分值
    """
    cf = financial.get("cf_operating")
    revenue = financial.get("revenue")
    if cf is None or revenue is None or revenue <= 0:
        return -1

    # cf_operating / revenue * 100 → 百分比
    ratio = (cf / revenue) * 100.0

    min_ratio = params.get("min_ratio", 5.0)
    max_score = params.get("max_score", 8.0)

    if ratio < min_ratio:
        return -1

    # 线性映射：min_ratio → 0, min_ratio+20 → max_score
    score = min(max_score, (ratio - min_ratio) / 20.0 * max_score)
    return round(max(0.0, score), 2)
