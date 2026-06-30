"""个股资金流聚合服务 — Core 级别 SQL 查询

数据源：daily_stock_fund_flow（腾讯自选股个股资金流）
分类依据：stocks.industry_l1（行业）/ stocks.concepts（题材，JSON 数组）
四大指数：ts_code 正则匹配（复用 market_heat_service BOARD_DEFINITIONS）
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select, func, case, text, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.stock_tables import DailyStockFundFlow, Stock, Daily
from ..models.index_tables import IndexInfo, IndexConstituent


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

BOARD_REGEX = {
    "sh_main": r"^[56]0[0-5]",
    "sh_star": r"^688",
    "sz_main": r"^00[0-3]",
    "sz_chi": r"^30[01]",
}

# ── 当日最新日期缓存 ──

_LAST_DATE_CACHE: dict = {}


def _index_ts_codes_subq():
    """返回所有指数 ts_code 的子查询，用于排除指数资金流记录"""
    return select(IndexInfo.ts_code).where(IndexInfo.ts_code.isnot(None))


def _latest_eff_subq(index_code: str):
    """返回每个 ts_code 最新 eff_date 的子查询（aliased）。

    替代全局 MAX(eff_date)，对 900002 等手动维护的指数也正确：
    每只股票独立取最新 eff_date，而非要求所有成分股同属一个调样批次。
    """
    ic = IndexConstituent.__table__
    return (
        select(
            ic.c.ts_code,
            func.max(ic.c.eff_date).label("max_eff_date"),
        )
        .where(ic.c.index_code == index_code)
        .group_by(ic.c.ts_code)
    ).alias("_latest_eff")


class FundFlowService:
    """个股资金流聚合查询"""

    # ═══════════════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def _compute_rolling_sums(
        db: AsyncSession,
        ts_codes: list[str],
        target_dates: list[str],
        windows: list[int] = [5, 10, 20],
    ) -> dict[str, dict[str, float]]:
        """Self-compute rolling N-day main_net_flow sums for given stocks/dates.

        Returns {ts_code: {date: {'5d': float, '10d': float, '20d': float}}}
        """
        if not ts_codes or not target_dates:
            return {}

        f = DailyStockFundFlow.__table__

        # Get all available trade dates for these stocks (up to max window before earliest target)
        max_window = max(windows)
        earliest_target = min(target_dates)

        all_dates_stmt = (
            select(f.c.trade_date)
            .where(f.c.ts_code.in_(ts_codes), f.c.trade_date <= max(target_dates))
            .distinct()
            .order_by(f.c.trade_date.asc())
        )
        date_result = await db.execute(all_dates_stmt)
        all_sorted_dates = [r[0] for r in date_result.all()]

        # Get all daily flows for the extended period
        cutoff_idx = max(0, len(all_sorted_dates) - len(target_dates) - max_window - 5)
        relevant_dates = all_sorted_dates[cutoff_idx:]

        flow_stmt = (
            select(f.c.trade_date, f.c.ts_code, f.c.main_net_flow)
            .where(
                f.c.ts_code.in_(ts_codes),
                f.c.trade_date.in_(relevant_dates),
            )
            .order_by(f.c.trade_date.asc())
        )
        flow_result = await db.execute(flow_stmt)

        # Build per-stock lookup: ts_code -> {date: flow}
        from collections import defaultdict
        flows: dict[str, dict[str, float]] = defaultdict(dict)
        for r in flow_result.mappings().all():
            flows[r["ts_code"]][r["trade_date"]] = float(r["main_net_flow"] or 0)

        # Compute rolling sums for each target date
        result: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        date_to_idx = {d: i for i, d in enumerate(all_sorted_dates)}

        for ts in ts_codes:
            stock_flows = flows.get(ts, {})
            for target in target_dates:
                if target not in date_to_idx:
                    continue
                target_idx = date_to_idx[target]
                for w in windows:
                    start_idx = max(0, target_idx - w + 1)
                    window_dates = all_sorted_dates[start_idx:target_idx + 1]
                    total = sum(stock_flows.get(d, 0) for d in window_dates)
                    key = f'{w}d'
                    result[ts][f"{target}|{key}"] = total

        return dict(result)

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
    async def _get_latest_snapshot_date(db: AsyncSession) -> str:
        """获取 intraday_fund_snapshot 中最新交易日（盘中快照用）"""
        sql = text("SELECT MAX(trade_date) FROM intraday_fund_snapshot")
        result = await db.execute(sql)
        return result.scalar()

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

        # 全市场合计（亿元）— 排除指数自身资金流
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
        ).where(
            tbl.c.trade_date == d,
            tbl.c.ts_code.not_in(_index_ts_codes_subq()),
        )
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

        # 四大指数分别汇总 — 排除指数自身资金流
        board_stmt = (
            select(
                BOARD_LABEL,
                func.coalesce(func.sum(tbl.c.main_net_flow) / 1e8, 0).label("main_net_yi"),
                func.coalesce(func.sum(tbl.c.jumbo_net_flow) / 1e8, 0).label("jumbo_net_yi"),
                func.count().filter(tbl.c.main_net_flow > 0).label("positive_count"),
                func.count().label("total_count"),
            )
            .where(
                tbl.c.trade_date == d,
                tbl.c.ts_code.not_in(_index_ts_codes_subq()),
            )
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
            .where(
                tbl.c.trade_date >= cutoff,
                tbl.c.ts_code.not_in(_index_ts_codes_subq()),
            )
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
            .where(
                tbl.c.trade_date >= cutoff,
                tbl.c.ts_code.not_in(_index_ts_codes_subq()),
            )
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
        board: Optional[str] = None,
    ) -> dict:
        """单日个股资金流排名（支持按板块过滤）"""
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
                f.c.main_inflow_circ_rate,
                f.c.main_inflow_rank,
                f.c.close_price,
            )
            .select_from(f.join(s, f.c.ts_code == s.c.ts_code))
            .where(f.c.trade_date == d, s.c.type == "stock")
        )
        if board and board in BOARD_REGEX:
            stmt = stmt.where(f.c.ts_code.regexp_match(BOARD_REGEX[board]))
        stmt = stmt.order_by(order_by).limit(limit)
        result = await db.execute(stmt)
        rows = result.mappings().all()

        # Compute real 5d/10d/20d rolling sums
        ts_codes = [r["ts_code"] for r in rows]
        rolling = await FundFlowService._compute_rolling_sums(db, ts_codes, [d])

        items = []
        for r in rows:
            ts = r["ts_code"]
            r5 = rolling.get(ts, {})
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
                "main_net_flow_5d": r5.get(f"{d}|5d", 0),
                "main_net_flow_10d": r5.get(f"{d}|10d", 0),
                "main_net_flow_20d": r5.get(f"{d}|20d", 0),
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
        """单只股票近 N 日资金流趋势（5d/10d/20d 自算）"""
        tbl = DailyStockFundFlow.__table__
        cutoff = (date.today() - timedelta(days=days + 25)).strftime("%Y-%m-%d")

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

        # 获取个股所属指数名称
        pure_code = ts_code.split(".")[0] if "." in ts_code else ts_code
        ic = IndexConstituent.__table__
        ii = IndexInfo.__table__

        # index_constituents.ts_code 格式不统一（有的带后缀如 600498.SH，有的不带）
        # 同时匹配两种格式
        code_match = or_(ic.c.ts_code == pure_code, ic.c.ts_code == ts_code)

        # 子查询：每个指数最新生效日期
        latest_eff = (
            select(
                ic.c.index_code,
                func.max(ic.c.eff_date).label("max_eff"),
            )
            .where(code_match)
            .group_by(ic.c.index_code)
        ).alias("latest_eff")

        index_stmt = (
            select(ii.c.index_code, ii.c.index_name)
            .select_from(
                ic.join(ii, ii.c.index_code == ic.c.index_code).join(
                    latest_eff,
                    (latest_eff.c.index_code == ic.c.index_code)
                    & (latest_eff.c.max_eff == ic.c.eff_date),
                )
            )
            .where(code_match)
            .distinct()
            .order_by(ii.c.index_name)
        )
        index_result = await db.execute(index_stmt)
        indices = [{"index_code": r.index_code, "index_name": r.index_name} for r in index_result.all()]

        # Collect daily main_net_flow for rolling window computation
        daily_flows = [(r["trade_date"], float(r["main_net_flow"] or 0)) for r in rows]
        date_to_flow = dict(daily_flows)
        all_dates = [d for d, _ in daily_flows]

        def rolling_sum(idx: int, window: int) -> float:
            start = max(0, idx - window + 1)
            return sum(date_to_flow.get(all_dates[i], 0) for i in range(start, idx + 1))

        return {
            "ts_code": ts_code,
            "stock_name": name,
            "indices": indices,
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
                    "main_net_flow_5d": rolling_sum(i, 5),
                    "main_net_flow_10d": rolling_sum(i, 10),
                    "main_net_flow_20d": rolling_sum(i, 20),
                    "close_price": float(r["close_price"] or 0),
                }
                for i, r in enumerate(rows)
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
            .where(
                tbl.c.trade_date >= cutoff,
                tbl.c.ts_code.not_in(_index_ts_codes_subq()),
            )
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

    # ═══════════════════════════════════════════════════════════════
    # 11. 个股盘中资金流变化
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_stock_intraday(
        db: AsyncSession,
        ts_code: str,
        trade_date: Optional[str] = None,
    ) -> dict:
        """单只股票当日盘中资金流快照（intraday_fund_snapshot）"""
        d = trade_date or await FundFlowService._get_latest_date(db)
        if not d:
            return {"ts_code": ts_code, "trade_date": None, "snapshots": []}

        sql = text(
            """
            SELECT snapshot_time, main_net_flow, jumbo_net_flow, block_net_flow,
                   main_net_flow_5d
            FROM intraday_fund_snapshot
            WHERE ts_code = :ts_code AND trade_date = :trade_date
            ORDER BY snapshot_time ASC
            """
        )
        result = await db.execute(sql, {"ts_code": ts_code, "trade_date": d})
        snapshots = [
            {
                "snapshot_time": str(r["snapshot_time"]),
                "main_net_flow": float(r["main_net_flow"] or 0),
                "jumbo_net_flow": float(r["jumbo_net_flow"] or 0),
                "block_net_flow": float(r["block_net_flow"] or 0),
                "main_net_flow_5d": float(r["main_net_flow_5d"] or 0),
            }
            for r in result.mappings().all()
        ]
        return {"ts_code": ts_code, "trade_date": d, "snapshots": snapshots}

    # ═══════════════════════════════════════════════════════════════
    # 12. 指数成分股 5日排名变化追踪
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_index_ranking_trend(
        db: AsyncSession,
        index_code: str,
        days: int = 10,
    ) -> dict:
        """过去 N 个交易日每只成分股的 5日累计排名变化
        用每日 main_net_flow 自算滚动 5 日累计，不依赖数据源字段
        """
        from collections import defaultdict

        ic = IndexConstituent.__table__
        s = Stock.__table__
        f = DailyStockFundFlow.__table__

        latest_subq = _latest_eff_subq(index_code)
        check = await db.execute(select(func.count()).select_from(latest_subq))
        if not check.scalar():
            return {"items": []}

        # Extend cutoff by 20 extra days for the 15d rolling window warm-up
        cutoff = (date.today() - timedelta(days=days + 25)).strftime("%Y-%m-%d")

        # Get all constituent stock codes (latest eff_date per stock)
        code_stmt = (
            select(s.c.ts_code, s.c.name.label("stock_name"))
            .select_from(
                ic.join(s, s.c.ts_code.like(func.concat(ic.c.ts_code, ".%")) | (s.c.ts_code == ic.c.ts_code))
                .join(latest_subq, (ic.c.ts_code == latest_subq.c.ts_code) & (ic.c.eff_date == latest_subq.c.max_eff_date))
            )
            .where(ic.c.index_code == index_code)
        )
        code_result = await db.execute(code_stmt)
        stocks = [(r["ts_code"], r["stock_name"] or "") for r in code_result.mappings().all()]
        ts_codes = [ts for ts, _ in stocks]

        # Get daily main_net_flow (raw, not the 5d field which may be inaccurate)
        flow_stmt = (
            select(f.c.trade_date, f.c.ts_code, f.c.main_net_flow)
            .where(
                f.c.ts_code.in_(ts_codes),
                f.c.trade_date >= cutoff,
            )
            .order_by(f.c.trade_date.asc())
        )
        flow_result = await db.execute(flow_stmt)

        # Group flows by (stock, date)
        stock_flows: dict[str, dict[str, float]] = defaultdict(dict)
        all_dates: set[str] = set()
        for r in flow_result.mappings().all():
            dt = r["trade_date"]
            stock_flows[r["ts_code"]][dt] = float(r["main_net_flow"] or 0)
            all_dates.add(dt)

        sorted_all_dates = sorted(all_dates)

        # Compute rolling 5-day and 15-day sums for each stock on each date
        stock_roll: dict[str, list[tuple]] = defaultdict(list)  # ts_code -> [(date, flow5d, flow15d, flow_today)]
        for ts, _ in stocks:
            flow_by_date = stock_flows.get(ts, {})
            for i, dt in enumerate(sorted_all_dates):
                today_flow = flow_by_date.get(dt, 0)
                # Sum the last 5 dates (including current)
                win5 = sorted_all_dates[max(0, i - 4): i + 1]
                flow5d = sum(flow_by_date.get(d, 0) for d in win5)
                # Sum the last 15 dates (including current)
                win15 = sorted_all_dates[max(0, i - 14): i + 1]
                flow15d = sum(flow_by_date.get(d, 0) for d in win15)
                stock_roll[ts].append((dt, flow5d, flow15d, today_flow))

        # For each date, rank stocks by computed 5d flow
        stock_ranks: dict[str, dict] = {}
        for ts, name in stocks:
            stock_ranks[ts] = {"stock_name": name, "dates": [], "ranks": [], "flows5d": [], "flows15d": [], "flows": []}

        for idx, dt in enumerate(sorted_all_dates):
            # Only rank starting from 15th date (when 15d rolling window is full)
            if idx < 14:
                continue
            day_items = [(ts, stock_roll[ts][idx][1], stock_roll[ts][idx][2], stock_roll[ts][idx][3])
                        for ts, _ in stocks if idx < len(stock_roll[ts])]
            day_items.sort(key=lambda x: x[1], reverse=True)  # sort by 5d flow desc
            for rank_i, (ts, flow5d, flow15d, flow_today) in enumerate(day_items):
                if ts in stock_ranks:
                    stock_ranks[ts]["dates"].append(dt)
                    stock_ranks[ts]["ranks"].append(rank_i + 1)
                    stock_ranks[ts]["flows5d"].append(flow5d)
                    stock_ranks[ts]["flows15d"].append(flow15d)
                    stock_ranks[ts]["flows"].append(flow_today)

        # Build result
        items = []
        for ts, data in stock_ranks.items():
            if len(data["ranks"]) < 2:
                continue
            first_rank = data["ranks"][0]
            last_rank = data["ranks"][-1]
            items.append({
                "ts_code": ts,
                "stock_name": data["stock_name"],
                "dates": data["dates"],
                "ranks": data["ranks"],
                "flows5d": data["flows5d"],
                "flows15d": data["flows15d"],
                "flows": data["flows"],
                "improvement": first_rank - last_rank,
                "current_rank": last_rank,
                "current_flow_5d": data["flows5d"][-1] if data["flows5d"] else 0,
                "current_flow_15d": data["flows15d"][-1] if data["flows15d"] else 0,
                "current_flow": data["flows"][-1] if data["flows"] else 0,
            })

        items.sort(key=lambda x: x["improvement"], reverse=True)
        return {"items": items}

    # ═══════════════════════════════════════════════════════════════
    # 13. 指数历史聚合
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_index_history(
        db: AsyncSession,
        index_code: str,
        days: int = 30,
    ) -> dict:
        """指数成分股近 N 日每日资金流合计（主力/超大单/大单 + 广度）"""
        ic = IndexConstituent.__table__
        s = Stock.__table__
        f = DailyStockFundFlow.__table__

        latest_subq = _latest_eff_subq(index_code)
        check = await db.execute(select(func.count()).select_from(latest_subq))
        if not check.scalar():
            return {"items": []}

        cutoff = (date.today() - timedelta(days=days + 5)).strftime("%Y-%m-%d")

        stmt = (
            select(
                f.c.trade_date,
                func.coalesce(func.sum(f.c.main_net_flow) / 1e8, 0).label("main_net_yi"),
                func.coalesce(func.sum(f.c.jumbo_net_flow) / 1e8, 0).label("jumbo_net_yi"),
                func.coalesce(func.sum(f.c.block_net_flow) / 1e8, 0).label("block_net_yi"),
                func.coalesce(func.count().filter(f.c.main_net_flow > 0), 0).label("positive_count"),
                func.count().label("total_count"),
            )
            .select_from(
                ic.join(s, s.c.ts_code.like(func.concat(ic.c.ts_code, ".%")) | (s.c.ts_code == ic.c.ts_code))
                .join(latest_subq, (ic.c.ts_code == latest_subq.c.ts_code) & (ic.c.eff_date == latest_subq.c.max_eff_date))
                .join(f, f.c.ts_code == s.c.ts_code)
            )
            .where(
                ic.c.index_code == index_code,
                f.c.trade_date >= cutoff,
            )
            .group_by(f.c.trade_date)
            .order_by(f.c.trade_date.asc())
        )
        result = await db.execute(stmt)
        items = []
        for r in result.mappings().all():
            total = r["total_count"] or 1
            items.append({
                "trade_date": FundFlowService._normalize_date(r["trade_date"]),
                "main_net_yi": round(float(r["main_net_yi"]), 2),
                "jumbo_net_yi": round(float(r["jumbo_net_yi"]), 2),
                "block_net_yi": round(float(r["block_net_yi"]), 2),
                "positive_pct": round(float(r["positive_count"] or 0) / total * 100, 1),
                "stock_count": total,
            })
        return {"items": items}

    # ═══════════════════════════════════════════════════════════════
    # 13. 指数列表
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_index_indices(db: AsyncSession) -> list[dict]:
        """返回可用的指数列表（从 index_info 表）"""
        tbl = IndexInfo.__table__
        stmt = select(
            tbl.c.index_code,
            tbl.c.index_name,
            tbl.c.full_name,
            tbl.c.publisher,
            tbl.c.constituent_count,
        ).order_by(tbl.c.index_code)
        result = await db.execute(stmt)
        return [
            {
                "index_code": r["index_code"],
                "index_name": r["index_name"],
                "full_name": r["full_name"] or "",
                "publisher": r["publisher"] or "",
                "constituent_count": r["constituent_count"] or 0,
            }
            for r in result.mappings().all()
        ]

    # ═══════════════════════════════════════════════════════════════
    # 12. 指数成分股资金流排名
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_index_constituents_flow(
        db: AsyncSession,
        index_code: str,
        trade_date: Optional[str] = None,
        sort: str = "main_net",
        limit: int = 100,
    ) -> dict:
        """指数成分股资金流排名 — JOIN index_constituents → stocks → daily_stock_fund_flow"""
        d = trade_date or await FundFlowService._get_latest_date(db)
        if not d:
            return {"trade_date": None, "items": []}

        f = DailyStockFundFlow.__table__
        s = Stock.__table__
        ic = IndexConstituent.__table__
        dl = Daily.__table__

        # Determine sort column
        sort_map = {
            "main_net": f.c.main_net_flow.desc(),
            "main_net_asc": f.c.main_net_flow.asc(),
            "jumbo": f.c.jumbo_net_flow.desc(),
            "block": f.c.block_net_flow.desc(),
            "weight": ic.c.weight.desc().nulls_last(),
        }
        order_by = sort_map.get(sort, sort_map["main_net"])

        # Get latest eff_date per stock for this index
        latest_subq = _latest_eff_subq(index_code)
        check = await db.execute(select(func.count()).select_from(latest_subq))
        if not check.scalar():
            return {"trade_date": d, "items": []}

        stmt = (
            select(
                f.c.ts_code,
                s.c.name.label("stock_name"),
                s.c.industry_l1.label("industry_name"),
                ic.c.weight,
                f.c.main_net_flow,
                f.c.jumbo_net_flow,
                f.c.block_net_flow,
                f.c.mid_net_flow,
                f.c.small_net_flow,
                f.c.main_in_flow,
                f.c.main_out_flow,
                f.c.retail_in_flow,
                f.c.retail_out_flow,
                f.c.main_inflow_circ_rate,
                f.c.main_inflow_rank,
                f.c.close_price,
                dl.c.pre_close,
            )
            .select_from(
                ic.join(s, s.c.ts_code.like(func.concat(ic.c.ts_code, ".%")) | (s.c.ts_code == ic.c.ts_code))
                .join(latest_subq, (ic.c.ts_code == latest_subq.c.ts_code) & (ic.c.eff_date == latest_subq.c.max_eff_date))
                .join(f, f.c.ts_code == s.c.ts_code)
                .join(dl, (dl.c.ts_code == s.c.ts_code) & (dl.c.trade_date == f.c.trade_date), isouter=True)
            )
            .where(
                ic.c.index_code == index_code,
                f.c.trade_date == d,
            )
            .order_by(order_by)
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.mappings().all()

        # Compute real 5d/10d/20d rolling sums
        ts_codes = [r["ts_code"] for r in rows]
        rolling = await FundFlowService._compute_rolling_sums(db, ts_codes, [d])

        items = []
        for r in rows:
            ts = r["ts_code"]
            r5 = rolling.get(ts, {})
            close = float(r["close_price"] or 0)
            pre_close = float(r["pre_close"] or 0)
            pct_change = round((close - pre_close) / pre_close * 100, 2) if pre_close else 0
            items.append({
                "ts_code": r["ts_code"],
                "stock_name": r["stock_name"] or "",
                "industry_name": r["industry_name"] or "",
                "weight": float(r["weight"] or 0),
                "main_net_flow": float(r["main_net_flow"] or 0),
                "jumbo_net_flow": float(r["jumbo_net_flow"] or 0),
                "block_net_flow": float(r["block_net_flow"] or 0),
                "mid_net_flow": float(r["mid_net_flow"] or 0),
                "small_net_flow": float(r["small_net_flow"] or 0),
                "main_in_flow": float(r["main_in_flow"] or 0),
                "main_out_flow": float(r["main_out_flow"] or 0),
                "retail_in_flow": float(r["retail_in_flow"] or 0),
                "retail_out_flow": float(r["retail_out_flow"] or 0),
                "main_net_flow_5d": r5.get(f"{d}|5d", 0),
                "main_net_flow_10d": r5.get(f"{d}|10d", 0),
                "main_net_flow_20d": r5.get(f"{d}|20d", 0),
                "main_inflow_circ_rate": float(r["main_inflow_circ_rate"] or 0),
                "main_inflow_rank": r["main_inflow_rank"],
                "close_price": close,
                "pct_change": pct_change,
            })
        return {"trade_date": FundFlowService._normalize_date(d), "items": items}

    # ═══════════════════════════════════════════════════════════════
    # 13. 指数成分股多股资金流趋势（批量）
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_index_multi_stock_trend(
        db: AsyncSession,
        index_code: str,
        days: int = 30,
        top_n: int = 5,
    ) -> dict:
        """Top N 成分股的多日资金流趋势 — 先找 Top N，再批量查趋势"""
        ic = IndexConstituent.__table__
        s = Stock.__table__
        f = DailyStockFundFlow.__table__

        # Get latest eff_date per stock for this index
        latest_subq = _latest_eff_subq(index_code)
        check = await db.execute(select(func.count()).select_from(latest_subq))
        if not check.scalar():
            return {"trade_date": "", "days": days, "stocks": []}

        # Get latest trade_date
        d = await FundFlowService._get_latest_date(db)
        if not d:
            return {"trade_date": "", "days": days, "stocks": []}

        # Find top N constituents by main_net_flow (latest date)
        top_stmt = (
            select(
                f.c.ts_code,
                s.c.name.label("stock_name"),
            )
            .select_from(
                ic.join(s, s.c.ts_code.like(func.concat(ic.c.ts_code, ".%")) | (s.c.ts_code == ic.c.ts_code))
                .join(latest_subq, (ic.c.ts_code == latest_subq.c.ts_code) & (ic.c.eff_date == latest_subq.c.max_eff_date))
                .join(f, f.c.ts_code == s.c.ts_code)
            )
            .where(
                ic.c.index_code == index_code,
                f.c.trade_date == d,
            )
            .order_by(f.c.main_net_flow.desc().nulls_last())
            .limit(top_n)
        )
        top_result = await db.execute(top_stmt)
        top_stocks = [(r["ts_code"], r["stock_name"] or "") for r in top_result.mappings().all()]
        if not top_stocks:
            return {"trade_date": FundFlowService._normalize_date(d), "days": days, "stocks": []}

        ts_codes = [ts for ts, _ in top_stocks]
        name_map = dict(top_stocks)

        # Batch trend query
        cutoff = (date.today() - timedelta(days=days + 5)).strftime("%Y-%m-%d")
        trend_stmt = (
            select(
                f.c.ts_code,
                f.c.trade_date,
                f.c.main_net_flow,
                f.c.jumbo_net_flow,
                f.c.block_net_flow,
                f.c.mid_net_flow,
                f.c.small_net_flow,
                f.c.close_price,
            )
            .where(
                f.c.ts_code.in_(ts_codes),
                f.c.trade_date >= cutoff,
            )
            .order_by(f.c.trade_date.asc())
        )
        trend_result = await db.execute(trend_stmt)

        # Group by ts_code
        stock_days: dict[str, list] = {ts: [] for ts in ts_codes}
        for r in trend_result.mappings().all():
            ts = r["ts_code"]
            if ts in stock_days:
                stock_days[ts].append({
                    "trade_date": FundFlowService._normalize_date(r["trade_date"]),
                    "main_net_flow": float(r["main_net_flow"] or 0),
                    "jumbo_net_flow": float(r["jumbo_net_flow"] or 0),
                    "block_net_flow": float(r["block_net_flow"] or 0),
                    "mid_net_flow": float(r["mid_net_flow"] or 0),
                    "small_net_flow": float(r["small_net_flow"] or 0),
                    "close_price": float(r["close_price"] or 0),
                })

        return {
            "trade_date": FundFlowService._normalize_date(d),
            "days": days,
            "stocks": [
                {"ts_code": ts, "stock_name": name_map.get(ts, ""), "days": stock_days.get(ts, [])}
                for ts in ts_codes
            ],
        }

    # ═══════════════════════════════════════════════════════════════
    # 14. 指数成分股行业资金流汇总
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_index_industry_summary(
        db: AsyncSession,
        index_code: str,
        trade_date: Optional[str] = None,
    ) -> dict:
        """指数成分股按行业聚合资金流"""
        d = trade_date or await FundFlowService._get_latest_date(db)
        if not d:
            return {"trade_date": None, "items": []}

        ic = IndexConstituent.__table__
        s = Stock.__table__
        f = DailyStockFundFlow.__table__

        latest_subq = _latest_eff_subq(index_code)
        check = await db.execute(select(func.count()).select_from(latest_subq))
        if not check.scalar():
            return {"trade_date": d, "items": []}

        stmt = (
            select(
                s.c.industry_l1.label("industry_name"),
                func.coalesce(func.sum(f.c.main_net_flow) / 1e8, 0).label("main_net_yi"),
                func.coalesce(func.sum(f.c.jumbo_net_flow) / 1e8, 0).label("jumbo_net_yi"),
                func.coalesce(func.sum(f.c.block_net_flow) / 1e8, 0).label("block_net_yi"),
                func.count().filter(f.c.main_net_flow > 0).label("up_count"),
                func.count().label("total_count"),
            )
            .select_from(
                ic.join(s, s.c.ts_code.like(func.concat(ic.c.ts_code, ".%")) | (s.c.ts_code == ic.c.ts_code))
                .join(latest_subq, (ic.c.ts_code == latest_subq.c.ts_code) & (ic.c.eff_date == latest_subq.c.max_eff_date))
                .join(f, f.c.ts_code == s.c.ts_code)
            )
            .where(
                ic.c.index_code == index_code,
                f.c.trade_date == d,
                s.c.industry_l1.isnot(None),
                s.c.industry_l1 != "",
            )
            .group_by(s.c.industry_l1)
            .order_by(func.sum(f.c.main_net_flow).desc())
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
                "positive_pct": round(float(r["up_count"] or 0) / total * 100, 1),
                "stock_count": total,
            })
        return {"trade_date": FundFlowService._normalize_date(d), "items": items}

    # ═══════════════════════════════════════════════════════════════
    # 15. 指数成分股 Treemap 数据（全部成分股，无 limit）
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_index_treemap(
        db: AsyncSession,
        index_code: str,
        trade_date: Optional[str] = None,
    ) -> dict:
        """全部指数成分股资金流 — treemap 用，需完整覆盖"""
        d = trade_date or await FundFlowService._get_latest_date(db)
        if not d:
            return {"trade_date": None, "items": []}

        ic = IndexConstituent.__table__
        s = Stock.__table__
        f = DailyStockFundFlow.__table__

        latest_subq = _latest_eff_subq(index_code)
        check = await db.execute(select(func.count()).select_from(latest_subq))
        if not check.scalar():
            return {"trade_date": d, "items": []}

        stmt = (
            select(
                f.c.ts_code,
                s.c.name.label("stock_name"),
                s.c.industry_l1.label("industry_name"),
                ic.c.weight,
                f.c.main_net_flow,
                f.c.jumbo_net_flow,
                f.c.block_net_flow,
                f.c.mid_net_flow,
                f.c.small_net_flow,
            )
            .select_from(
                ic.join(s, s.c.ts_code.like(func.concat(ic.c.ts_code, ".%")) | (s.c.ts_code == ic.c.ts_code))
                .join(latest_subq, (ic.c.ts_code == latest_subq.c.ts_code) & (ic.c.eff_date == latest_subq.c.max_eff_date))
                .join(f, f.c.ts_code == s.c.ts_code)
            )
            .where(
                ic.c.index_code == index_code,
                f.c.trade_date == d,
            )
            .order_by(f.c.main_net_flow.desc().nulls_last())
        )
        result = await db.execute(stmt)
        items = []
        for r in result.mappings().all():
            items.append({
                "ts_code": r["ts_code"],
                "stock_name": r["stock_name"] or "",
                "industry_name": r["industry_name"] or "",
                "weight": float(r["weight"] or 0),
                "main_net_flow": float(r["main_net_flow"] or 0),
                "jumbo_net_flow": float(r["jumbo_net_flow"] or 0),
                "block_net_flow": float(r["block_net_flow"] or 0),
                "mid_net_flow": float(r["mid_net_flow"] or 0),
                "small_net_flow": float(r["small_net_flow"] or 0),
            })
        return {"trade_date": FundFlowService._normalize_date(d), "items": items}

    # ═══════════════════════════════════════════════════════════════
    # 16. 指数盘中快照（Bar Chart Race 用）
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def get_index_snapshots(
        db: AsyncSession,
        index_code: str,
        trade_date: Optional[str] = None,
    ) -> dict:
        """查询 intraday_fund_snapshot，按 snapshot_time 分组返回

        对于复合指数（如 900009），其成分股快照数据存储在
        intraday_fund_snapshot 中但 index_code 字段为源指数代码。
        因此按成分股 ts_code 匹配，而非按 index_code 过滤。
        """
        # 1. 获取指数成分股 ts_code 列表（每只股票独立取最新 eff_date）
        latest_subq = _latest_eff_subq(index_code)
        check = await db.execute(select(func.count()).select_from(latest_subq))
        if not check.scalar():
            return {"trade_date": None, "snapshots": []}

        ic = IndexConstituent.__table__
        s = Stock.__table__
        const_stmt = (
            select(s.c.ts_code)
            .select_from(
                ic.join(s, s.c.ts_code.like(func.concat(ic.c.ts_code, ".%")) | (s.c.ts_code == ic.c.ts_code))
                .join(latest_subq, (ic.c.ts_code == latest_subq.c.ts_code) & (ic.c.eff_date == latest_subq.c.max_eff_date))
            )
            .where(ic.c.index_code == index_code)
        )
        const_result = await db.execute(const_stmt)
        const_codes = [r[0] for r in const_result.all()]
        if not const_codes:
            return {"trade_date": None, "snapshots": []}

        # 2. 确定查询日期
        if trade_date:
            d = trade_date
        else:
            d = await FundFlowService._get_latest_snapshot_date(db)
        if not d:
            return {"trade_date": None, "snapshots": []}

        # 3. 按成分股 ts_code 查询快照（不限 index_code）
        sql = text(
            """
            SELECT
                sn.snapshot_time,
                sn.ts_code,
                s2.name AS stock_name,
                sn.main_net_flow,
                sn.jumbo_net_flow,
                sn.block_net_flow,
                sn.main_net_flow_5d
            FROM intraday_fund_snapshot sn
            JOIN stocks s2 ON sn.ts_code = s2.ts_code
            WHERE sn.trade_date = :trade_date
              AND sn.ts_code = ANY(:ts_codes)
            ORDER BY sn.snapshot_time ASC, sn.main_net_flow DESC
            """
        )
        result = await db.execute(sql, {
            "ts_codes": const_codes,
            "trade_date": d,
        })

        # Collect all rows and unique ts_codes
        all_rows = list(result.mappings().all())
        ts_codes = list(set(r["ts_code"] for r in all_rows))

        # Compute 3-day cumulative: sum of last 2 completed trading days'
        # main_net_flow from daily data + current intraday main_net_flow.
        # This way the 3d total changes as today's intraday flow accumulates.
        prev_2d_flow: dict[str, float] = {}
        if ts_codes:
            f = DailyStockFundFlow.__table__
            # Find the 2 most recent trading days strictly before the snapshot date
            prev_dates_stmt = (
                select(f.c.trade_date)
                .where(f.c.trade_date < d, f.c.ts_code.in_(ts_codes))
                .distinct()
                .order_by(f.c.trade_date.desc())
                .limit(2)
            )
            prev_dates_result = await db.execute(prev_dates_stmt)
            prev_dates = [r[0] for r in prev_dates_result.all()]
            if prev_dates:
                prev_sum_stmt = (
                    select(
                        f.c.ts_code,
                        func.coalesce(func.sum(f.c.main_net_flow), 0).label("flow_2d"),
                    )
                    .where(f.c.ts_code.in_(ts_codes), f.c.trade_date.in_(prev_dates))
                    .group_by(f.c.ts_code)
                )
                prev_sum_result = await db.execute(prev_sum_stmt)
                prev_2d_flow = {
                    r["ts_code"]: float(r["flow_2d"] or 0)
                    for r in prev_sum_result.mappings().all()
                }

        # Group by snapshot_time, rounded to 3-minute buckets.
        # Cron runs every 3 minutes; stocks from different source indices
        # are saved within seconds of each other → merge into one frame.
        from datetime import datetime as _dt

        bucket_stocks: dict[str, dict[str, dict]] = {}
        for r in all_rows:
            raw_ts = r["snapshot_time"]
            if isinstance(raw_ts, str):
                parsed = _dt.fromisoformat(raw_ts.replace("Z", "+00:00"))
            else:
                parsed = raw_ts
            minute = parsed.minute // 3 * 3
            bucket = parsed.replace(second=0, microsecond=0, minute=minute)
            bucket_key = bucket.isoformat()

            if bucket_key not in bucket_stocks:
                bucket_stocks[bucket_key] = {}

            ts = r["ts_code"]
            main_net = float(r["main_net_flow"] or 0)
            main_net_flow_3d = prev_2d_flow.get(ts, 0) + main_net

            # Dedup within bucket: keep latest value per ts_code
            bucket_stocks[bucket_key][ts] = {
                "ts_code": ts,
                "stock_name": r["stock_name"] or "",
                "main_net_flow": main_net,
                "jumbo_net_flow": float(r["jumbo_net_flow"] or 0),
                "block_net_flow": float(r["block_net_flow"] or 0),
                "main_net_flow_5d": float(r["main_net_flow_5d"] or 0),
                "main_net_flow_3d": main_net_flow_3d,
            }

        # Forward-fill: carry last known values into buckets where a stock
        # has no fresh snap. This prevents stocks from disappearing between
        # sync cycles — e.g. a stock only in 900002 won't vanish at 10:39
        # while waiting for 900002's own sync, because its 10:36 snap from
        # the previous cycle carries forward.
        sorted_buckets = sorted(bucket_stocks.keys())
        prev: dict[str, dict] = {}
        for bk in sorted_buckets:
            current = bucket_stocks[bk]
            for ts, data in prev.items():
                if ts not in current:
                    current[ts] = dict(data)  # shallow copy, values are all immutable
            prev.update(current)

        snapshots = [
            {
                "snapshot_time": bucket_key,
                "stocks": sorted(
                    bucket_stocks[bucket_key].values(),
                    key=lambda x: x["main_net_flow"],
                    reverse=True,
                ),
            }
            for bucket_key in sorted_buckets
        ]

        return {"trade_date": FundFlowService._normalize_date(d), "snapshots": snapshots}
