"""
AI 策略接口
- 自然语言 → 策略配置（规则解析）
- 参考个股选股策略（DeepSeek 分析）
"""
import re
import json
import asyncio
from typing import Optional
from datetime import datetime, timedelta
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
from ..factors import get_factor_meta

router = APIRouter()


# ============================================================
# 自然语言解析（保留原功能）
# ============================================================

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

    factor_names = [
        get_factor_meta(fid)["name"]
        for fid in matched_factors
        if get_factor_meta(fid)
    ]
    name = (
        "AI生成-" + "+".join([n["name"] for n in factor_names[:3]])
        if factor_names
        else "AI生成的策略"
    )

    return {
        "name": name,
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
                m = re.search(pattern, prompt)
                if m:
                    try:
                        val = float(m.group(1))
                        if pdef["type"] == "int":
                            val = int(val)
                        params[pname] = val
                    except (ValueError, IndexError):
                        pass
    return params


def _gen_explanation(matched_factors: set, prompt: str) -> str:
    if not matched_factors:
        return "未能识别到有效的因子，请尝试使用更具体的描述（如'均线金叉'、'RSI超卖'等）"
    names = [
        get_factor_meta(fid)["name"]
        for fid in matched_factors
        if get_factor_meta(fid)
    ]
    return f"已识别到以下因子：{', '.join(names)}。系统已自动配置参数，您可以在策略构建器中手动调整。"


@router.post("/ai/generate-strategy")
async def generate_strategy(
    req: AIStrategyRequest, db: AsyncSession = Depends(get_db)
):
    result = _rule_based_parse(req.prompt)
    return {"code": 0, "data": result}


# ============================================================
# 参考个股选股策略（DeepSeek 分析）
# ============================================================

class AnalyzeStockRequest(BaseModel):
    ts_code: str
    date: str  # YYYY-MM-DD
    model: str = "deepseek-chat"
    prompt: str = ""


class ConfirmStrategyRequest(BaseModel):
    task_id: str
    strategy_name: str = ""
    indicators: list[dict]


@router.post("/ai/analyze-stock")
async def analyze_stock(
    req: AnalyzeStockRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交 AI 分析任务（股票K线 → DeepSeek 分析指标）"""
    # 去重
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
        return {
            "code": 400,
            "message": "请勿重复提交，1 分钟内已有相同请求",
            "data": None,
        }

    # 获取 K 线数据
    kline = await StockService.get_kline(req.ts_code, days=90)
    if not kline.get("items"):
        return {"code": 404, "message": "该股票在指定时间内无数据", "data": None}

    # 过滤到截止日期之前
    items = [
        r for r in kline["items"]
        if r["trade_date"] <= req.date.replace("-", "")
    ]
    if len(items) < 20:
        return {
            "code": 400,
            "message": "数据不足（至少需要 20 个交易日）",
            "data": None,
        }

    # 创建任务
    task = AIStrategyTask(
        user_id=current_user.id,
        status="processing",
        ts_code=req.ts_code,
        date=req.date,
        model=req.model,
        user_prompt=req.prompt,
        kline_summary=json.dumps(
            {
                "start_date": items[0]["trade_date"],
                "end_date": items[-1]["trade_date"],
                "trading_days": len(items),
            }
        ),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # 后台异步执行
    asyncio.create_task(
        _run_analysis(task.task_id, items, kline["name"], req)
    )

    return {
        "code": 0,
        "data": {"task_id": task.task_id, "status": "processing"},
    }


async def _run_analysis(
    task_id: str,
    items: list[dict],
    stock_name: str,
    req: AnalyzeStockRequest,
):
    """后台执行 DeepSeek 分析"""
    from ..database import async_session
    from ..services.llm_service import analyze_kline as _llm_analyze

    session = await async_session()
    try:
        task = (
            await session.execute(
                select(AIStrategyTask).where(
                    AIStrategyTask.task_id == task_id
                )
            )
        ).scalar_one()

        # 调用 DeepSeek
        result = await _llm_analyze(
            df_rows=items,
            ts_code=req.ts_code,
            stock_name=stock_name,
            date=req.date,
            model=req.model,
            user_prompt=req.prompt,
        )

        task.result_json = json.dumps(result, ensure_ascii=False)
        task.status = "completed"
        await session.commit()

    except Exception as e:
        import traceback
        err_msg = f"{type(e).__name__}: {e}"
        print(f"[AI Analysis ERROR] task={task_id}: {err_msg}")
        traceback.print_exc()
        try:
            task = (
                await session.execute(
                    select(AIStrategyTask).where(
                        AIStrategyTask.task_id == task_id
                    )
                )
            ).scalar_one()
            task.status = "failed"
            task.error_message = err_msg
            await session.commit()
        except Exception as inner_e:
            print(f"[AI Analysis ERROR] Failed to update task status: {inner_e}")
    finally:
        await session.close()


@router.get("/ai/analyze-stock/{task_id}")
async def get_analysis_result(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询分析结果"""
    task = (
        await db.execute(
            select(AIStrategyTask).where(
                AIStrategyTask.task_id == task_id,
                AIStrategyTask.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status == "processing":
        return {"code": 0, "data": {"status": "processing"}}

    if task.status == "failed":
        return {
            "code": 0,
            "data": {
                "status": "failed",
                "error_message": task.error_message,
            },
        }

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
    """获取当前用户的 AI 分析任务历史"""
    tasks = (
        await db.execute(
            select(AIStrategyTask)
            .where(AIStrategyTask.user_id == current_user.id)
            .order_by(AIStrategyTask.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    return {
        "code": 0,
        "data": {
            "tasks": [
                {
                    "task_id": t.task_id,
                    "ts_code": t.ts_code,
                    "date": t.date,
                    "status": t.status,
                    "created_at": t.created_at.isoformat()
                    if t.created_at
                    else "",
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
    task = (
        await db.execute(
            select(AIStrategyTask).where(
                AIStrategyTask.task_id == req.task_id,
                AIStrategyTask.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    result = await match_and_generate(
        task=task,
        indicators=req.indicators,
        strategy_name=req.strategy_name,
        buy_logic="OR",
        user_id=current_user.id,
    )

    # 保存策略
    if req.strategy_name:
        name = req.strategy_name
    else:
        from datetime import datetime
        ts = datetime.now().strftime("%H%M%S")
        name = f"AI参考-{task.ts_code}-{task.date}-{ts}"
    strategy = Strategy(
        name=name,
        description=f"由AI基于 {task.ts_code} {task.date} 的K线数据生成",
        file_path="",
        factor_config=json.dumps(
            result["factor_config"], ensure_ascii=False
        ),
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
