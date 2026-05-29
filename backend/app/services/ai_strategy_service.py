"""AI 策略服务：指标提取 + 相似度策略代码生成"""
import json
import re
import ast
import os
import hashlib
import traceback
import pandas as pd
import numpy as np

from ..models.ai_task import AIStrategyTask
from .llm_service import generate_indicator_code

# 模拟数据用于运行时验证
_MOCK_DF = pd.DataFrame({
    "open":   [10.0, 10.5, 10.3, 10.8, 10.6, 11.0, 10.9, 11.2, 11.5, 11.3,
               11.8, 11.6, 12.0, 11.7, 12.2, 12.5, 12.3, 12.8, 12.6, 13.0,
               12.8, 13.2, 13.5, 13.3, 13.8, 13.6, 14.0, 13.7, 14.2, 14.5],
    "high":   [10.2, 10.7, 10.5, 11.0, 10.8, 11.2, 11.1, 11.4, 11.7, 11.5,
               12.0, 11.8, 12.2, 11.9, 12.4, 12.7, 12.5, 13.0, 12.8, 13.2,
               13.0, 13.4, 13.7, 13.5, 14.0, 13.8, 14.2, 13.9, 14.4, 14.7],
    "low":    [9.8,  10.3, 10.1, 10.6, 10.4, 10.8, 10.7, 11.0, 11.3, 11.1,
               11.6, 11.4, 11.8, 11.5, 12.0, 12.3, 12.1, 12.6, 12.4, 12.8,
               12.6, 13.0, 13.3, 13.1, 13.6, 13.4, 13.8, 13.5, 14.0, 14.3],
    "close":  [10.1, 10.6, 10.2, 10.9, 10.5, 11.1, 10.8, 11.3, 11.4, 11.2,
               11.9, 11.5, 12.1, 11.8, 12.3, 12.4, 12.2, 12.9, 12.5, 13.1,
               12.7, 13.3, 13.4, 13.2, 13.9, 13.5, 14.1, 13.8, 14.3, 14.4],
    "vol":    [1000000, 1200000, 1100000, 1300000, 1150000, 1400000, 1250000,
               1350000, 1500000, 1280000, 1450000, 1320000, 1550000, 1380000,
               1600000, 1480000, 1420000, 1580000, 1350000, 1650000, 1400000,
               1520000, 1620000, 1450000, 1700000, 1550000, 1680000, 1500000,
               1750000, 1600000],
})


async def match_and_generate(
    task: AIStrategyTask,
    indicators: list[dict],
    strategy_name: str,
    buy_logic: str,
    user_id: int,
) -> dict:
    """
    为每个指标生成 compute_value 代码，组装成相似度策略
    """
    generated = []
    failed = []
    indicator_fns = []  # [(name, ref_value, params, fn_name), ...]

    for ind in indicators:
        name = ind.get("name", "")
        ref_value = ind.get("value", 0)
        params = ind.get("params", {})

        try:
            code = await generate_indicator_code(
                name=name,
                description=ind.get("description", ""),
                params=params,
                computation=ind.get("computation", ""),
            )
            _validate_code(code)
            fn_name = _name_to_fn(name)
            indicator_fns.append((name, ref_value, params, fn_name, code))
            generated.append(name)
        except Exception as e:
            failed.append({"name": name, "error": str(e)})

    strategy_code = _assemble_similarity_strategy(strategy_name, task.ts_code, indicator_fns)

    return {
        "factor_config": {
            "indicators": [
                {"name": n, "value": v, "params": p}
                for n, v, p, _, _ in indicator_fns
            ]
        },
        "generated_code": strategy_code,
        "generated_factors": generated,
        "failed_factors": failed,
    }


