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
)
from .financial import FinancialReport, DailyValuation

# 设置关系
Strategy.backtest_reports = relationship("BacktestReport", back_populates="strategy", cascade="all, delete-orphan")
Strategy.strategy_runs = relationship("StrategyRun", back_populates="strategy", cascade="all, delete-orphan")
Strategy.batch_backtest_reports = relationship("BatchBacktestReport", back_populates="strategy", cascade="all, delete-orphan")
Strategy.owner = relationship("User", back_populates="strategies")
Strategy.ratings = relationship("StrategyRating", back_populates="strategy", cascade="all, delete-orphan")
Strategy.comments = relationship("StrategyComment", back_populates="strategy", cascade="all, delete-orphan")
BacktestReport.owner = relationship("User", back_populates="backtest_reports")
StrategyRun.owner = relationship("User", back_populates="strategy_runs")
BatchBacktestReport.owner = relationship("User", back_populates="batch_backtest_reports")
User.strategies = relationship("Strategy", back_populates="owner")
User.backtest_reports = relationship("BacktestReport", back_populates="owner")
User.strategy_runs = relationship("StrategyRun", back_populates="owner")
User.batch_backtest_reports = relationship("BatchBacktestReport", back_populates="owner")
User.ratings = relationship("StrategyRating", back_populates="user")
User.comments = relationship("StrategyComment", back_populates="user")
