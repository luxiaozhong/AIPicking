"""股票搜索 API"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..services.stock_service import StockService

router = APIRouter()


@router.get("/search")
async def search_stocks(
    q: str = Query(..., min_length=1, description="搜索关键词（股票代码或名称）"),
    limit: int = Query(10, ge=1, le=50, description="返回数量上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """搜索股票（按代码或名称模糊匹配）"""
    result = await StockService.search(db, q, limit)
    return {"code": 0, "message": "ok", "data": result}


@router.get("/kline")
async def get_kline(
    ts_code: str = Query(..., min_length=1, description="股票代码"),
    days: int = Query(365, ge=1, le=730, description="数据天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取股票 K 线数据"""
    result = await StockService.get_kline(db, ts_code, days)
    return {"code": 0, "message": "ok", "data": result}
