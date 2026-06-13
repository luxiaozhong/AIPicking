"""个股资金流 API"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..services.fund_flow_service import FundFlowService

router = APIRouter()


@router.get("/overview")
async def get_fund_flow_overview(
    trade_date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD，默认最新"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """市场总览 — 全市场 KPI + 四大指数资金流 + 资金广度"""
    data = await FundFlowService.get_overview(db, trade_date)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/history")
async def get_fund_flow_history(
    days: int = Query(30, ge=1, le=365, description="查询天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """全市场资金流历史 — 近 N 日每日合计（折线图）"""
    data = await FundFlowService.get_history(db, days)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/board-history")
async def get_board_history(
    days: int = Query(30, ge=1, le=365, description="查询天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """四大指数资金流历史 — 近 N 日分指数时间序列（面积图）"""
    data = await FundFlowService.get_board_history(db, days)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/industry")
async def get_industry_flow(
    trade_date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD，默认最新"),
    sort: str = Query("net", pattern="^(net|breadth)$", description="排序: net=净流入, breadth=广度"),
    limit: int = Query(50, ge=1, le=100, description="返回条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """行业资金流排名 — 按 industry_l1 聚合"""
    data = await FundFlowService.get_industry_flow(db, trade_date, sort, limit)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/concept")
async def get_concept_flow(
    trade_date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD，默认最新"),
    sort: str = Query("net", pattern="^(net|breadth)$", description="排序: net=净流入, breadth=广度"),
    limit: int = Query(50, ge=1, le=100, description="返回条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """题材资金流排名 — 按 concepts 展开后聚合"""
    data = await FundFlowService.get_concept_flow(db, trade_date, sort, limit)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/heatmap")
async def get_heatmap(
    days: int = Query(20, ge=5, le=60, description="查询天数"),
    sector_type: str = Query("industry", pattern="^(industry|concept)$", description="分类: industry=行业, concept=题材"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """板块资金流热力图 — 近 N 日 × 行业/题材"""
    data = await FundFlowService.get_sector_heatmap(db, days, sector_type)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/stocks")
async def get_stock_ranking(
    trade_date: Optional[str] = Query(None, description="交易日 YYYY-MM-DD，默认最新"),
    sort: str = Query("main_net", description="排序字段: main_net, main_net_asc, inflow_rate, jumbo, block, mid, small"),
    limit: int = Query(100, ge=10, le=500, description="返回条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """个股资金流排名"""
    data = await FundFlowService.get_stock_ranking(db, trade_date, sort, limit)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/stocks/{ts_code}/trend")
async def get_stock_trend(
    ts_code: str,
    days: int = Query(30, ge=5, le=365, description="查询天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """个股资金流趋势 — 近 N 日每日明细"""
    data = await FundFlowService.get_stock_trend(db, ts_code, days)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/breadth-history")
async def get_breadth_history(
    days: int = Query(30, ge=5, le=365, description="查询天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """资金广度历史 — 近 N 日每日主力净流入为正的股票占比"""
    data = await FundFlowService.get_breadth_history(db, days)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/available-dates")
async def get_available_dates(
    days: int = Query(60, ge=1, le=120, description="查询天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """有数据的交易日列表（日期选择器用）"""
    data = await FundFlowService.get_available_dates(db, days)
    return {"code": 0, "message": "ok", "data": data}
