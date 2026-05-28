"""
量比因子
量比 = 当日成交量 / 过去N日平均成交量，衡量成交量放大程度
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "volume_ratio",
    "name": "量比放大",
    "category": "量能类",
    "description": "当日量比超过阈值，视为放量信号，配合价格上涨产生买入信号",
    "params": [
        {"name": "lookback", "label": "平均成交量周期", "type": "int", "default": 5, "min": 1, "max": 30},
        {"name": "threshold", "label": "量比阈值", "type": "float", "default": 2.0, "min": 1.0, "max": 10.0},
        {"name": "require_price_up", "label": "要求价格上涨", "type": "bool", "default": True},
    ],
    "signal_type": "buy",
}


def compute(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    计算量比信号
    买入：量比超过阈值，且（可选）当日收盘价 > 前一日收盘价
    """
    lookback = params.get("lookback", 5)
    threshold = params.get("threshold", 2.0)
    require_price_up = params.get("require_price_up", True)

    volume = df["volume"]
    avg_volume = volume.shift(1).rolling(window=lookback).mean()
    volume_ratio = volume / avg_volume

    buy_signal = volume_ratio > threshold
    if require_price_up:
        buy_signal = buy_signal & (df["close"] > df["close"].shift(1))

    signal = pd.Series(0, index=df.index)
    signal[buy_signal] = 1
    return signal.astype(int)
