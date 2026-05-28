"""
启明星（早晨之星）形态因子
三日K线形态：长阴线 + 十字星 + 长阳线，预示底部反转
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "pattern_morning_star",
    "name": "启明星",
    "category": "形态类",
    "description": "三日K线底部反转形态：长阴线+十字星+长阳线，产生买入信号",
    "params": [
        {"name": "body_ratio", "label": "阳线实体占比最小(%)", "type": "float", "default": 50.0, "min": 10.0, "max": 100.0},
    ],
    "signal_type": "buy",
}


def _calc_body(df: pd.DataFrame) -> pd.Series:
    return abs(df["close"] - df["open"])


def _calc_range(df: pd.DataFrame) -> pd.Series:
    return df["high"] - df["low"]


def compute(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    识别启明星形态
    Day1: 长阴线（收盘价 < 开盘价，实体较大）
    Day2: 十字星（实体很小，缺口向下）
    Day3: 长阳线（收盘价 > 开盘价，收盘价深入Day1实体）
    """
    body_ratio = params.get("body_ratio", 50.0) / 100

    open_ = df["open"]
    close = df["close"]
    high = df["high"]
    low = df["low"]

    body = _calc_body(df)
    range_ = _calc_range(df)

    # 实体占K线长度的最小比例
    min_body_ratio = body / range_.replace(0, np.nan) >= body_ratio

    # Day1: 阴线，实体较大
    day1_bear = (close.shift(2) < open_.shift(2))
    day1_big_body = min_body_ratio.shift(2) if hasattr(min_body_ratio, 'shift') else True

    # Day2: 十字星（实体很小）
    day2_body_small = body.shift(1) < range_.shift(1) * 0.1
    # Day2 有向下缺口
    day2_gap_down = (high.shift(1) < close.shift(2))

    # Day3: 阳线，实体较大，收盘价深入Day1实体
    day3_bull = close > open_
    day3_big_body = min_body_ratio
    day3_recovery = close > (open_.shift(2) + close.shift(2)) / 2

    morning_star = day1_bear & day2_body_small & day2_gap_down & day3_bull & day3_big_body & day3_recovery
    morning_star = morning_star.fillna(False)

    signal = pd.Series(0, index=df.index)
    signal[morning_star] = 1
    return signal.astype(int)
