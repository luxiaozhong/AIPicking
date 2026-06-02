"""交易模拟回测 API 路由"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..middleware.auth import get_current_user
from ..schemas.trade_sim import (
    TradeSimCreate,
    TradeSimResponse,
    TradeSimListResponse,
)
from ..services.trade_sim_service import TradeSimService
from ..factors.trade_sim_stops import StopFactorRegistry

router = APIRouter()


@router.post("/", response_model=TradeSimResponse, status_code=202)
async def create_trade_sim(
    data: TradeSimCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """提交交易模拟回测（异步执行）"""
    report = await TradeSimService.create(db, data, current_user.id)
    return _format_response(report)


@router.get("/", response_model=TradeSimListResponse)
async def list_trade_sims(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    strategy_id: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """查询交易模拟列表"""
    items, total = await TradeSimService.get_list(
        db, page, limit, strategy_id, status,
        current_user.id, current_user.role,
    )
    return {
        "items": [_format_response(item) for item in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


# IMPORTANT: GET /factors must be BEFORE GET /{report_id}
# otherwise FastAPI would match "factors" as a report_id
@router.get("/factors")
async def get_stop_factors():
    """获取可用止损止盈因子列表（供前端渲染表单）"""
    return StopFactorRegistry.get_all()


@router.get("/{report_id}", response_model=TradeSimResponse)
async def get_trade_sim(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """查询交易模拟详情（含 trades + summary）"""
    report = await TradeSimService.get_detail(
        db, report_id, current_user.id, current_user.role,
    )
    return _format_response(report)


@router.delete("/{report_id}")
async def delete_trade_sim(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """删除交易模拟报告"""
    await TradeSimService.delete(
        db, report_id, current_user.id, current_user.role,
    )
    return {"message": "已删除"}


def _format_response(report) -> dict:
    """将 ORM 对象格式化为响应 dict"""
    config = None
    if report.config:
        try:
            config = json.loads(report.config)
        except (json.JSONDecodeError, TypeError):
            config = {}

    trades = None
    if report.trades:
        try:
            trades = json.loads(report.trades)
        except (json.JSONDecodeError, TypeError):
            trades = []

    summary = None
    if report.summary:
        try:
            summary = json.loads(report.summary)
        except (json.JSONDecodeError, TypeError):
            summary = {}

    return {
        "id": report.id,
        "strategy_id": report.strategy_id,
        "strategy_name": report.strategy_name,
        "cutoff_date": str(report.cutoff_date) if report.cutoff_date else None,
        "config": config,
        "trades": trades,
        "summary": summary,
        "status": report.status,
        "error_message": report.error_message,
        "created_at": report.created_at,
        "started_at": report.started_at,
        "completed_at": report.completed_at,
    }
