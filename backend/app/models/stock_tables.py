"""股票数据库表模型 — 从 SQLite 迁移到 PostgreSQL 用"""
from sqlalchemy import (
    Column, String, Integer, Float, Text, BigInteger,
    Index, UniqueConstraint
)
from .base import BaseModel


class Stock(BaseModel):
    """股票基础信息表"""
    __tablename__ = "stocks"

    ts_code = Column(String(20), unique=True, nullable=False, index=True)
    symbol = Column(String(10))
    name = Column(String(100))
    market = Column(String(10))
    list_date = Column(String(8))
    industry_l1 = Column(String(50))
    industry_l2 = Column(String(50))
    industry_l3 = Column(String(50))
    region = Column(String(50), default="")
    concepts = Column(Text)
    total_shares = Column(BigInteger, default=0)
    float_shares = Column(BigInteger, default=0)
    update_time = Column(String(30))


class Daily(BaseModel):
    """日线行情数据表"""
    __tablename__ = "daily"
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uq_daily_code_date"),
        Index("idx_daily_date", "trade_date"),
        Index("idx_daily_code", "ts_code"),
    )

    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(String(8), nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    vol = Column(Float)
    amount = Column(Float)
    adj_close = Column(Float)
    market_cap = Column(Float, nullable=True)
    circ_market_cap = Column(Float, nullable=True)


class SectorFlow(BaseModel):
    """板块资金流向表"""
    __tablename__ = "sector_flow"
    __table_args__ = (
        UniqueConstraint("trade_date", "sector_code", "sector_type", name="uq_sector_flow"),
        Index("idx_sector_flow_date", "trade_date"),
        Index("idx_sector_flow_code", "sector_code", "sector_type"),
        Index("idx_sector_flow_type", "sector_type"),
    )

    trade_date = Column(String(10), nullable=False)
    sector_code = Column(String(20), nullable=False)
    sector_name = Column(String(100), nullable=False)
    sector_type = Column(String(20), nullable=False)
    change_pct = Column(Float)
    total_amount = Column(Float)
    main_inflow = Column(Float)
    main_inflow_pct = Column(Float)
    retail_inflow = Column(Float)
    retail_inflow_pct = Column(Float)
    net_inflow = Column(Float)
    big_order_inflow = Column(Float)
    big_order_inflow_pct = Column(Float)
    mid_order_inflow = Column(Float)
    mid_order_inflow_pct = Column(Float)
    small_order_inflow = Column(Float)
    tiny_order_inflow = Column(Float)
    update_time = Column(String(30))


class StockTheme(BaseModel):
    """股票主题/概念表"""
    __tablename__ = "stock_themes"

    ts_code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100))
    industry_l1 = Column(String(50))
    industry_l2 = Column(String(50))
    industry_l3 = Column(String(50))
    region = Column(String(50))
    themes = Column(Text)
    update_time = Column(String(30))


class DailyHotStock(BaseModel):
    """每日热门股票表"""
    __tablename__ = "daily_hot_stocks"
    __table_args__ = (
        UniqueConstraint("trade_date", "stock_code", name="uq_hot_stocks"),
        Index("idx_hot_stocks_date", "trade_date"),
        Index("idx_hot_stocks_code", "stock_code"),
        Index("idx_hot_stocks_reason", "reason"),
    )

    trade_date = Column(String(10), nullable=False)
    stock_code = Column(String(20), nullable=False)
    stock_name = Column(String(100), nullable=False)
    close = Column(Float)
    change_amt = Column(Float)
    change_pct = Column(Float)
    turnover_pct = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    reason = Column(String(200))
    market = Column(String(10))
    dde_net = Column(Float)
    sort_order = Column(Integer)


class DailyHotTheme(BaseModel):
    """每日热门主题表"""
    __tablename__ = "daily_hot_themes"
    __table_args__ = (
        UniqueConstraint("trade_date", "theme_name", name="uq_hot_themes"),
        Index("idx_hot_themes_date", "trade_date"),
        Index("idx_hot_themes_name", "theme_name"),
    )

    trade_date = Column(String(10), nullable=False)
    theme_name = Column(String(100), nullable=False)
    stock_count = Column(Integer, nullable=False)


class DailyNorthboundFlow(BaseModel):
    """每日北向资金流向表"""
    __tablename__ = "daily_northbound_flow"
    __table_args__ = (
        UniqueConstraint("trade_date", name="uq_northbound"),
        Index("idx_northbound_date", "trade_date"),
    )

    trade_date = Column(String(10), nullable=False)
    hgt_net_yi = Column(Float)
    sgt_net_yi = Column(Float)
    total_net_yi = Column(Float)
    data_points = Column(Integer)


class DailyIndustryFlow(BaseModel):
    """每日行业资金流向表"""
    __tablename__ = "daily_industry_flow"
    __table_args__ = (
        UniqueConstraint("trade_date", "industry_code", name="uq_industry_flow"),
        Index("idx_industry_flow_date", "trade_date"),
        Index("idx_industry_flow_code", "industry_code"),
        Index("idx_industry_flow_rank", "trade_date", "rank"),
    )

    trade_date = Column(String(10), nullable=False)
    industry_code = Column(String(20), nullable=False)
    industry_name = Column(String(100), nullable=False)
    change_pct = Column(Float)
    up_count = Column(Integer)
    down_count = Column(Integer)
    leader_stock = Column(String(20))
    leader_change = Column(Float)
    main_net_yi = Column(Float)
    super_large_net_yi = Column(Float)
    large_net_yi = Column(Float)
    mid_net_yi = Column(Float)
    small_net_yi = Column(Float)
    rank = Column(Integer)
