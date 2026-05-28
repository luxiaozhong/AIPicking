"""
固定止盈因子
持仓盈利达到N%时自动卖出
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "risk_take_profit",
    "name": "固定止盈",
    "category": "风控类",
    "description": "持仓盈利达到N%时止盈卖出",
    "params": [
        {"name": "profit_pct", "label": "止盈比例(%)", "type": "float", "default": 15.0, "min": 1.0, "max": 100.0},
    ],
    "signal_type": "sell",
}


def compute_with_position(df: pd.DataFrame, params: dict, position: pd.Series) -> pd.Series:
    """
    带持仓信息的止盈计算
    position: 持仓Series，非零表示持仓，值为买入价
    """
    profit_pct = params.get("profit_pct", 15.0) / 100
    close = df["close"]

    signal = pd.Series(0, index=df.index)
    has_position = position != 0
    target_price = position * (1 + profit_pct)
    take_profit_signal = has_position & (close >= target_price)

    signal[take_profit_signal.fillna(False)] = -1
    return signal.astype(int)
