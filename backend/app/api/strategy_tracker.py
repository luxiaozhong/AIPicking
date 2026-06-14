"""当前策略跟踪 API"""

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user_holding import UserHolding
from ..models.stock_tables import Daily

router = APIRouter()


# ── Request schemas ──────────────────────────────────────────


class HoldingItem(BaseModel):
    ts_code: str
    stock_name: str = ""
    shares: int = 0
    buy_price: float = 0.0


class SaveHoldingsRequest(BaseModel):
    strategy_id: int
    date: str  # YYYY-MM-DD
    holdings: List[HoldingItem]
    cash: float = 0.0  # 账户现金余额


# ── Response schemas ─────────────────────────────────────────


class HoldingResponse(BaseModel):
    id: int
    strategy_id: int
    date: str
    ts_code: str
    stock_name: str
    shares: int
    buy_price: float
    created_at: Optional[datetime] = None


class NavPoint(BaseModel):
    date: str
    holdings_value: float  # 持仓市值
    cash: float  # 现金
    total_value: float  # 总净值


# ── POST /holdings ───────────────────────────────────────────


@router.post("/holdings")
async def save_holdings(
    data: SaveHoldingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """保存某日持仓（先删除该日旧数据，再插入新数据）"""
    # 删除该用户、策略、日期的旧持仓
    await db.execute(
        delete(UserHolding).where(
            UserHolding.user_id == current_user.id,
            UserHolding.strategy_id == data.strategy_id,
            UserHolding.date == data.date,
        )
    )

    # 插入新持仓
    for h in data.holdings:
        if not h.ts_code:
            continue
        holding = UserHolding(
            user_id=current_user.id,
            strategy_id=data.strategy_id,
            date=data.date,
            ts_code=h.ts_code,
            stock_name=h.stock_name,
            shares=h.shares,
            buy_price=h.buy_price,
        )
        db.add(holding)

    await db.commit()
    return {"message": "保存成功", "count": len(data.holdings)}


# ── GET /holdings ────────────────────────────────────────────


@router.get("/holdings")
async def get_holdings(
    strategy_id: int = Query(..., description="策略 ID"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """查询持仓历史"""
    stmt = (
        select(UserHolding)
        .where(
            UserHolding.user_id == current_user.id,
            UserHolding.strategy_id == strategy_id,
        )
        .order_by(UserHolding.date.desc(), UserHolding.ts_code)
    )
    if start_date:
        stmt = stmt.where(UserHolding.date >= start_date)
    if end_date:
        stmt = stmt.where(UserHolding.date <= end_date)

    result = await db.execute(stmt)
    holdings = result.scalars().all()

    # 按日期分组
    grouped: dict = {}
    for h in holdings:
        if h.date not in grouped:
            grouped[h.date] = []
        grouped[h.date].append(
            {
                "id": h.id,
                "strategy_id": h.strategy_id,
                "date": h.date,
                "ts_code": h.ts_code,
                "stock_name": h.stock_name,
                "shares": h.shares,
                "buy_price": h.buy_price,
                "created_at": h.created_at,
            }
        )

    return {"items": grouped, "total_dates": len(grouped)}


# ── GET /nav ─────────────────────────────────────────────────


@router.get("/nav")
async def get_nav(
    strategy_id: int = Query(..., description="策略 ID"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """计算账户净值历史

    逻辑：
    1. 查出用户所有持仓记录，按日期分组
    2. 对每个日期，查 daily 表获取持仓股票的当日收盘价
    3. 净值 = Σ(持仓股数 × 当日收盘价) + 现金
    """
    # 查询持仓记录
    stmt = (
        select(UserHolding)
        .where(
            UserHolding.user_id == current_user.id,
            UserHolding.strategy_id == strategy_id,
        )
    )
    if start_date:
        stmt = stmt.where(UserHolding.date >= start_date)
    if end_date:
        stmt = stmt.where(UserHolding.date <= end_date)

    result = await db.execute(stmt)
    holdings = result.scalars().all()

    if not holdings:
        return {"nav": [], "message": "暂无持仓记录"}

    # 按日期分组持仓
    holdings_by_date: dict = {}
    all_ts_codes: set = set()
    for h in holdings:
        if h.date not in holdings_by_date:
            holdings_by_date[h.date] = []
        holdings_by_date[h.date].append(h)
        all_ts_codes.add(h.ts_code)

    # 获取所有涉及股票的收盘价（一次查询）
    dates = sorted(holdings_by_date.keys())
    price_stmt = (
        select(Daily.trade_date, Daily.ts_code, Daily.close)
        .where(
            Daily.trade_date.in_(dates),
            Daily.ts_code.in_(list(all_ts_codes)),
        )
    )
    price_result = await db.execute(price_stmt)
    price_rows = price_result.all()

    # 构建价格索引: {date: {ts_code: close}}
    price_index: dict = {}
    for row in price_rows:
        d = row.trade_date
        if d not in price_index:
            price_index[d] = {}
        price_index[d][row.ts_code] = float(row.close or 0)

    # 计算每日净值
    nav_points = []
    for date in dates:
        day_holdings = holdings_by_date[date]
        holdings_value = 0.0
        day_prices = price_index.get(date, {})

        for h in day_holdings:
            close_price = day_prices.get(h.ts_code, h.buy_price)
            holdings_value += h.shares * close_price

        # 现金简化：从第一条记录起累计。实际现金需要从 Save 时的 cash 字段获取。
        # 当前简化：cash = 0，净值 = 持仓市值
        cash = 0.0
        nav_points.append(
            {
                "date": date,
                "holdings_value": round(holdings_value, 2),
                "cash": cash,
                "total_value": round(holdings_value + cash, 2),
            }
        )

    return {"nav": nav_points, "count": len(nav_points)}
