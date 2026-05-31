"""策略评分模型"""

from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .base import BaseModel


class StrategyRating(BaseModel):
    """策略评分表"""

    __tablename__ = "strategy_ratings"

    strategy_id = Column(Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    score = Column(Integer, nullable=False)

    strategy = relationship("Strategy", back_populates="ratings")
    user = relationship("User", back_populates="ratings")

    __table_args__ = (
        UniqueConstraint("strategy_id", "user_id", name="uq_strategy_user_rating"),
    )
