"""市场热度服务 — Core 级别 SQL 查询"""
from typing import Optional
from sqlalchemy import select, func, case
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
        """返回 4 个核心 KPI：市场温度、北向资金、涨跌比、领涨板块
        各子查询使用各自表的最新日期（日期格式不同）。"""

        # 各表最新日期
        daily_date = trade_date or await MarketHeatService._get_latest_date_for(db, Daily.__table__.c)
        nb_date = await MarketHeatService._get_latest_date_for(db, DailyNorthboundFlow.__table__.c)
        sector_date = await MarketHeatService._get_latest_date_for(db, DailySectorFlow.__table__.c)

        if not daily_date:
            return {"trade_date": None, "temperature": None, "northbound": None,
                    "advance_decline": None, "leading_sectors": []}

        # 北向资金（用 northbound_flow 自己表的日期，或用户指定日期转格式）
        northbound = None
        nb_query_date = trade_date or nb_date
        if nb_query_date:
            nb_query_date = MarketHeatService._to_yyyy_mm_dd(nb_query_date) if trade_date else nb_date
        if nb_query_date:
            nb_stmt = select(DailyNorthboundFlow.__table__).where(
                DailyNorthboundFlow.trade_date == nb_query_date
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

        # 领涨板块 Top 3（用 sector_flow 自己表的最新日期）
        leading = []
        if sector_date:
            sector_stmt = select(DailySectorFlow.__table__).where(
                DailySectorFlow.trade_date == sector_date,
                DailySectorFlow.sector_type == "industry"
            ).order_by(DailySectorFlow.change_pct.desc()).limit(3)
            sector_result = await db.execute(sector_stmt)
            leading = [dict(r) for r in sector_result.mappings().all()]

        # 计算市场温度
        temperature = MarketHeatService._calc_temperature(
            northbound=northbound,
            adv=adv,
            date=daily_date,
            db=db,
        )

        return {
            "trade_date": daily_date,
            "temperature": temperature,
            "northbound": northbound,
            "advance_decline": adv,
            "leading_sectors": [
                {
                    "sector_name": s["sector_name"],
                    "change_pct": s["change_pct"],
                    "main_net_yi": s["main_net_yi"],
                }
                for s in leading
            ],
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
        # 行业名可能有罗马数字后缀（如 电子化学品Ⅱ vs 电子化学品），做模糊匹配
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
        date = MarketHeatService._to_yyyy_mm_dd(date)
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
        date = MarketHeatService._to_yyyy_mm_dd(date)
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

        daily_date = MarketHeatService._to_yyyymmdd(yyyymmdd_date)
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
        date = MarketHeatService._to_yyyy_mm_dd(date)

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
        date = MarketHeatService._to_yyyy_mm_dd(date)

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

    @staticmethod
    def _to_yyyymmdd(date_str: str) -> str:
        """将 YYYY-MM-DD 转为 YYYYMMDD"""
        return date_str.replace("-", "") if len(date_str) == 10 else date_str

    @staticmethod
    def _to_yyyy_mm_dd(date_str: str) -> str:
        """将 YYYYMMDD 转为 YYYY-MM-DD"""
        if len(date_str) == 8:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str

    # ── 市场温度计算 ─────────────────────────────────────────

    @staticmethod
    def _calc_temperature(
        northbound: Optional[dict],
        adv: dict,
        date: str,
        db: Optional[AsyncSession] = None,
    ) -> dict:
        """5 维度综合评分，每维度 0-20 分，满分 100"""
        scores = {}

        # 1. 资金面 (20): 北向净流入方向+规模
        nb_score = 10  # 中性
        if northbound and northbound.get("total_net_yi"):
            net = northbound["total_net_yi"]
            if net > 50:
                nb_score = 20
            elif net > 20:
                nb_score = 17
            elif net > 0:
                nb_score = 14
            elif net > -20:
                nb_score = 7
            elif net > -50:
                nb_score = 3
            else:
                nb_score = 0
        scores["capital"] = nb_score

        # 2. 涨跌结构 (20): 上涨占比
        total = adv.get("total", 0) or 0
        up = adv.get("up_count", 0) or 0
        ratio = up / total if total > 0 else 0.5
        scores["breadth"] = min(20, round(ratio * 25))  # 80%+ = 满分

        # 3. 情绪面 (20): 涨停数（从 daily 表统计，简化处理）
        # 注：数据库中无直接 limit_up/down 列，使用 change_pct 推算
        # 此处从 adv 统计中提取，若无精确数据则给中值
        scores["sentiment"] = 10  # 中性默认值

        # 4. 板块集中度 (20): 适中最好（过度集中=不可持续）
        scores["concentration"] = 10  # 中性默认值

        # 5. 热度延续 (20): 需要前后两天数据比较
        scores["continuity"] = 10  # 中性默认值

        total_score = sum(scores.values())
        level = (
            "冰点" if total_score <= 30 else
            "偏冷" if total_score <= 50 else
            "中性" if total_score <= 70 else
            "偏热" if total_score <= 85 else
            "过热"
        )

        return {
            "score": total_score,
            "level": level,
            "dimensions": scores,
        }

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
        db: AsyncSession, sector_name: str, trade_date: Optional[str] = None
    ) -> list[dict]:
        """领涨板块内涨幅前 15 个股（行业名模糊匹配，去除罗马数字等后缀）"""
        date = trade_date or await MarketHeatService._get_latest_date_for(db, Daily.__table__.c)
        if not date:
            return []

        from ..models.stock_tables import Stock

        # 去除 Ⅰ/Ⅱ/Ⅲ 等罗马数字后缀
        import re
        base_name = re.sub(r'[Ⅰ-ⅧⅠⅡⅢⅣⅤⅥⅦⅧ]+$', '', sector_name).strip()

        stmt = (
            select(
                Stock.ts_code, Stock.name, Daily.close, Daily.open,
                ((Daily.close - Daily.open) / func.nullif(Daily.open, 0) * 100).label("change_pct"),
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
            .order_by(((Daily.close - Daily.open) / func.nullif(Daily.open, 0)).desc())
            .limit(15)
        )
        result = await db.execute(stmt)
        return [
            {"ts_code": r.ts_code, "name": r.name, "close": r.close, "open": r.open,
             "change_pct": round(r.change_pct, 2) if r.change_pct else None}
            for r in result.all()
        ]
