"""股票数据库表模型 — PostgreSQL"""
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
    trade_date = Column(String(10), nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    pre_close = Column(Float, nullable=True)
    vol = Column(Float)
    amount = Column(Float)
    adj_close = Column(Float)


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
    """每日北向资金流向表

    数据源：东财 RPT_MUTUAL_DEAL_HISTORY（深股通 MUTUAL_TYPE="002"）
    注意：沪股通自 2024-08-16 起不再披露净买额（港交所政策调整），hgt_net_yi 为 NULL。
    total_net_yi = sgt_net_yi（仅深股通）。
    """
    __tablename__ = "daily_northbound_flow"
    __table_args__ = (
        UniqueConstraint("trade_date", name="uq_northbound"),
        Index("idx_northbound_date", "trade_date"),
    )

    trade_date = Column(String(10), nullable=False)
    hgt_net_yi = Column(Float, nullable=True)   # 沪股通净买入(亿) — 2024-08 后不可用
    sgt_net_yi = Column(Float)                   # 深股通净买入(亿)
    sgt_buy_yi = Column(Float)                   # 深股通买入额(亿)
    sgt_sell_yi = Column(Float)                  # 深股通卖出额(亿)
    total_net_yi = Column(Float)                 # 合计净买入(亿) = sgt_net_yi
    data_points = Column(Integer)                # 已弃用（原 hexin 分钟点数）


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


class DailyMarketTemperature(BaseModel):
    """每日市场温度评分表 — 由 sync_market_temperature.py 写入"""
    __tablename__ = "daily_market_temperature"
    __table_args__ = (
        UniqueConstraint("trade_date", name="uq_market_temp_date"),
        Index("idx_mkt_temp_date", "trade_date"),
    )

    trade_date = Column(String(10), unique=True, nullable=False, index=True)
    score = Column(Integer, nullable=False)
    level = Column(String(10), nullable=False)
    capital_score = Column(Integer, nullable=False)
    breadth_score = Column(Integer, nullable=False)
    sentiment_score = Column(Integer, nullable=False)
    concentration_score = Column(Integer, nullable=False)
    continuity_score = Column(Integer, nullable=False)


class DailyBoardTemperature(BaseModel):
    """四大指数板块温度表 — 由 sync_market_temperature.py 写入

    board_code: sh_main(上证主板) / sh_star(科创板) / sz_main(深证主板) / sz_chi(创业板)
    """
    __tablename__ = "daily_board_temperature"
    __table_args__ = (
        UniqueConstraint("trade_date", "board_code", name="uq_board_temp"),
        Index("idx_board_temp_date", "trade_date"),
    )

    trade_date = Column(String(10), nullable=False, index=True)
    board_code = Column(String(20), nullable=False)
    board_name = Column(String(20), nullable=False)
    score = Column(Integer, nullable=False)
    level = Column(String(10), nullable=False)
    breadth_score = Column(Integer, nullable=False)    # 涨跌结构 0-40
    sentiment_score = Column(Integer, nullable=False)  # 情绪面 0-30
    volume_score = Column(Integer, nullable=False)     # 量能活跃度 0-30


class DailyMarketStress(BaseModel):
    """每日市场压力指数表 — 由 sync_market_temperature.py 写入

    衡量市场恐慌/紧张程度，方向与 VIX 一致（越高越糟）。
    包含 5 个维度：指数跌幅、波动率、跌停潮、下跌广度、北向出逃。
    """
    __tablename__ = "daily_market_stress"
    __table_args__ = (
        UniqueConstraint("trade_date", name="uq_market_stress_date"),
        Index("idx_stress_date", "trade_date"),
    )

    trade_date = Column(String(10), unique=True, nullable=False, index=True)
    score = Column(Integer, nullable=False)
    level = Column(String(10), nullable=False)
    decline_score = Column(Float, nullable=False)     # 指数跌幅 0-25
    volatility_score = Column(Float, nullable=False)  # 波动率 0-25
    limitdown_score = Column(Float, nullable=False)   # 跌停潮 0-25
    breadth_score = Column(Float, nullable=False)     # 下跌广度 0-15
    northbound_score = Column(Float, nullable=False)  # 北向出逃 0-10


class DailyStockFundFlow(BaseModel):
    """每日个股资金流向表 — 腾讯自选股资金流数据

    数据源：proxy.finance.qq.com（通过 westock-data-clawhub npm 包获取）
    覆盖全体 A 股，每交易日每只股票一条记录。
    金额单位：元（与 API 返回一致）。

    写入脚本：scripts/sync_stock_fund_flow.py
    """
    __tablename__ = "daily_stock_fund_flow"
    __table_args__ = (
        UniqueConstraint("trade_date", "ts_code", name="uq_stock_fund_flow"),
        Index("idx_sff_date", "trade_date"),
        Index("idx_sff_code", "ts_code"),
    )

    trade_date = Column(String(10), nullable=False, index=True, comment="交易日期 YYYY-MM-DD")
    ts_code = Column(String(20), nullable=False, index=True, comment="股票代码 ts_code 格式 600519.SH")

    # ── 核心资金流（元）──
    main_net_flow = Column(Float, comment="主力净流入")
    jumbo_net_flow = Column(Float, comment="超大单净流入")
    block_net_flow = Column(Float, comment="大单净流入")
    mid_net_flow = Column(Float, comment="中单净流入")
    small_net_flow = Column(Float, comment="小单净流入")
    main_in_flow = Column(Float, comment="主力流入")
    main_out_flow = Column(Float, comment="主力流出")
    retail_in_flow = Column(Float, comment="散户流入")
    retail_out_flow = Column(Float, comment="散户流出")

    # ── 多日窗口累计（元）──
    main_net_flow_5d = Column(Float, comment="主力净流入 5 日累计")
    main_net_flow_10d = Column(Float, comment="主力净流入 10 日累计")
    main_net_flow_20d = Column(Float, comment="主力净流入 20 日累计")

    # ── 排名与比率 ──
    main_inflow_circ_rate = Column(Float, comment="主买占流通市值比率")
    main_inflow_rank = Column(Integer, comment="全市场主力流入排名")
    main_inflow_industry_rank = Column(Integer, comment="行业主力流入排名")

    # ── 价格 ──
    close_price = Column(Float, comment="收盘价")
    fwd_close_price = Column(Float, comment="前收盘价")
    lastest_traded_price = Column(Float, comment="最新成交价")
    end_date = Column(String(10), comment="数据截止日期 YYYY-MM-DD")
    secu_code = Column(String(20), comment="证券代码（腾讯格式）")

    # ── 复杂结构体（JSON 文本）──
    block_trading_infos = Column(Text, comment="大宗交易信息 JSON")
    margin_trade_infos = Column(Text, comment="融资融券信息 JSON")
    lhb_trading_details = Column(Text, comment="龙虎榜交易明细 JSON")
    lhb_infos = Column(Text, comment="龙虎榜信息 JSON")


# daily_industry_flow → 已合并到 daily_sector_flow (sector_type='industry')
