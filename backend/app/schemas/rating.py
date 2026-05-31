"""评分相关的 Pydantic schemas"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class RatingCreate(BaseModel):
    """提交/更新评分请求"""
    score: int = Field(..., ge=1, le=5, description="评分，1-5")


class RatingResponse(BaseModel):
    """单个评分响应"""
    id: int
    strategy_id: int
    user_id: int
    user_name: Optional[str] = None
    score: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RatingStats(BaseModel):
    """评分统计响应"""
    average: Optional[float] = Field(None, description="平均评分")
    count: int = Field(0, description="评分总人数")
    distribution: dict = Field(default_factory=dict, description="各星级人数 {1: n, 2: n, ...}")
    current_user_score: Optional[int] = Field(None, description="当前用户的评分")
