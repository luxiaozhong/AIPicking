"""
均线支撑因子
股价在均线上方运行，回调到均线附近获得支撑
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "trend_ma_support",
    "name": "均线支撑",
    "category": "趋势类",
    "description": "股价在均线上方获得支撑，回调至均线附近时产生买入信号",
    "params": [
        {"name": "ma_period", "label": "均线周期", "type": "int", "default": 20, "min": 5, "max": 250},
        {"name": "tolerance", "label": "容差比例(%)", "type": "float", "default": 1.0, "min": 0.1, "max": 5.0},
    ],
    "signal_type": "buy",
}


def compute(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    计算均线支撑信号
    买入信号：股价在均线上方，且当日最低价接近均线（容差范围内）
    """
    ma_period = params.get("ma_period", 20)
    tolerance = params.get("tolerance", 1.0) / 100  # 转为小数

    close = df["close"]
    low = df["low"]
    ma = close.rolling(window=ma_period).mean()

    # 股价在均线上方
    above_ma = close > ma
    # 最低价接近均线（在容差范围内）
    near_ma = (low - ma).abs() / ma <= tolerance
    # 前一日不在均线上方（或距离均线较远），当日回到均线附近
    # 注意：shift(1) 会产生 NaN（float 类型），需要填充为 False
    signal = above_ma & near_ma & ~above_ma.shift(1).fillna(False)

    result = pd.Series(0, index=df.index)
    result[signal] = 1
    return result.astype(int)
