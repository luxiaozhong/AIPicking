"""股票搜索服务 — 通过 SQLAlchemy ORM 查询 PostgreSQL"""
from sqlalchemy import select, literal_column
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.stock_tables import Stock, Daily
from ..models.index_tables import IndexInfo


class StockService:
    """股票搜索和 K 线数据查询"""

    @staticmethod
    async def search(db: AsyncSession, q: str, limit: int = 10) -> dict:
        like_q = f"%{q}%"
        stock_stmt = (
            select(Stock.ts_code, Stock.symbol, Stock.name, Stock.market)
            .where(
                (Stock.ts_code.ilike(like_q)) | (Stock.name.ilike(like_q)) | (Stock.pinyin_initials.ilike(like_q))
            )
            .order_by(Stock.ts_code)
            .limit(limit)
        )
        idx_stmt = (
            select(
                IndexInfo.ts_code,
                literal_column("''").label("symbol"),
                IndexInfo.full_name.label("name"),
                literal_column("''").label("market"),
            )
            .where(
                IndexInfo.ts_code.isnot(None),
                (IndexInfo.ts_code.ilike(like_q)) | (IndexInfo.index_name.ilike(like_q)) | (IndexInfo.full_name.ilike(like_q))
            )
            .limit(limit)
        )
        stock_result = await db.execute(stock_stmt)
        items = [
            {"ts_code": r.ts_code, "symbol": r.symbol, "name": r.name, "market": r.market}
            for r in stock_result.all()
        ]
        # 补充指数搜索结果
        if len(items) < limit:
            idx_result = await db.execute(idx_stmt)
            for r in idx_result.all():
                items.append({"ts_code": r.ts_code, "symbol": r.symbol, "name": r.name, "market": r.market})
        return {"items": items[:limit], "total": len(items[:limit])}

    @staticmethod
    async def get_kline(db: AsyncSession, ts_code: str, days: int = 365) -> dict:
        # 名称查找：优先 stocks，回退 index_info
        stock_name = None
        stock_result = await db.execute(select(Stock.name).where(Stock.ts_code == ts_code))
        stock_name = stock_result.scalar()
        if not stock_name:
            idx_result = await db.execute(
                select(IndexInfo.full_name).where(IndexInfo.ts_code == ts_code)
            )
            idx_name = idx_result.scalar()
            if idx_name:
                stock_name = idx_name

        stmt = (
            select(
                Daily.trade_date, Daily.open, Daily.high, Daily.low,
                Daily.close, Daily.pre_close, Daily.vol, Daily.amount
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
                "low": r.low, "close": r.close, "pre_close": r.pre_close,
                "vol": r.vol, "amount": r.amount,
            }
            for r in reversed(rows)
        ]
        return {"ts_code": ts_code, "name": stock_name or "", "items": items}
