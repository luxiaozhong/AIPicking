# AI 参考个股选股策略 — 实现计划

> **For agentic workers:** 按 Task 顺序执行，每个 Task 内的 Step 顺序执行为原子操作。Steps 使用 checkbox (`- [ ]`) 语法追踪。

**目标:** 实现"参考个股选股策略"功能：用户输入个股+日期，DeepSeek 分析 K 线数据给出量化指标建议，用户确认后自动匹配/生成因子代码并组装策略。

**架构:** 异步任务+轮询模式。新增 `AIStrategyTask` 模型追踪任务状态。新增 `llm_service.py` 封装 DeepSeek API 调用。扩展 `ai.py` 路由暴露 API。新增前端页面 `/strategies/ai-builder`（两步向导 + 历史列表）。

**技术栈:** FastAPI + SQLAlchemy async + SQLite, httpx（调 DeepSeek API）, React 18 + TypeScript + Ant Design + Zustand

---

### Task 1: 配置 & 模型层

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/models/ai_task.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/.env`

- [ ] **Step 1: 添加 DeepSeek 配置到 config.py**

```python
# backend/app/config.py — 在 __init__ 里添加以下行：
self.DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
self.DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
self.DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "60"))
```

- [ ] **Step 2: 创建 AIStrategyTask 模型**

```python
# backend/app/models/ai_task.py
"""AI 分析任务模型"""
import uuid
from sqlalchemy import Column, String, Text, Integer, ForeignKey, DateTime
from .base import BaseModel, beijing_now


class AIStrategyTask(BaseModel):
    __tablename__ = "ai_strategy_tasks"

    task_id = Column(String(36), unique=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(20), default="processing", index=True)  # processing / completed / failed
    ts_code = Column(String(20), nullable=False)
    date = Column(String(10), nullable=False)
    model = Column(String(50), default="deepseek-chat")
    user_prompt = Column(Text)
    kline_summary = Column(Text)  # JSON
    result_json = Column(Text)  # JSON: AI 分析结果
    error_message = Column(Text)
    created_at = Column(DateTime, default=beijing_now)
```

- [ ] **Step 3: 注册模型到 __init__.py**

```python
# backend/app/models/__init__.py — 添加：
from .ai_task import AIStrategyTask
```

- [ ] **Step 4: 在 .env 中添加 DeepSeek 配置（实际值让用户自行填入）**

```bash
# backend/.env — 添加：
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TIMEOUT=60
```

- [ ] **Step 5: 运行迁移创建表**

```bash
cd backend && source venv/bin/activate
python -c "
from app.database import init_db, engine
import asyncio
asyncio.run(init_db())
print('Migration done')
"
```

预期：无报错，`ai_strategy_tasks` 表创建成功。

---

### Task 2: LLM 服务 (DeepSeek 集成)

**Files:**
- Create: `backend/app/services/llm_service.py`

- [ ] **Step 1: 引入 httpx 依赖**

```bash
cd backend && source venv/bin/activate && pip install httpx
```

- [ ] **Step 2: 实现 llm_service.py**

```python
# backend/app/services/llm_service.py
"""DeepSeek LLM 服务：K线分析 + 因子代码生成"""
import json
import re
import httpx
from ..config import settings

SYSTEM_PROMPT = """你是一位资深量化分析师。分析给定的股票K线数据，识别可以用来构建交易策略的量化指标。

要求：
1. 从趋势、动量、量能、形态、风控五个维度全面分析
2. 对每个指标给出具体的参数建议（基于K线数据的实际数值）
3. 说明为什么选这个指标（基于数据的实际表现）
4. 只返回 JSON 格式，不要任何其他文字

返回格式：
{
  "summary": "整体分析总结（50字以内）",
  "indicators": [
    {
      "name": "指标中文名称",
      "category": "趋势类|动量类|量能类|形态类|风控类",
      "description": "指标在策略中的作用",
      "signal_type": "buy|sell|both",
      "reason": "基于数据选择此指标的理由",
      "params": {"param_name": value},
      "code_required": false,
      "code_reference": "如果 code_required=true，提供计算逻辑的伪代码或公式参考"
    }
  ]
}"""

CODE_GEN_PROMPT = """你是一位 Python 量化开发工程师。请根据以下指标描述，生成符合指定格式的因子计算代码。

要求：
1. 必须定义 FACTOR_META 字典（id, name, category, description, params, signal_type）
2. 必须定义 compute(df, params) 函数
3. compute 返回值是 pandas Series：1=买入信号, -1=卖出信号, 0=无信号
4. 只能 import pandas 和 numpy
5. 不能使用 os, sys, exec, eval 等危险函数
6. 代码需要处理边界情况（数据不足等）
7. 只返回 Python 代码，不要任何 markdown 标记或解释文字

参考格式：
```python
import pandas as pd
import numpy as np

FACTOR_META = {
    "id": "category_slug_name",
    "name": "指标中文名",
    "category": "分类",
    "description": "描述",
    "params": [{"name": "period", "label": "周期", "type": "int", "default": 20, "min": 2, "max": 100}],
    "signal_type": "buy",
}

def compute(df: pd.DataFrame, params: dict) -> pd.Series:
    ...
```"""


async def analyze_kline(
    df_rows: list[dict],
    ts_code: str,
    stock_name: str,
    date: str,
    model: str,
    user_prompt: str = "",
) -> dict:
    """分析K线数据，返回量化指标列表"""
    df_str = _format_kline(df_rows)
    user_prompt_line = f"用户关注方向：{user_prompt}" if user_prompt else "请全面分析"

    user_msg = f"""股票：{ts_code} {stock_name}
截止日期：{date}
数据范围：{df_rows[0]['trade_date']} ~ {df_rows[-1]['trade_date']}（{len(df_rows)} 个交易日）

{user_prompt_line}

K线数据（date open high low close vol）：
{df_str}"""

    response_text = await _call_deepseek(SYSTEM_PROMPT, user_msg, model)
    return _parse_analysis_response(response_text)


async def generate_factor_code(
    name: str,
    category: str,
    description: str,
    signal_type: str,
    params: dict,
    code_reference: str,
    model: str = "deepseek-chat",
) -> str:
    """生成新因子的 Python 代码"""
    user_msg = f"""指标名称：{name}
分类：{category}
描述：{description}
信号类型：{signal_type}
参数：{json.dumps(params, ensure_ascii=False)}
计算逻辑参考：{code_reference}

请生成此因子的完整 Python 代码。"""

    code = await _call_deepseek(CODE_GEN_PROMPT, user_msg, model)
    code = _clean_code(code)
    return code


