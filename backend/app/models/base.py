"""SQLAlchemy 基类"""

from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, DateTime

Base = declarative_base()

BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_now():
    """返回北京时间（UTC+8），不带时区信息（SQLite 兼容）"""
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


class BaseModel(Base):
    """基础模型类（抽象类）"""

    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at = Column(DateTime, default=beijing_now)
    updated_at = Column(DateTime, default=beijing_now, onupdate=beijing_now)
