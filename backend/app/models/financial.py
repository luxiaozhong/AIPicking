"""基本面数据 ORM 模型"""
from sqlalchemy import (
    Column, String, Float, BigInteger, UniqueConstraint, Index
)
from .base import BaseModel


class FinancialReport(BaseModel):
    """财报季报快照 — 每只股票每报告期一条记录"""
    __tablename__ = "financial_reports"
    __table_args__ = (
        UniqueConstraint("ts_code", "report_date", name="uq_fin_code_date"),
        Index("idx_fin_code", "ts_code"),
        Index("idx_fin_date", "report_date"),
        Index("idx_fin_type", "report_type"),
    )

    ts_code = Column(String(20), nullable=False, index=True)
    report_date = Column(String(10), nullable=False)   # YYYY-MM-DD
    report_type = Column(String(10), nullable=False)   # Q1/Q2/Q3/FY
    pub_date = Column(String(10))                      # 实际发布日期

    # 盈利质量
    eps = Column(Float)
    bvps = Column(Float)
    roe = Column(Float)
    roa = Column(Float)
    gross_margin = Column(Float)
    net_margin = Column(Float)

    # 成长性
    net_profit = Column(Float)          # 万元
    net_profit_yoy = Column(Float)      # %
    revenue = Column(Float)             # 万元
    revenue_yoy = Column(Float)         # %

    # 财务健康
    debt_to_assets = Column(Float)
    current_ratio = Column(Float)
    quick_ratio = Column(Float)

    # 现金流
    cf_operating = Column(Float)        # 万元
    cf_ratio = Column(Float)

    # 股本
    total_shares = Column(BigInteger)
    float_shares = Column(BigInteger)

    # 新浪补充
    total_assets = Column(Float)
    total_liabilities = Column(Float)
    shareholders_equity = Column(Float)

    # 元数据
    source = Column(String(20), default="mootdx")


class DailyValuation(BaseModel):
    """每日估值快照 — 每只股票每个交易日一条记录"""
    __tablename__ = "daily_valuation"
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uq_dv_code_date"),
        Index("idx_dv_code", "ts_code"),
        Index("idx_dv_date", "trade_date"),
    )

    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(String(10), nullable=False)  # YYYY-MM-DD

    pe_ttm = Column(Float)
    pe_static = Column(Float)
    pb = Column(Float)
    market_cap = Column(Float)          # 亿元
    circ_market_cap = Column(Float)     # 亿元
    dividend_yield = Column(Float)      # %

    source = Column(String(20), default="tencent")
