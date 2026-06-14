"""每日调仓回测 API 路由"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..middleware.auth import get_current_user
from ..schemas.rebalance import (
    RebalanceCreate,
    RebalanceResponse,
    RebalanceListResponse,
)
from ..services.rebalance_service import RebalanceService

router = APIRouter()


@router.post("", response_model=RebalanceResponse, status_code=202)
async def create_rebalance(
    data: RebalanceCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """提交调仓回测（异步执行）"""
    report = await RebalanceService.create(db, data, current_user.id)
    return _format_response(report)


@router.get("", response_model=RebalanceListResponse)
async def list_rebalances(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    strategy_id: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """查询调仓回测列表"""
    items, total = await RebalanceService.get_list(
        db, page, limit, strategy_id, status,
        current_user.id, current_user.role,
    )
    return {
        "items": [_format_response(item) for item in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{report_id}", response_model=RebalanceResponse)
async def get_rebalance(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """查询调仓回测详情"""
    report = await RebalanceService.get_detail(
        db, report_id, current_user.id, current_user.role,
    )
    return _format_response(report)


@router.delete("/{report_id}")
async def delete_rebalance(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """删除调仓回测报告"""
    await RebalanceService.delete(
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

    daily_snapshots = None
    if report.daily_snapshots:
        try:
            daily_snapshots = json.loads(report.daily_snapshots)
        except (json.JSONDecodeError, TypeError):
            daily_snapshots = []

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
        "name": report.name,
        "status": report.status,
        "start_date": report.start_date,
        "end_date": report.end_date,
        "config": config,
        "total_days": report.total_days or 0,
        "completed_days": report.completed_days or 0,
        "daily_snapshots": daily_snapshots,
        "trades": trades,
        "summary": summary,
        "error_message": report.error_message,
        "created_at": report.created_at,
        "started_at": report.started_at,
        "completed_at": report.completed_at,
    }
