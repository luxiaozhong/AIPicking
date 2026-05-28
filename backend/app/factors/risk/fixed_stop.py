"""
固定止损因子
买入后价格跌破买入价的N%时产生卖出信号
注意：此因子需要持仓信息，在回测引擎中处理
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "risk_fixed_stop",
    "name": "固定止损",
    "category": "风控类",
    "description": "价格跌破买入价N%时止损卖出",
    "params": [
        {"name": "stop_loss_pct", "label": "止损比例(%)", "type": "float", "default": 5.0, "min": 0.5, "max": 20.0},
    ],
    "signal_type": "sell",
}


def compute(df: pd.DataFrame, params: dict, buy_price: float = None) -> pd.Series:
    """
    计算固定止损信号
    卖出信号：当前价格 < 买入价 * (1 - stop_loss_pct/100)
    注意：此因子需要外部传入买入价，通常在回测引擎中逐笔计算
    """
    stop_loss_pct = params.get("stop_loss_pct", 5.0) / 100
    close = df["close"]

    signal = pd.Series(0, index=df.index)
    if buy_price is not None:
        stop_price = buy_price * (1 - stop_loss_pct)
        signal[close < stop_price] = -1

    return signal.astype(int)


def compute_with_position(df: pd.DataFrame, params: dict, position: pd.Series) -> pd.Series:
    """
    带持仓信息的止损计算
    position: 持仓Series，非零表示持仓，值为买入价
    """
    stop_loss_pct = params.get("stop_loss_pct", 5.0) / 100
    close = df["close"]

    stop_signal = pd.Series(0, index=df.index)
    # 有持仓且价格跌破止损线
    has_position = position != 0
    stop_price = position * (1 - stop_loss_pct)
    stop_signal[has_position & (close < stop_price)] = -1

    return stop_signal.astype(int)
