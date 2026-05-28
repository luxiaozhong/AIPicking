"""
MACD金叉/死叉因子
MACD快线(DIF)上穿慢线(DEA)形成金叉，下穿形成死叉
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "momentum_macd",
    "name": "MACD金叉死叉",
    "category": "动量类",
    "description": "MACD快线上穿慢线形成金叉买入，下穿形成死叉卖出",
    "params": [
        {"name": "fast_period", "label": "快线周期", "type": "int", "default": 12, "min": 2, "max": 50},
        {"name": "slow_period", "label": "慢线周期", "type": "int", "default": 26, "min": 5, "max": 100},
        {"name": "signal_period", "label": "信号线周期", "type": "int", "default": 9, "min": 2, "max": 30},
    ],
    "signal_type": "both",
}


def _calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    计算MACD金叉死叉信号
    买入：DIF上穿DEA
    卖出：DIF下穿DEA
    """
    fast = params.get("fast_period", 12)
    slow = params.get("slow_period", 26)
    signal = params.get("signal_period", 9)

    close = df["close"]
    ema_fast = _calc_ema(close, fast)
    ema_slow = _calc_ema(close, slow)
    dif = ema_fast - ema_slow
    dea = _calc_ema(dif, signal)

    # 金叉：DIF上穿DEA
    golden_cross = (dif.shift(1) <= dea.shift(1)) & (dif > dea)
    # 死叉：DIF下穿DEA
    death_cross = (dif.shift(1) >= dea.shift(1)) & (dif < dea)

    signal_series = pd.Series(0, index=df.index)
    signal_series[golden_cross] = 1
    signal_series[death_cross] = -1
    return signal_series.astype(int)