def _format_kline(df_rows: list[dict]) -> str:
    """格式化K线数据为紧凑文本"""
    lines = []
    for r in df_rows:
        lines.append(
            f"{r['trade_date']} {r['open']:.2f} {r['high']:.2f} {r['low']:.2f} {r['close']:.2f} {r.get('vol', r.get('volume', 0))}"
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
    """解析 DeepSeek 分析响应，支持重试"""
    # 尝试提取 JSON（可能被 markdown 代码块包裹）
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if json_match:
        text = json_match.group(1).strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # 尝试找到 { 开头 } 结尾
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
        result = json.loads(text)

    # 基本校验
    if "indicators" not in result:
        raise ValueError("Response missing 'indicators' key")
    if "summary" not in result:
        result["summary"] = ""

    return result


def _clean_code(code: str) -> str:
    """清理 DeepSeek 返回的代码（去除 markdown 标记）"""
    code = code.strip()
    # 去掉 ```python ... ``` 包裹
    match = re.search(r"```(?:python)?\s*([\s\S]*?)```", code)
    if match:
        code = match.group(1).strip()
    return code
```

- [ ] **Step 3: 验证模块可导入**

```bash
cd backend && source venv/bin/activate
python -c "from app.services.llm_service import analyze_kline, generate_factor_code; print('OK')"
```

---

### Task 3: AI 策略服务层 (因子匹配 + 代码生成 + 策略组装)

**Files:**
- Create: `backend/app/services/ai_strategy_service.py`

- [ ] **Step 1: 实现 ai_strategy_service.py**

```python
# backend/app/services/ai_strategy_service.py
"""AI 策略服务：因子匹配 + 新因子代码生成 + 策略组装"""
import json
import difflib
import re
import ast
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.ai_task import AIStrategyTask
from ..factors import list_factors, get_factor_meta, FACTOR_REGISTRY
from ..config import settings
from .llm_service import generate_factor_code
from .code_generator import generate_strategy_code


async def match_and_generate(
    task: AIStrategyTask,
    indicators: list[dict],
    strategy_name: str,
    buy_logic: str,
    user_id: int,
) -> dict:
    """
    匹配因子 + 生成新因子代码 + 组装策略
    返回: {strategy_id, factor_config, generated_factors, failed_factors}
    """
    result = json.loads(task.result_json or "{}")
    all_indicators = result.get("indicators", [])

    # Step 1: 匹配因子
    buy_factors = []
    sell_factors = []
    risk_factors = []
    generated = []
    failed = []

    for ind in indicators:
        fid = ind.get("matched_factor_id")
        if not fid:
            fid = _fuzzy_match(ind["name"], ind.get("category", ""))

        if fid:
            factor_item = {"factor_id": fid, "params": ind.get("params", {})}
        else:
            # 需要生成新代码
            try:
                fid = await _generate_and_save_factor(ind)
                generated.append(fid)
                factor_item = {"factor_id": fid, "params": ind.get("params", {})}
            except Exception as e:
                failed.append({"name": ind["name"], "error": str(e)})
                continue

        # 分类
        signal_type = ind.get("signal_type", "buy")
        if signal_type == "buy":
            buy_factors.append(factor_item)
        elif signal_type == "sell":
            sell_factors.append(factor_item)
        elif signal_type == "both":
            buy_factors.append(factor_item)
            sell_factors.append(factor_item)

        # 风控因子单独处理
        meta = get_factor_meta(fid)
        if meta and meta.get("category") == "风控类":
            risk_factors.append(factor_item)

    # Step 2: 组装 factor_config
    factor_config = {
        "buy_signals": {"logic": buy_logic, "factors": buy_factors},
        "sell_signals": {"factors": sell_factors},
        "risk_factors": risk_factors,
    }

    # Step 3: 生成策略代码
    code = generate_strategy_code(strategy_name or "AI参考策略", factor_config)

    return {
        "factor_config": factor_config,
        "generated_code": code,
        "generated_factors": generated,
        "failed_factors": failed,
    }


def _fuzzy_match(name: str, category: str) -> str | None:
    """模糊匹配现有因子，返回 factor_id 或 None"""
    name_lower = name.lower()
    best_ratio = 0
    best_id = None

    for fid, meta in FACTOR_REGISTRY.items():
        meta_name = meta["name"].lower()
        ratio = difflib.SequenceMatcher(None, name_lower, meta_name).ratio()
        # 同类别加权
        if meta.get("category") == category:
            ratio += 0.1
        if ratio > best_ratio:
            best_ratio = ratio
            best_id = fid

    if best_ratio >= 0.8:
        return best_id
    return None


async def _generate_and_save_factor(indicator: dict) -> str:
    """调用 DeepSeek 生成因子代码，验证并保存"""
    name = indicator["name"]
    category = indicator.get("category", "其他")
    signal_type = indicator.get("signal_type", "buy")
    params = indicator.get("params", {})
    code_reference = indicator.get("code_reference", "")

    # 生成代码
    code = await generate_factor_code(
        name=name,
        category=category,
        description=indicator.get("description", ""),
        signal_type=signal_type,
        params=params,
        code_reference=code_reference,
    )

    # 校验
    _validate_factor_code(code)

    # 生成 factor_id 和文件名
    cat_map = {
        "趋势类": "trend", "动量类": "momentum", "量能类": "volume",
        "形态类": "pattern", "风控类": "risk",
    }
    cat_dir = cat_map.get(category, "momentum")
    slug = _name_to_slug(name)
    factor_id = f"{cat_dir}_{slug}"

    # 保存文件
    factors_dir = os.path.join(os.path.dirname(__file__), "..", "factors", cat_dir)
    os.makedirs(factors_dir, exist_ok=True)
    filepath = os.path.join(factors_dir, f"{slug}.py")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code)

    # 注意：需要重启服务才能自动注册（或手动触发重新导入）
    return factor_id


