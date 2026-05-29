"""
OBV能量潮因子
OBV（On-Balance Volume）通过成交量变化预测价格走势
OBV创新高预示上升趋势延续
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "volume_obv",
    "name": "OBV能量潮",
    "category": "量能类",
    "description": "OBV创新高产生买入信号，OBV创新低产生卖出信号",
    "params": [
        {"name": "lookback", "label": "观察周期(天)", "type": "int", "default": 20, "min": 5, "max": 100},
    ],
    "signal_type": "both",
}


def compute(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    计算OBV信号
    买入：OBV创N日新高
    卖出：OBV创N日新低
    """
    lookback = params.get("lookback", 20)

    close = df["close"]
    volume = df["volume"] if "volume" in df.columns else df["vol"]

    # 计算OBV
    obv = pd.Series(0, index=df.index, dtype=float)
    for i in range(1, len(df)):
        if close.iloc[i] > close.iloc[i - 1]:
            obv.iloc[i] = obv.iloc[i - 1] + volume.iloc[i]
        elif close.iloc[i] < close.iloc[i - 1]:
            obv.iloc[i] = obv.iloc[i - 1] - volume.iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i - 1]

    # OBV创N日新高 → 买入
    obv_high = obv > obv.shift(1).rolling(window=lookback).max()
    # OBV创N日新低 → 卖出
    obv_low = obv < obv.shift(1).rolling(window=lookback).min()

    signal = pd.Series(0, index=df.index)
    signal[obv_high] = 1
    signal[obv_low] = -1
    return signal.astype(int)
