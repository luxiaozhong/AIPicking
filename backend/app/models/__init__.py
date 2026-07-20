"""Models package"""

from sqlalchemy.orm import relationship
from .base import Base, BaseModel
from .user import User
from .strategy import Strategy
from .backtest import BacktestReport, StrategyRun, BatchBacktestReport
from .ai_task import AIStrategyTask
from .ai_factor import AIFactor
from .strategy_rating import StrategyRating
from .strategy_comment import StrategyComment
from .stock_tables import (
    Stock, Daily, DailySectorFlow, StockTheme,
    DailyHotStock, DailyHotTheme, DailyNorthboundFlow,
    DailyDragonTiger, DailyDragonTigerSeat,
    DailyMarketTemperature, DailyBoardTemperature, DailyMarketStress,
)
from .financial import FinancialReport, DailyValuation
from .index_tables import IndexInfo, IndexConstituent
from .voice_token import VoiceToken
from .trade_sim import TradeSimReport, BatchTradeSimReport
from .rebalance import RebalanceReport
from .user_holding import UserHolding
from .strategy_daily_rec import StrategyDailyRec
from .user_strategy_config import UserStrategyConfig
from .paper_trade import PaperTrade

# 设置关系
Strategy.backtest_reports = relationship("BacktestReport", back_populates="strategy", cascade="all, delete-orphan")
Strategy.strategy_runs = relationship("StrategyRun", back_populates="strategy", cascade="all, delete-orphan")
Strategy.batch_backtest_reports = relationship("BatchBacktestReport", back_populates="strategy", cascade="all, delete-orphan")
Strategy.owner = relationship("User", back_populates="strategies")
Strategy.ratings = relationship("StrategyRating", back_populates="strategy", cascade="all, delete-orphan")
Strategy.comments = relationship("StrategyComment", back_populates="strategy", cascade="all, delete-orphan")
Strategy.trade_sim_reports = relationship("TradeSimReport", back_populates="strategy", cascade="all, delete-orphan")
BacktestReport.owner = relationship("User", back_populates="backtest_reports")
StrategyRun.owner = relationship("User", back_populates="strategy_runs")
BatchBacktestReport.owner = relationship("User", back_populates="batch_backtest_reports")
User.strategies = relationship("Strategy", back_populates="owner")
User.backtest_reports = relationship("BacktestReport", back_populates="owner")
User.strategy_runs = relationship("StrategyRun", back_populates="owner")
User.batch_backtest_reports = relationship("BatchBacktestReport", back_populates="owner")
User.ratings = relationship("StrategyRating", back_populates="user")
User.comments = relationship("StrategyComment", back_populates="user")
TradeSimReport.owner = relationship("User", back_populates="trade_sim_reports")
User.trade_sim_reports = relationship("TradeSimReport", back_populates="owner")
Strategy.batch_trade_sim_reports = relationship("BatchTradeSimReport", back_populates="strategy", cascade="all, delete-orphan")
BatchTradeSimReport.owner = relationship("User", back_populates="batch_trade_sim_reports")
User.batch_trade_sim_reports = relationship("BatchTradeSimReport", back_populates="owner")
Strategy.rebalance_reports = relationship("RebalanceReport", back_populates="strategy", cascade="all, delete-orphan")
RebalanceReport.owner = relationship("User", back_populates="rebalance_reports")
User.rebalance_reports = relationship("RebalanceReport", back_populates="owner")
UserHolding.owner = relationship("User", back_populates="holdings")
UserHolding.strategy = relationship("Strategy", back_populates="holdings")
User.holdings = relationship("UserHolding", back_populates="owner")
Strategy.holdings = relationship("UserHolding", back_populates="strategy")
UserStrategyConfig.owner = relationship("User", back_populates="strategy_configs")
UserStrategyConfig.strategy = relationship("Strategy", back_populates="user_configs")
User.strategy_configs = relationship("UserStrategyConfig", back_populates="owner")
Strategy.user_configs = relationship("UserStrategyConfig", back_populates="strategy")
PaperTrade.owner = relationship("User", back_populates="paper_trades")
PaperTrade.strategy = relationship("Strategy", back_populates="paper_trades")
User.paper_trades = relationship("PaperTrade", back_populates="owner")
Strategy.paper_trades = relationship("PaperTrade", back_populates="strategy")