def _validate_factor_code(code: str):
    """验证因子代码"""
    # AST 语法检查
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"因子代码语法错误: {e}")

    # 检查危险导入
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if node.modules:
                names = [alias.name for alias in node.names]
                for n in names:
                    if n not in ("pandas", "numpy"):
                        raise ValueError(f"禁止导入: {n}")

    # 检查必需的定义
    has_meta = False
    has_compute = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "FACTOR_META":
                    has_meta = True
        if isinstance(node, ast.FunctionDef) and node.name == "compute":
            has_compute = True

    if not has_meta:
        raise ValueError("缺少 FACTOR_META 定义")
    if not has_compute:
        raise ValueError("缺少 compute 函数定义")


def _name_to_slug(name: str) -> str:
    """中文名称转英文 slug"""
    import hashlib
    # 使用 hash 保证唯一性
    hash_part = hashlib.md5(name.encode()).hexdigest()[:8]
    # 尝试提取英文/拼音部分
    cleaned = re.sub(r"[^a-zA-Z0-9_一-鿿]", "", name)
    if re.match(r"^[a-zA-Z_]+$", cleaned):
        return cleaned.lower()
    return f"ai_{hash_part}"
```

- [ ] **Step 2: 验证模块可导入**

```bash
cd backend && source venv/bin/activate
python -c "from app.services.ai_strategy_service import match_and_generate; print('OK')"
```

---

### Task 4: AI API 路由 (重写 + 新增端点)

**Files:**
- Rewrite: `backend/app/api/ai.py`

- [ ] **Step 1: 重写 ai.py 路由**

```python
# backend/app/api/ai.py
"""
AI 策略接口
- 自然语言 → 策略配置（规则解析）
- 参考个股选股策略（DeepSeek 分析）
"""
import re
import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from ..database import get_db
from ..models.ai_task import AIStrategyTask
from ..models.user import User
from ..models.strategy import Strategy
from ..middleware.auth import get_current_user
from ..services.stock_service import StockService
from ..services.ai_strategy_service import match_and_generate
from ..services.strategy_service import save_strategy_from_ai
from ..factors import list_factors, get_factor_meta

router = APIRouter()


# === 自然语言解析（保留原功能） ===

class AIStrategyRequest(BaseModel):
    prompt: str = "用户输入的自然语言策略描述"


KEYWORD_MAP = {
    "金叉": "trend_ma_cross", "死叉": "trend_ma_cross", "均线": "trend_ma_cross",
    "支撑": "trend_ma_support", "突破": "trend_breakout", "新高": "trend_breakout",
    "MACD": "momentum_macd", "RSI": "momentum_rsi", "超买": "momentum_rsi",
    "超卖": "momentum_rsi", "KDJ": "momentum_kdj",
    "量比": "volume_ratio", "放量": "volume_ratio", "OBV": "volume_obv",
    "能量潮": "volume_obv", "换手": "volume_turnover",
    "止损": "risk_fixed_stop", "止盈": "risk_take_profit",
    "追踪止损": "risk_trailing_stop", "回撤": "risk_trailing_stop",
}

PARAM_PATTERNS = {
    "short_period": [r"短.?期.?(\d+)", r"(\d+).*日均线"],
    "long_period": [r"长.?期.?(\d+)", r"(\d+).*日均线"],
    "stop_loss_pct": [r"止损.?(\d+\.?\d*)\s*%"],
    "take_profit_pct": [r"止盈.?(\d+\.?\d*)\s*%"],
    "oversold": [r"超卖.?(\d+)"],
    "overbought": [r"超买.?(\d+)"],
}


def _rule_based_parse(prompt: str) -> dict:
    prompt_lower = prompt.lower()
    matched_factors = set()
    for keyword, factor_id in KEYWORD_MAP.items():
        if keyword.lower() in prompt_lower:
            matched_factors.add(factor_id)

    buy_factors, sell_factors, risk_factors = [], [], []
    for fid in matched_factors:
        meta = get_factor_meta(fid)
        if meta is None:
            continue
        signal_type = meta.get("signal_type", "both")
        params = _extract_params(prompt, meta.get("params", []))
        factor_item = {"factor_id": fid, "params": params}

        if signal_type == "buy":
            buy_factors.append(factor_item)
        elif signal_type == "sell":
            sell_factors.append(factor_item)
        else:
            if any(w in prompt_lower for w in ["买入", "买", "进场"]):
                buy_factors.append(factor_item)
            elif any(w in prompt_lower for w in ["卖出", "卖", "出场"]):
                sell_factors.append(factor_item)
            else:
                buy_factors.append(factor_item)
                sell_factors.append(factor_item)

    factor_names = [get_factor_meta(fid)["name"] for fid in matched_factors if get_factor_meta(fid)]
    strategy_name = "AI生成-" + "+".join([n["name"] for n in factor_names[:3]]) if factor_names else "AI生成的策略"

    return {
        "name": strategy_name,
        "description": f"由AI根据描述生成: {prompt}",
        "factor_config": {
            "buy_signals": {"logic": "AND", "factors": buy_factors},
            "sell_signals": {"factors": sell_factors},
            "risk_factors": risk_factors,
        },
        "explanation": _gen_explanation(matched_factors, prompt),
    }


def _extract_params(prompt: str, param_defs: list) -> dict:
    params = {}
    for pdef in param_defs:
        pname = pdef["name"]
        if pname in PARAM_PATTERNS:
            for pattern in PARAM_PATTERNS[pname]:
                match = re.search(pattern, prompt)
                if match:
                    try:
                        val = float(match.group(1))
                        if pdef["type"] == "int":
                            val = int(val)
                        params[pname] = val
                    except (ValueError, IndexError):
                        pass
    return params


def _gen_explanation(matched_factors: set, prompt: str) -> str:
    if not matched_factors:
        return "未能识别到有效的因子，请尝试使用更具体的描述（如'均线金叉'、'RSI超卖'等）"
    factor_names = []
    for fid in matched_factors:
        meta = get_factor_meta(fid)
        if meta:
            factor_names.append(meta["name"])
    return f"已识别到以下因子：{', '.join(factor_names)}。系统已自动配置参数，您可以在策略构建器中手动调整。"


@router.post("/ai/generate-strategy")
async def generate_strategy(req: AIStrategyRequest, db: AsyncSession = Depends(get_db)):
    result = _rule_based_parse(req.prompt)
    return {"code": 0, "data": result}


# === 参考个股选股策略（DeepSeek 分析） ===

class AnalyzeStockRequest(BaseModel):
    ts_code: str
    date: str  # YYYY-MM-DD
    model: str = "deepseek-chat"
    prompt: str = ""


