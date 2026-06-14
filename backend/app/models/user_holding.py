"""用户持仓记录模型"""

from sqlalchemy import Column, String, Integer, Float, ForeignKey
from .base import BaseModel


class UserHolding(BaseModel):
    """用户实际持仓记录表"""

    __tablename__ = "user_holdings"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    strategy_id = Column(
        Integer, ForeignKey("strategies.id"), nullable=False, index=True
    )
    date = Column(String(10), nullable=False, comment="交易日期 YYYY-MM-DD")
    ts_code = Column(String(20), nullable=False, comment="股票代码")
    stock_name = Column(String(50), comment="股票名称")
    shares = Column(Integer, nullable=False, default=0, comment="持仓股数")
    buy_price = Column(Float, nullable=False, default=0.0, comment="买入均价")
