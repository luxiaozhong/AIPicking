"""临时观察指数 API — 手动管理 900002 成分股"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user, require_admin
from ..models.user import User
from ..services.watchlist_service import get_stocks, add_stocks, remove_stock

router = APIRouter()


class AddStocksRequest(BaseModel):
    ts_codes: list[str]


@router.get("")
async def list_watchlist(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取临时观察指数所有成分股"""
    result = await get_stocks(db)
    return {"code": 0, "message": "ok", "data": result}


@router.post("/stocks")
async def add_watchlist_stocks(
    body: AddStocksRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """批量添加股票到临时观察指数（管理员）"""
    result = await add_stocks(db, body.ts_codes)
    return {"code": 0, "message": f"已添加 {result['added']} 只股票", "data": result}


@router.delete("/stocks/{ts_code}")
async def remove_watchlist_stock(
    ts_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """从临时观察指数删除股票（管理员）"""
    result = await remove_stock(db, ts_code)
    if result["removed"]:
        return {"code": 0, "message": f"已移除 {ts_code}", "data": result}
    else:
        return {"code": 1, "message": f"未找到 {ts_code}", "data": result}
