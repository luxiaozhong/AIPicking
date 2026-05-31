"""基本面数据 API"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..services.financial_service import FinancialService

router = APIRouter()


@router.get("/financials/{ts_code}")
async def get_financial_reports(
    ts_code: str,
    periods: int = Query(20, ge=1, le=40, description="返回期数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单股财报历史"""
    result = await FinancialService.get_reports(db, ts_code, periods)
    return {"code": 0, "message": "ok", "data": result}


@router.get("/financials/{ts_code}/latest")
async def get_latest_financial_report(
    ts_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单股最新一期财报"""
    result = await FinancialService.get_latest_report(db, ts_code)
    return {"code": 0, "message": "ok", "data": result}


@router.get("/valuation/{ts_code}")
async def get_valuation_history(
    ts_code: str,
    days: int = Query(365, ge=1, le=730, description="数据天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单股估值历史"""
    result = await FinancialService.get_valuation_history(db, ts_code, days)
    return {"code": 0, "message": "ok", "data": result}


@router.get("/valuation/snapshot")
async def get_valuation_snapshot(
    trade_date: Optional[str] = Query(None, description="交易日 YYYYMMDD，默认最新"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取全市场最新估值快照"""
    result = await FinancialService.get_latest_valuation_snapshot(
        db, trade_date, limit
    )
    return {"code": 0, "message": "ok", "data": result}


@router.get("/financials/screen")
async def screen_stocks(
    roe_min: Optional[float] = Query(None, description="ROE 下限 (%)"),
    pe_max: Optional[float] = Query(None, description="PE 上限"),
    pb_max: Optional[float] = Query(None, description="PB 上限"),
    revenue_growth_min: Optional[float] = Query(
        None, description="营收增长率下限 (%)"
    ),
    net_profit_growth_min: Optional[float] = Query(
        None, description="净利增长率下限 (%)"
    ),
    debt_max: Optional[float] = Query(None, description="资产负债率上限 (%)"),
    market_cap_min: Optional[float] = Query(None, description="市值下限 (亿元)"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """基本面筛选"""
    result = await FinancialService.screen(
        db,
        roe_min=roe_min,
        pe_max=pe_max,
        pb_max=pb_max,
        revenue_growth_min=revenue_growth_min,
        net_profit_growth_min=net_profit_growth_min,
        debt_max=debt_max,
        market_cap_min=market_cap_min,
        limit=limit,
    )
    return {"code": 0, "message": "ok", "data": result}
