"""策略评论模型"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from .base import BaseModel


class StrategyComment(BaseModel):
    """策略评论表"""

    __tablename__ = "strategy_comments"

    strategy_id = Column(Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)

    strategy = relationship("Strategy", back_populates="comments")
    user = relationship("User", back_populates="comments")

    @property
    def user_name(self) -> str:
        return self.user.username if self.user else None
