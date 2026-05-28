"""批量回测 API 路由"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.backtest_service import BacktestService
from ..schemas.backtest import (
    BatchBacktestCreate, BatchBacktestResponse, BatchBacktestListResponse,
)
from ..middleware.auth import get_current_user
from ..models.user import User

router = APIRouter()


@router.post("", response_model=BatchBacktestResponse, status_code=202)
async def create_batch_backtest(
    backtest: BatchBacktestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交批量回测任务（异步执行）"""
    return await BacktestService.create_batch_backtest(db, backtest, user_id=current_user.id)


@router.get("", response_model=BatchBacktestListResponse)
async def list_batch_backtests(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    strategy_id: Optional[int] = Query(None, description="策略 ID 筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取批量回测列表"""
    backtests, total = await BacktestService.get_batch_backtests(
        db, page, limit, strategy_id,
        user_id=current_user.id, user_role=current_user.role
    )

    return {
        "items": backtests,
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{backtest_id}", response_model=BatchBacktestResponse)
async def get_batch_backtest(
    backtest_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个批量回测详情（含 daily_results）"""
    return await BacktestService.get_batch_backtest(
        db, backtest_id, user_id=current_user.id, user_role=current_user.role
    )


@router.delete("/{backtest_id}", status_code=204)
async def delete_batch_backtest(
    backtest_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除批量回测报告"""
    await BacktestService.delete_batch_backtest(
        db, backtest_id, user_id=current_user.id, user_role=current_user.role
    )
