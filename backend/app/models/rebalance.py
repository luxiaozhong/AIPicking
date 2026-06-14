"""每日调仓回测报告模型"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .base import BaseModel


class RebalanceReport(BaseModel):
    """每日调仓回测报告

    模拟每日根据策略信号调仓的交易过程：
    - 每日收盘后运行策略选出 top N
    - 次日开盘买入／卖出
    - 记录每日持仓快照和净值曲线
    """

    __tablename__ = "rebalance_reports"

    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255))
    status = Column(String(20), default="pending", index=True)
    start_date = Column(String(8), nullable=False)   # YYYYMMDD
    end_date = Column(String(8), nullable=False)      # YYYYMMDD
    config = Column(Text)           # JSON: {N, M, index_code, initial_capital}
    total_days = Column(Integer, default=0)
    completed_days = Column(Integer, default=0)
    daily_snapshots = Column(Text)  # JSON: [{date, holdings, cash, total_value, ...}]
    trades = Column(Text)           # JSON: [{date, ts_code, name, action, price, shares, amount, reason}]
    summary = Column(Text)          # JSON: {initial_capital, final_value, total_return_pct, ...}
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    def __init__(self, **kwargs):
        kwargs.setdefault("total_days", 0)
        kwargs.setdefault("completed_days", 0)
        kwargs.setdefault("status", "pending")
        super().__init__(**kwargs)

    strategy = relationship("Strategy", back_populates="rebalance_reports")
    owner = relationship("User", back_populates="rebalance_reports")

    @property
    def strategy_name(self):
        return self.strategy.name if self.strategy else None
