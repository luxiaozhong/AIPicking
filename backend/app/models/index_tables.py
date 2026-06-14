"""指数成分股相关表 — 支持多指数扩展

设计原则：
- index_info：指数元数据，一个指数一条记录
- index_constituents：成分股明细，按生效日期 (eff_date) 区分不同调样周期
- 唯一约束 (index_code, ts_code, eff_date) 保证同一指数、同一股票、同一生效日不重复
- 支持沪深/北交所/港股等不同交易所的指数
- 权重和市值随每次调样更新

数据源：akshare (index_detail_cni / index_stock_cons_csindex 等)
更新频率：跟随指数季度调样（每年 3/6/9/12 月）
"""

from sqlalchemy import (
    Column, String, Integer, Float, Index, UniqueConstraint
)
from .base import BaseModel


class IndexInfo(BaseModel):
    """指数元数据表 — 存储指数基本信息

    每新增一个指数策略，先在此注册指数元数据。
    """
    __tablename__ = "index_info"
    __table_args__ = (
        UniqueConstraint("index_code", name="uq_index_info_code"),
        Index("idx_index_info_publisher", "publisher"),
    )

    index_code = Column(String(20), unique=True, nullable=False, index=True,
                        comment="指数代码，如 980080（国证成长100）")
    index_name = Column(String(50), nullable=False,
                        comment="指数简称，如 成长100")
    full_name = Column(String(100),
                       comment="指数全称，如 国证成长100")
    publisher = Column(String(20), default="国证",
                       comment="编制机构：国证/中证/深证/上证")
    constituent_count = Column(Integer, default=0,
                               comment="预期成分股数量")
    data_source = Column(String(50), default="akshare.index_detail_cni",
                         comment="数据获取接口")
    last_sync_date = Column(String(10),
                            comment="最近一次同步日期 YYYY-MM-DD")


class IndexConstituent(BaseModel):
    """指数成分股明细表 — 按生效日期存储每次调样的成分股列表

    每次指数调样后执行 sync 脚本，存量数据保留（eff_date 不同），
    便于回测时获取历史上某一天的成分股列表。
    """
    __tablename__ = "index_constituents"
    __table_args__ = (
        UniqueConstraint("index_code", "ts_code", "eff_date",
                         name="uq_index_constituent"),
        Index("idx_ic_index_code", "index_code"),
        Index("idx_ic_ts_code", "ts_code"),
        Index("idx_ic_eff_date", "eff_date"),
        Index("idx_ic_code_date", "index_code", "eff_date"),
    )

    index_code = Column(String(20), nullable=False, index=True,
                        comment="指数代码，如 980080")
    ts_code = Column(String(20), nullable=False, index=True,
                     comment="股票代码（原始格式），如 000408")
    stock_name = Column(String(100), nullable=False,
                        comment="股票简称")
    industry = Column(String(50),
                      comment="所属行业分类（来自指数编制方）")
    market_cap = Column(Float,
                        comment="总市值（亿元），成分股确定日的市值")
    weight = Column(Float,
                    comment="权重（%），在指数中的占比")
    eff_date = Column(String(10), nullable=False, index=True,
                      comment="生效日期 YYYY-MM-DD，指数调样后生效日")
