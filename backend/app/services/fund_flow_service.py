"""个股资金流聚合服务 — Core 级别 SQL 查询

数据源：daily_stock_fund_flow（腾讯自选股个股资金流）
分类依据：stocks.industry_l1（行业）/ stocks.concepts（题材，JSON 数组）
四大指数：ts_code 正则匹配（复用 market_heat_service BOARD_DEFINITIONS）
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select, func, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.stock_tables import DailyStockFundFlow, Stock


# ── 四大指数板块分类（来自 market_heat_service.py BOARD_DEFINITIONS）──

BOARD_LABEL = case(
    (DailyStockFundFlow.__table__.c.ts_code.regexp_match("^[56]0[0-5]"), "sh_main"),
    (DailyStockFundFlow.__table__.c.ts_code.regexp_match("^688"), "sh_star"),
    (DailyStockFundFlow.__table__.c.ts_code.regexp_match("^00[0-3]"), "sz_main"),
    (DailyStockFundFlow.__table__.c.ts_code.regexp_match("^30[01]"), "sz_chi"),
    else_="other",
).label("board_code")

BOARD_NAMES = {
    "sh_main": "上证主板",
    "sh_star": "科创板",
    "sz_main": "深证主板",
    "sz_chi": "创业板",
    "other": "其他",
}

# ── 当日最新日期缓存 ──

_LAST_DATE_CACHE: dict = {}


class FundFlowService:
    """个股资金流聚合查询"""

    # ═══════════════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def _get_latest_date(db: AsyncSession) -> str:
        """获取 daily_stock_fund_flow 中最新交易日"""
        cache_key = id(db)
        if cache_key in _LAST_DATE_CACHE:
            return _LAST_DATE_CACHE[cache_key]

        stmt = select(func.max(DailyStockFundFlow.__table__.c.trade_date))
        result = await db.execute(stmt)
        d = result.scalar()
        _LAST_DATE_CACHE[cache_key] = d
        return d

    @staticmethod
    def _normalize_date(d) -> str:
        """统一日期格式 YYYY-MM-DD"""
        if d is None:
            return ""
        s = str(d)
        return s[:10] if len(s) >= 10 else s

    # ═══════════════════════════════════════════════════════════════
    # 1. 市场总览 — KPI 汇总 + 四大指数 + 广度
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_overview(
        db: AsyncSession, trade_date: Optional[str] = None
    ) -> dict:
        """单日资金流全景：全市场合计 + 四大指数分别汇总 + 资金广度"""
        d = trade_date or await FundFlowService._get_latest_date(db)
        if not d:
            return {"trade_date": None, "summary": None, "boards": [], "breadth": None}

        tbl = DailyStockFundFlow.__table__

        # 全市场合计（亿元）
        sum_stmt = select(
            func.coalesce(func.sum(tbl.c.main_net_flow) / 1e8, 0).label("main_net_yi"),
            func.coalesce(func.sum(tbl.c.jumbo_net_flow) / 1e8, 0).label("jumbo_net_yi"),
            func.coalesce(func.sum(tbl.c.block_net_flow) / 1e8, 0).label("block_net_yi"),
            func.coalesce(func.sum(tbl.c.mid_net_flow) / 1e8, 0).label("mid_net_yi"),
            func.coalesce(func.sum(tbl.c.small_net_flow) / 1e8, 0).label("small_net_yi"),
            func.coalesce(
                (func.sum(tbl.c.retail_in_flow) - func.sum(tbl.c.retail_out_flow)) / 1e8, 0
            ).label("retail_net_yi"),
            func.coalesce(func.sum(tbl.c.main_in_flow) / 1e8, 0).label("main_in_yi"),
            func.coalesce(func.sum(tbl.c.main_out_flow) / 1e8, 0).label("main_out_yi"),
            func.coalesce(
                func.count().filter(tbl.c.main_net_flow > 0), 0
            ).label("positive_count"),
            func.count().label("total_count"),
        ).where(tbl.c.trade_date == d)
        result = await db.execute(sum_stmt)
        row = result.mappings().first()
        if not row or row["total_count"] == 0:
            return {"trade_date": d, "summary": None, "boards": [], "breadth": None}

        summary = {
            "main_net_yi": round(float(row["main_net_yi"]), 2),
            "jumbo_net_yi": round(float(row["jumbo_net_yi"]), 2),
            "block_net_yi": round(float(row["block_net_yi"]), 2),
            "mid_net_yi": round(float(row["mid_net_yi"]), 2),
            "small_net_yi": round(float(row["small_net_yi"]), 2),
            "retail_net_yi": round(float(row["retail_net_yi"]), 2),
            "main_in_yi": round(float(row["main_in_yi"]), 2),
            "main_out_yi": round(float(row["main_out_yi"]), 2),
        }

        # 四大指数分别汇总
        board_stmt = (
            select(
                BOARD_LABEL,
                func.coalesce(func.sum(tbl.c.main_net_flow) / 1e8, 0).label("main_net_yi"),
                func.coalesce(func.sum(tbl.c.jumbo_net_flow) / 1e8, 0).label("jumbo_net_yi"),
                func.count().filter(tbl.c.main_net_flow > 0).label("positive_count"),
                func.count().label("total_count"),
            )
            .where(tbl.c.trade_date == d)
            .group_by(text("board_code"))
            .order_by(text("board_code"))
        )
        result = await db.execute(board_stmt)
        boards = []
        for r in result.mappings().all():
            bc = r["board_code"]
            if bc == "other":
                continue
            total = r["total_count"] or 1
            boards.append({
                "board_code": bc,
                "board_name": BOARD_NAMES.get(bc, bc),
                "main_net_yi": round(float(r["main_net_yi"]), 2),
                "jumbo_net_yi": round(float(r["jumbo_net_yi"]), 2),
                "positive_pct": round(float(r["positive_count"] or 0) / total * 100, 1),
                "stock_count": total,
            })

        # 资金广度
        breadth = {
            "positive_count": row["positive_count"],
            "total_count": row["total_count"],
            "positive_pct": round(
                float(row["positive_count"] or 0) / max(row["total_count"], 1) * 100, 1
            ),
        }

        return {
            "trade_date": FundFlowService._normalize_date(d),
            "summary": summary,
            "boards": boards,
            "breadth": breadth,
        }

    # ═══════════════════════════════════════════════════════════════
    # 2. 全市场资金流历史（近 N 日时间序列）
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_history(
        db: AsyncSession, days: int = 30
    ) -> list[dict]:
        """近 N 日全市场每日资金流合计"""
        tbl = DailyStockFundFlow.__table__
        cutoff = (date.today() - timedelta(days=days + 5)).strftime("%Y-%m-%d")

        stmt = (
            select(
                tbl.c.trade_date,
                func.coalesce(func.sum(tbl.c.main_net_flow) / 1e8, 0).label("main_net_yi"),
                func.coalesce(func.sum(tbl.c.jumbo_net_flow) / 1e8, 0).label("jumbo_net_yi"),
                func.coalesce(func.sum(tbl.c.block_net_flow) / 1e8, 0).label("block_net_yi"),
                func.coalesce(func.sum(tbl.c.mid_net_flow) / 1e8, 0).label("mid_net_yi"),
                func.coalesce(func.sum(tbl.c.small_net_flow) / 1e8, 0).label("small_net_yi"),
                func.coalesce(
                    (func.sum(tbl.c.retail_in_flow) - func.sum(tbl.c.retail_out_flow)) / 1e8, 0
                ).label("retail_net_yi"),
            )
            .where(tbl.c.trade_date >= cutoff)
            .group_by(tbl.c.trade_date)
            .order_by(tbl.c.trade_date.asc())
        )
        result = await db.execute(stmt)
        return [
            {
                "trade_date": FundFlowService._normalize_date(r["trade_date"]),
                "main_net_yi": round(float(r["main_net_yi"]), 2),
                "jumbo_net_yi": round(float(r["jumbo_net_yi"]), 2),
                "block_net_yi": round(float(r["block_net_yi"]), 2),
                "mid_net_yi": round(float(r["mid_net_yi"]), 2),
                "small_net_yi": round(float(r["small_net_yi"]), 2),
                "retail_net_yi": round(float(r["retail_net_yi"]), 2),
            }
            for r in result.mappings().all()
        ]

    # ═══════════════════════════════════════════════════════════════
    # 3. 四大指数资金流历史（分指数时间序列，面积图用）
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_board_history(
        db: AsyncSession, days: int = 30
    ) -> list[dict]:
        """近 N 日各指数每日资金流（每个 date × board 一条记录）"""
        tbl = DailyStockFundFlow.__table__
        cutoff = (date.today() - timedelta(days=days + 5)).strftime("%Y-%m-%d")

        stmt = (
            select(
                tbl.c.trade_date,
                BOARD_LABEL,
                func.coalesce(func.sum(tbl.c.main_net_flow) / 1e8, 0).label("main_net_yi"),
            )
            .where(tbl.c.trade_date >= cutoff)
            .group_by(tbl.c.trade_date, text("board_code"))
            .order_by(tbl.c.trade_date.asc())
        )
        result = await db.execute(stmt)
        rows = []
        for r in result.mappings().all():
            bc = r["board_code"]
            if bc == "other":
                continue
            rows.append({
                "trade_date": FundFlowService._normalize_date(r["trade_date"]),
                "board_code": bc,
                "board_name": BOARD_NAMES.get(bc, bc),
                "main_net_yi": round(float(r["main_net_yi"]), 2),
            })
        return rows

    # ═══════════════════════════════════════════════════════════════
    # 4. 行业资金流排名
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_industry_flow(
        db: AsyncSession,
        trade_date: Optional[str] = None,
        sort: str = "net",
        limit: int = 50,
    ) -> dict:
        """按 industry_l1 聚合的资金流排名"""
        d = trade_date or await FundFlowService._get_latest_date(db)
        if not d:
            return {"trade_date": None, "items": []}

        f = DailyStockFundFlow.__table__
        s = Stock.__table__

        stmt = (
            select(
                s.c.industry_l1.label("industry_name"),
                func.coalesce(func.sum(f.c.main_net_flow) / 1e8, 0).label("main_net_yi"),
                func.coalesce(func.sum(f.c.jumbo_net_flow) / 1e8, 0).label("jumbo_net_yi"),
                func.coalesce(func.sum(f.c.block_net_flow) / 1e8, 0).label("block_net_yi"),
                func.coalesce(func.sum(f.c.mid_net_flow) / 1e8, 0).label("mid_net_yi"),
                func.coalesce(func.sum(f.c.small_net_flow) / 1e8, 0).label("small_net_yi"),
                func.coalesce(
                    func.avg(f.c.main_inflow_circ_rate), 0
                ).label("avg_inflow_rate"),
                func.coalesce(func.count().filter(f.c.main_net_flow > 0), 0).label("up_count"),
                func.count().label("total_count"),
            )
            .select_from(f.join(s, f.c.ts_code == s.c.ts_code))
            .where(
                f.c.trade_date == d,
                s.c.industry_l1.isnot(None),
                s.c.industry_l1 != "",
            )
            .group_by(s.c.industry_l1)
            .order_by(
                func.sum(f.c.main_net_flow).desc()
                if sort == "net"
                else func.count().filter(f.c.main_net_flow > 0).desc()
            )
            .limit(limit)
        )
        result = await db.execute(stmt)
        items = []
        for r in result.mappings().all():
            total = r["total_count"] or 1
            items.append({
                "industry_name": r["industry_name"],
                "main_net_yi": round(float(r["main_net_yi"]), 2),
                "jumbo_net_yi": round(float(r["jumbo_net_yi"]), 2),
                "block_net_yi": round(float(r["block_net_yi"]), 2),
                "mid_net_yi": round(float(r["mid_net_yi"]), 2),
                "small_net_yi": round(float(r["small_net_yi"]), 2),
                "avg_inflow_rate": round(float(r["avg_inflow_rate"]), 2),
                "positive_pct": round(float(r["up_count"]) / total * 100, 1),
                "stock_count": total,
            })
        return {"trade_date": FundFlowService._normalize_date(d), "items": items}

    # ═══════════════════════════════════════════════════════════════
    # 5. 题材资金流排名
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_concept_flow(
        db: AsyncSession,
        trade_date: Optional[str] = None,
        sort: str = "net",
        limit: int = 50,
    ) -> dict:
        """按 concepts 展开后聚合的资金流排名

        concepts 是 JSON 数组如 '["AI","芯片"]'，用 jsonb_array_elements_text 展开。
        一只股票属于多个概念时，其资金流会被重复计入各概念（归因到每个相关概念）。
        """
        d = trade_date or await FundFlowService._get_latest_date(db)
        if not d:
            return {"trade_date": None, "items": []}

        # concepts JSON 展开用原生 SQL（SQLAlchemy Core 对 LATERAL 支持有限）
        sql = text(
            """
            SELECT
                trim(concept_item) AS concept_name,
                COALESCE(SUM(f.main_net_flow) / 1e8, 0) AS main_net_yi,
                COALESCE(SUM(f.block_net_flow) / 1e8, 0) AS block_net_yi,
                COALESCE(SUM(f.mid_net_flow) / 1e8, 0) AS mid_net_yi,
                COALESCE(SUM(f.small_net_flow) / 1e8, 0) AS small_net_yi,
                COUNT(DISTINCT f.ts_code) AS stock_count,
                COALESCE(COUNT(*) FILTER (WHERE f.main_net_flow > 0), 0) AS up_count
            FROM daily_stock_fund_flow f
            JOIN stocks s ON f.ts_code = s.ts_code
            CROSS JOIN LATERAL jsonb_array_elements_text(
                CASE
                    WHEN s.concepts ~ '^\\s*\\[' THEN s.concepts::jsonb
                    ELSE to_jsonb(string_to_array(s.concepts, ','))
                END
            ) AS concept_item
            WHERE f.trade_date = :trade_date
              AND s.concepts IS NOT NULL
              AND s.concepts != ''
            GROUP BY trim(concept_item)
            ORDER BY SUM(f.main_net_flow) DESC
            LIMIT :limit
            """
        )
        result = await db.execute(sql, {"trade_date": d, "limit": limit})
        items = []
        for r in result.mappings().all():
            total = max(r["stock_count"] or 1, 1)
            items.append({
                "concept_name": (r["concept_name"] or "").strip('" '),
                "main_net_yi": round(float(r["main_net_yi"]), 2),
                "block_net_yi": round(float(r["block_net_yi"]), 2),
                "mid_net_yi": round(float(r["mid_net_yi"]), 2),
                "small_net_yi": round(float(r["small_net_yi"]), 2),
                "positive_pct": round(float(r["up_count"] or 0) / total * 100, 1),
                "stock_count": r["stock_count"],
            })
        return {"trade_date": FundFlowService._normalize_date(d), "items": items}

    # ═══════════════════════════════════════════════════════════════
    # 6. 板块热力图（行业 或 题材 × 近 N 日）
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_sector_heatmap(
        db: AsyncSession,
        days: int = 20,
        sector_type: str = "industry",
    ) -> dict:
        """近 N 日每个行业/题材每日的主力净流入，热力图用"""
        cutoff = (date.today() - timedelta(days=days + 5)).strftime("%Y-%m-%d")

        if sector_type == "industry":
            f = DailyStockFundFlow.__table__
            s = Stock.__table__
            stmt = (
                select(
                    f.c.trade_date,
                    s.c.industry_l1.label("sector_name"),
                    func.coalesce(func.sum(f.c.main_net_flow) / 1e8, 0).label("main_net_yi"),
                )
                .select_from(f.join(s, f.c.ts_code == s.c.ts_code))
                .where(
                    f.c.trade_date >= cutoff,
                    s.c.industry_l1.isnot(None),
                    s.c.industry_l1 != "",
                )
                .group_by(f.c.trade_date, s.c.industry_l1)
                .order_by(f.c.trade_date.asc())
            )
            result = await db.execute(stmt)
        else:
            sql = text(
                """
                SELECT
                    f.trade_date,
                    trim(concept_item) AS sector_name,
                    COALESCE(SUM(f.main_net_flow) / 1e8, 0) AS main_net_yi
                FROM daily_stock_fund_flow f
                JOIN stocks s ON f.ts_code = s.ts_code
                CROSS JOIN LATERAL jsonb_array_elements_text(
                    CASE
                        WHEN s.concepts ~ '^\\s*\\[' THEN s.concepts::jsonb
                        ELSE to_jsonb(string_to_array(s.concepts, ','))
                    END
                ) AS concept_item
                WHERE f.trade_date >= :cutoff
                  AND s.concepts IS NOT NULL
                  AND s.concepts != ''
                GROUP BY f.trade_date, trim(concept_item)
                ORDER BY f.trade_date ASC
                """
            )
            result = await db.execute(sql, {"cutoff": cutoff})

        rows = []
        for r in result.mappings().all():
            sn = r["sector_name"]
            if sector_type == "concept":
                sn = (sn or "").strip('" ')
            if not sn:
                continue
            rows.append({
                "trade_date": FundFlowService._normalize_date(r["trade_date"]),
                "sector_name": sn,
                "main_net_yi": round(float(r["main_net_yi"]), 2),
            })
        return {"type": sector_type, "days": days, "rows": rows}

    # ═══════════════════════════════════════════════════════════════
    # 7. 个股资金流排名
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_stock_ranking(
        db: AsyncSession,
        trade_date: Optional[str] = None,
        sort: str = "main_net",
        limit: int = 100,
    ) -> dict:
        """单日个股资金流排名（支持多种排序方式）"""
        d = trade_date or await FundFlowService._get_latest_date(db)
        if not d:
            return {"trade_date": None, "items": []}

        f = DailyStockFundFlow.__table__
        s = Stock.__table__

        sort_cols = {
            "main_net": f.c.main_net_flow.desc(),
            "main_net_asc": f.c.main_net_flow.asc(),
            "inflow_rate": f.c.main_inflow_circ_rate.desc().nulls_last(),
            "jumbo": f.c.jumbo_net_flow.desc(),
            "block": f.c.block_net_flow.desc(),
            "mid": f.c.mid_net_flow.desc(),
            "small": f.c.small_net_flow.desc(),
        }
        order_by = sort_cols.get(sort, sort_cols["main_net"])

        stmt = (
            select(
                f.c.ts_code,
                s.c.name.label("stock_name"),
                s.c.industry_l1.label("industry_name"),
                f.c.main_net_flow,
                f.c.jumbo_net_flow,
                f.c.block_net_flow,
                f.c.mid_net_flow,
                f.c.small_net_flow,
                f.c.main_in_flow,
                f.c.main_out_flow,
                f.c.retail_in_flow,
                f.c.retail_out_flow,
                f.c.main_net_flow_5d,
                f.c.main_net_flow_10d,
                f.c.main_net_flow_20d,
                f.c.main_inflow_circ_rate,
                f.c.main_inflow_rank,
                f.c.close_price,
            )
            .select_from(f.join(s, f.c.ts_code == s.c.ts_code))
            .where(f.c.trade_date == d)
            .order_by(order_by)
            .limit(limit)
        )
        result = await db.execute(stmt)
        items = []
        for r in result.mappings().all():
            items.append({
                "ts_code": r["ts_code"],
                "stock_name": r["stock_name"] or "",
                "industry_name": r["industry_name"] or "",
                "main_net_flow": float(r["main_net_flow"] or 0),
                "jumbo_net_flow": float(r["jumbo_net_flow"] or 0),
                "block_net_flow": float(r["block_net_flow"] or 0),
                "mid_net_flow": float(r["mid_net_flow"] or 0),
                "small_net_flow": float(r["small_net_flow"] or 0),
                "main_in_flow": float(r["main_in_flow"] or 0),
                "main_out_flow": float(r["main_out_flow"] or 0),
                "retail_in_flow": float(r["retail_in_flow"] or 0),
                "retail_out_flow": float(r["retail_out_flow"] or 0),
                "main_net_flow_5d": float(r["main_net_flow_5d"] or 0),
                "main_net_flow_10d": float(r["main_net_flow_10d"] or 0),
                "main_net_flow_20d": float(r["main_net_flow_20d"] or 0),
                "main_inflow_circ_rate": float(r["main_inflow_circ_rate"] or 0),
                "main_inflow_rank": r["main_inflow_rank"],
                "close_price": float(r["close_price"] or 0),
            })
        return {"trade_date": FundFlowService._normalize_date(d), "items": items}

    # ═══════════════════════════════════════════════════════════════
    # 8. 个股资金流趋势（单股近 N 日）
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_stock_trend(
        db: AsyncSession,
        ts_code: str,
        days: int = 30,
    ) -> dict:
        """单只股票近 N 日资金流趋势"""
        tbl = DailyStockFundFlow.__table__
        cutoff = (date.today() - timedelta(days=days + 5)).strftime("%Y-%m-%d")

        stmt = (
            select(tbl)
            .where(tbl.c.ts_code == ts_code, tbl.c.trade_date >= cutoff)
            .order_by(tbl.c.trade_date.asc())
        )
        result = await db.execute(stmt)
        rows = result.mappings().all()
        if not rows:
            return {"ts_code": ts_code, "days": [], "stock_name": ""}

        # 获取股票名称
        s_tbl = Stock.__table__
        name_stmt = select(s_tbl.c.name).where(s_tbl.c.ts_code == ts_code)
        name_result = await db.execute(name_stmt)
        name = name_result.scalar() or ""

        return {
            "ts_code": ts_code,
            "stock_name": name,
            "days": [
                {
                    "trade_date": FundFlowService._normalize_date(r["trade_date"]),
                    "main_net_flow": float(r["main_net_flow"] or 0),
                    "jumbo_net_flow": float(r["jumbo_net_flow"] or 0),
                    "block_net_flow": float(r["block_net_flow"] or 0),
                    "mid_net_flow": float(r["mid_net_flow"] or 0),
                    "small_net_flow": float(r["small_net_flow"] or 0),
                    "main_in_flow": float(r["main_in_flow"] or 0),
                    "main_out_flow": float(r["main_out_flow"] or 0),
                    "retail_in_flow": float(r["retail_in_flow"] or 0),
                    "retail_out_flow": float(r["retail_out_flow"] or 0),
                    "main_net_flow_5d": float(r["main_net_flow_5d"] or 0),
                    "main_net_flow_10d": float(r["main_net_flow_10d"] or 0),
                    "main_net_flow_20d": float(r["main_net_flow_20d"] or 0),
                    "close_price": float(r["close_price"] or 0),
                }
                for r in rows
            ],
        }

    # ═══════════════════════════════════════════════════════════════
    # 9. 广度历史（每日主力净流入为正的股票占比，折线图用）
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_breadth_history(
        db: AsyncSession, days: int = 30
    ) -> list[dict]:
        """近 N 日每日资金广度（%正净流入股票）"""
        tbl = DailyStockFundFlow.__table__
        cutoff = (date.today() - timedelta(days=days + 5)).strftime("%Y-%m-%d")

        stmt = (
            select(
                tbl.c.trade_date,
                func.count().filter(tbl.c.main_net_flow > 0).label("positive_count"),
                func.count().label("total_count"),
            )
            .where(tbl.c.trade_date >= cutoff)
            .group_by(tbl.c.trade_date)
            .order_by(tbl.c.trade_date.asc())
        )
        result = await db.execute(stmt)
        return [
            {
                "trade_date": FundFlowService._normalize_date(r["trade_date"]),
                "positive_pct": round(
                    float(r["positive_count"] or 0) / max(r["total_count"], 1) * 100, 1
                ),
                "positive_count": r["positive_count"],
                "total_count": r["total_count"],
            }
            for r in result.mappings().all()
        ]

    # ═══════════════════════════════════════════════════════════════
    # 10. 可用日期列表
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_available_dates(
        db: AsyncSession, days: int = 60
    ) -> list[str]:
        """有数据的交易日列表"""
        tbl = DailyStockFundFlow.__table__
        cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        stmt = (
            select(tbl.c.trade_date)
            .where(tbl.c.trade_date >= cutoff)
            .distinct()
            .order_by(tbl.c.trade_date.desc())
        )
        result = await db.execute(stmt)
        return [FundFlowService._normalize_date(r["trade_date"]) for r in result.mappings().all()]