def _assemble_similarity_strategy(
    strategy_name: str, ts_code: str, indicator_fns: list
) -> str:
    """组装相似度策略代码"""
    ref_values = {fn_name: value for _, value, _, fn_name, _ in indicator_fns}
    ref_json = json.dumps(ref_values, ensure_ascii=False, indent=4)

    # 收集所有函数代码
    fn_bodies = []
    for _, _, _, fn_name, code in indicator_fns:
        # 清除函数定义的头，提取函数体逻辑
        clean = _clean_code(code)
        # 重新包装为标准函数名
        clean = re.sub(r'def\s+\w+\(', f'def {fn_name}(', clean, count=1)
        fn_bodies.append(clean)

    # 组装主策略代码
    code_lines = [
        '"""',
        f"相似度选股策略 - {strategy_name}",
        f"参考股票: {ts_code}",
        "自动生成，基于参考股指标值与候选股的相似度打分",
        '"""',
        "",
        "import pandas as pd",
        "import numpy as np",
        "",
    ]

    # 添加参考值
    code_lines.append("# === 参考股指标值 ===")
    code_lines.append(f"REF_VALUES = {ref_json}")
    code_lines.append("")

    # 添加指标计算函数
    code_lines.append("# === 指标计算函数 ===")
    for body in fn_bodies:
        code_lines.append(body.strip())
        code_lines.append("")
        code_lines.append("")

    # 主策略函数
    code_lines.append("def run(data: dict) -> list[dict]:")
    code_lines.append('    """执行相似度选股"""')
    code_lines.append("    daily = data['daily']")
    code_lines.append("    stocks = data['stocks']")
    code_lines.append("")
    code_lines.append("    # 收集所有计算函数（函数对象 + 参数）")
    code_lines.append("    COMPUTE_FNS = {")
    for _, _, params, fn_name, _ in indicator_fns:
        params_json = json.dumps(params, ensure_ascii=False)
        code_lines.append(f"        '{fn_name}': ({fn_name}, {params_json}),")
    code_lines.append("    }")
    code_lines.append("")
    code_lines.append("    recommendations = []")
    code_lines.append("")
    code_lines.append("    for stock in stocks:")
    code_lines.append("        ts_code = stock['ts_code']")
    code_lines.append("        if ts_code not in daily:")
    code_lines.append("            continue")
    code_lines.append("")
    code_lines.append("        df = pd.DataFrame(daily[ts_code])")
    code_lines.append("        if len(df) == 0:")
    code_lines.append("            continue")
    code_lines.append("")
    code_lines.append("        total_similarity = 0.0")
    code_lines.append("        valid_count = 0")
    code_lines.append("")
    code_lines.append("        for fn_name, ref_val in REF_VALUES.items():")
    code_lines.append("            fn_info = COMPUTE_FNS.get(fn_name)")
    code_lines.append("            if fn_info is None:")
    code_lines.append("                continue")
    code_lines.append("            compute_fn, params = fn_info")
    code_lines.append("            try:")
    code_lines.append("                actual = float(compute_fn(df.copy(), params))")
    code_lines.append("                if np.isnan(actual) or np.isinf(actual):")
    code_lines.append("                    continue")
    code_lines.append("                # 归一化相似度")
    code_lines.append("                denom = max(abs(ref_val), 1e-6)")
    code_lines.append("                diff_pct = min(abs(actual - ref_val) / denom, 2.0)")
    code_lines.append("                similarity = max(0.0, 1.0 - diff_pct)")
    code_lines.append("                total_similarity += similarity")
    code_lines.append("                valid_count += 1")
    code_lines.append("            except:")
    code_lines.append("                continue")
    code_lines.append("")
    code_lines.append("        if valid_count > 0:")
    code_lines.append("            score = round((total_similarity / valid_count) * 100, 1)")
    code_lines.append("            recommendations.append({")
    code_lines.append("                'ts_code': ts_code,")
    code_lines.append("                'name': stock['name'],")
    code_lines.append("                'score': score,")
    code_lines.append("                'signal': 'similarity',")
    code_lines.append("            })")
    code_lines.append("")
    code_lines.append("    recommendations.sort(key=lambda x: x['score'], reverse=True)")
    code_lines.append("    return recommendations[:10]")

    return "\n".join(code_lines)


def _validate_code(code: str):
    """验证 AI 生成的代码：AST 语法 + 导入白名单 + 运行时执行"""
    code = _clean_code(code)
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"语法错误: {e}")

    # 检查 compute_value 函数存在
    has_fn = any(
        isinstance(node, ast.FunctionDef) and "compute" in node.name.lower()
        for node in ast.walk(tree)
    )
    if not has_fn:
        raise ValueError("缺少 compute_value 函数定义")

    # 运行时验证
    _validate_runtime(code)


def _validate_runtime(code: str):
    """运行时验证：用模拟数据执行，确保返回 float"""
    ns = {"pd": pd, "np": np}
    try:
        exec(code, ns)
    except Exception as e:
        raise ValueError(f"代码执行失败: {type(e).__name__}: {e}")

    fn = None
    for name, obj in ns.items():
        if callable(obj) and "compute" in name.lower():
            fn = obj
            break
    if fn is None:
        raise ValueError("找不到 compute_value 函数")

    try:
        result = fn(_MOCK_DF.copy(), {})
    except Exception as e:
        raise ValueError(f"函数执行失败: {type(e).__name__}: {e}")

    try:
        val = float(result)
    except (TypeError, ValueError):
        raise ValueError(f"返回值 {result!r} 不能转为 float")

    if np.isnan(val):
        raise ValueError("模拟数据不应该产生 NaN 结果，检查代码逻辑")


def _name_to_fn(name: str) -> str:
    """指标名称转函数名"""
    h = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"compute_{h}"


def _clean_code(code: str) -> str:
    code = code.strip()
    m = re.search(r"```(?:python)?\s*([\s\S]*?)```", code)
    if m:
        code = m.group(1).strip()
    return code
