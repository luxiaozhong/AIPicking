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
from fastapi.responses import StreamingResponse
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
    """后台执行 DeepSeek 分析（120s 超时）"""
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

        # 调用 DeepSeek（120 秒超时）
        result = await asyncio.wait_for(
            _llm_analyze(
                df_rows=items,
                ts_code=req.ts_code,
                stock_name=stock_name,
                date=req.date,
                model=req.model,
                user_prompt=req.prompt,
            ),
            timeout=120,
        )

        task.result_json = json.dumps(result, ensure_ascii=False)
        task.status = "review"  # 指标已提取，待生成策略
        await session.commit()

    except asyncio.TimeoutError:
        print(f"[AI Analysis TIMEOUT] task={task_id}")
        try:
            task = (
                await session.execute(
                    select(AIStrategyTask).where(
                        AIStrategyTask.task_id == task_id
                    )
                )
            ).scalar_one()
            task.status = "failed"
            task.error_message = "分析超时（120 秒），请重试"
            await session.commit()
        except Exception as inner_e:
            print(f"[AI Analysis ERROR] Failed to update timeout status: {inner_e}")
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


@router.delete("/ai/analyze-stock/{task_id}")
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除分析任务"""
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

    await db.delete(task)
    await db.commit()
    return {"code": 0, "message": "已删除"}


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

    if task.status == "generating":
        progress_data = None
        try:
            raw = json.loads(task.result_json or "{}")
            progress_data = raw.get("progress")
        except Exception:
            pass
        return {"code": 0, "data": {"status": "generating", "progress": progress_data}}

    if task.status == "failed":
        return {
            "code": 0,
            "data": {
                "status": "failed",
                "error_message": task.error_message,
            },
        }

    # review（指标就绪）或 completed（策略已生成）
    result = json.loads(task.result_json or "{}")
    strategy_id = result.get("strategy_id")
    kline_summary = json.loads(task.kline_summary or "{}")
    return {
        "code": 0,
        "data": {
            "status": task.status,  # "review" 或 "completed"
            "summary": result.get("summary", ""),
            "indicators": result.get("indicators", []),
            "kline_summary": kline_summary,
            "strategy_id": strategy_id,
            "generated_factors": result.get("generated_factors", []),
            "failed_factors": result.get("failed_factors", []),
        },
    }


@router.get("/ai/analyze-stock/{task_id}/stream")
async def stream_analysis(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE 实时推送任务状态和进度"""
    # 验证任务存在且属于当前用户
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

    async def event_stream():
        seen_status = None
        seen_progress = None
        while True:
            # 每次循环刷新 DB 状态
            await db.refresh(task)
            status = task.status
            result_json = task.result_json

            # 只在状态或进度变化时推送
            progress = None
            if result_json:
                try:
                    data = json.loads(result_json)
                    progress = data.get("progress")
                except Exception:
                    pass

            # 终端状态：推送最终结果后结束
            if status in ("review", "completed", "failed"):
                if status != seen_status:
                    payload = _build_status_payload(task, status, result_json, progress)
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            # 非终端状态：状态或进度变化时推送
            if status != seen_status or (
                progress and progress != seen_progress
            ):
                payload = _build_status_payload(task, status, result_json, progress)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                seen_status = status
                seen_progress = progress

            await asyncio.sleep(2)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _build_status_payload(
    task: AIStrategyTask, status: str, result_json, progress
) -> dict:
    """构建 SSE 推送的 JSON payload"""
    payload: dict = {"status": status, "ts_code": task.ts_code, "date": task.date}

    if status == "generating" and progress:
        payload["progress"] = progress

    if status in ("review", "completed") and result_json:
        try:
            data = json.loads(result_json)
            if status == "review":
                payload["summary"] = data.get("summary", "")
                payload["indicators"] = data.get("indicators", [])
            if data.get("strategy_id"):
                payload["strategy_id"] = data["strategy_id"]
            if data.get("generated_factors"):
                payload["generated_factors"] = data["generated_factors"]
            if data.get("failed_factors"):
                payload["failed_factors"] = data["failed_factors"]
        except Exception:
            pass

    if status == "failed":
        payload["error_message"] = task.error_message

    return payload


