"""认证相关 Pydantic 模型"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserInfo(BaseModel):
    """用户信息（嵌入 Token 响应）"""
    id: int
    username: str
    role: str

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInfo


class RefreshRequest(BaseModel):
    """刷新 Token 请求"""
    refresh_token: str