class ConfirmStrategyRequest(BaseModel):
    task_id: str
    strategy_name: str = ""
    indicators: list[dict]
    buy_logic: str = "AND"


@router.post("/ai/analyze-stock")
async def analyze_stock(
    req: AnalyzeStockRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交 AI 分析任务（股票K线 → DeepSeek 分析指标）"""
    # 去重：同用户+同股票+同日期 1 分钟内
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(minutes=1)
    existing = await db.execute(
        select(AIStrategyTask).where(
            AIStrategyTask.user_id == current_user.id,
            AIStrategyTask.ts_code == req.ts_code,
            AIStrategyTask.date == req.date,
            AIStrategyTask.created_at >= cutoff,
        )
    )
    if existing.scalar_one_or_none():
        return {"code": 400, "message": "请勿重复提交，1 分钟内已有相同请求", "data": None}

    # 获取 K 线数据
    kline = await StockService.get_kline(req.ts_code, days=90)

    if not kline.get("items"):
        return {"code": 404, "message": "该股票在指定时间内无数据", "data": None}

    # 过滤到截止日期之前的数据
    items = [r for r in kline["items"] if r["trade_date"] <= req.date.replace("-", "")]
    if len(items) < 20:
        return {"code": 400, "message": "数据不足（至少需要 20 个交易日）", "data": None}

    # 创建任务
    task = AIStrategyTask(
        user_id=current_user.id,
        status="processing",
        ts_code=req.ts_code,
        date=req.date,
        model=req.model,
        user_prompt=req.prompt,
        kline_summary=json.dumps({
            "start_date": items[0]["trade_date"],
            "end_date": items[-1]["trade_date"],
            "trading_days": len(items),
        }),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # 异步执行分析
    asyncio.create_task(
        _run_analysis(task.task_id, items, kline["name"], req)
    )

    return {
        "code": 0,
        "data": {"task_id": task.task_id, "status": "processing"},
    }


async def _run_analysis(task_id: str, items: list[dict], stock_name: str, req: AnalyzeStockRequest):
    """后台执行分析任务"""
    from ..database import async_session
    from .llm_service import analyze_kline as _llm_analyze

    session = await async_session()
    try:
        task = (await session.execute(
            select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
        )).scalar_one()

        result = await _llm_analyze(
            df_rows=items,
            ts_code=req.ts_code,
            stock_name=stock_name,
            date=req.date,
            model=req.model,
            user_prompt=req.prompt,
        )

        # AI 返回后，自动匹配因子
        for ind in result.get("indicators", []):
            name = ind.get("name", "")
            category = ind.get("category", "")
            # 尝试精确匹配
            matched_id = _keyword_factor_match(name)
            if matched_id:
                ind["code_required"] = False
                ind["matched_factor_id"] = matched_id
            else:
                ind["code_required"] = True
                ind["matched_factor_id"] = None

        task.result_json = json.dumps(result, ensure_ascii=False)
        task.status = "completed"
        await session.commit()

    except Exception as e:
        try:
            task = (await session.execute(
                select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
            )).scalar_one()
            task.status = "failed"
            task.error_message = str(e)
            await session.commit()
        except Exception:
            pass
    finally:
        await session.close()


def _keyword_factor_match(name: str) -> str | None:
    """用关键词精确匹配现有因子，辅助 AI 推荐"""
    name_lower = name.lower()
    keyword_to_id = {
        "macd": "momentum_macd", "rsi": "momentum_rsi", "kdj": "momentum_kdj",
        "obv": "volume_obv", "能量潮": "volume_obv",
        "换手": "volume_turnover", "换手率": "volume_turnover",
        "量比": "volume_ratio", "放量": "volume_ratio",
        "金叉": "trend_ma_cross", "死叉": "trend_ma_cross", "均线": "trend_ma_cross",
        "支撑": "trend_ma_support", "均线支撑": "trend_ma_support",
        "突破": "trend_breakout", "新高": "trend_breakout",
        "止损": "risk_fixed_stop", "止盈": "risk_take_profit",
        "追踪止损": "risk_trailing_stop",
        "吞没": "pattern_engulfing", "锤子": "pattern_hammer",
        "早晨之星": "pattern_morning_star", "启明星": "pattern_morning_star",
    }
    for keyword, fid in keyword_to_id.items():
        if keyword in name_lower:
            return fid
    return None


@router.get("/ai/analyze-stock/{task_id}")
async def get_analysis_result(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询分析结果"""
    task = (await db.execute(
        select(AIStrategyTask).where(
            AIStrategyTask.task_id == task_id,
            AIStrategyTask.user_id == current_user.id,
        )
    )).scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status == "processing":
        return {"code": 0, "data": {"status": "processing"}}

    if task.status == "failed":
        return {"code": 0, "data": {"status": "failed", "error_message": task.error_message}}

    result = json.loads(task.result_json or "{}")
    kline_summary = json.loads(task.kline_summary or "{}")
    return {
        "code": 0,
        "data": {
            "status": "completed",
            "summary": result.get("summary", ""),
            "indicators": result.get("indicators", []),
            "kline_summary": kline_summary,
        },
    }


@router.get("/ai/analyze-stock/tasks")
async def list_tasks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    """获取当前用户的分析任务历史"""
    tasks = (await db.execute(
        select(AIStrategyTask)
        .where(AIStrategyTask.user_id == current_user.id)
        .order_by(AIStrategyTask.created_at.desc())
        .offset(offset)
        .limit(limit)
    )).scalars().all()

    return {
        "code": 0,
        "data": {
            "tasks": [
                {
                    "task_id": t.task_id,
                    "ts_code": t.ts_code,
                    "date": t.date,
                    "status": t.status,
                    "created_at": t.created_at.isoformat() if t.created_at else "",
                }
                for t in tasks
            ]
        },
    }


@router.post("/ai/confirm-strategy")
async def confirm_strategy(
    req: ConfirmStrategyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """确认指标 → 生成策略"""
    task = (await db.execute(
        select(AIStrategyTask).where(
            AIStrategyTask.task_id == req.task_id,
            AIStrategyTask.user_id == current_user.id,
        )
    )).scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    result = await match_and_generate(
        task=task,
        indicators=req.indicators,
        strategy_name=req.strategy_name,
        buy_logic=req.buy_logic,
        user_id=current_user.id,
    )

    # 保存策略到数据库
    name = req.strategy_name or f"AI参考-{task.ts_code}-{task.date}"
    strategy = Strategy(
        name=name,
        description=f"由AI基于 {task.ts_code} {task.date} 的K线数据生成",
        factor_config=json.dumps(result["factor_config"], ensure_ascii=False),
        generated_code=result["generated_code"],
        user_id=current_user.id,
        status="active",
        version=1,
    )
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)

    return {
        "code": 0,
        "data": {
            "strategy_id": strategy.id,
            "factor_config": result["factor_config"],
            "generated_factors": result["generated_factors"],
            "failed_factors": result["failed_factors"],
        },
    }
```

- [ ] **Step 2: 验证路由注册**

检查 `backend/app/main.py` 是否需要修改 — 已有 `app.include_router(ai.router, prefix="/api/v1", tags=["ai"])`，无需改动。

- [ ] **Step 3: 验证新端点可访问**

```bash
cd backend && source venv/bin/activate
python -c "
from app.api.ai import router
routes = [r.path for r in router.routes]
print('Routes:', routes)
"
```

预期输出包含：
```
Routes: ['/ai/generate-strategy', '/ai/analyze-stock', '/ai/analyze-stock/{task_id}', '/ai/analyze-stock/tasks', '/ai/confirm-strategy']
```

---

### Task 5: 前端 AI 策略服务 & Store

**Files:**
- Modify: `frontend/src/services/aiService.ts`
- Create: `frontend/src/stores/aiStrategyStore.ts`
- Create: `frontend/src/types/aiStrategy.ts`

- [ ] **Step 1: 添加 TypeScript 类型定义**

```typescript
// frontend/src/types/aiStrategy.ts
export interface AnalyzeStockRequest {
  ts_code: string;
  date: string;
  model: 'deepseek-chat' | 'deepseek-reasoner';
  prompt: string;
}

export interface IndicatorItem {
  name: string;
  category: string;
  description: string;
  signal_type: 'buy' | 'sell' | 'both';
  reason: string;
  params: Record<string, number>;
  code_required: boolean;
  matched_factor_id: string | null;
  code_reference?: string;
}

export interface AnalysisResult {
  status: 'processing' | 'completed' | 'failed';
  summary?: string;
  indicators?: IndicatorItem[];
  kline_summary?: {
    start_date: string;
    end_date: string;
    trading_days: number;
  };
  error_message?: string;
}

export interface AnalysisTask {
  task_id: string;
  ts_code: string;
  date: string;
  status: string;
  created_at: string;
}

export interface ConfirmStrategyRequest {
  task_id: string;
  strategy_name?: string;
  indicators: IndicatorItem[];
  buy_logic: 'AND' | 'OR';
}

export interface ConfirmStrategyResponse {
  strategy_id: number;
  factor_config: any;
  generated_factors: string[];
  failed_factors: { name: string; error: string }[];
}

export interface StockInfo {
  ts_code: string;
  name: string;
  symbol: string;
  market: string;
}
```

- [ ] **Step 2: 更新 AI 服务**

```typescript
// frontend/src/services/aiService.ts — 替换整个文件
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
});