@router.post("/ai/confirm-strategy")
async def confirm_strategy(
    req: ConfirmStrategyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """确认指标 → 后台生成策略（异步，避免 DeepSeek 调用超时）"""
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

    if task.status not in ("completed", "review"):
        return {"code": 400, "message": "分析尚未完成", "data": None}

    # 标记为生成中
    task.status = "generating"
    await db.commit()

    # 后台异步生成
    asyncio.create_task(
        _run_generation(
            task_id=req.task_id,
            indicators=req.indicators,
            strategy_name=req.strategy_name,
            user_id=current_user.id,
        )
    )

    return {
        "code": 0,
        "data": {"status": "generating"},
    }


async def _run_generation(
    task_id: str,
    indicators: list[dict],
    strategy_name: str,
    user_id: int,
):
    """后台执行策略生成（并发调用 DeepSeek，300s 超时，带进度）"""
    from ..database import async_session
    from ..services.ai_strategy_service import match_and_generate_with_progress

    session = await async_session()
    try:
        task = (
            await session.execute(
                select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
            )
        ).scalar_one()

        total = len(indicators)

        async def update_progress(completed: int):
            """将进度写入任务的 result_json"""
            task.result_json = json.dumps(
                {"progress": {"completed": completed, "total": total}},
                ensure_ascii=False,
            )
            await session.commit()

        # 300 秒超时（50+ 个指标并发生成）
        result = await asyncio.wait_for(
            match_and_generate_with_progress(
                task=task,
                indicators=indicators,
                strategy_name=strategy_name,
                buy_logic="OR",
                user_id=user_id,
                on_progress=update_progress,
            ),
            timeout=300,
        )

        # 保存策略
        if strategy_name:
            name = strategy_name
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
            user_id=user_id,
            status="active",
            version=1,
        )
        session.add(strategy)
        await session.commit()
        await session.refresh(strategy)

        # 更新任务状态
        task.status = "completed"
        task.result_json = json.dumps(
            {"strategy_id": strategy.id, "generated_factors": result["generated_factors"],
             "failed_factors": result["failed_factors"]},
            ensure_ascii=False,
        )
        await session.commit()

    except asyncio.TimeoutError:
        print(f"[Generation TIMEOUT] task={task_id}")
        try:
            task = (
                await session.execute(
                    select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
                )
            ).scalar_one()
            task.status = "failed"
            task.error_message = "策略生成超时（300 秒），请重试或减少指标数量"
            await session.commit()
        except Exception:
            pass
    except Exception as e:
        import traceback
        print(f"[Generation ERROR] task={task_id}: {e}")
        traceback.print_exc()
        try:
            task = (
                await session.execute(
                    select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
                )
            ).scalar_one()
            task.status = "failed"
            task.error_message = str(e)
            await session.commit()
        except Exception:
            pass
    finally:
        await session.close()


# ============================================================
# 自然语言策略（DeepSeek 因子识别 + 相似度策略生成）
# ============================================================

class AnalyzeNLRequest(BaseModel):
    prompt: str
    model: str = "deepseek-chat"


class ConfirmNLStrategyRequest(BaseModel):
    task_id: str
    strategy_name: str = ""
    indicators: list[dict]


