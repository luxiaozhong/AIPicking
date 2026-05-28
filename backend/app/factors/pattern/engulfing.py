"""
吞没形态因子
看涨吞没：阳线实体完全包围前一日阴线实体，底部反转信号
看跌吞没：阴线实体完全包围前一日阳线实体，顶部反转信号
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "pattern_engulfing",
    "name": "吞没形态",
    "category": "形态类",
    "description": "看涨吞没产生买入信号，看跌吞没产生卖出信号",
    "params": [],
    "signal_type": "both",
}


def compute(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    识别吞没形态
    买入：看涨吞没（当前阳线实体完全包含前一日阴线实体）
    卖出：看跌吞没（当前阴线实体完全包含前一日阳线实体）
    """
    open_ = df["open"]
    close = df["close"]

    # 前一日K线
    prev_open = open_.shift(1)
    prev_close = close.shift(1)

    # 前一日是阴线，当前是阳线
    prev_bear = prev_close < prev_open
    curr_bull = close > open_

    # 看涨吞没：当前阳线实体完全包含前一日阴线实体
    bullish_engulfing = prev_bear & curr_bull & (open_ <= prev_close) & (close >= prev_open)

    # 前一日是阳线，当前是阴线
    prev_bull = prev_close > prev_open
    curr_bear = close < open_

    # 看跌吞没
    bearish_engulfing = prev_bull & curr_bear & (open_ >= prev_close) & (close <= prev_open)

    signal = pd.Series(0, index=df.index)
    signal[bullish_engulfing.fillna(False)] = 1
    signal[bearish_engulfing.fillna(False)] = -1
    return signal.astype(int)
