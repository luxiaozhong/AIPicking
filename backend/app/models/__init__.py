"""Models package"""

from sqlalchemy.orm import relationship
from .base import Base, BaseModel
from .user import User
from .strategy import Strategy
from .backtest import BacktestReport, StrategyRun, BatchBacktestReport
from .ai_task import AIStrategyTask

# 设置关系
Strategy.backtest_reports = relationship("BacktestReport", back_populates="strategy")
Strategy.strategy_runs = relationship("StrategyRun", back_populates="strategy")
Strategy.batch_backtest_reports = relationship("BatchBacktestReport", back_populates="strategy")
Strategy.owner = relationship("User", back_populates="strategies")
BacktestReport.owner = relationship("User", back_populates="backtest_reports")
StrategyRun.owner = relationship("User", back_populates="strategy_runs")
BatchBacktestReport.owner = relationship("User", back_populates="batch_backtest_reports")
User.strategies = relationship("Strategy", back_populates="owner")
User.backtest_reports = relationship("BacktestReport", back_populates="owner")
User.strategy_runs = relationship("StrategyRun", back_populates="owner")
User.batch_backtest_reports = relationship("BatchBacktestReport", back_populates="owner")
