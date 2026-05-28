"""
RSI超买超卖因子
RSI进入超卖区间产生买入信号，进入超买区间产生卖出信号
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "momentum_rsi",
    "name": "RSI超买超卖",
    "category": "动量类",
    "description": "RSI进入超卖区间买入，进入超买区间卖出",
    "params": [
        {"name": "period", "label": "RSI周期", "type": "int", "default": 14, "min": 2, "max": 50},
        {"name": "oversold", "label": "超卖阈值", "type": "int", "default": 30, "min": 10, "max": 50},
        {"name": "overbought", "label": "超买阈值", "type": "int", "default": 70, "min": 50, "max": 90},
    ],
    "signal_type": "both",
}


def _calc_rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def compute(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    计算RSI信号
    买入：RSI从超卖区间下方上穿超卖线
    卖出：RSI从超买区间上方下穿超买线
    """
    period = params.get("period", 14)
    oversold = params.get("oversold", 30)
    overbought = params.get("overbought", 70)

    rsi = _calc_rsi(df["close"], period)

    # 从超卖区上穿 → 买入
    buy_signal = (rsi.shift(1) < oversold) & (rsi >= oversold)
    # 从超买区下穿 → 卖出
    sell_signal = (rsi.shift(1) > overbought) & (rsi <= overbought)

    signal = pd.Series(0, index=df.index)
    signal[buy_signal] = 1
    signal[sell_signal] = -1
    return signal.astype(int)
