"""市场热度 API"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..services.market_heat_service import MarketHeatService

router = APIRouter()


@router.get("/overview")
async def get_overview(
    trade_date: Optional[str] = Query(None, description="交易日 YYYYMMDD，默认最新"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """市场概览 KPI（市场温度、北向资金、涨跌比、领涨板块）"""
    data = await MarketHeatService.get_overview(db, trade_date)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/sectors")
async def get_sectors(
    trade_date: Optional[str] = Query(None),
    sector_type: str = Query("industry", pattern="^(industry|concept)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """板块资金流列表（热力图数据源）"""
    data = await MarketHeatService.get_sectors(db, trade_date, sector_type)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/sectors/{sector_code}")
async def get_sector_detail(
    sector_code: str,
    trade_date: Optional[str] = Query(None),
    days: int = Query(10, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """板块详情：近 N 日资金流趋势 + 成分股 Top5"""
    data = await MarketHeatService.get_sector_detail(db, sector_code, trade_date, days)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/themes")
async def get_themes(
    trade_date: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """热门主题列表（词云数据源）"""
    data = await MarketHeatService.get_themes(db, trade_date, limit)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/themes/{theme_name}")
async def get_theme_detail(
    theme_name: str,
    trade_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """主题关联股票列表"""
    data = await MarketHeatService.get_theme_detail(db, theme_name, trade_date)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/hot-stocks")
async def get_hot_stocks(
    trade_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """热门股票分页列表"""
    data = await MarketHeatService.get_hot_stocks(db, trade_date, page, page_size)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/dragon-tiger")
async def get_dragon_tiger(
    trade_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """龙虎榜分页列表（含席位明细）"""
    data = await MarketHeatService.get_dragon_tiger(db, trade_date, page, page_size)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/northbound")
async def get_northbound(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """北向资金日趋势"""
    data = await MarketHeatService.get_northbound(db, days)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/available-dates")
async def get_available_dates(
    days: int = Query(20, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """有数据的交易日列表（日期选择器用）"""
    data = await MarketHeatService.get_available_dates(db, days)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/change-distribution")
async def get_change_distribution(
    trade_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """涨跌幅度分段统计（柱状图数据源）"""
    data = await MarketHeatService.get_change_distribution(db, trade_date)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/leading-sector-stocks")
async def get_leading_sector_stocks(
    sector_name: str = Query(..., description="板块名称"),
    trade_date: Optional[str] = Query(None),
    sort_order: str = Query("desc", description="排序：desc 涨幅靠前，asc 跌幅靠前"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """板块内个股 Top 15"""
    data = await MarketHeatService.get_leading_sector_stocks(db, sector_name, trade_date, sort_order)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/temperature-history")
async def get_temperature_history(
    days: int = Query(60, ge=1, le=365, description="查询天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """市场温度历史趋势（近 N 日）"""
    data = await MarketHeatService.get_temperature_history(db, days)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/board-temperatures")
async def get_board_temperatures(
    trade_date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD，默认最新"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """四大指数板块温度"""
    data = await MarketHeatService.get_board_temperatures(db, trade_date)
    return {"code": 0, "message": "ok", "data": data}
