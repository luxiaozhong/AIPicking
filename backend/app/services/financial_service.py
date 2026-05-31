"""财务数据查询服务"""
from typing import Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.financial import FinancialReport, DailyValuation
from ..models.stock_tables import Stock


class FinancialService:
    """基本面数据查询"""

    @staticmethod
    async def get_reports(
        db: AsyncSession,
        ts_code: str,
        periods: int = 20,
    ) -> list[dict]:
        """获取单股最近 N 期财报"""
        stmt = (
            select(FinancialReport)
            .where(FinancialReport.ts_code == ts_code)
            .order_by(desc(FinancialReport.report_date))
            .limit(periods)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "ts_code": r.ts_code,
                "report_date": r.report_date,
                "report_type": r.report_type,
                "pub_date": r.pub_date,
                "eps": r.eps, "bvps": r.bvps,
                "roe": r.roe, "roa": r.roa,
                "gross_margin": r.gross_margin,
                "net_margin": r.net_margin,
                "net_profit": r.net_profit,
                "net_profit_yoy": r.net_profit_yoy,
                "revenue": r.revenue,
                "revenue_yoy": r.revenue_yoy,
                "debt_to_assets": r.debt_to_assets,
                "current_ratio": r.current_ratio,
                "quick_ratio": r.quick_ratio,
                "cf_operating": r.cf_operating,
                "cf_ratio": r.cf_ratio,
                "total_shares": r.total_shares,
                "float_shares": r.float_shares,
                "total_assets": r.total_assets,
                "total_liabilities": r.total_liabilities,
                "shareholders_equity": r.shareholders_equity,
                "source": r.source,
            }
            for r in rows
        ]

    @staticmethod
    async def get_latest_report(
        db: AsyncSession,
        ts_code: str,
    ) -> Optional[dict]:
        """获取最新一期财报"""
        stmt = (
            select(FinancialReport)
            .where(FinancialReport.ts_code == ts_code)
            .order_by(desc(FinancialReport.report_date))
            .limit(1)
        )
        result = await db.execute(stmt)
        r = result.scalars().first()
        if not r:
            return None
        return {
            "ts_code": r.ts_code,
            "report_date": r.report_date,
            "report_type": r.report_type,
            "pub_date": r.pub_date,
            "eps": r.eps, "bvps": r.bvps,
            "roe": r.roe, "roa": r.roa,
            "gross_margin": r.gross_margin,
            "net_margin": r.net_margin,
            "net_profit": r.net_profit,
            "net_profit_yoy": r.net_profit_yoy,
            "revenue": r.revenue,
            "revenue_yoy": r.revenue_yoy,
            "debt_to_assets": r.debt_to_assets,
            "current_ratio": r.current_ratio,
            "quick_ratio": r.quick_ratio,
            "cf_operating": r.cf_operating,
            "cf_ratio": r.cf_ratio,
            "total_shares": r.total_shares,
            "float_shares": r.float_shares,
            "total_assets": r.total_assets,
            "total_liabilities": r.total_liabilities,
            "shareholders_equity": r.shareholders_equity,
            "source": r.source,
        }

    @staticmethod
    async def get_valuation_history(
        db: AsyncSession,
        ts_code: str,
        days: int = 365,
    ) -> list[dict]:
        """获取单股估值历史"""
        stmt = (
            select(DailyValuation)
            .where(DailyValuation.ts_code == ts_code)
            .order_by(desc(DailyValuation.trade_date))
            .limit(days)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "ts_code": r.ts_code,
                "trade_date": r.trade_date,
                "pe_ttm": r.pe_ttm,
                "pe_static": r.pe_static,
                "pb": r.pb,
                "market_cap": r.market_cap,
                "circ_market_cap": r.circ_market_cap,
                "dividend_yield": r.dividend_yield,
                "source": r.source,
            }
            for r in reversed(rows)  # 升序返回
        ]

    @staticmethod
    async def get_latest_valuation_snapshot(
        db: AsyncSession,
        trade_date: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """获取全市场最新估值快照"""
        if trade_date:
            stmt = (
                select(DailyValuation)
                .where(DailyValuation.trade_date == trade_date)
                .limit(limit)
            )
        else:
            # 取最新交易日的数据
            from sqlalchemy import func
            subq = (
                select(func.max(DailyValuation.trade_date))
                .scalar_subquery()
            )
            stmt = (
                select(DailyValuation)
                .where(DailyValuation.trade_date == subq)
                .limit(limit)
            )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "ts_code": r.ts_code,
                "trade_date": r.trade_date,
                "pe_ttm": r.pe_ttm,
                "pe_static": r.pe_static,
                "pb": r.pb,
                "market_cap": r.market_cap,
                "circ_market_cap": r.circ_market_cap,
                "dividend_yield": r.dividend_yield,
                "source": r.source,
            }
            for r in rows
        ]

    @staticmethod
    async def screen(
        db: AsyncSession,
        roe_min: Optional[float] = None,
        pe_max: Optional[float] = None,
        pb_max: Optional[float] = None,
        revenue_growth_min: Optional[float] = None,
        net_profit_growth_min: Optional[float] = None,
        debt_max: Optional[float] = None,
        market_cap_min: Optional[float] = None,
        limit: int = 50,
    ) -> list[dict]:
        """简单筛选 — 最新财报 + 最新估值联查"""
        from sqlalchemy import and_

        # 每个股票取最新一期财报
        fin_subq = (
            select(
                FinancialReport.ts_code,
                FinancialReport.roe,
                FinancialReport.revenue_yoy,
                FinancialReport.net_profit_yoy,
                FinancialReport.debt_to_assets,
                FinancialReport.net_profit,
                FinancialReport.revenue,
                FinancialReport.report_date,
            )
            .distinct(FinancialReport.ts_code)
            .order_by(FinancialReport.ts_code, desc(FinancialReport.report_date))
            .subquery()
        )

        # 取最新估值
        val_subq = (
            select(
                DailyValuation.ts_code,
                DailyValuation.pe_ttm,
                DailyValuation.pb,
                DailyValuation.market_cap,
                DailyValuation.trade_date,
            )
            .distinct(DailyValuation.ts_code)
            .order_by(DailyValuation.ts_code, desc(DailyValuation.trade_date))
            .subquery()
        )

        stmt = (
            select(
                Stock.ts_code, Stock.name,
                fin_subq.c.roe, fin_subq.c.revenue_yoy,
                fin_subq.c.net_profit_yoy, fin_subq.c.debt_to_assets,
                fin_subq.c.net_profit, fin_subq.c.revenue,
                val_subq.c.pe_ttm, val_subq.c.pb, val_subq.c.market_cap,
            )
            .join(fin_subq, Stock.ts_code == fin_subq.c.ts_code)
            .join(val_subq, Stock.ts_code == val_subq.c.ts_code)
            .where(Stock.ts_code.isnot(None), Stock.ts_code != "")
        )

        if roe_min is not None:
            stmt = stmt.where(fin_subq.c.roe >= roe_min)
        if pe_max is not None:
            stmt = stmt.where(val_subq.c.pe_ttm <= pe_max)
        if pb_max is not None:
            stmt = stmt.where(val_subq.c.pb <= pb_max)
        if revenue_growth_min is not None:
            stmt = stmt.where(fin_subq.c.revenue_yoy >= revenue_growth_min)
        if net_profit_growth_min is not None:
            stmt = stmt.where(fin_subq.c.net_profit_yoy >= net_profit_growth_min)
        if debt_max is not None:
            stmt = stmt.where(fin_subq.c.debt_to_assets <= debt_max)
        if market_cap_min is not None:
            stmt = stmt.where(val_subq.c.market_cap >= market_cap_min)

        stmt = stmt.order_by(desc(fin_subq.c.roe)).limit(limit)
        result = await db.execute(stmt)
        rows = result.all()
        return [
            {
                "ts_code": r.ts_code,
                "name": r.name,
                "roe": r.roe,
                "revenue_yoy": r.revenue_yoy,
                "net_profit_yoy": r.net_profit_yoy,
                "debt_to_assets": r.debt_to_assets,
                "net_profit": r.net_profit,
                "revenue": r.revenue,
                "pe_ttm": r.pe_ttm,
                "pb": r.pb,
                "market_cap": r.market_cap,
            }
            for r in rows
        ]