export const aiService = {
  async generateStrategy(prompt: string) {
    const response = await api.post('/ai/generate-strategy', { prompt });
    return response.data;
  },

  async analyzeStock(data: { ts_code: string; date: string; model: string; prompt: string }) {
    const response = await api.post('/ai/analyze-stock', data);
    return response.data;
  },

  async getAnalysisResult(taskId: string) {
    const response = await api.get(`/ai/analyze-stock/${taskId}`);
    return response.data;
  },

  async getTasks(limit = 20, offset = 0) {
    const response = await api.get('/ai/analyze-stock/tasks', { params: { limit, offset } });
    return response.data;
  },

  async confirmStrategy(data: {
    task_id: string;
    strategy_name?: string;
    indicators: any[];
    buy_logic?: string;
  }) {
    const response = await api.post('/ai/confirm-strategy', data);
    return response.data;
  },
};
```

- [ ] **Step 3: 创建 AI Strategy Zustand Store**

```typescript
// frontend/src/stores/aiStrategyStore.ts
import { create } from 'zustand';
import { aiService } from '@/services/aiService';
import type { AnalysisResult, AnalysisTask, IndicatorItem } from '@/types/aiStrategy';

interface AIStrategyState {
  // 分析状态
  taskId: string | null;
  status: 'idle' | 'submitting' | 'polling' | 'completed' | 'failed';
  error: string | null;
  result: AnalysisResult | null;

  // 指标确认
  indicators: IndicatorItem[];
  buyLogic: 'AND' | 'OR';

  // 历史任务
  tasks: AnalysisTask[];
  tasksLoading: boolean;

  // 提交后状态
  submitting: boolean;
  generatedStrategyId: number | null;

  // Actions
  submitAnalysis: (tsCode: string, date: string, model: string, prompt: string) => Promise<void>;
  pollResult: (taskId: string) => Promise<void>;
  clearAnalysis: () => void;
  updateIndicator: (index: number, field: string, value: any) => void;
  removeIndicator: (index: number) => void;
  addIndicator: (indicator: IndicatorItem) => void;
  setBuyLogic: (logic: 'AND' | 'OR') => void;
  confirmAndGenerate: (strategyName?: string) => Promise<number>;
  fetchTasks: () => Promise<void>;
  loadTask: (taskId: string) => Promise<void>;
}

