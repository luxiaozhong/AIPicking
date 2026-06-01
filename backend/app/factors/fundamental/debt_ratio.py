"""
资产负债率因子 — 仅筛选

高资产负债率意味着高财务杠杆和潜在风险。
- 筛选模式：负债率超过阈值 → 剔除
- 不打分（负债率本身不是"越高越好"的指标）
"""

FACTOR_META = {
    "id": "fundamental_debt_ratio",
    "name": "资产负债率",
    "category": "基本面类",
    "factor_type": "fundamental",
    "description": "基于资产负债率筛选。负债率过高 → 剔除，控制财务风险。",
    "params": [
        {"name": "max_debt", "label": "最高负债率(%)", "type": "float", "default": 70.0, "min": 0, "max": 100},
    ],
    "usage_modes": ["screening"],
}


def compute(financial: dict, market_data: dict, params: dict) -> float:
    """
    资产负债率筛选。

    Args:
        financial: 最新财报字段 dict（需要 debt_to_assets）
        market_data: 未使用
        params: {'max_debt': float}

    Returns:
        -1: 筛选不通过（负债率超过阈值或为 None）
        0: 通过筛选
    """
    debt = financial.get("debt_to_assets")
    if debt is None:
        return -1

    max_debt = params.get("max_debt", 70.0)

    if debt > max_debt:
        return -1

    return 0  # 通过，不加分
