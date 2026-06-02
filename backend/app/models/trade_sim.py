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
    def strategy_name(self) -> str:
        return self.strategy.name if self.strategy else None
