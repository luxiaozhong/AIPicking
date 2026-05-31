"""评论相关的 Pydantic schemas"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class CommentCreate(BaseModel):
    """发表评论请求"""
    content: str = Field(..., min_length=1, max_length=2000, description="评论内容")


class CommentResponse(BaseModel):
    """评论响应"""
    id: int
    strategy_id: int
    user_id: int
    user_name: Optional[str] = None
    content: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CommentListResponse(BaseModel):
    """评论列表响应"""
    items: List[CommentResponse]
    total: int
    page: int = 1
    limit: int = 20
