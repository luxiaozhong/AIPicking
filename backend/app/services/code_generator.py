"""
策略代码生成引擎
根据因子配置，自动生成完整的量化策略 Python 代码

新格式：生成 run(data) 函数，接受数据字典，返回推荐股票列表

双层因子体系：
  Tier 1 — K 线因子（compute(df, params)），从 factors/ 目录加载
  Tier 2 — 选股条件 + 评分修正（内联生成），定义在 factors/conditions.py
"""

import json
import textwrap
from typing import Dict, List, Any

from ..factors.conditions import (
    get_condition_meta,
    get_helper_code,
    get_setup_code,
)


def generate_strategy_code(name: str, factor_config: Dict[str, Any]) -> str:
    """
    根据因子配置生成策略代码

    factor_config 结构：
    {
        "selection_conditions": {           # 选股预筛选（Tier 2，可选）
            "logic": "AND",                 # AND / OR
            "conditions": [
                {"condition_id": "dt_institution", "params": {"days": 5}},
            ]
        },
        "scoring_modifiers": [              # 评分修正（Tier 2，可选）
            {"condition_id": "dt_net_buy_score", "params": {"days": 5, "max_score": 15}},
        ],
        "buy_signals": {
            "logic": "AND",
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
    selection = factor_config.get("selection_conditions", {})
    scorers = factor_config.get("scoring_modifiers", [])

    buy_factors = buy_signals.get("factors", [])
    sell_factors = sell_signals.get("factors", [])
    buy_logic = buy_signals.get("logic", "AND")
    sel_conditions = selection.get("conditions", [])
    sel_logic = selection.get("logic", "AND")

    # 收集所有 K 线因子 ID
    all_factor_ids = set()
    for f in buy_factors + sell_factors + risk_factors:
        all_factor_ids.add(f["factor_id"])

    # ── 生成 K 线因子 import ──
    imports = []
    for fid in sorted(all_factor_ids):
        parts = fid.split("_", 1)
        if len(parts) == 2:
            module_path = f"factors.{parts[0]}.{parts[1]}"
        else:
            module_path = f"factors.{fid}"
        imports.append(f"from {module_path} import compute as {fid}_compute")

    # ── 生成买入信号代码 ──
    buy_code_lines = []
    for i, f in enumerate(buy_factors):
        fid = f["factor_id"]
        params = f.get("params", {})
        params_str = json.dumps(params, ensure_ascii=False)
        buy_code_lines.append(
            f"        buy_{i} = {fid}_compute(df, {params_str}) == 1"
        )

    if buy_factors:
        if buy_logic == "AND":
            buy_parts = " & ".join([f"buy_{i}" for i in range(len(buy_factors))])
            buy_result = f"        buy_signal = ({buy_parts}).astype(int)"
        else:
            buy_parts = " | ".join([f"buy_{i}" for i in range(len(buy_factors))])
            buy_result = f"        buy_signal = ({buy_parts}).astype(int)"
    else:
        buy_result = "        buy_signal = pd.Series(0, index=df.index)"

    # ── 生成卖出信号代码 ──
    sell_code_lines = []
    for i, f in enumerate(sell_factors):
        fid = f["factor_id"]
        params = f.get("params", {})
        params_str = json.dumps(params, ensure_ascii=False)
        sell_code_lines.append(
            f"        sell_{i} = {fid}_compute(df, {params_str}) == -1"
        )

    if sell_factors:
        sell_parts = " | ".join([f"sell_{i}" for i in range(len(sell_factors))])
        sell_result = f"        sell_signal = ({sell_parts}).astype(int)"
    else:
        sell_result = "        sell_signal = pd.Series(0, index=df.index)"

    # ── 生成选股条件代码（Tier 2 pre_filter）──
    sel_check_lines = _gen_selection_checks(sel_conditions, sel_logic)

    # ── 生成评分修正代码（Tier 2 score_modifier）──
    score_lines = _gen_scoring_modifiers(scorers)

    # ── 是否使用了 Tier 2 条件 ──
    has_tier2 = bool(sel_conditions or scorers)

    signal_str = ', '.join([f['factor_id'] for f in buy_factors]) if buy_factors else '综合信号'

    # ═══════════════════════════════════════════════════════════
    # 组装完整代码
    # ═══════════════════════════════════════════════════════════
    code = f'''"""
