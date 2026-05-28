"""策略模型"""

from sqlalchemy import Column, String, Text, Integer, ForeignKey
from sqlalchemy.orm import relationship
from .base import BaseModel


class Strategy(BaseModel):
    """策略表模型"""

    __tablename__ = "strategies"

    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text)
    file_path = Column(Text)  # 策略脚本文件路径（相对路径，因子策略可为空）
    params_schema = Column(Text)  # JSON 字符串（可选）
    tags = Column(Text)  # 逗号分隔的标签
    status = Column(String(50), default="active", index=True)
    version = Column(Integer, default=1)
    # 新增：因子配置（JSON）和生成的代码
    factor_config = Column(Text)  # JSON 字符串，因子组合配置
    generated_code = Column(Text)  # 自动生成的策略代码
    # 用户关联
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    owner = relationship("User", back_populates="strategies")

    @property
    def owner_name(self) -> str:
        return self.owner.username if self.owner else None