@router.post("/ai/analyze-nl")
async def analyze_nl(
    req: AnalyzeNLRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交自然语言分析任务"""
    if len(req.prompt.strip()) < 5:
        return {"code": 400, "message": "请至少输入5个字符描述策略思路", "data": None}

    cutoff = datetime.now() - timedelta(minutes=1)
    existing = await db.execute(
        select(AIStrategyTask).where(
            AIStrategyTask.user_id == current_user.id,
            AIStrategyTask.task_type == "natural_language",
            AIStrategyTask.user_prompt == req.prompt.strip(),
            AIStrategyTask.created_at >= cutoff,
        )
    )
    if existing.scalar_one_or_none():
        return {
            "code": 400,
            "message": "请勿重复提交，1 分钟内已有相同请求",
            "data": None,
        }

    task = AIStrategyTask(
        user_id=current_user.id,
        status="processing",
        task_type="natural_language",
        user_prompt=req.prompt.strip(),
        model=req.model,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    asyncio.create_task(
        _run_nl_analysis(task.task_id, req.prompt.strip(), req.model)
    )

    return {
        "code": 0,
        "data": {"task_id": task.task_id, "status": "processing"},
    }


async def _run_nl_analysis(task_id: str, prompt: str, model: str):
    """后台执行自然语言 DeepSeek 分析（120s 超时）"""
    from ..database import async_session
    from ..services.ai_nl_service import analyze_natural_language as _nl_analyze

    session = await async_session()
    try:
        task = (
            await session.execute(
                select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
            )
        ).scalar_one()

        result = await asyncio.wait_for(
            _nl_analyze(prompt=prompt, model=model),
            timeout=120,
        )

        task.result_json = json.dumps(result, ensure_ascii=False)
        task.status = "review"
        await session.commit()

    except asyncio.TimeoutError:
        print(f"[NL Analysis TIMEOUT] task={task_id}")
        try:
            task = (
                await session.execute(
                    select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
                )
            ).scalar_one()
            task.status = "failed"
            task.error_message = "分析超时（120 秒），请重试"
            await session.commit()
        except Exception as inner_e:
            print(f"[NL Analysis ERROR] Failed to update timeout: {inner_e}")
    except Exception as e:
        import traceback
        err_msg = f"{type(e).__name__}: {e}"
        print(f"[NL Analysis ERROR] task={task_id}: {err_msg}")
        traceback.print_exc()
        try:
            task = (
                await session.execute(
                    select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
                )
            ).scalar_one()
            task.status = "failed"
            task.error_message = err_msg
            await session.commit()
        except Exception as inner_e:
            print(f"[NL Analysis ERROR] Failed to update task: {inner_e}")
    finally:
        await session.close()


@router.get("/ai/analyze-nl/{task_id}")
async def get_nl_analysis_result(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询 NL 分析结果"""
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

    if task.status == "generating":
        progress_data = None
        try:
            raw = json.loads(task.result_json or "{}")
            progress_data = raw.get("progress")
        except Exception:
            pass
        return {"code": 0, "data": {"status": "generating", "progress": progress_data}}

    if task.status == "failed":
        return {
            "code": 0,
            "data": {"status": "failed", "error_message": task.error_message},
        }

    result = json.loads(task.result_json or "{}")
    classified = result.get("classified", {"matched": [], "new": []})
    return {
        "code": 0,
        "data": {
            "status": task.status,
            "summary": result.get("summary", ""),
            "indicators": result.get("indicators", []),
            "classified": classified,
            "strategy_id": result.get("strategy_id"),
            "generated_factors": result.get("generated_factors", []),
            "failed_factors": result.get("failed_factors", []),
        },
    }


@router.get("/ai/analyze-nl/{task_id}/stream")
async def stream_nl_analysis(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE 实时推送 NL 任务状态和进度"""
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

    async def event_stream():
        seen_status = None
        seen_progress = None
        while True:
            await db.refresh(task)
            status = task.status
            result_json = task.result_json

            progress = None
            if result_json:
                try:
                    data = json.loads(result_json)
                    progress = data.get("progress")
                except Exception:
                    pass

            if status in ("review", "completed", "failed"):
                if status != seen_status:
                    payload = _build_nl_sse_payload(task, status, result_json, progress)
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            if status != seen_status or (progress and progress != seen_progress):
                payload = _build_nl_sse_payload(task, status, result_json, progress)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                seen_status = status
                seen_progress = progress

            await asyncio.sleep(2)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _build_nl_sse_payload(task, status, result_json, progress) -> dict:
    """构建 NL SSE 推送 payload"""
    payload: dict = {"status": status}

    if status == "generating" and progress:
        payload["progress"] = progress

    if status in ("review", "completed") and result_json:
        try:
            data = json.loads(result_json)
            if status == "review":
                payload["summary"] = data.get("summary", "")
                payload["indicators"] = data.get("indicators", [])
                payload["classified"] = data.get("classified", {})
            if data.get("strategy_id"):
                payload["strategy_id"] = data["strategy_id"]
            if data.get("generated_factors"):
                payload["generated_factors"] = data["generated_factors"]
            if data.get("failed_factors"):
                payload["failed_factors"] = data["failed_factors"]
        except Exception:
            pass

    if status == "failed":
        payload["error_message"] = task.error_message

    return payload


@router.post("/ai/confirm-nl-strategy")
async def confirm_nl_strategy(
    req: ConfirmNLStrategyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """确认 NL 因子列表 → 后台生成相似度策略"""
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

    if task.status not in ("completed", "review"):
        return {"code": 400, "message": "分析尚未完成", "data": None}

    task.status = "generating"
    await db.commit()

    asyncio.create_task(
        _run_nl_generation(
            task_id=req.task_id,
            indicators=req.indicators,
            strategy_name=req.strategy_name,
            user_id=current_user.id,
        )
    )

    return {"code": 0, "data": {"status": "generating"}}


async def _run_nl_generation(
    task_id: str,
    indicators: list[dict],
    strategy_name: str,
    user_id: int,
):
    """后台执行 NL 策略生成（300s 超时，带进度）"""
    from ..database import async_session
    from ..services.ai_strategy_service import match_and_generate_with_progress

    session = await async_session()
    try:
        task = (
            await session.execute(
                select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
            )
        ).scalar_one()

        total = len(indicators)

        async def update_progress(completed: int):
            task.result_json = json.dumps(
                {"progress": {"completed": completed, "total": total}},
                ensure_ascii=False,
            )
            await session.commit()

        result = await asyncio.wait_for(
            match_and_generate_with_progress(
                task=task,
                indicators=indicators,
                strategy_name=strategy_name,
                buy_logic="OR",
                user_id=user_id,
                on_progress=update_progress,
            ),
            timeout=300,
        )

        if strategy_name:
            name = strategy_name
        else:
            from datetime import datetime as dt
            ts = dt.now().strftime("%H%M%S")
            name = f"AI策略-{ts}"

        strategy = Strategy(
            name=name,
            description=f"由AI根据自然语言描述生成: {task.user_prompt or ''}",
            file_path="",
            factor_config=json.dumps(
                result["factor_config"], ensure_ascii=False
            ),
            generated_code=result["generated_code"],
            user_id=user_id,
            status="active",
            version=1,
        )
        session.add(strategy)
        await session.commit()
        await session.refresh(strategy)

        task.status = "completed"
        task.result_json = json.dumps(
            {
                "strategy_id": strategy.id,
                "generated_factors": result["generated_factors"],
                "failed_factors": result["failed_factors"],
            },
            ensure_ascii=False,
        )
        await session.commit()

    except asyncio.TimeoutError:
        print(f"[NL Generation TIMEOUT] task={task_id}")
        try:
            task = (
                await session.execute(
                    select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
                )
            ).scalar_one()
            task.status = "failed"
            task.error_message = "策略生成超时（300 秒），请重试或减少指标数量"
            await session.commit()
        except Exception:
            pass
    except Exception as e:
        import traceback
        print(f"[NL Generation ERROR] task={task_id}: {e}")
        traceback.print_exc()
        try:
            task = (
                await session.execute(
                    select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
                )
            ).scalar_one()
            task.status = "failed"
            task.error_message = str(e)
            await session.commit()
        except Exception:
            pass
    finally:
        await session.close()