export const useAIStrategyStore = create<AIStrategyState>((set, get) => ({
  taskId: null,
  status: 'idle',
  error: null,
  result: null,
  indicators: [],
  buyLogic: 'AND',
  tasks: [],
  tasksLoading: false,
  submitting: false,
  generatedStrategyId: null,

  submitAnalysis: async (tsCode, date, model, prompt) => {
    set({ status: 'submitting', error: null });
    try {
      const res = await aiService.analyzeStock({ ts_code: tsCode, date, model, prompt });
      if (res.code === 0) {
        const taskId = res.data.task_id;
        set({ taskId, status: 'polling' });
        // 开始轮询
        get().pollResult(taskId);
      } else if (res.code === 400) {
        set({ status: 'idle', error: res.message || '请勿重复提交' });
      } else {
        set({ status: 'failed', error: res.message || '提交失败' });
      }
    } catch (e: any) {
      set({ status: 'failed', error: e.response?.data?.message || '提交分析失败' });
    }
  },

  pollResult: async (taskId: string) => {
    const poll = async () => {
      try {
        const res = await aiService.getAnalysisResult(taskId);
        if (res.code !== 0) return;

        const data = res.data;
        if (data.status === 'completed') {
          set({
            status: 'completed',
            result: data,
            indicators: data.indicators || [],
            error: null,
          });
          get().fetchTasks();
        } else if (data.status === 'failed') {
          set({ status: 'failed', error: data.error_message || '分析失败' });
          get().fetchTasks();
        } else {
          // 继续轮询
          setTimeout(poll, 2000);
        }
      } catch {
        // 轮询失败继续重试
        setTimeout(poll, 3000);
      }
    };
    setTimeout(poll, 2000);
  },

  clearAnalysis: () => set({
    taskId: null, status: 'idle', error: null, result: null, indicators: [],
  }),

  updateIndicator: (index, field, value) => {
    const indicators = [...get().indicators];
    indicators[index] = { ...indicators[index], [field]: value };
    set({ indicators });
  },

  removeIndicator: (index) => {
    set({ indicators: get().indicators.filter((_, i) => i !== index) });
  },

  addIndicator: (indicator) => {
    set({ indicators: [...get().indicators, indicator] });
  },

  setBuyLogic: (buyLogic) => set({ buyLogic }),

  confirmAndGenerate: async (strategyName) => {
    const { taskId, indicators, buyLogic } = get();
    set({ submitting: true });
    try {
      const res = await aiService.confirmStrategy({
        task_id: taskId!,
        strategy_name: strategyName,
        indicators,
        buy_logic: buyLogic,
      });

      if (res.code === 0) {
        set({ generatedStrategyId: res.data.strategy_id, submitting: false });
        return res.data.strategy_id;
      } else {
        set({ submitting: false, error: res.message || '生成策略失败' });
        throw new Error(res.message);
      }
    } catch (e: any) {
      set({ submitting: false, error: e.response?.data?.message || '生成策略失败' });
      throw e;
    }
  },

  fetchTasks: async () => {
    set({ tasksLoading: true });
    try {
      const res = await aiService.getTasks();
      if (res.code === 0) {
        set({ tasks: res.data.tasks || [] });
      }
    } catch {
      // silent fail for task list
    } finally {
      set({ tasksLoading: false });
    }
  },

  loadTask: async (taskId: string) => {
    set({ taskId, status: 'completed' });
    try {
      const res = await aiService.getAnalysisResult(taskId);
      if (res.code === 0 && res.data.status === 'completed') {
        set({
          result: res.data,
          indicators: res.data.indicators || [],
          error: null,
        });
      } else if (res.data.status === 'failed') {
        set({ status: 'failed', error: res.data.error_message });
      }
    } catch (e: any) {
      set({ status: 'failed', error: '加载任务失败' });
    }
  },
}));
```

- [ ] **Step 4: 验证编译**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

预期：无类型错误（可能有现有警告，忽略）。

---

### Task 6: 前端 AI 策略构建器页面

**Files:**
- Create: `frontend/src/pages/AIStrategyBuilder.tsx`

- [ ] **Step 1: 实现页面组件**

```typescript
// frontend/src/pages/AIStrategyBuilder.tsx
import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Card, Form, Input, DatePicker, Select, Button, Typography, Alert,
  Table, Tag, InputNumber, Space, Row, Col, Spin, List, Empty, Popconfirm, message,
} from 'antd';
import {
  RobotOutlined, PlusOutlined, DeleteOutlined,
  CheckCircleOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useAIStrategyStore } from '@/stores/aiStrategyStore';
import { aiService } from '@/services/aiService';
import type { IndicatorItem } from '@/types/aiStrategy';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const CATEGORY_OPTIONS = [
  { label: '趋势类', value: '趋势类' },
  { label: '动量类', value: '动量类' },
  { label: '量能类', value: '量能类' },
  { label: '形态类', value: '形态类' },
  { label: '风控类', value: '风控类' },
];

const SIGNAL_OPTIONS = [
  { label: '买入', value: 'buy' },
  { label: '卖出', value: 'sell' },
  { label: '双向', value: 'both' },
];

