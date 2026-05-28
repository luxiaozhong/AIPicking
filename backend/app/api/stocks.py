"""股票搜索 API"""

from fastapi import APIRouter, Depends, Query

from ..middleware.auth import get_current_user
from ..models.user import User
from ..services.stock_service import StockService

router = APIRouter()


@router.get("/search")
def search_stocks(
    q: str = Query(..., min_length=1, description="搜索关键词（股票代码或名称）"),
    limit: int = Query(10, ge=1, le=50, description="返回数量上限"),
    current_user: User = Depends(get_current_user),
):
    """搜索股票（按代码或名称模糊匹配）"""
    return StockService.search(q, limit)
