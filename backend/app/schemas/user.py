"""用户管理 Pydantic 模型"""

from typing import Optional
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """创建用户请求"""
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserUpdate(BaseModel):
    """更新用户请求（所有字段可选）"""
    username: Optional[str] = Field(None, min_length=2, max_length=50)
    password: Optional[str] = Field(None, min_length=6, max_length=128)
    role: Optional[str] = Field(None, pattern="^(admin|user)$")
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    """用户响应"""
    id: int
    username: str
    role: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """用户列表响应"""
    items: list[UserResponse]
    total: int
    page: int
    limit: int
