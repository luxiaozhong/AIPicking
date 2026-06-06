"""市场热度服务 — Core 级别 SQL 查询"""
from typing import Optional
from sqlalchemy import select, func, case
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.stock_tables import (
    Daily, DailySectorFlow, DailyHotStock, DailyHotTheme,
    DailyNorthboundFlow, DailyDragonTiger, DailyDragonTigerSeat
)


class MarketHeatService:

    # ── 工具方法 ─────────────────────────────────────────────

    @staticmethod
    async def _get_latest_date_for(db: AsyncSession, table) -> Optional[str]:
        """获取指定表最新有数据的交易日"""
        stmt = select(func.max(table.trade_date))
        result = await db.execute(stmt)
        return result.scalar()

    # ── 概览 KPI ─────────────────────────────────────────────

    @staticmethod
    async def get_overview(db: AsyncSession, trade_date: Optional[str] = None) -> dict:
        """返回 4 个核心 KPI：市场温度、北向资金、涨跌比、领涨板块"""

        daily_date = trade_date or await MarketHeatService._get_latest_date_for(db, Daily.__table__.c)
        nb_date = trade_date or await MarketHeatService._get_latest_date_for(db, DailyNorthboundFlow.__table__.c)
        sector_date = trade_date or await MarketHeatService._get_latest_date_for(db, DailySectorFlow.__table__.c)

        if not daily_date:
            return {"trade_date": None, "temperature": None, "northbound": None,
                    "advance_decline": None, "leading_sectors": []}

        # 北向资金
        northbound = None
        if nb_date:
            nb_stmt = select(DailyNorthboundFlow.__table__).where(
                DailyNorthboundFlow.trade_date == nb_date
            )
            nb_result = await db.execute(nb_stmt)
            nb_row = nb_result.mappings().first()
            northbound = dict(nb_row) if nb_row else None

        # 涨跌比（用 daily 表的日期）
        adv_stmt = select(
            func.count().label("total"),
            func.sum(
                case((Daily.close > Daily.open, 1), else_=0)
            ).label("up_count"),
            func.sum(
                case((Daily.close < Daily.open, 1), else_=0)
            ).label("down_count"),
        ).where(Daily.trade_date == daily_date, ~Daily.ts_code.like("%.IDX"))
        adv_result = await db.execute(adv_stmt)
        adv_row = adv_result.mappings().first()
        adv = dict(adv_row) if adv_row else {"total": 0, "up_count": 0, "down_count": 0}

        # 领涨板块 Top 2
        leading = []
        # 领跌板块 Bottom 2
        lagging = []
        if sector_date:
            sector_stmt = select(DailySectorFlow.__table__).where(
                DailySectorFlow.trade_date == sector_date,
                DailySectorFlow.sector_type == "industry"
            ).order_by(DailySectorFlow.change_pct.desc()).limit(2)
            sector_result = await db.execute(sector_stmt)
            leading = [dict(r) for r in sector_result.mappings().all()]

            lagging_stmt = select(DailySectorFlow.__table__).where(
                DailySectorFlow.trade_date == sector_date,
                DailySectorFlow.sector_type == "industry"
            ).order_by(DailySectorFlow.change_pct.asc()).limit(2)
            lagging_result = await db.execute(lagging_stmt)
            lagging = [dict(r) for r in lagging_result.mappings().all()]

        # 计算市场温度
        temperature = await MarketHeatService._calc_temperature(
            northbound=northbound,
            adv=adv,
            date=daily_date,
            db=db,
        )

        def _fmt_sector(s):
            return {
                "sector_name": s["sector_name"],
                "change_pct": s["change_pct"],
                "main_net_yi": s["main_net_yi"],
            }

        # 板块温度（尝试从持久化表读取，失败则跳过）
        board_temps = await MarketHeatService.get_board_temperatures(db, daily_date)

        return {
            "trade_date": daily_date,
            "temperature": temperature,
            "northbound": northbound,
            "advance_decline": adv,
            "leading_sectors": [_fmt_sector(s) for s in leading],
            "lagging_sectors": [_fmt_sector(s) for s in lagging],
            "board_temperatures": board_temps,
        }

    # ── 板块资金流 ────────────────────────────────────────────

    @staticmethod
    async def get_sectors(
        db: AsyncSession, trade_date: Optional[str], sector_type: str = "industry"
    ) -> list[dict]:
        date = trade_date or await MarketHeatService._get_latest_date_for(db, DailySectorFlow.__table__.c)
        if not date:
            return []

        async def _query(d: str) -> list[dict]:
            stmt = select(DailySectorFlow.__table__).where(
                DailySectorFlow.trade_date == d,
                DailySectorFlow.sector_type == sector_type,
            ).order_by(DailySectorFlow.net_inflow.desc())
            result = await db.execute(stmt)
            return [dict(r) for r in result.mappings().all()]

        items = await _query(date)
        # 指定日期无数据时自动回退到最新
        if not items and trade_date:
            fallback = await MarketHeatService._get_latest_date_for(db, DailySectorFlow.__table__.c)
            if fallback and fallback != date:
                items = await _query(fallback)
        return items

    @staticmethod
    async def get_sector_detail(
        db: AsyncSession, sector_code: str, trade_date: Optional[str], days: int = 10
    ) -> dict:
        """板块详情：近 N 日资金流趋势 + 成分股 Top5"""
        date = trade_date or await MarketHeatService._get_latest_date_for(db, DailySectorFlow.__table__.c)
        if not date:
            return {"trend": [], "stocks": [], "info": None}

        async def _fetch(d: str) -> tuple:
            info_stmt = select(DailySectorFlow.__table__).where(
                DailySectorFlow.trade_date == d,
                DailySectorFlow.sector_code == sector_code,
            )
            info_result = await db.execute(info_stmt)
            info_row = info_result.mappings().first()
            info = dict(info_row) if info_row else None

            trend_stmt = select(DailySectorFlow.__table__).where(
                DailySectorFlow.sector_code == sector_code,
                DailySectorFlow.trade_date <= d,
            ).order_by(DailySectorFlow.trade_date.desc()).limit(days)
            trend_result = await db.execute(trend_stmt)
            trend = [dict(r) for r in reversed(list(trend_result.mappings().all()))]
            return info, trend

        info, trend = await _fetch(date)

        # 指定日期无数据时自动回退到最新
        if not info and trade_date:
            fallback = await MarketHeatService._get_latest_date_for(db, DailySectorFlow.__table__.c)
            if fallback and fallback != date:
                info, trend = await _fetch(fallback)
                date = fallback

        # 成分股 Top5（从 daily 表查当天该板块涨幅最大的 stock）
        # 成分股 Top5（daily 表已统一为 YYYY-MM-DD）
        top5 = []
        if info:
            import re
            base_name = re.sub(r'[Ⅰ-Ⅷ]+$', '', info["sector_name"]).strip()
            from ..models.stock_tables import Stock
            stock_stmt = (
                select(Stock.ts_code, Stock.name, Daily.close, Daily.open)
                .join(Daily, Stock.ts_code == Daily.ts_code)
                .where(
                    Daily.trade_date == date,
                    (Stock.industry_l2 == info["sector_name"]) |
                    (Stock.industry_l1 == info["sector_name"]) |
                    (Stock.industry_l2 == base_name) |
                    (Stock.industry_l1 == base_name) |
                    Stock.concepts.ilike(f"%{base_name}%"),
                )
                .order_by(
                    ((Daily.close - Daily.open) / func.nullif(Daily.open, 0)).desc()
                )
                .limit(5)
            )
            stock_result = await db.execute(stock_stmt)
            top5 = [
                {"ts_code": r.ts_code, "name": r.name, "close": r.close, "open": r.open}
                for r in stock_result.all()
            ]

        return {"info": info, "trend": trend, "stocks": top5}

    # ── 主题 ─────────────────────────────────────────────────

    @staticmethod
    async def get_themes(db: AsyncSession, trade_date: Optional[str], limit: int = 20) -> list[dict]:
        date = trade_date or await MarketHeatService._get_latest_date_for(db, DailyHotTheme.__table__.c)
        if not date:
            return []
        # date is already YYYY-MM-DD (all tables unified)
        stmt = select(DailyHotTheme.__table__).where(
            DailyHotTheme.trade_date == date
        ).order_by(DailyHotTheme.stock_count.desc()).limit(limit)
        result = await db.execute(stmt)
        return [dict(r) for r in result.mappings().all()]

    @staticmethod
    async def get_theme_detail(
        db: AsyncSession, theme_name: str, trade_date: Optional[str]
    ) -> list[dict]:
        """主题关联股票：从 hot_stocks 的 reason 字段模糊匹配"""
        date = trade_date or await MarketHeatService._get_latest_date_for(db, DailyHotStock.__table__.c)
        if not date:
            return []
        # date is already YYYY-MM-DD (all tables unified)
        stmt = select(DailyHotStock.__table__).where(
            DailyHotStock.trade_date == date,
            DailyHotStock.reason.ilike(f"%{theme_name}%"),
        ).order_by(DailyHotStock.sort_order.asc())
        result = await db.execute(stmt)
        items = [dict(r) for r in result.mappings().all()]
        return await MarketHeatService._enrich_with_daily(db, items, date)

    # ── 数据增强 ─────────────────────────────────────────────

    @staticmethod
    async def _enrich_with_daily(
        db: AsyncSession, items: list[dict], yyyymmdd_date: str
    ) -> list[dict]:
        """从 daily 表和 stocks 表补齐收盘价、涨幅、换手率"""
        if not items:
            return items

        daily_date = yyyymmdd_date  # daily 表已统一为 YYYY-MM-DD
        codes = [it["stock_code"] for it in items]
        from ..models.stock_tables import Stock

        # 将纯数字 code 转为 ts_code: 6xxxxx→SH, 其他→SZ
        def _to_ts(code: str) -> str:
            if code.startswith(("6", "9")):
                return f"{code}.SH"
            return f"{code}.SZ"

        code_to_ts = {c: _to_ts(c) for c in codes}
        ts_codes = list(code_to_ts.values())

        # 流通股本
        stock_stmt = select(Stock.ts_code, Stock.float_shares).where(
            Stock.ts_code.in_(ts_codes)
        )
        stock_result = await db.execute(stock_stmt)
        ts_to_shares = {r.ts_code: (r.float_shares or 0) for r in stock_result.all()}

        # 当日行情 + 前一日收盘价
        if ts_codes:
            daily_alias = Daily.__table__.alias()
            prev_alias = Daily.__table__.alias()

            stmt = (
                select(
                    daily_alias.c.ts_code,
                    daily_alias.c.close,
                    daily_alias.c.open,
                    daily_alias.c.vol,
                    func.coalesce(prev_alias.c.close, daily_alias.c.open).label("prev_close"),
                )
                .select_from(daily_alias)
                .outerjoin(
                    prev_alias,
                    (daily_alias.c.ts_code == prev_alias.c.ts_code)
                    & (prev_alias.c.trade_date == (
                        select(func.max(Daily.__table__.c.trade_date))
                        .where(
                            (Daily.__table__.c.ts_code == daily_alias.c.ts_code)
                            & (Daily.__table__.c.trade_date < daily_date)
                        )
                        .scalar_subquery()
                    )),
                )
                .where(
                    daily_alias.c.trade_date == daily_date,
                    daily_alias.c.ts_code.in_(ts_codes),
                )
            )
            result = await db.execute(stmt)
            daily_map = {}
            for r in result.mappings().all():
                d = dict(r)
                code = d.pop("ts_code")
                daily_map[code] = d
        else:
            daily_map = {}

        for item in items:
            code = item["stock_code"]
            ts = code_to_ts.get(code)
            d = daily_map.get(ts, {}) if ts else {}
            item["close"] = d.get("close")
            item["open"] = d.get("open")
            if d.get("close") and d.get("prev_close") and d["prev_close"] != 0:
                item["change_pct"] = round(
                    (d["close"] - d["prev_close"]) / d["prev_close"] * 100, 2
                )
            vol = d.get("vol") or 0
            shares = ts_to_shares.get(ts, 0) or 0 if ts else 0
            if vol and shares:
                item["turnover_pct"] = round(vol * 100 / shares * 100, 2)

        return items

    # ── 热门股票 / 龙虎榜 / 北向 ──────────────────────────────

    @staticmethod
    async def get_hot_stocks(
        db: AsyncSession, trade_date: Optional[str], page: int = 1, page_size: int = 20
    ) -> dict:
        date = trade_date or await MarketHeatService._get_latest_date_for(db, DailyHotStock.__table__.c)
        if not date:
            return {"items": [], "total": 0}
        # date is already YYYY-MM-DD (all tables unified)

        # 总数
        count_stmt = select(func.count()).select_from(DailyHotStock.__table__).where(
            DailyHotStock.trade_date == date
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = select(DailyHotStock.__table__).where(
            DailyHotStock.trade_date == date
        ).order_by(DailyHotStock.sort_order.asc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        result = await db.execute(stmt)
        items = [dict(r) for r in result.mappings().all()]
        items = await MarketHeatService._enrich_with_daily(db, items, date)
        return {"items": items, "total": total}

    @staticmethod
    async def get_dragon_tiger(
        db: AsyncSession, trade_date: Optional[str], page: int = 1, page_size: int = 20
    ) -> dict:
        date = trade_date or await MarketHeatService._get_latest_date_for(db, DailyDragonTiger.__table__.c)
        if not date:
            return {"items": [], "total": 0}
        # date is already YYYY-MM-DD (all tables unified)

        count_stmt = select(func.count()).select_from(DailyDragonTiger.__table__).where(
            DailyDragonTiger.trade_date == date
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = select(DailyDragonTiger.__table__).where(
            DailyDragonTiger.trade_date == date
        ).order_by(DailyDragonTiger.net_buy_wan.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        result = await db.execute(stmt)
        items = [dict(r) for r in result.mappings().all()]

        # 批量加载席位明细（避免 N+1）
        if items:
            codes = [item["stock_code"] for item in items]
            seat_stmt = select(DailyDragonTigerSeat.__table__).where(
                DailyDragonTigerSeat.trade_date == date,
                DailyDragonTigerSeat.stock_code.in_(codes),
            ).order_by(DailyDragonTigerSeat.stock_code, DailyDragonTigerSeat.seat_type, DailyDragonTigerSeat.rank)
            seat_result = await db.execute(seat_stmt)
            all_seats = [dict(s) for s in seat_result.mappings().all()]

            # 按 stock_code 分组
            seats_by_code: dict[str, list[dict]] = {}
            for seat in all_seats:
                code = seat["stock_code"]
                seats_by_code.setdefault(code, []).append(seat)

            for item in items:
                item["seats"] = seats_by_code.get(item["stock_code"], [])

        return {"items": items, "total": total}

    @staticmethod
    async def get_northbound(db: AsyncSession, days: int = 30) -> list[dict]:
        stmt = select(DailyNorthboundFlow.__table__).order_by(
            DailyNorthboundFlow.__table__.c.trade_date.asc()
        ).limit(days)
        result = await db.execute(stmt)
        return [dict(r) for r in result.mappings().all()]

    @staticmethod
    async def get_available_dates(db: AsyncSession, days: int = 20) -> list[str]:
        """有数据的交易日列表（从 daily 表取，覆盖最广）"""
        stmt = (
            select(Daily.__table__.c.trade_date)
            .distinct()
            .order_by(Daily.__table__.c.trade_date.desc())
            .limit(days)
        )
        result = await db.execute(stmt)
        return [r[0] for r in result.all()]

    # ── 市场温度计算 ─────────────────────────────────────────

    @staticmethod
    def _score_to_level(total_score: int) -> str:
        if total_score <= 30:
            return "冰点"
        elif total_score <= 50:
            return "偏冷"
        elif total_score <= 70:
            return "中性"
        elif total_score <= 85:
            return "偏热"
        return "过热"

    @staticmethod
    async def _calc_capital_score(northbound: Optional[dict]) -> int:
        """1. 资金面 (20): 北向净流入方向+规模"""
        if northbound and northbound.get("total_net_yi") is not None:
            net = northbound["total_net_yi"]
            if net > 50:
                return 20
            elif net > 20:
                return 17
            elif net > 0:
                return 14
            elif net > -20:
                return 7
            elif net > -50:
                return 3
            else:
                return 0
        return 10  # 无数据 → 中性

    @staticmethod
    def _calc_breadth_score(adv: dict) -> int:
        """2. 涨跌结构 (20): 上涨占比"""
        total = adv.get("total", 0) or 0
        up = adv.get("up_count", 0) or 0
        ratio = up / total if total > 0 else 0.5
        return min(20, round(ratio * 25))  # 80%+ = 满分

    @staticmethod
    async def _calc_sentiment_score(db: AsyncSession, date: str) -> int:
        """3. 情绪面 (20): 涨停/跌停比 + 活跃度

        通过 daily 表自连接计算真实日涨跌幅 (close - prev_close) / prev_close，
        统计涨停(>=9.8%)和跌停(<=-9.8%)数量。
        """
        # 自连接获取 prev_close，与 _enrich_with_daily 中模式一致
        daily_alias = Daily.__table__.alias()
        prev_alias = Daily.__table__.alias()

        change_expr = (
            (daily_alias.c.close - func.coalesce(prev_alias.c.close, daily_alias.c.open))
            / func.nullif(func.coalesce(prev_alias.c.close, daily_alias.c.open), 0)
            * 100
        )

        stmt = select(
            func.count().label("total"),
            func.sum(case((change_expr >= 9.8, 1), else_=0)).label("limit_up"),
            func.sum(case((change_expr <= -9.8, 1), else_=0)).label("limit_down"),
        ).select_from(daily_alias).outerjoin(
            prev_alias,
            (daily_alias.c.ts_code == prev_alias.c.ts_code)
            & (prev_alias.c.trade_date == (
                select(func.max(Daily.__table__.c.trade_date))
                .where(
                    (Daily.__table__.c.ts_code == daily_alias.c.ts_code)
                    & (Daily.__table__.c.trade_date < date)
                )
                .scalar_subquery()
            )),
        ).where(
            daily_alias.c.trade_date == date,
            ~daily_alias.c.ts_code.like("%.IDX"),
        )

        result = await db.execute(stmt)
        row = result.mappings().first()
        if not row:
            return 10

        limit_up = row.get("limit_up", 0) or 0
        limit_down = row.get("limit_down", 0) or 0
        total_limits = limit_up + limit_down

        if total_limits == 0:
            return 10  # 无涨跌停 → 中性

        # 涨跌停方向比
        limit_ratio = limit_up / total_limits

        # 活跃度因子：触及涨跌停的股票越多，市场越活跃
        activity_factor = min(1.0, total_limits / 100.0)

        # 方向分 + 活跃度加权
        sentiment_raw = limit_ratio * 20
        sentiment = round(sentiment_raw * (0.5 + 0.5 * activity_factor))
        return max(0, min(20, sentiment))

    @staticmethod
    async def _calc_concentration_score(db: AsyncSession, date: str) -> int:
        """4. 板块集中度 (20): 头部 3 行业资金流入占比

        适度集中最好（30%-50%），过度集中或过度分散都不健康。
        """
        stmt = select(DailySectorFlow.__table__.c.net_inflow).where(
            DailySectorFlow.trade_date == date,
            DailySectorFlow.sector_type == "industry",
        )
        result = await db.execute(stmt)
        inflows = [abs(r[0]) for r in result.all() if r[0] is not None]

        if not inflows:
            return 10

        total_abs = sum(inflows)
        if total_abs == 0:
            return 10

        top3_abs = sum(sorted(inflows, reverse=True)[:3])
        concentration = top3_abs / total_abs  # 0.0 - 1.0

        # 倒 U 型评分：适度集中最好
        if 0.30 <= concentration <= 0.50:
            return 20
        elif 0.20 <= concentration < 0.30 or 0.50 < concentration <= 0.60:
            return 15
        elif 0.10 <= concentration < 0.20 or 0.60 < concentration <= 0.70:
            return 10
        elif 0.0 < concentration < 0.10 or 0.70 < concentration <= 0.80:
            return 5
        else:  # > 0.80 过度集中
            return 0

    @staticmethod
    async def _calc_continuity_score(db: AsyncSession, date: str) -> int:
        """5. 热度延续 (20): 热门主题与前一日 Jaccard 相似度"""
        # 当日主题
        today_stmt = select(DailyHotTheme.theme_name).where(
            DailyHotTheme.trade_date == date,
        )
        today_result = await db.execute(today_stmt)
        today_themes = {r[0] for r in today_result.all()}

        if not today_themes:
            return 10

        # 前一交易日
        prev_stmt = select(func.max(DailyHotTheme.trade_date)).where(
            DailyHotTheme.trade_date < date,
        )
        prev_date_result = await db.execute(prev_stmt)
        prev_date = prev_date_result.scalar()

        if not prev_date:
            return 10  # 无前一日数据 → 中性

        yesterday_stmt = select(DailyHotTheme.theme_name).where(
            DailyHotTheme.trade_date == prev_date,
        )
        yesterday_result = await db.execute(yesterday_stmt)
        yesterday_themes = {r[0] for r in yesterday_result.all()}

        if not yesterday_themes:
            return 10

        intersection = today_themes & yesterday_themes
        union = today_themes | yesterday_themes
        jaccard = len(intersection) / len(union) if union else 0

        return round(jaccard * 20)

    @staticmethod
    async def _calc_temperature(
        northbound: Optional[dict],
        adv: dict,
        date: str,
        db: AsyncSession,
    ) -> dict:
        """5 维度综合评分，每维度 0-20 分，满分 100"""
        scores = {}

        scores["capital"] = await MarketHeatService._calc_capital_score(northbound)
        scores["breadth"] = MarketHeatService._calc_breadth_score(adv)
        scores["sentiment"] = await MarketHeatService._calc_sentiment_score(db, date)
        scores["concentration"] = await MarketHeatService._calc_concentration_score(db, date)
        scores["continuity"] = await MarketHeatService._calc_continuity_score(db, date)

        total_score = sum(scores.values())
        level = MarketHeatService._score_to_level(total_score)

        return {
            "score": total_score,
            "level": level,
            "dimensions": scores,
        }

    @staticmethod
    async def save_temperature(db: AsyncSession, trade_date: str) -> dict:
        """计算并持久化指定交易日市场温度（幂等）"""
        from ..models.stock_tables import DailyMarketTemperature

        # 获取概览所需的基础数据
        nb_stmt = select(DailyNorthboundFlow.__table__).where(
            DailyNorthboundFlow.trade_date == trade_date
        )
        nb_result = await db.execute(nb_stmt)
        nb_row = nb_result.mappings().first()
        northbound = dict(nb_row) if nb_row else None

        adv_stmt = select(
            func.count().label("total"),
            func.sum(case((Daily.close > Daily.open, 1), else_=0)).label("up_count"),
            func.sum(case((Daily.close < Daily.open, 1), else_=0)).label("down_count"),
        ).where(Daily.trade_date == trade_date, ~Daily.ts_code.like("%.IDX"))
        adv_result = await db.execute(adv_stmt)
        adv_row = adv_result.mappings().first()
        adv = dict(adv_row) if adv_row else {"total": 0, "up_count": 0, "down_count": 0}

        temperature = await MarketHeatService._calc_temperature(
            northbound=northbound, adv=adv, date=trade_date, db=db,
        )

        dims = temperature["dimensions"]

        # 幂等 upsert（Core 级别）
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(DailyMarketTemperature.__table__).values(
            trade_date=trade_date,
            score=temperature["score"],
            level=temperature["level"],
            capital_score=dims["capital"],
            breadth_score=dims["breadth"],
            sentiment_score=dims["sentiment"],
            concentration_score=dims["concentration"],
            continuity_score=dims["continuity"],
        ).on_conflict_do_update(
            constraint="uq_market_temp_date",
            set_=dict(
                score=temperature["score"],
                level=temperature["level"],
                capital_score=dims["capital"],
                breadth_score=dims["breadth"],
                sentiment_score=dims["sentiment"],
                concentration_score=dims["concentration"],
                continuity_score=dims["continuity"],
            ),
        )
        await db.execute(stmt)
        await db.commit()

        return temperature

    @staticmethod
    async def get_temperature_history(
        db: AsyncSession, days: int = 60
    ) -> list[dict]:
        """近 N 日市场温度历史"""
        from ..models.stock_tables import DailyMarketTemperature

        stmt = (
            select(DailyMarketTemperature.__table__)
            .order_by(DailyMarketTemperature.__table__.c.trade_date.desc())
            .limit(days)
        )
        result = await db.execute(stmt)
        rows = result.mappings().all()

        history = []
        for row in reversed(list(rows)):
            r = dict(row)
            history.append({
                "trade_date": r["trade_date"],
                "score": r["score"],
                "level": r["level"],
                "dimensions": {
                    "capital": r["capital_score"],
                    "breadth": r["breadth_score"],
                    "sentiment": r["sentiment_score"],
                    "concentration": r["concentration_score"],
                    "continuity": r["continuity_score"],
                },
            })
        return history

    # ── 四大指数板块温度 ────────────────────────────────────

    # 板块定义：board_code → (board_name, PostgreSQL ts_code 正则)
    BOARD_DEFINITIONS = [
        ("sh_main",  "上证主板", r"^[56]0[0-5]"),
        ("sh_star",  "科创板",   r"^688"),
        ("sz_main",  "深证主板", r"^00[0-3]"),
        ("sz_chi",   "创业板",   r"^30[01]"),
    ]

    @staticmethod
    async def _calc_board_temp(
        db: AsyncSession,
        date: str,
        ts_pattern: str,
    ) -> dict:
        """计算单个板块的温度（3 维度 × 100 分）"""
        from sqlalchemy import text as sa_text

        daily_alias = Daily.__table__.alias()
        prev_alias = Daily.__table__.alias()

        change_expr = (
            (daily_alias.c.close - func.coalesce(prev_alias.c.close, daily_alias.c.open))
            / func.nullif(func.coalesce(prev_alias.c.close, daily_alias.c.open), 0)
            * 100
        )

        # 涨跌结构 + 情绪面 + 成交量
        stmt = select(
            func.count().label("total"),
            func.sum(case((daily_alias.c.close > daily_alias.c.open, 1), else_=0)).label("up_count"),
            func.sum(case((daily_alias.c.close < daily_alias.c.open, 1), else_=0)).label("down_count"),
            func.sum(case((change_expr >= 9.8, 1), else_=0)).label("limit_up"),
            func.sum(case((change_expr <= -9.8, 1), else_=0)).label("limit_down"),
            func.sum(daily_alias.c.amount).label("total_amount"),
        ).select_from(daily_alias).outerjoin(
            prev_alias,
            (daily_alias.c.ts_code == prev_alias.c.ts_code)
            & (prev_alias.c.trade_date == (
                select(func.max(Daily.__table__.c.trade_date))
                .where(
                    (Daily.__table__.c.ts_code == daily_alias.c.ts_code)
                    & (Daily.__table__.c.trade_date < date)
                )
                .scalar_subquery()
            )),
        ).where(
            daily_alias.c.trade_date == date,
            ~daily_alias.c.ts_code.like("%.IDX"),
            sa_text(f"daily_1.ts_code ~ '{ts_pattern}'"),
        )

        result = await db.execute(stmt)
        row = result.mappings().first()
        if not row or (row.get("total", 0) or 0) == 0:
            return {"score": 50, "level": "中性",
                    "dimensions": {"breadth": 20, "sentiment": 15, "volume": 15}}

        total = row["total"] or 0
        up = row["up_count"] or 0
        limit_up = row["limit_up"] or 0
        limit_down = row["limit_down"] or 0
        total_amount = row["total_amount"] or 0

        # 1. 涨跌结构 (0-40)
        ratio = up / total if total > 0 else 0.5
        breadth = min(40, round(ratio * 50))

        # 2. 情绪面 (0-30)
        total_limits = limit_up + limit_down
        if total_limits > 0:
            limit_ratio = limit_up / total_limits
            activity = min(1.0, total_limits / (total * 0.03))  # 活跃度：3%触及涨跌停即满分
            sentiment = round(limit_ratio * 30 * (0.5 + 0.5 * activity))
        else:
            sentiment = 15

        # 3. 量能活跃度 (0-30): 当日成交额 vs 近20日日均成交额
        # 先按日汇总板块成交额，再取20日均值
        daily_sum_subq = (
            select(
                Daily.__table__.c.trade_date,
                func.sum(Daily.__table__.c.amount).label("daily_total"),
            )
            .where(
                Daily.__table__.c.trade_date < date,
                sa_text(f"daily.ts_code ~ '{ts_pattern}'"),
                ~Daily.__table__.c.ts_code.like("%.IDX"),
            )
            .group_by(Daily.__table__.c.trade_date)
            .order_by(Daily.__table__.c.trade_date.desc())
            .limit(20)
        ).subquery()
        avg_amt_stmt = select(func.avg(daily_sum_subq.c.daily_total))
        avg_result = await db.execute(avg_amt_stmt)
        avg_amount = avg_result.scalar() or total_amount

        if avg_amount and avg_amount > 0 and total_amount > 0:
            vol_ratio = total_amount / avg_amount
            volume = min(30, round(vol_ratio * 15))
        else:
            volume = 15

        scores = {"breadth": breadth, "sentiment": max(0, min(30, sentiment)), "volume": max(0, min(30, volume))}
        total_score = sum(scores.values())
        level = MarketHeatService._score_to_level(total_score)

        return {"score": total_score, "level": level, "dimensions": scores}

    @staticmethod
    async def save_board_temperatures(db: AsyncSession, trade_date: str) -> list[dict]:
        """计算并持久化四大板块温度（幂等）"""
        from ..models.stock_tables import DailyBoardTemperature
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        results = []
        for board_code, board_name, ts_pattern in MarketHeatService.BOARD_DEFINITIONS:
            temp = await MarketHeatService._calc_board_temp(db, trade_date, ts_pattern)
            dims = temp["dimensions"]

            stmt = pg_insert(DailyBoardTemperature.__table__).values(
                trade_date=trade_date,
                board_code=board_code,
                board_name=board_name,
                score=temp["score"],
                level=temp["level"],
                breadth_score=dims["breadth"],
                sentiment_score=dims["sentiment"],
                volume_score=dims["volume"],
            ).on_conflict_do_update(
                constraint="uq_board_temp",
                set_=dict(
                    score=temp["score"],
                    level=temp["level"],
                    breadth_score=dims["breadth"],
                    sentiment_score=dims["sentiment"],
                    volume_score=dims["volume"],
                ),
            )
            await db.execute(stmt)
            results.append({
                "board_code": board_code,
                "board_name": board_name,
                **temp,
            })

        await db.commit()
        return results

    @staticmethod
    async def get_board_temperatures(
        db: AsyncSession, trade_date: Optional[str] = None
    ) -> list[dict]:
        """获取指定日期的板块温度（默认最新）"""
        from ..models.stock_tables import DailyBoardTemperature

        if not trade_date:
            stmt = select(func.max(DailyBoardTemperature.__table__.c.trade_date))
            result = await db.execute(stmt)
            trade_date = result.scalar()
        if not trade_date:
            return []

        stmt = select(DailyBoardTemperature.__table__).where(
            DailyBoardTemperature.__table__.c.trade_date == trade_date,
        ).order_by(DailyBoardTemperature.__table__.c.board_code)
        result = await db.execute(stmt)
        rows = result.mappings().all()

        return [
            {
                "board_code": r["board_code"],
                "board_name": r["board_name"],
                "score": r["score"],
                "level": r["level"],
                "dimensions": {
                    "breadth": r["breadth_score"],
                    "sentiment": r["sentiment_score"],
                    "volume": r["volume_score"],
                },
            }
            for r in rows
        ]

    # ── 涨跌分布 ─────────────────────────────────────────────

    @staticmethod
    async def get_change_distribution(
        db: AsyncSession, trade_date: Optional[str] = None
    ) -> list[dict]:
        """涨跌幅度分段统计（用于柱状图）"""
        date = trade_date or await MarketHeatService._get_latest_date_for(db, Daily.__table__.c)
        if not date:
            return []

        # 用当日 (close-open)/open 计算日内涨跌
        change_expr = (Daily.close - Daily.open) / func.nullif(Daily.open, 0) * 100

        buckets = [
            (-100, -10, "-10%以下"),
            (-10, -5, "-10%~-5%"),
            (-5, -2, "-5%~-2%"),
            (-2, 0, "-2%~0%"),
            (0, 2, "0%~2%"),
            (2, 5, "2%~5%"),
            (5, 10, "5%~10%"),
            (10, 100, "10%以上"),
        ]

        result = []
        for lo, hi, label in buckets:
            stmt = select(func.count()).select_from(Daily.__table__).where(
                Daily.trade_date == date,
                ~Daily.ts_code.like("%.IDX"),
                change_expr >= lo,
                change_expr < hi,
            )
            cnt = (await db.execute(stmt)).scalar() or 0
            result.append({"label": label, "lo": lo, "hi": hi, "count": cnt})

        return result

    # ── 领涨板块个股 ──────────────────────────────────────────

    @staticmethod
    async def get_leading_sector_stocks(
        db: AsyncSession, sector_name: str, trade_date: Optional[str] = None,
        sort_order: str = "desc",
    ) -> list[dict]:
        """板块内个股 Top 15：sort_order='desc' 领涨（涨幅靠前），'asc' 领跌（跌幅靠前）"""
        date = trade_date or await MarketHeatService._get_latest_date_for(db, Daily.__table__.c)
        if not date:
            return []

        from ..models.stock_tables import Stock

        # 去除 Ⅰ/Ⅱ/Ⅲ 等罗马数字后缀
        import re
        base_name = re.sub(r'[Ⅰ-ⅧⅠⅡⅢⅣⅤⅥⅦⅧ]+$', '', sector_name).strip()

        # 标准当日涨跌幅 = (close - pre_close) / pre_close * 100
        # 用关联子查询取前一交易日收盘价
        PrevDaily = aliased(Daily)
        pre_close_subq = (
            select(PrevDaily.close)
            .where(PrevDaily.ts_code == Stock.ts_code, PrevDaily.trade_date < date)
            .order_by(PrevDaily.trade_date.desc())
            .limit(1)
            .correlate(Stock)
            .scalar_subquery()
        )
        change_expr = (
            (Daily.close - pre_close_subq)
            / func.nullif(pre_close_subq, 0) * 100
        )
        order_clause = change_expr.desc() if sort_order == "desc" else change_expr.asc()

        stmt = (
            select(
                Stock.ts_code, Stock.name, Daily.close, Daily.open,
                change_expr.label("change_pct"),
            )
            .join(Daily, Stock.ts_code == Daily.ts_code)
            .where(
                Daily.trade_date == date,
                (Stock.industry_l2 == sector_name)
                | (Stock.industry_l1 == sector_name)
                | (Stock.industry_l2 == base_name)
                | (Stock.industry_l1 == base_name)
                | Stock.concepts.ilike(f"%{base_name}%"),
                ~Stock.ts_code.like("%.IDX"),
            )
            .order_by(order_clause)
            .limit(15)
        )
        result = await db.execute(stmt)
        return [
            {"ts_code": r.ts_code, "name": r.name, "close": r.close, "open": r.open,
             "change_pct": round(r.change_pct, 2) if r.change_pct else None}
            for r in result.all()
        ]
