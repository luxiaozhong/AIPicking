"""
AI 策略生成接口
MVP 版本：规则解析（关键词匹配）
后续可升级为 LLM 调用（腾讯混元）
"""
import re
import json
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ..database import get_db
from ..factors import list_factors, get_factor_meta

router = APIRouter()


class AIStrategyRequest(BaseModel):
    prompt: str = "用户输入的自然语言策略描述"


# 关键词 → 因子ID 映射表（规则解析用）
KEYWORD_MAP = {
    # 趋势类
    "金叉": "trend_ma_cross",
    "死叉": "trend_ma_cross",
    "均线": "trend_ma_cross",
    "支撑": "trend_ma_support",
    "突破": "trend_breakout",
    "新高": "trend_breakout",
    # 动量类
    "MACD": "momentum_macd",
    "RSI": "momentum_rsi",
    "超买": "momentum_rsi",
    "超卖": "momentum_rsi",
    "KDJ": "momentum_kdj",
    # 量能类
    "量比": "volume_ratio",
    "放量": "volume_ratio",
    "OBV": "volume_obv",
    "能量潮": "volume_obv",
    "换手": "volume_turnover",
    # 风控类
    "止损": "risk_fixed_stop",
    "止盈": "risk_take_profit",
    "追踪止损": "risk_trailing_stop",
    "回撤": "risk_trailing_stop",
}

# 参数提取正则
PARAM_PATTERNS = {
    "short_period": [r"短.?期.?(\d+)", r"(\d+).*日均线"],
    "long_period": [r"长.?期.?(\d+)", r"(\d+).*日均线"],
    "stop_loss_pct": [r"止损.?(\d+\.?\d*)\s*%"],
    "take_profit_pct": [r"止盈.?(\d+\.?\d*)\s*%"],
    "oversold": [r"超卖.?(\d+)"],
    "overbought": [r"超买.?(\d+)"],
}


def _rule_based_parse(prompt: str) -> dict:
    """
    规则解析：关键词匹配 + 正则提取参数
    返回因子配置 dict
    """
    prompt_lower = prompt.lower()
    matched_factors = set()

    # 关键词匹配
    for keyword, factor_id in KEYWORD_MAP.items():
        if keyword.lower() in prompt_lower:
            matched_factors.add(factor_id)

    # 分类因子
    buy_factors = []
    sell_factors = []
    risk_factors = []

    for fid in matched_factors:
        meta = get_factor_meta(fid)
        if meta is None:
            continue
        signal_type = meta.get("signal_type", "both")

        # 提取参数
        params = _extract_params(prompt, meta.get("params", []))

        factor_item = {"factor_id": fid, "params": params}

        if signal_type == "buy":
            buy_factors.append(factor_item)
        elif signal_type == "sell":
            sell_factors.append(factor_item)
        else:  # both: 根据关键词判断是买入还是卖出
            if any(w in prompt_lower for w in ["买入", "买", "进场", "进场"]):
                buy_factors.append(factor_item)
            elif any(w in prompt_lower for w in ["卖出", "卖", "出场", "出场"]):
                sell_factors.append(factor_item)
            else:
                # 默认同时加入买卖
                buy_factors.append(factor_item)
                sell_factors.append(factor_item)

    # 生成策略名称
    factor_names = [get_factor_meta(fid)["name"] for fid in matched_factors if get_factor_meta(fid)]
    strategy_name = "AI生成-" + "+".join([n["name"] for n in factor_names[:3]]) if factor_names else "AI生成的策略"

    return {
        "name": strategy_name,
        "description": f"由AI根据描述生成: {prompt}",
        "factor_config": {
            "buy_signals": {
                "logic": "AND",
                "factors": buy_factors
            },
            "sell_signals": {
                "factors": sell_factors
            },
            "risk_factors": risk_factors
        },
        "explanation": _gen_explanation(matched_factors, prompt)
    }


def _extract_params(prompt: str, param_defs: list) -> dict:
    """从 prompt 中提取参数"""
    params = {}
    for pdef in param_defs:
        pname = pdef["name"]
        if pname in PARAM_PATTERNS:
            for pattern in PARAM_PATTERNS[pname]:
                match = re.search(pattern, prompt)
                if match:
                    try:
                        val = float(match.group(1))
                        # 转为 int 如果参数是 int 类型
                        if pdef["type"] == "int":
                            val = int(val)
                        params[pname] = val
                    except (ValueError, IndexError):
                        pass
    return params


def _gen_explanation(matched_factors: set, prompt: str) -> str:
    """生成解释文本"""
    if not matched_factors:
        return "未能识别到有效的因子，请尝试使用更具体的描述（如'均线金叉'、'RSI超卖'等）"

    factor_names = []
    for fid in matched_factors:
        meta = get_factor_meta(fid)
        if meta:
            factor_names.append(meta["name"])

    return f"已识别到以下因子：{', '.join(factor_names)}。系统已自动配置参数，您可以在策略构建器中手动调整。"


@router.post("/ai/generate-strategy")
async def generate_strategy(
    req: AIStrategyRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    自然语言 → 策略配置
    MVP 版本使用规则解析，后续可升级为 LLM 调用
    """
    result = _rule_based_parse(req.prompt)

    return {
        "code": 0,
        "data": result
    }
