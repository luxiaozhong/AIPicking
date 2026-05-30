"""自然语言策略分析服务"""
import json
import re
import difflib

from .llm_service import _call_deepseek

NL_ANALYSIS_SYSTEM_PROMPT = """你是一位量化策略分析师。根据用户的自然语言描述，识别其中涉及的量化因子/指标，并给出每个因子的参考值。

任务：
1. 从用户描述中提取所有量化因子概念
2. 每个因子给出：name, category, description, params, ref_value（浮点数）, computation
3. 如果用户描述的是交易思路（如"底部放量"），将其映射为可计算的因子组合
4. ref_value 反映用户描述的"理想状态"数值

严格按照以下 JSON 格式返回，不要有任何额外文字：
{
  "summary": "对用户策略思路的概述",
  "strategy_type": "similarity",
  "indicators": [
    {
      "name": "RSI 14日",
      "category": "动量类",
      "description": "14日相对强弱指标",
      "params": {"period": 14},
      "ref_value": 30.0,
      "computation": "RSI = 100 - 100/(1 + RS)..."
    }
  ]
}"""


async def analyze_natural_language(prompt: str, model: str = "deepseek-chat") -> dict:
    """调用 DeepSeek 从自然语言中识别因子和参考值"""
    user_msg = f"""用户描述：{prompt}

请识别上述描述中涉及的量化因子/指标，并给出每个因子的参考值。"""

    response_text = await _call_deepseek(NL_ANALYSIS_SYSTEM_PROMPT, user_msg, model)
    result = _parse_nl_response(response_text)

    # 对每个指标分类：matched（已有因子）vs new（需生成）
    classified = _classify_indicators(result.get("indicators", []))
    result["classified"] = classified

    return result


def _parse_nl_response(text: str) -> dict:
    """解析 DeepSeek NL 分析响应"""
    # 尝试提取 markdown JSON 块
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if json_match:
        text = json_match.group(1).strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start: end + 1]
        result = json.loads(text)

    if "indicators" not in result:
        raise ValueError("Response missing 'indicators' key")
    if "summary" not in result:
        result["summary"] = ""

    # 确保每个指标有 ref_value
    for ind in result.get("indicators", []):
        if "ref_value" not in ind:
            ind["ref_value"] = 0.0
        if "params" not in ind:
            ind["params"] = {}

    return result


def _classify_indicators(indicators: list[dict]) -> dict:
    """将指标分类为 matched（匹配已有因子）和 new（需生成）"""
    from ..factors import FACTOR_REGISTRY

    matched = []
    new = []

    for ind in indicators:
        factor_id = _match_indicator_to_factor(ind, FACTOR_REGISTRY)
        if factor_id:
            ind["matched_factor_id"] = factor_id
            matched.append(ind)
        else:
            ind["matched_factor_id"] = None
            new.append(ind)

    return {"matched": matched, "new": new}


def _match_indicator_to_factor(indicator: dict, registry: dict):  # returns Optional[str]
    """将单个指标匹配到因子库"""
    import difflib

    name = indicator.get("name", "")
    category = indicator.get("category", "")
    name_lower = name.lower()

    best_score = 0.0
    best_id = None

    aliases_map = {
        "momentum_rsi": ["相对强弱", "rsi 14日", "rsi14", "rsi"],
        "momentum_macd": ["macd 金叉", "macd 死叉", "macd金叉", "macd死叉", "macd"],
        "momentum_kdj": ["kdj 金叉", "kdj金叉", "kdj"],
        "trend_ma_cross": ["均线金叉", "均线交叉", "金叉", "ma cross", "均线"],
        "trend_breakout": ["突破新高", "突破", "新高", "breakout"],
        "trend_ma_support": ["均线支撑", "支撑"],
        "volume_obv": ["能量潮", "obv", "on balance volume"],
        "volume_turnover": ["换手率", "换手", "turnover"],
        "volume_volume_ratio": ["量比", "放量", "量比放大", "volume ratio"],
        "pattern_hammer": ["锤子线", "锤子", "hammer"],
        "pattern_morning_star": ["启明星", "早晨之星", "morning star"],
        "pattern_engulfing": ["吞没", "看涨吞没", "engulfing"],
        "risk_fixed_stop": ["止损", "固定止损", "stop loss"],
        "risk_take_profit": ["止盈", "固定止盈", "take profit"],
        "risk_trailing_stop": ["追踪止损", "移动止损", "trailing stop", "回撤"],
    }

    for fid, meta in registry.items():
        reg_name = meta.get("name", "")
        reg_name_lower = reg_name.lower()

        # Direct substring match
        if name_lower in reg_name_lower or reg_name_lower in name_lower:
            score = 0.9
        else:
            score = difflib.SequenceMatcher(None, name_lower, reg_name_lower).ratio()

        # Check aliases
        for alias in aliases_map.get(fid, []):
            alias_score = difflib.SequenceMatcher(None, name_lower, alias.lower()).ratio()
            score = max(score, alias_score)

        if score > best_score:
            best_score = score
            best_id = fid

    if best_score >= 0.6 and best_id:
        return best_id
    return None
