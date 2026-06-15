"""用户策略配置模型"""

from sqlalchemy import Column, String, Integer, Float, ForeignKey, UniqueConstraint
from .base import BaseModel


class UserStrategyConfig(BaseModel):
    """用户级别的策略配置

    存储每个用户对每个策略的个性化设置，如初始本金等。
    """

    __tablename__ = "user_strategy_configs"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    strategy_id = Column(
        Integer, ForeignKey("strategies.id"), nullable=False, index=True
    )
    initial_capital = Column(
        Float, nullable=False, default=500000.0, comment="初始本金（元）"
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "strategy_id", name="uq_user_strategy_config"
        ),
    )
