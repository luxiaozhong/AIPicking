"""AI 分析任务模型"""
import uuid
from sqlalchemy import Column, String, Text, Integer, ForeignKey, DateTime
from .base import BaseModel, beijing_now


class AIStrategyTask(BaseModel):
    __tablename__ = "ai_strategy_tasks"

    task_id = Column(
        String(36),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: str(uuid.uuid4()),
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    task_type = Column(
        String(20), default="stock_reference", index=True
    )  # "stock_reference" | "natural_language"
    status = Column(String(20), default="processing", index=True)
    ts_code = Column(String(20), nullable=True)  # stock_reference 必填，natural_language 为空
    date = Column(String(10), nullable=True)      # stock_reference 必填，natural_language 为空
    model = Column(String(50), default="deepseek-chat")
    user_prompt = Column(Text)
    kline_summary = Column(Text)  # JSON
    result_json = Column(Text)  # JSON
    error_message = Column(Text)
    created_at = Column(DateTime, default=beijing_now)
