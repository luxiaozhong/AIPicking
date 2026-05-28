"""
锤子线因子
底部反转K线：实体小且在顶部，下影线长度是实体的2倍以上
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "pattern_hammer",
    "name": "锤子线",
    "category": "形态类",
    "description": "锤子线（下影线长，实体小）产生底部反转买入信号",
    "params": [
        {"name": "shadow_ratio", "label": "最小影线/实体比", "type": "float", "default": 2.0, "min": 1.0, "max": 10.0},
        {"name": "max_body_ratio", "label": "最大实体/全长比", "type": "float", "default": 0.4, "min": 0.1, "max": 0.5},
    ],
    "signal_type": "buy",
}


def compute(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    识别锤子线形态
    条件：
    1. 阴线或阳线均可（此处关注底部反转，不限涨跌）
    2. 下影线长度 >= 实体长度 * shadow_ratio
    3. 实体占全长比例 <= max_body_ratio
    4. 出现在下跌趋势后（前N日收盘价为跌）
    """
    shadow_ratio = params.get("shadow_ratio", 2.0)
    max_body_ratio = params.get("max_body_ratio", 0.4)

    open_ = df["open"]
    close = df["close"]
    high = df["high"]
    low = df["low"]

    body = abs(close - open_)
    total_range = high - low
    lower_shadow = pd.Series(0, index=df.index)
    # 阳线：下影线 = open - low
    lower_shadow[close >= open_] = open_ - low
    # 阴线：下影线 = close - low
    lower_shadow[close < open_] = close - low

    # 条件：下影线/实体比 >= 阈值
    has_long_shadow = (lower_shadow / body.replace(0, np.nan)) >= shadow_ratio
    has_long_shadow = has_long_shadow.fillna(False)

    # 实体占全长比例 <= 阈值
    body_ratio_small = (body / total_range.replace(0, np.nan)) <= max_body_ratio
    body_ratio_small = body_ratio_small.fillna(False)

    # 出现在下跌趋势后（前5日收盘均价下跌）
    downtrend = df["close"].shift(1).rolling(5).mean() < df["close"].shift(6).rolling(5).mean()

    hammer = has_long_shadow & body_ratio_small & downtrend

    signal = pd.Series(0, index=df.index)
    signal[hammer.fillna(False)] = 1
    return signal.astype(int)
