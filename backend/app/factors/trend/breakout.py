"""
突破新高因子
股价突破N日最高价，视为突破信号
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "trend_breakout",
    "name": "突破新高",
    "category": "趋势类",
    "description": "股价突破N日最高价，产生买入信号；跌破N日最低价，产生卖出信号",
    "params": [
        {"name": "lookback", "label": "观察周期(天)", "type": "int", "default": 20, "min": 5, "max": 250},
    ],
    "signal_type": "both",
}


def compute(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    计算突破信号
    买入：收盘价突破N日最高价
    卖出：收盘价跌破N日最低价
    """
    lookback = params.get("lookback", 20)

    high = df["high"]
    low = df["low"]
    close = df["close"]

    # N日最高价和最低价（不含当日）
    highest = high.shift(1).rolling(window=lookback).max()
    lowest = low.shift(1).rolling(window=lookback).min()

    # 突破新高
    breakout_up = close > highest
    # 跌破新低
    breakout_down = close < lowest

    signal = pd.Series(0, index=df.index)
    signal[breakout_up] = 1
    signal[breakout_down] = -1
    return signal.astype(int)
