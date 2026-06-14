"""策略每日推荐缓存"""

from sqlalchemy import Column, String, Integer, Text, ForeignKey
from .base import BaseModel


class StrategyDailyRec(BaseModel):
    """策略每日推荐结果缓存

    每个 (strategy_id, cutoff_date) 只执行一次策略，
    结果缓存在此表，避免重复计算。
    """

    __tablename__ = "strategy_daily_recs"

    strategy_id = Column(
        Integer, ForeignKey("strategies.id"), nullable=False, index=True
    )
    cutoff_date = Column(String(8), nullable=False, comment="策略执行截止日 YYYYMMDD")
    trade_date = Column(String(10), nullable=False, comment="实际数据日期 YYYY-MM-DD")
    recommendations = Column(Text, nullable=False, comment="推荐结果 JSON")
