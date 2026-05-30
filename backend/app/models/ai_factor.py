"""AI 生成因子模型"""
from sqlalchemy import Column, String, Text, Integer, ForeignKey
from .base import BaseModel


class AIFactor(BaseModel):
    __tablename__ = "ai_factors"

    factor_id = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)
    description = Column(Text)
    params_schema = Column(Text)  # JSON
    file_path = Column(String(200))  # .py 文件路径
    created_by = Column(Integer, ForeignKey("users.id"))
    usage_count = Column(Integer, default=0)
