"""回测相关 API 路由（新逻辑）"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.backtest_service import BacktestService
from ..schemas.backtest import (
    BacktestCreate, BacktestResponse, BacktestListResponse,
    StrategyExecuteResponse
)
from ..middleware.auth import get_current_user
from ..models.user import User

router = APIRouter()


@router.get("", response_model=BacktestListResponse)
async def list_backtests(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    strategy_id: Optional[int] = Query(None, description="策略 ID 筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    stock: Optional[str] = Query(None, description="股票代码或名称搜索"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取回测报告列表"""
    backtests, total = await BacktestService.get_backtests(
        db, page, limit, strategy_id, status, stock,
        user_id=current_user.id, user_role=current_user.role
    )

    return {
        "items": backtests,
        "total": total,
        "page": page,
        "limit": limit
    }


@router.post("", response_model=BacktestResponse, status_code=202)
async def create_backtest(
    backtest: BacktestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交回测任务（异步执行）"""
    return await BacktestService.create_backtest(db, backtest, user_id=current_user.id)


@router.get("/{backtest_id}", response_model=BacktestResponse)
async def get_backtest(
    backtest_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个回测报告详情"""
    return await BacktestService.get_backtest(
        db, backtest_id, user_id=current_user.id, user_role=current_user.role
    )


@router.delete("/{backtest_id}", status_code=204)
async def delete_backtest(
    backtest_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除回测报告"""
    await BacktestService.delete_backtest(
        db, backtest_id, user_id=current_user.id, user_role=current_user.role
    )


# ============================================================
# 策略执行接口（不属于 backtest 资源，但放在这里方便管理）
# ============================================================

@router.post(
    "/execute/{strategy_id}",
    response_model=StrategyExecuteResponse,
    tags=["strategies"]
)
async def execute_strategy(
    strategy_id: int,
    cutoff_date: Optional[str] = Query(None, description="截止日，格式 YYYYMMDD，默认为今日"),
    ts_code: Optional[str] = Query(None, description="目标股票代码。传入时只分析该股票，不传则全市场扫描"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行策略（同步，立即返回推荐结果）

    用于：
    - 全市场扫描：不传 ts_code，返回策略选出的 Top N
    - 单股查询：传 ts_code，返回该股票在当前策略下的评分
      例：POST /execute/26?ts_code=300328.SZ&cutoff_date=20260520
    """
    result = await BacktestService.execute_strategy(db, strategy_id, cutoff_date, ts_code=ts_code)
    return result
