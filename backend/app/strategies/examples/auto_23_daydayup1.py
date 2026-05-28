"""
自动生成的策略代码 - daydayup1
注意：此文件由系统自动生成，请勿手动修改
"""

import pandas as pd
import numpy as np

from factors.momentum.macd import compute as momentum_macd_compute
from factors.pattern.morning_star import compute as pattern_morning_star_compute
from factors.volume.turnover import compute as volume_turnover_compute


def run(data: dict) -> list[dict]:
    """
    执行策略，返回推荐股票列表

    Args:
        data: {
            "cutoff_date": "20260525",
            "stocks": [{"ts_code": "...", "name": "...", ...}],
            "daily": {"600001.SZ": [{"trade_date": "...", ...}]}
        }

    Returns:
        list[dict]: [{"ts_code": "...", "name": "...", "score": 85.2, "signal": "..."}, ...]
    """
    cutoff_date = data["cutoff_date"]
    stocks = data["stocks"]
    daily = data["daily"]

    recommendations = []

    for stock in stocks:
        ts_code = stock["ts_code"]

        # 获取该股票的日线数据
        if ts_code not in daily:
            continue

        df = pd.DataFrame(daily[ts_code])
        if len(df) == 0:
            continue

        # === 买入信号因子 ===
        buy_0 = volume_turnover_compute(df, {"min_turnover": 2, "max_turnover": 20, "require_price_up": true}) == 1
        buy_1 = momentum_macd_compute(df, {"fast_period": 12, "slow_period": 26, "signal_period": 9}) == 1
        buy_2 = pattern_morning_star_compute(df, {"body_ratio": 50}) == 1
        buy_signal = (buy_0 & buy_1 & buy_2).astype(int)

        # === 卖出信号因子 ===
        # 无卖出因子
        sell_signal = pd.Series(0, index=df.index)

        # === 风控因子（触发时不推荐）===
        # 无风控因子

        # 如果买入信号满足，添加到推荐列表
        if buy_signal.iloc[-1] == 1 and not sell_signal.iloc[-1] == 1:
            # 计算得分（简单加分：信号越多分越高）
            score = 50
            if buy_0.iloc[-1] == 1: score += 10
            if buy_1.iloc[-1] == 1: score += 10
            if buy_2.iloc[-1] == 1: score += 10

            recommendations.append({
                "ts_code": ts_code,
                "name": stock["name"],
                "score": score,
                "signal": "volume_turnover, momentum_macd, pattern_morning_star"
            })

    # 按得分排序，返回前 10 只
    recommendations.sort(key=lambda x: x["score"], reverse=True)
    return recommendations[:10]