自动生成的策略代码 - {name}
注意：此文件由系统自动生成，请勿手动修改
"""

import pandas as pd
import numpy as np

{chr(10).join(imports)}
'''

    # Tier 2 helper functions
    if has_tier2:
        code += get_helper_code() + "\n"

    code += f'''
def run(data: dict) -> list[dict]:
    """
    执行策略，返回推荐股票列表

    Args:
        data: {{
            "cutoff_date": "20260525",
            "stocks": [{{"ts_code": "...", "name": "...", ...}}],
            "daily": {{"600001.SZ": [{{"trade_date": "...", ...}}]}},
            "daily_sector_flow": [...],
            "hot_stocks": [...],
            "dragon_tiger": [...],
            "dragon_tiger_seats": [...],
        }}

    Returns:
        list[dict]: [{{"ts_code": "...", "name": "...", "score": 85.2, "signal": "..."}}, ...]
    """
    cutoff_date = data["cutoff_date"]
    stocks = data["stocks"]
    daily = data["daily"]
'''

    # Tier 2 setup code (build indexes before the loop)
    if has_tier2:
        code += get_setup_code() + "\n"
    else:
        code += "\n"

    code += '''    recommendations = []

    for stock in stocks:
        ts_code = stock["ts_code"]

        # 获取该股票的日线数据
        if ts_code not in daily:
            continue

        df = pd.DataFrame(daily[ts_code])
        if len(df) == 0:
            continue

'''

    # Selection condition checks (pre-filter)
    if sel_check_lines:
        code += "        # === 选股条件（预筛选）===\n"
        code += sel_check_lines + "\n"

    # Buy signals
    code += "        # === 买入信号因子 ===\n"
    code += (chr(10).join(buy_code_lines) if buy_code_lines else "        # 无买入因子") + "\n"
    code += buy_result + "\n\n"

    # Sell signals
    code += "        # === 卖出信号因子 ===\n"
    code += (chr(10).join(sell_code_lines) if sell_code_lines else "        # 无卖出因子") + "\n"
    code += sell_result + "\n\n"

    # Risk factors
    code += "        # === 风控因子（触发时不推荐）===\n"
    if risk_factors:
        for i, f in enumerate(risk_factors):
            code += _gen_risk_code(i, f) + "\n"
    else:
        code += "        # 无风控因子\n"
    code += "\n"

    # Main recommendation logic
    code += '''        # 如果买入信号满足，添加到推荐列表
        if buy_signal.iloc[-1] == 1 and not sell_signal.iloc[-1] == 1:
            # 计算得分（简单加分：信号越多分越高）
            score = 50
'''

    # K-line factor scoring
    for i in range(len(buy_factors)):
        code += f"            if buy_{i}.iloc[-1] == 1: score += 10\n"

    # Tier 2 score modifiers
    if score_lines:
        code += "\n            # === 评分修正 ===\n"
        code += score_lines

    code += f'''
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


def _gen_selection_checks(conditions: List[Dict], logic: str) -> str:
    """生成选股条件检查代码（pre_filter）"""
    if not conditions:
        return ""

    check_blocks = []
    for idx, cond in enumerate(conditions):
        meta = get_condition_meta(cond["condition_id"])
        if not meta:
            continue
        params = cond.get("params", {})
        template = meta.get("check", "")
        if not template:
            continue

        # 填充参数模板
        filled = template
        filled = filled.replace("{idx}", str(idx))
        filled = filled.replace("{ts_code}", "ts_code")
        for p_name, p_val in params.items():
            if isinstance(p_val, str):
                filled = filled.replace(f"{{{p_name}}}", p_val)
            else:
                filled = filled.replace(f"{{{p_name}}}", str(p_val))

        check_blocks.append(filled)

    if not check_blocks:
        return ""

    if logic == "AND" or len(check_blocks) == 1:
        return "\n".join(check_blocks)
    else:
        # OR logic: 任一满足即可
        # 用 flag 模式实现
        or_lines = ["        _sel_ok = False"]
        for i, block in enumerate(check_blocks):
            # 用 try-except 包裹，跳过失败的 condition
            indented = "\n".join("    " + line for line in block.split("\n"))
            # 把最后的 continue 替换为 flag 设置
            indented = indented.replace("            continue", "            pass")
            or_lines.append(f"        try:\n{indented}\n            _sel_ok = True\n        except Exception:\n            pass")
        or_lines.append("        if not _sel_ok:\n            continue")
        return "\n".join(or_lines)


def _gen_scoring_modifiers(scorers: List[Dict]) -> str:
    """生成评分修正代码（score_modifier）"""
    if not scorers:
        return ""

    lines = []
    for idx, sc in enumerate(scorers):
        meta = get_condition_meta(sc["condition_id"])
        if not meta or meta.get("type") != "score_modifier":
            continue
        params = sc.get("params", {})
        template = meta.get("score", "")
        if not template:
            continue

        filled = template
        filled = filled.replace("{idx}", str(idx))
        filled = filled.replace("{ts_code}", "ts_code")
        for p_name, p_val in params.items():
            if isinstance(p_val, str):
                filled = filled.replace(f"{{{p_name}}}", p_val)
            else:
                filled = filled.replace(f"{{{p_name}}}", str(p_val))

        lines.append(filled)

    return "\n".join(lines)


def _gen_risk_code(index: int, factor: Dict[str, Any]) -> str:
    """生成风控因子代码（辅助函数）"""
    fid = factor["factor_id"]
    params = factor.get("params", {})
    params_str = json.dumps(params, ensure_ascii=False)
    return (
        f"        risk_sell_{index} = {fid}_compute(df, {params_str}) == -1\n"
        f"        if risk_sell_{index}.iloc[-1] == 1:\n"
        f"            continue"
    )