const AIStrategyBuilder: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [form] = Form.useForm();
  const [stockSearch, setStockSearch] = useState('');
  const [stockOptions, setStockOptions] = useState<{ value: string; label: string }[]>([]);
  const [searching, setSearching] = useState(false);

  const {
    status, error, result, indicators, buyLogic,
    taskId, tasks, tasksLoading, submitting,
    submitAnalysis, updateIndicator, removeIndicator, addIndicator,
    setBuyLogic, confirmAndGenerate, fetchTasks, loadTask, clearAnalysis,
  } = useAIStrategyStore();

  const [addingNew, setAddingNew] = useState(false);
  const [newIndicatorForm] = Form.useForm();

  useEffect(() => {
    fetchTasks();
  }, []);

  // URL ?task_id=xxx
  useEffect(() => {
    const tid = searchParams.get('task_id');
    if (tid) {
      loadTask(tid);
    }
  }, [searchParams]);

  // 股票搜索
  const handleStockSearch = useCallback(async (q: string) => {
    if (q.length < 1) return;
    setSearching(true);
    try {
      const data = (await import('@/services/stockService')).default;
      const res = await data.search(q);
      const items = res.data?.items || res.items || [];
      setStockOptions(items.map((s: any) => ({
        value: s.ts_code,
        label: `${s.ts_code} ${s.name}`,
      })));
    } catch {
      // ignore
    } finally {
      setSearching(false);
    }
  }, []);

  // 提交分析
  const handleSubmit = async (values: any) => {
    await submitAnalysis(
      values.ts_code,
      values.date.format('YYYY-MM-DD'),
      values.model,
      values.prompt || '',
    );
  };

  // 确认生成
  const handleConfirm = async () => {
    try {
      const strategyId = await confirmAndGenerate(form.getFieldValue('strategy_name'));
      message.success('策略生成成功！');
      navigate(`/strategies/${strategyId}`);
    } catch {
      message.error('生成策略失败');
    }
  };

  // 添加新指标
  const handleAddIndicator = () => {
    const values = newIndicatorForm.getFieldsValue();
    const newInd: IndicatorItem = {
      name: values.name,
      category: values.category || '动量类',
      description: values.description || '',
      signal_type: values.signal_type || 'buy',
      reason: '用户手动添加',
      params: values.params || {},
      code_required: true,
      matched_factor_id: null,
    };
    addIndicator(newInd);
    newIndicatorForm.resetFields();
    setAddingNew(false);
  };

  // 指标表格列
  const columns = [
    {
      title: '选择',
      width: 50,
      render: () => <CheckCircleOutlined style={{ color: '#52c41a' }} />,
    },
    {
      title: '指标名称',
      dataIndex: 'name',
      width: 150,
    },
    {
      title: '类别',
      dataIndex: 'category',
      width: 80,
      render: (v: string, _: any, i: number) => (
        <Select
          value={v}
          size="small"
          style={{ width: 80 }}
          options={CATEGORY_OPTIONS}
          onChange={(val) => updateIndicator(i, 'category', val)}
        />
      ),
    },
    {
      title: '信号',
      dataIndex: 'signal_type',
      width: 70,
      render: (v: string, _: any, i: number) => (
        <Select
          value={v}
          size="small"
          style={{ width: 70 }}
          options={SIGNAL_OPTIONS}
          onChange={(val) => updateIndicator(i, 'signal_type', val)}
        />
      ),
    },
    {
      title: '参数',
      dataIndex: 'params',
      width: 120,
      render: (params: Record<string, number>, _: any, i: number) => (
        <Space size={4} wrap>
          {Object.entries(params || {}).map(([k, v]) => (
            <InputNumber
              key={k}
              size="small"
              style={{ width: 80 }}
              addonBefore={k}
              value={v}
              onChange={(val) => {
                const newParams = { ...params, [k]: val ?? 0 };
                updateIndicator(i, 'params', newParams);
              }}
            />
          ))}
        </Space>
      ),
    },
    {
      title: '匹配因子',
      dataIndex: 'matched_factor_id',
      width: 130,
      render: (v: string | null) => v ? <Tag color="green">{v}</Tag> : <Tag color="orange">新生成</Tag>,
    },
    {
      title: '依据',
      dataIndex: 'reason',
      ellipsis: true,
    },
    {
      title: '操作',
      width: 50,
      render: (_: any, __: any, i: number) => (
        <Button size="small" danger icon={<DeleteOutlined />} onClick={() => removeIndicator(i)} />
      ),
    },
  ];

  // 提交表单
  if (status === 'idle' || status === 'submitting' || status === 'failed') {
    return (
      <Row gutter={24}>
        <Col span={16}>
          <Card title="参考个股选股策略">
            {error && <Alert message={error} type="error" style={{ marginBottom: 16 }} closable />}
            <Form form={form} layout="vertical" onFinish={handleSubmit}>
              <Form.Item label="股票代码" name="ts_code" rules={[{ required: true, message: '请输入或搜索股票' }]}>
                <Select
                  showSearch
                  placeholder="输入股票代码或名称搜索"
                  onSearch={(v) => { setStockSearch(v); handleStockSearch(v); }}
                  options={stockOptions}
                  loading={searching}
                  filterOption={false}
                />
              </Form.Item>

              <Form.Item label="时间点" name="date" rules={[{ required: true, message: '请选择日期' }]}>
                <DatePicker style={{ width: '100%' }} placeholder="选择分析截止日期" />
              </Form.Item>

              <Form.Item label="大模型" name="model" initialValue="deepseek-chat">
                <Select
                  options={[
                    { label: 'DeepSeek Chat（快速）', value: 'deepseek-chat' },
                    { label: 'DeepSeek Reasoner（深度推理）', value: 'deepseek-reasoner' },
                  ]}
                />
              </Form.Item>

              <Form.Item label="分析提示（可选）" name="prompt">
                <TextArea rows={3} placeholder="例如：重点关注底部反转信号、偏好趋势突破类指标" />
              </Form.Item>

              <Button
                type="primary"
                htmlType="submit"
                loading={status === 'submitting'}
                icon={<RobotOutlined />}
                size="large"
                block
              >
                提交 AI 分析
              </Button>
            </Form>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="历史分析" size="small">
            {tasksLoading ? <Spin /> : tasks.length === 0 ? (
              <Empty description="暂无分析记录" />
            ) : (
              <List
                size="small"
                dataSource={tasks}
                renderItem={(t) => (
                  <List.Item
                    style={{ cursor: t.status === 'completed' ? 'pointer' : 'default' }}
                    onClick={() => t.status === 'completed' && loadTask(t.task_id)}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <span>{t.ts_code}</span>
                          <Tag color={t.status === 'completed' ? 'green' : 'red'}>{t.status}</Tag>
                        </Space>
                      }
                      description={`${t.date} · ${t.created_at?.slice(0, 16)}`}
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
      </Row>
    );
  }

  // 轮询中
  if (status === 'polling') {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <Spin size="large" />
          <Paragraph style={{ marginTop: 24 }}>
            <RobotOutlined style={{ marginRight: 8 }} />
            DeepSeek 正在分析 K 线数据...
          </Paragraph>
          <Text type="secondary">正在识别量化指标，最长可能需要 60 秒</Text>
        </div>
      </Card>
    );
  }

  // 确认指标
  return (
    <Row gutter={24}>
      <Col span={16}>
        <Card
          title="确认量化指标"
          extra={
            <Space>
              <Button onClick={clearAnalysis}>返回重新分析</Button>
              <Button
                type="primary"
                loading={submitting}
                icon={<RobotOutlined />}
                onClick={handleConfirm}
              >
                确认并生成策略
              </Button>
            </Space>
          }
        >
          {/* AI 总结 */}
          {result?.summary && (
            <Alert
              type="info"
              message="AI 分析总结"
              description={result.summary}
              style={{ marginBottom: 16 }}
            />
          )}

          {/* 买入逻辑 */}
          <Form.Item label="买入逻辑">
            <Select value={buyLogic} onChange={setBuyLogic} style={{ width: 100 }}>
              <Select.Option value="AND">AND（全部满足）</Select.Option>
              <Select.Option value="OR">OR（任一满足）</Select.Option>
            </Select>
          </Form.Item>

          {/* 策略名称 */}
          <Form.Item label="策略名称">
            <Input
              placeholder="自定义策略名称（可选）"
              onChange={(e) => form.setFieldValue('strategy_name', e.target.value)}
            />
          </Form.Item>

          {/* 指标表格 */}
          <Table
            rowKey="name"
            columns={columns}
            dataSource={indicators}
            pagination={false}
            size="small"
            scroll={{ x: 900 }}
            footer={() => (
              addingNew ? (
                <Form form={newIndicatorForm} layout="inline" onFinish={handleAddIndicator}>
                  <Form.Item name="name" rules={[{ required: true }]}>
                    <Input placeholder="指标名称" />
                  </Form.Item>
                  <Form.Item name="category" initialValue="动量类">
                    <Select options={CATEGORY_OPTIONS} style={{ width: 90 }} />
                  </Form.Item>
                  <Form.Item name="signal_type" initialValue="buy">
                    <Select options={SIGNAL_OPTIONS} style={{ width: 70 }} />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" icon={<PlusOutlined />}>添加</Button>
                  </Form.Item>
                  <Form.Item>
                    <Button onClick={() => setAddingNew(false)}>取消</Button>
                  </Form.Item>
                </Form>
              ) : (
                <Button type="dashed" icon={<PlusOutlined />} onClick={() => setAddingNew(true)} block>
                  添加指标
                </Button>
              )
            )}
          />

          {/* 生成结果 */}
          {submitting && <Spin tip="正在生成策略..." style={{ display: 'block', marginTop: 16 }} />}
        </Card>
      </Col>

      <Col span={8}>
        <Card title="历史分析" size="small">
          {tasksLoading ? <Spin /> : tasks.length === 0 ? (
            <Empty description="暂无分析记录" />
          ) : (
            <List
              size="small"
              dataSource={tasks}
              renderItem={(t) => (
                <List.Item
                  style={{ cursor: t.status === 'completed' ? 'pointer' : 'default', background: t.task_id === taskId ? '#f0f5ff' : undefined }}
                  onClick={() => t.status === 'completed' && loadTask(t.task_id)}
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <span>{t.ts_code}</span>
                        <Tag color={t.status === 'completed' ? 'green' : t.status === 'processing' ? 'blue' : 'red'}>
                          {t.status === 'completed' ? '已完成' : t.status === 'processing' ? '分析中' : '失败'}
                        </Tag>
                      </Space>
                    }
                    description={`${t.date} · ${t.created_at?.slice(0, 16)}`}
                  />
                </List.Item>
              )}
            />
          )}
        </Card>
      </Col>
    </Row>
  );
};

