"""股票搜索服务 — 查询外部 SQLite stocks 表"""

import sqlite3

from ..config import settings


class StockService:
    """股票搜索（外部数据库只读查询）"""

    @staticmethod
    def search(q: str, limit: int = 10) -> dict:
        conn = sqlite3.connect(settings.STOCK_DB_PATH)
        conn.row_factory = sqlite3.Row

        like_q = f"%{q}%"
        cursor = conn.execute(
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
        rows = cursor.fetchall()
        conn.close()

        return {
            "items": [dict(r) for r in rows],
            "total": len(rows),
        }

    @staticmethod
    def get_kline(ts_code: str, days: int = 365) -> dict:
        """获取单只股票的日 K 线数据"""
        conn = sqlite3.connect(settings.STOCK_DB_PATH)
        conn.row_factory = sqlite3.Row

        # 获取股票名称
        stock = conn.execute(
            "SELECT name FROM stocks WHERE ts_code = ?", (ts_code,)
        ).fetchone()

        # 获取最近 N 个交易日的 OHLCV 数据
        rows = conn.execute(
            """
            SELECT trade_date, open, high, low, close, vol, amount
            FROM daily
            WHERE ts_code = ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (ts_code, days),
        ).fetchall()
        conn.close()

        items = [dict(r) for r in reversed(rows)]
        return {
            "ts_code": ts_code,
            "name": stock["name"] if stock else "",
            "items": items,
        }
