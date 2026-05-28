"""用户模型"""

from sqlalchemy import Column, String, Boolean
from .base import BaseModel


class User(BaseModel):
    """用户表"""

    __tablename__ = "users"

    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user", index=True)  # admin / user
    is_active = Column(Boolean, default=True)
