"""DeepSeek LLM 服务：K线指标提取 + 计算代码生成"""
import json
import re
import httpx
from ..config import settings

ANALYSIS_SYSTEM_PROMPT = """你是一位资深量化分析师。分析给定的股票K线数据，提取该股票在截止日期的量化指标的实际计算值。

你的任务是：
1. 尽可能多地计算各种量化指标（趋势、动量、量能、波动率、形态等维度）
2. 每个指标给出：名称、类别、计算公式描述、参数、在截止日的实际计算值
3. 指标值必须是 NUMERIC（浮点数），不能是 buy/sell 信号

严格按照以下 JSON 格式返回，不要有任何额外文字：
{
  "summary": "该股票整体特征概述",
  "indicators": [
    {
      "name": "RSI 14日",
      "category": "动量类",
      "description": "14日相对强弱指标",
      "params": {"period": 14},
      "value": 45.2,
      "computation": "RSI = 100 - 100/(1 + RS)，详细公式..."
    }
  ]
}"""

CODE_GEN_SYSTEM_PROMPT = """你是一位 Python 量化开发工程师。根据指标描述，生成计算该指标值的函数。

要求：
1. 函数名必须是 compute_value(df, params)
2. df 包含 columns: open, high, low, close, vol
3. 返回值是 float（标的最后一行的指标值），不是 Series
4. 只能 import pandas 和 numpy
5. 处理边界情况：数据不足时返回 NaN
6. 只返回 Python 代码，不要任何 markdown 标记

示例格式：
```python
import pandas as pd
import numpy as np

def compute_value(df, params):
    period = params.get("period", 14)
    if len(df) < period:
        return float('nan')
    close = df['close']
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain.iloc[-1] / max(avg_loss.iloc[-1], 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi)
```"""


async def analyze_kline(
    df_rows: list[dict],
    ts_code: str,
    stock_name: str,
    date: str,
    model: str,
    user_prompt: str = "",
) -> dict:
    """分析K线数据，提取量化指标的实际值"""
    df_str = _format_kline(df_rows)
    user_prompt_line = f"用户关注方向：{user_prompt}" if user_prompt else "请尽可能多地提取各类量化指标的实际计算值"

    user_msg = f"""股票：{ts_code} {stock_name}
截止日期：{date}
数据范围：{df_rows[0]['trade_date']} ~ {df_rows[-1]['trade_date']}（{len(df_rows)} 个交易日）
价格变化：{df_rows[0]['close']:.2f} -> {df_rows[-1]['close']:.2f}

{user_prompt_line}

K线数据（date open high low close vol）：
{df_str}"""

    response_text = await _call_deepseek(ANALYSIS_SYSTEM_PROMPT, user_msg, model)
    return _parse_analysis_response(response_text)


async def generate_indicator_code(
    name: str,
    description: str,
    params: dict,
    computation: str,
    model: str = "deepseek-chat",
) -> str:
    """生成单个指标的计算函数代码"""
    user_msg = f"""指标名称：{name}
描述：{description}
参数：{json.dumps(params, ensure_ascii=False)}
计算公式：{computation}

请生成 compute_value(df, params) 函数来计算此指标的数值。"""

    code = await _call_deepseek(CODE_GEN_SYSTEM_PROMPT, user_msg, model)
    return _clean_code(code)


def _format_kline(df_rows: list[dict]) -> str:
    """格式化K线数据为紧凑文本"""
    lines = []
    for r in df_rows:
        vol = r.get("vol", r.get("volume", 0))
        lines.append(
            f"{r['trade_date']} {r['open']:.2f} {r['high']:.2f} "
            f"{r['low']:.2f} {r['close']:.2f} {vol}"
        )
    return "\n".join(lines)


async def _call_deepseek(system_prompt: str, user_msg: str, model: str) -> str:
    """调用 DeepSeek API"""
    if not settings.DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY 未配置")

    async with httpx.AsyncClient(timeout=settings.DEEPSEEK_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.3,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _parse_analysis_response(text: str) -> dict:
    """解析 DeepSeek 分析响应"""
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if json_match:
        text = json_match.group(1).strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
        result = json.loads(text)

    if "indicators" not in result:
        raise ValueError("Response missing 'indicators' key")
    if "summary" not in result:
        result["summary"] = ""
    for ind in result.get("indicators", []):
        if "value" not in ind:
            ind["value"] = 0.0
        if "params" not in ind:
            ind["params"] = {}

    return result


def _clean_code(code: str) -> str:
    """清理 DeepSeek 返回的代码（去除 markdown 标记）"""
    code = code.strip()
    match = re.search(r"```(?:python)?\s*([\s\S]*?)```", code)
    if match:
        code = match.group(1).strip()
    return code
