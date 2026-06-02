"""交易模拟回测报告模型"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from .base import BaseModel


class TradeSimReport(BaseModel):
    """交易模拟回测报告

    用户输入投资总额，资金均分到策略评分前N只股票，
    逐日追踪并执行止损止盈条件，记录逐笔交易明细和汇总。
    """

    __tablename__ = "trade_sim_reports"

    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    cutoff_date = Column(Date, nullable=False)
    config = Column(Text, default="{}")     # JSON: total_amount, top_n, max_hold_days, stop_factors
    trades = Column(Text, default="[]")     # JSON: 逐笔交易明细（含 daily_tracking）
    summary = Column(Text, default="{}")    # JSON: 汇总统计
    status = Column(String(20), default="pending", index=True)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    def __init__(self, **kwargs):
        kwargs.setdefault("config", "{}")
        kwargs.setdefault("trades", "[]")
        kwargs.setdefault("summary", "{}")
        kwargs.setdefault("status", "pending")
        super().__init__(**kwargs)

    strategy = relationship("Strategy", back_populates="trade_sim_reports")
    owner = relationship("User", back_populates="trade_sim_reports")

    @property
    def strategy_name(self):
        return self.strategy.name if self.strategy else None


class BatchTradeSimReport(BaseModel):
    """批量交易模拟回测报告"""

    __tablename__ = "batch_trade_sim_reports"

    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255))
    status = Column(String(20), default="pending", index=True)
    start_date = Column(String(8), nullable=False)   # YYYYMMDD
    end_date = Column(String(8), nullable=False)      # YYYYMMDD
    config = Column(Text)        # JSON: total_amount, top_n, max_hold_days, stop_factors
    total_days = Column(Integer, default=0)
    completed_days = Column(Integer, default=0)
    daily_results = Column(Text)  # JSON: [{cutoff_date, trades, summary, status, error_message}]
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    def __init__(self, **kwargs):
        kwargs.setdefault("total_days", 0)
        kwargs.setdefault("completed_days", 0)
        kwargs.setdefault("status", "pending")
        super().__init__(**kwargs)

    strategy = relationship("Strategy", back_populates="batch_trade_sim_reports")
    owner = relationship("User", back_populates="batch_trade_sim_reports")

    @property
    def strategy_name(self):
        return self.strategy.name if self.strategy else None
