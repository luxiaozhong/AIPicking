"""回测报告模型（新逻辑：截止日推荐 + 后续表现追踪）"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .base import BaseModel


class BacktestReport(BaseModel):
    """回测报告表模型

    新逻辑：
    1. 用截止日及之前的数据运行策略，选出推荐股票
    2. 追踪这些股票在截止日后 N 天的表现
    """

    __tablename__ = "backtest_reports"

    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255))
    status = Column(String(50), default="pending", index=True)
    cutoff_date = Column(String(8), nullable=False)  # 截止日，格式 YYYYMMDD
    config = Column(Text)  # JSON 字符串，存储 track_days 等配置
    recommendations = Column(Text)  # JSON 字符串，推荐股票列表（完成后填充）
    summary = Column(Text)  # JSON 字符串，汇总指标（完成后填充）
    error_message = Column(Text)  # 错误信息，失败时填充
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # 关系
    strategy = relationship("Strategy", back_populates="backtest_reports")
    owner = relationship("User", back_populates="backtest_reports")

    @property
    def strategy_name(self) -> str:
        """策略名称（从关联的 Strategy 读取）"""
        return self.strategy.name if self.strategy else None


class StrategyRun(BaseModel):
    """策略执行记录表模型（执行策略功能）"""

    __tablename__ = "strategy_runs"

    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    cutoff_date = Column(String(8), nullable=False)  # 执行截止日
    recommendations = Column(Text, nullable=False)  # JSON 字符串，推荐股票列表
    created_at = Column(DateTime)

    # 关系
    strategy = relationship("Strategy", back_populates="strategy_runs")
    owner = relationship("User", back_populates="strategy_runs")


class BatchBacktestReport(BaseModel):
    """批量回测报告模型

    一次批量回测覆盖多个交易日，每天独立运行策略并追踪表现。
    daily_results 存储每日结果数组。
    """

    __tablename__ = "batch_backtest_reports"

    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255))
    status = Column(String(50), default="pending", index=True)
    start_date = Column(String(8), nullable=False)
    end_date = Column(String(8), nullable=False)
    config = Column(Text)  # JSON: track_days, strategy config
    total_days = Column(Integer, default=0)
    completed_days = Column(Integer, default=0)
    daily_results = Column(Text)  # JSON 数组
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    strategy = relationship("Strategy", back_populates="batch_backtest_reports")
    owner = relationship("User", back_populates="batch_backtest_reports")

    @property
    def strategy_name(self) -> str:
        return self.strategy.name if self.strategy else None
