"""策略模拟盘 — 不可变交易日志"""

from sqlalchemy import Column, String, Integer, Float, ForeignKey
from .base import BaseModel


class PaperTrade(BaseModel):
    """模拟盘交易记录（不可变）

    每笔交易只增不删不改。账户状态完全由交易序列推导得出。
    net_amount 为负表示现金流出（买入），为正表示现金流入（卖出）。
    """

    __tablename__ = "paper_trades"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    strategy_id = Column(
        Integer, ForeignKey("strategies.id"), nullable=False, index=True
    )

    # 'buy' | 'sell'
    action = Column(String(4), nullable=False, comment="交易方向")

    # T+1 执行日（实际以开盘价成交的日期）
    exec_date = Column(String(10), nullable=False, index=True, comment="执行日 YYYY-MM-DD")

    # T 推荐日（策略出推荐的日期）
    rec_date = Column(String(10), nullable=False, index=True, comment="推荐日 YYYY-MM-DD")

    ts_code = Column(String(20), nullable=False, index=True, comment="股票代码")
    stock_name = Column(String(50), nullable=False, comment="股票名称")
    shares = Column(Integer, nullable=False, comment="股数")
    price = Column(Float, nullable=False, comment="成交价（T+1 开盘价）")
    amount = Column(Float, nullable=False, comment="成交金额 = shares * price")
    commission = Column(Float, nullable=False, default=0.0, comment="手续费")
    stamp_duty = Column(Float, nullable=False, default=0.0, comment="印花税（仅卖出）")
    net_amount = Column(
        Float,
        nullable=False,
        comment="净现金流：买入为负(含手续费)，卖出为正(扣除费用后)",
    )
