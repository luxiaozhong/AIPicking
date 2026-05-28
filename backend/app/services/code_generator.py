"""
策略代码生成引擎
根据因子配置，自动生成完整的量化策略 Python 代码

新格式：生成 run(data) 函数，接受数据字典，返回推荐股票列表
"""

import json
import textwrap
from typing import Dict, List, Any


def generate_strategy_code(name: str, factor_config: Dict[str, Any]) -> str:
    """
    根据因子配置生成策略代码（新格式）

    factor_config 结构：
    {
        "buy_signals": {
            "logic": "AND",  # AND / OR
            "factors": [{"factor_id": "...", "params": {...}}]
        },
        "sell_signals": {
            "factors": [{"factor_id": "...", "params": {...}}]
        },
        "risk_factors": [
            {"factor_id": "...", "params": {...}}
        ]
    }
    """
    buy_signals = factor_config.get("buy_signals", {})
    sell_signals = factor_config.get("sell_signals", {})
    risk_factors = factor_config.get("risk_factors", [])

    buy_factors = buy_signals.get("factors", [])
    sell_factors = sell_signals.get("factors", [])
    buy_logic = buy_signals.get("logic", "AND")

    # 收集所有需要用到的因子 ID
    all_factor_ids = set()
    for f in buy_factors + sell_factors + risk_factors:
        all_factor_ids.add(f["factor_id"])

    # 生成因子 import 语句
    imports = []
    for fid in sorted(all_factor_ids):
        # 将 factor_id 转为模块路径，例如 trend_ma_cross -> factors.trend.ma_cross
        parts = fid.split("_", 1)
        if len(parts) == 2:
            module_path = f"factors.{parts[0]}.{parts[1]}"
        else:
            module_path = f"factors.{fid}"
        imports.append(f"from {module_path} import compute as {fid}_compute")

    # 生成买入信号计算代码
    buy_code_lines = []
    for i, f in enumerate(buy_factors):
        fid = f["factor_id"]
        params = f.get("params", {})
        params_str = json.dumps(params, ensure_ascii=False)
        buy_code_lines.append(
            f"        buy_{i} = {fid}_compute(df, {params_str}) == 1"
        )

    # 买入信号组合逻辑
    if buy_factors:
        if buy_logic == "AND":
            # 使用 & 操作符，保持 pandas Series 类型
            buy_parts = " & ".join([f"buy_{i}" for i in range(len(buy_factors))])
            buy_result = f"        buy_signal = ({buy_parts}).astype(int)"
        else:
            # 使用 | 操作符，保持 pandas Series 类型
            buy_parts = " | ".join([f"buy_{i}" for i in range(len(buy_factors))])
            buy_result = f"        buy_signal = ({buy_parts}).astype(int)"
    else:
        buy_result = "        buy_signal = pd.Series(0, index=df.index)"

    # 生成卖出信号计算代码
    sell_code_lines = []
    for i, f in enumerate(sell_factors):
        fid = f["factor_id"]
        params = f.get("params", {})
        params_str = json.dumps(params, ensure_ascii=False)
        sell_code_lines.append(
            f"        sell_{i} = {fid}_compute(df, {params_str}) == -1"
        )

    if sell_factors:
        # 使用 | 操作符，保持 pandas Series 类型
        sell_parts = " | ".join([f"sell_{i}" for i in range(len(sell_factors))])
        sell_result = f"        sell_signal = ({sell_parts}).astype(int)"
    else:
        sell_result = "        sell_signal = pd.Series(0, index=df.index)"

    # 计算 signal 字符串（代码生成时确定）
    signal_str = ', '.join([f['factor_id'] for f in buy_factors]) if buy_factors else '综合信号'
    
    # 组装完整代码（新格式：run(data) 函数）
    code = f'''"""
自动生成的策略代码 - {name}
注意：此文件由系统自动生成，请勿手动修改
"""

import pandas as pd
import numpy as np

{chr(10).join(imports)}


def run(data: dict) -> list[dict]:
    """
    执行策略，返回推荐股票列表

    Args:
        data: {{
            "cutoff_date": "20260525",
            "stocks": [{{"ts_code": "...", "name": "...", ...}}],
            "daily": {{"600001.SZ": [{{"trade_date": "...", ...}}]}}
        }}

    Returns:
        list[dict]: [{{"ts_code": "...", "name": "...", "score": 85.2, "signal": "..."}}, ...]
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
{chr(10).join(buy_code_lines) if buy_code_lines else "        # 无买入因子"}
{buy_result}

        # === 卖出信号因子 ===
{chr(10).join(sell_code_lines) if sell_code_lines else "        # 无卖出因子"}
{sell_result}

        # === 风控因子（触发时不推荐）===
{chr(10).join(_gen_risk_code(i, f) for i, f in enumerate(risk_factors)) if risk_factors else "        # 无风控因子"}

        # 如果买入信号满足，添加到推荐列表
        if buy_signal.iloc[-1] == 1 and not sell_signal.iloc[-1] == 1:
            # 计算得分（简单加分：信号越多分越高）
            score = 50
{chr(10).join(f"            if buy_{i}.iloc[-1] == 1: score += 10" for i in range(len(buy_factors)))}

            recommendations.append({{
                "ts_code": ts_code,
                "name": stock["name"],
                "score": score,
                "signal": "{signal_str}"
            }})

    # 按得分排序，返回前 10 只
    recommendations.sort(key=lambda x: x["score"], reverse=True)
    return recommendations[:10]
'''

    return code


def _gen_risk_code(index: int, factor: Dict[str, Any]) -> str:
    """生成风控因子代码（辅助函数）"""
    fid = factor["factor_id"]
    params = factor.get("params", {})
    params_str = json.dumps(params, ensure_ascii=False)
    return f"        risk_sell_{index} = {fid}_compute(df, {params_str}) == -1\\n        if risk_sell_{index}.iloc[-1] == 1:\\n            continue"
