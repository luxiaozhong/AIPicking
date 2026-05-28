"""股票搜索服务 — 查询外部 SQLite stocks 表"""

import aiosqlite

from ..config import settings


class StockService:
    """股票搜索（外部数据库只读查询）"""

    @staticmethod
    async def search(q: str, limit: int = 10) -> dict:
        async with aiosqlite.connect(settings.STOCK_DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            like_q = f"%{q}%"
            cursor = await conn.execute(
                """
                SELECT ts_code, symbol, name, market
                FROM stocks
                WHERE ts_code LIKE ? OR name LIKE ?
                ORDER BY
                  CASE
                    WHEN ts_code = ? THEN 0
                    WHEN name = ? THEN 1
                    WHEN ts_code LIKE ? THEN 2
                    ELSE 3
                  END,
                  ts_code
                LIMIT ?
                """,
                (like_q, like_q, q, q, f"{q}%", limit),
            )
            rows = await cursor.fetchall()
            return {
                "items": [dict(r) for r in rows],
                "total": len(rows),
            }

    @staticmethod
    async def get_kline(ts_code: str, days: int = 365) -> dict:
        """获取单只股票的日 K 线数据"""
        async with aiosqlite.connect(settings.STOCK_DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row

            stock_cursor = await conn.execute(
                "SELECT name FROM stocks WHERE ts_code = ?", (ts_code,)
            )
            stock = await stock_cursor.fetchone()

            cursor = await conn.execute(
                """
                SELECT trade_date, open, high, low, close, vol, amount
                FROM daily
                WHERE ts_code = ?
                ORDER BY trade_date DESC
                LIMIT ?
                """,
                (ts_code, days),
            )
            rows = await cursor.fetchall()

        items = [dict(r) for r in reversed(rows)]
        return {
            "ts_code": ts_code,
            "name": stock["name"] if stock else "",
            "items": items,
        }