export default AIStrategyBuilder;
```

- [ ] **Step 2: 验证编译**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

---

### Task 7: 前端路由 & 导航入口

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/StrategyList.tsx`

- [ ] **Step 1: 添加路由到 App.tsx**

在 `App.tsx` 的 import 区域添加：
```typescript
import AIStrategyBuilder from '@/pages/AIStrategyBuilder';
```

在 `<Routes>` 内部，`/strategies/builder` 路由下方添加：
```tsx
<Route
  path="/strategies/ai-builder"
  element={
    <ProtectedRoute>
      <AIStrategyBuilder />
    </ProtectedRoute>
  }
/>
```

- [ ] **Step 2: 在 StrategyList 页面添加导航按钮**

在 `StrategyList.tsx` 的 `extra` 区域，"可视化构建"按钮旁添加：

```tsx
<Button icon={<RobotOutlined />} onClick={() => navigate('/strategies/ai-builder')}>
  AI 参考选股
</Button>
```

同时在文件顶部 import 区域添加：
```typescript
import { RobotOutlined } from '@ant-design/icons';
```

注意检查 `RobotOutlined` 是否已在 import 中，如果没有则添加。

- [ ] **Step 3: 验证编译**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

预期：编译成功，无类型错误。

---

### Task 8: 集成测试 & 手动验证

- [ ] **Step 1: 验证 `ai_strategy_service.py` 与 `api/ai.py` 的接口一致性**

`match_and_generate` 函数签名已不含 `db` 参数，确认 `confirm_strategy` 路由中对该函数的调用不传 `db`。

- [ ] **Step 3: 启动后端验证路由**

```bash
cd backend && source venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 2
curl -s http://localhost:8000/health
```

预期：`{"status": "healthy"}`

- [ ] **Step 4: 验证新增 API 端点注册**

```bash
curl -s http://localhost:8000/openapi.json | python -m json.tool | grep -E '"ai/' | head -10
```

预期：显示 `/api/v1/ai/generate-strategy`, `/api/v1/ai/analyze-stock`, `/api/v1/ai/analyze-stock/{task_id}`, `/api/v1/ai/analyze-stock/tasks`, `/api/v1/ai/confirm-strategy`

- [ ] **Step 5: 启动前端验证页面**

```bash
cd frontend && npm run dev &
sleep 3
```

访问 `http://localhost:5173/strategies/ai-builder`，应该看到表单页面。

- [ ] **Step 6: 验证导航按钮**

访问 `http://localhost:5173/strategies`，应该在页面顶部看到"AI 参考选股"按钮在"可视化构建"旁边。

---

### Task 9: 因子重新导入支持

**Files:**
- Modify: `backend/app/factors/__init__.py`

- [ ] **Step 1: 添加运行时重新加载因子的函数**

在 `factors/__init__.py` 添加一个 `reload_factors()` 函数，允许新生成的因子代码在不重启服务的情况下被注册：

```python
def reload_factors():
    """重新加载所有因子（用于 AI 生成新因子后热加载）"""
    FACTOR_REGISTRY.clear()
    FACTOR_MODULES.clear()
    for _subdir in _subdirs:
        _subdir_path = os.path.join(_factor_dir, _subdir)
        if not os.path.isdir(_subdir_path):
            continue
        for _filename in os.listdir(_subdir_path):
            if _filename.endswith(".py") and not _filename.startswith("__"):
                _module_name = f"app.factors.{_subdir}.{_filename[:-3]}"
                try:
                    _module = importlib.import_module(_module_name)
                    importlib.reload(_module)
                    if hasattr(_module, "FACTOR_META"):
                        register_factor(_module.FACTOR_META, _module)
                except Exception as e:
                    print(f"加载因子失败 {_module_name}: {e}")
```

- [ ] **Step 2: 在 `ai_strategy_service.py` 的 `_generate_and_save_factor` 中保存后调用 `reload_factors()`**

```python
from ..factors import reload_factors

# 保存代码后：
with open(filepath, "w", encoding="utf-8") as f:
    f.write(code)

# 重新加载因子注册表
reload_factors()
```

- [ ] **Step 3: 验证热加载**

```bash
cd backend && source venv/bin/activate
python -c "
from app.factors import reload_factors, list_factors
print('Before:', len(list_factors()))
reload_factors()
print('After:', len(list_factors()))
"
```
