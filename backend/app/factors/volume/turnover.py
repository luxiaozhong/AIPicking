"""
换手率因子
换手率 = 成交量 / 流通股本，反映股票活跃程度
"""
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "volume_turnover",
    "name": "换手率筛选",
    "category": "量能类",
    "description": "换手率在区间内视为活跃度合适，产生买入信号",
    "params": [
        {"name": "min_turnover", "label": "最小换手率(%)", "type": "float", "default": 2.0, "min": 0.1, "max": 20.0},
        {"name": "max_turnover", "label": "最大换手率(%)", "type": "float", "default": 15.0, "min": 1.0, "max": 50.0},
        {"name": "require_price_up", "label": "要求价格上涨", "type": "bool", "default": True},
    ],
    "signal_type": "buy",
}


def compute(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    计算换手率信号
    买入：换手率在指定区间内，且（可选）价格上涨
    注意：此处使用 volume / 10000 模拟换手率（实际应从基本面数据获取流通股本）
    """
    min_turnover = params.get("min_turnover", 2.0)
    max_turnover = params.get("max_turnover", 15.0)
    require_price_up = params.get("require_price_up", True)

    # 使用成交量模拟换手率（实际应用中应除以流通股本）
    # 这里简单用 volume / 1e6 作为模拟换手率
    vol_col = "volume" if "volume" in df.columns else "vol"
    turnover = df[vol_col] / 1e6 * 100  # 转为百分比

    in_range = (turnover >= min_turnover) & (turnover <= max_turnover)
    buy_signal = in_range
    if require_price_up:
        buy_signal = buy_signal & (df["close"] > df["close"].shift(1))

    # 首日是NaN，需要填充为False
    buy_signal = buy_signal.fillna(False)

    signal = pd.Series(0, index=df.index)
    signal[buy_signal] = 1
    return signal.astype(int)
