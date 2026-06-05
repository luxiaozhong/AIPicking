"""市场热度服务 — Core 级别 SQL 查询"""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.stock_tables import (
    Daily, DailySectorFlow, DailyHotStock, DailyHotTheme,
    DailyNorthboundFlow, DailyDragonTiger, DailyDragonTigerSeat
)


class MarketHeatService:

    # ── 工具方法 ─────────────────────────────────────────────

    @staticmethod
    async def _get_latest_date(db: AsyncSession) -> Optional[str]:
        """获取最新有数据的交易日"""
        stmt = select(func.max(DailySectorFlow.trade_date))
        result = await db.execute(stmt)
        return result.scalar()

    # ── 概览 KPI ─────────────────────────────────────────────

    @staticmethod
    async def get_overview(db: AsyncSession, trade_date: Optional[str] = None) -> dict:
        """返回 4 个核心 KPI：市场温度、北向资金、涨跌比、领涨板块"""
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return {"trade_date": None, "temperature": None, "northbound": None,
                    "advance_decline": None, "leading_sector": None}

        # 北向资金
        nb_stmt = select(DailyNorthboundFlow.__table__).where(
            DailyNorthboundFlow.trade_date == date
        )
        nb_result = await db.execute(nb_stmt)
        nb_row = nb_result.mappings().first()
        northbound = dict(nb_row) if nb_row else None

        # 涨跌比：从 daily 表统计当日上涨/下跌家数
        adv_stmt = select(
            func.count().label("total"),
            func.sum(
                func.case((Daily.close > Daily.open, 1), else_=0)
            ).label("up_count"),
            func.sum(
                func.case((Daily.close < Daily.open, 1), else_=0)
            ).label("down_count"),
        ).where(Daily.trade_date == date, ~Daily.ts_code.like("%.IDX"))
        adv_result = await db.execute(adv_stmt)
        adv_row = adv_result.mappings().first()
        adv = dict(adv_row) if adv_row else {"total": 0, "up_count": 0, "down_count": 0}

        # 领涨板块：sector_flow 按 change_pct 降序取第一
        sector_stmt = select(DailySectorFlow.__table__).where(
            DailySectorFlow.trade_date == date,
            DailySectorFlow.sector_type == "industry"
        ).order_by(DailySectorFlow.change_pct.desc()).limit(1)
        sector_result = await db.execute(sector_stmt)
        leading = dict(sector_result.mappings().first()) if sector_result else None

        # 计算市场温度
        temperature = MarketHeatService._calc_temperature(
            northbound=northbound,
            adv=adv,
            date=date,
            db=db,
        )

        return {
            "trade_date": date,
            "temperature": temperature,
            "northbound": northbound,
            "advance_decline": adv,
            "leading_sector": {
                "sector_name": leading["sector_name"],
                "change_pct": leading["change_pct"],
                "main_net_yi": leading["main_net_yi"],
            } if leading else None,
        }

    # ── 板块资金流 ────────────────────────────────────────────

    @staticmethod
    async def get_sectors(
        db: AsyncSession, trade_date: Optional[str], sector_type: str = "industry"
    ) -> list[dict]:
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return []
        stmt = select(DailySectorFlow.__table__).where(
            DailySectorFlow.trade_date == date,
            DailySectorFlow.sector_type == sector_type,
        ).order_by(DailySectorFlow.rank.asc())
        result = await db.execute(stmt)
        return [dict(r) for r in result.mappings().all()]

    @staticmethod
    async def get_sector_detail(
        db: AsyncSession, sector_code: str, trade_date: Optional[str], days: int = 10
    ) -> dict:
        """板块详情：近 N 日资金流趋势 + 成分股 Top5"""
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return {"trend": [], "stocks": [], "info": None}

        # 基本信息
        info_stmt = select(DailySectorFlow.__table__).where(
            DailySectorFlow.trade_date == date,
            DailySectorFlow.sector_code == sector_code,
        )
        info_result = await db.execute(info_stmt)
        info = dict(info_result.mappings().first()) if info_result else None

        # 近 N 日趋势
        trend_stmt = select(DailySectorFlow.__table__).where(
            DailySectorFlow.sector_code == sector_code,
            DailySectorFlow.trade_date <= date,
        ).order_by(DailySectorFlow.trade_date.desc()).limit(days)
        trend_result = await db.execute(trend_stmt)
        trend = [dict(r) for r in reversed(list(trend_result.mappings().all()))]

        # 成分股 Top5（从 daily 表查当天该板块涨幅最大的 stock）
        # 注：daily 表的 industry 概念需通过 stocks.industry_l1/l2/l3 关联
        top5 = []
        if info:
            from ..models.stock_tables import Stock
            stock_stmt = (
                select(Stock.ts_code, Stock.name, Daily.close, Daily.open)
                .join(Daily, Stock.ts_code == Daily.ts_code)
                .where(
                    Daily.trade_date == date,
                    (Stock.industry_l2 == info["sector_name"]) |
                    (Stock.industry_l1 == info["sector_name"])
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
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return []
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
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return []
        stmt = select(DailyHotStock.__table__).where(
            DailyHotStock.trade_date == date,
            DailyHotStock.reason.ilike(f"%{theme_name}%"),
        ).order_by(DailyHotStock.sort_order.asc())
        result = await db.execute(stmt)
        return [dict(r) for r in result.mappings().all()]

    # ── 热门股票 / 龙虎榜 / 北向 ──────────────────────────────

    @staticmethod
    async def get_hot_stocks(
        db: AsyncSession, trade_date: Optional[str], page: int = 1, page_size: int = 20
    ) -> dict:
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return {"items": [], "total": 0}

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
        return {"items": items, "total": total}

    @staticmethod
    async def get_dragon_tiger(
        db: AsyncSession, trade_date: Optional[str], page: int = 1, page_size: int = 20
    ) -> dict:
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return {"items": [], "total": 0}

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

        # 为每个股票附加席位明细
        for item in items:
            seat_stmt = select(DailyDragonTigerSeat.__table__).where(
                DailyDragonTigerSeat.trade_date == date,
                DailyDragonTigerSeat.stock_code == item["stock_code"],
            ).order_by(DailyDragonTigerSeat.seat_type, DailyDragonTigerSeat.rank)
            seat_result = await db.execute(seat_stmt)
            item["seats"] = [dict(s) for s in seat_result.mappings().all()]

        return {"items": items, "total": total}

    @staticmethod
    async def get_northbound(db: AsyncSession, days: int = 30) -> list[dict]:
        stmt = select(DailyNorthboundFlow.__table__).order_by(
            DailyNorthboundFlow.trade_date.desc()
        ).limit(days)
        result = await db.execute(stmt)
        return [dict(r) for r in reversed(list(result.mappings().all()))]

    @staticmethod
    async def get_available_dates(db: AsyncSession, days: int = 20) -> list[str]:
        stmt = (
            select(DailySectorFlow.trade_date)
            .distinct()
            .order_by(DailySectorFlow.trade_date.desc())
            .limit(days)
        )
        result = await db.execute(stmt)
        return [r[0] for r in result.all()]

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
