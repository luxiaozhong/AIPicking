"""
均线金叉/死叉因子
短期均线上穿长期均线形成金叉（买入信号），下穿形成死叉（卖出信号）
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "trend_ma_cross",
    "name": "均线金叉死叉",
    "category": "趋势类",
    "description": "短期均线上穿长期均线形成金叉买入信号，下穿形成死叉卖出信号",
    "params": [
        {"name": "short_period", "label": "短期均线周期", "type": "int", "default": 5, "min": 1, "max": 60},
        {"name": "long_period", "label": "长期均线周期", "type": "int", "default": 20, "min": 5, "max": 250},
    ],
    "signal_type": "both",
}


def compute(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    计算均线金叉死叉信号
    df: 包含 open/high/low/close/volume 列的 DataFrame
    params: 因子参数
    return: Series，1=金叉(买入), -1=死叉(卖出), 0=无信号
    """
    short_period = params.get("short_period", 5)
    long_period = params.get("long_period", 20)

    close = df["close"]
    short_ma = close.rolling(window=short_period).mean()
    long_ma = close.rolling(window=long_period).mean()

    # 金叉：短均线从下方穿越长均线（前一天 short_ma <= long_ma，当天 short_ma > long_ma）
    golden_cross = (short_ma.shift(1) <= long_ma.shift(1)) & (short_ma > long_ma)
    # 死叉：短均线从上方穿越长均线
    death_cross = (short_ma.shift(1) >= long_ma.shift(1)) & (short_ma < long_ma)

    signal = pd.Series(0, index=df.index)
    signal[golden_cross] = 1
    signal[death_cross] = -1
    return signal.astype(int)
