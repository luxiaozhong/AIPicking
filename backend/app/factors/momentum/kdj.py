"""
KDJ金叉死叉因子
K线与D线的交叉产生买卖信号，J线辅助判断超买超卖
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "momentum_kdj",
    "name": "KDJ金叉死叉",
    "category": "动量类",
    "description": "K线上穿D线形成金叉买入，下穿形成死叉卖出；J>100超买，J<0超卖",
    "params": [
        {"name": "n", "label": "RSV周期", "type": "int", "default": 9, "min": 2, "max": 30},
        {"name": "m1", "label": "K值平滑周期", "type": "int", "default": 3, "min": 1, "max": 10},
        {"name": "m2", "label": "D值平滑周期", "type": "int", "default": 3, "min": 1, "max": 10},
    ],
    "signal_type": "both",
}


def compute(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    计算KDJ信号
    买入：K线上穿D线（金叉）
    卖出：K线下穿D线（死叉）
    """
    n = params.get("n", 9)
    m1 = params.get("m1", 3)
    m2 = params.get("m2", 3)

    high = df["high"]
    low = df["low"]
    close = df["close"]

    # 计算RSV
    lowest_low = low.rolling(window=n).min()
    highest_high = high.rolling(window=n).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low) * 100

    # 计算K、D、J值
    k = rsv.ewm(com=m1 - 1, adjust=False).mean()
    d = k.ewm(com=m2 - 1, adjust=False).mean()

    # 金叉：K上穿D
    golden_cross = (k.shift(1) <= d.shift(1)) & (k > d)
    # 死叉：K下穿D
    death_cross = (k.shift(1) >= d.shift(1)) & (k < d)

    signal = pd.Series(0, index=df.index)
    signal[golden_cross] = 1
    signal[death_cross] = -1
    return signal.astype(int)
