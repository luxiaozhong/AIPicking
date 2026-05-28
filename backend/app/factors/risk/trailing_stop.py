"""
追踪止损因子
从最高价回撤N%时卖出，动态调整止损线
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "risk_trailing_stop",
    "name": "追踪止损",
    "category": "风控类",
    "description": "从持仓期间最高价回撤N%时止损卖出",
    "params": [
        {"name": "trailing_pct", "label": "回撤比例(%)", "type": "float", "default": 8.0, "min": 1.0, "max": 30.0},
    ],
    "signal_type": "sell",
}


def compute_with_position(df: pd.DataFrame, params: dict, entry_idx: pd.Series) -> pd.Series:
    """
    带持仓信息的追踪止损计算
    entry_idx: 买入日的索引Series，标记每次买入的位置
    追踪止损：持仓期间最高价 * (1 - trailing_pct/100)
    """
    trailing_pct = params.get("trailing_pct", 8.0) / 100
    close = df["close"]
    high = df["high"]

    signal = pd.Series(0, index=df.index)

    # 简化实现：对每个持仓计算最高价和止损价
    # 完整逻辑在回测引擎中实现
    # 此处提供向量化计算接口
    highest_since_entry = high.cummax()
    stop_price = highest_since_entry * (1 - trailing_pct)
    stop_signal = close < stop_price
    signal[stop_signal.fillna(False)] = -1

    return signal.astype(int)
