"""股票数据库表模型 — 从 SQLite 迁移到 PostgreSQL 用"""
from sqlalchemy import (
    Column, String, Integer, Float, Text, BigInteger, Boolean,
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


class DailySectorFlow(BaseModel):
    """每日板块资金流向表 — 替换旧 sector_flow / daily_industry_flow

    覆盖行业板块 (m:90+t:2) 和概念板块 (m:90+t:3)。
    net_inflow = main + large + mid + small（亿元），由 ingest 脚本计算。
    """
    __tablename__ = "daily_sector_flow"
    __table_args__ = (
        UniqueConstraint("trade_date", "sector_type", "sector_code",
                         name="uq_daily_sector_flow"),
        Index("idx_dsf_date", "trade_date"),
        Index("idx_dsf_type", "sector_type"),
        Index("idx_dsf_code", "sector_type", "sector_code"),
        Index("idx_dsf_name", "sector_type", "sector_name"),
    )

    trade_date = Column(String(10), nullable=False)
    sector_type = Column(String(20), nullable=False)
    sector_code = Column(String(20), nullable=False)
    sector_name = Column(String(100), nullable=False)
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
    net_inflow = Column(Float)
    rank = Column(Integer)


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


class DailyDragonTiger(BaseModel):
    """每日龙虎榜上榜汇总"""
    __tablename__ = "daily_dragon_tiger"
    __table_args__ = (
        UniqueConstraint("trade_date", "stock_code", name="uq_dragon_tiger"),
        Index("idx_dt_date", "trade_date"),
        Index("idx_dt_code", "stock_code"),
    )

    trade_date = Column(String(10), nullable=False)
    stock_code = Column(String(20), nullable=False)
    stock_name = Column(String(100))
    reason = Column(String(200))
    close = Column(Float)
    change_pct = Column(Float)
    turnover_pct = Column(Float)
    net_buy_wan = Column(Float)
    buy_wan = Column(Float)
    sell_wan = Column(Float)


class DailyDragonTigerSeat(BaseModel):
    """每日龙虎榜买卖席位明细"""
    __tablename__ = "daily_dragon_tiger_seats"
    __table_args__ = (
        UniqueConstraint("trade_date", "stock_code", "seat_type", "rank",
                         name="uq_dt_seats"),
        Index("idx_dts_date", "trade_date"),
        Index("idx_dts_code", "stock_code"),
    )

    trade_date = Column(String(10), nullable=False)
    stock_code = Column(String(20), nullable=False)
    seat_type = Column(String(4), nullable=False)  # buy / sell
    rank = Column(Integer, nullable=False)          # 1-5
    seat_name = Column(String(100))
    seat_code = Column(String(20))
    buy_amt_wan = Column(Float)
    sell_amt_wan = Column(Float)
    net_amt_wan = Column(Float)
    is_institution = Column(Boolean, default=False)


# daily_industry_flow → 已合并到 daily_sector_flow (sector_type='industry')
