"""股票搜索服务 — 通过 SQLAlchemy ORM 查询 PostgreSQL"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.stock_tables import Stock, Daily


class StockService:
    """股票搜索和 K 线数据查询"""

    @staticmethod
    async def search(db: AsyncSession, q: str, limit: int = 10) -> dict:
        like_q = f"%{q}%"
        stmt = (
            select(Stock.ts_code, Stock.symbol, Stock.name, Stock.market)
            .where(
                (Stock.ts_code.ilike(like_q)) | (Stock.name.ilike(like_q))
            )
            .order_by(Stock.ts_code)
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.all()
        items = [
            {"ts_code": r.ts_code, "symbol": r.symbol, "name": r.name, "market": r.market}
            for r in rows
        ]
        return {"items": items, "total": len(items)}

    @staticmethod
    async def get_kline(db: AsyncSession, ts_code: str, days: int = 365) -> dict:
        stock_stmt = select(Stock.name).where(Stock.ts_code == ts_code)
        stock_result = await db.execute(stock_stmt)
        stock_name = stock_result.scalar()

        stmt = (
            select(
                Daily.trade_date, Daily.open, Daily.high, Daily.low,
                Daily.close, Daily.vol, Daily.amount
            )
            .where(Daily.ts_code == ts_code)
            .order_by(Daily.trade_date.desc())
            .limit(days)
        )
        result = await db.execute(stmt)
        rows = result.all()
        items = [
            {
                "trade_date": r.trade_date, "open": r.open, "high": r.high,
                "low": r.low, "close": r.close, "vol": r.vol, "amount": r.amount,
            }
            for r in reversed(rows)
        ]
        return {"ts_code": ts_code, "name": stock_name or "", "items": items}
