"""认证 API 路由"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.auth import LoginRequest, LoginResponse, RefreshRequest, UserInfo
from ..services.auth_service import (
    authenticate_user,
    create_tokens,
    decode_token,
    create_access_token,
)
from ..middleware.auth import get_current_user
from ..models.user import User

router = APIRouter()


@router.post("/login", response_model=dict)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录"""
    user = await authenticate_user(db, body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    tokens = create_tokens(user.id, user.role)

    return {
        "code": 0,
        "data": {
            **tokens,
            "user": UserInfo.model_validate(user).model_dump(),
        },
    }


@router.post("/refresh", response_model=dict)
async def refresh_token(body: RefreshRequest):
    """刷新 Access Token"""
    payload = decode_token(body.refresh_token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Refresh Token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 类型无效",
        )

    user_id = int(payload.get("sub"))
    role = payload.get("role", "user")

    new_access_token = create_access_token(user_id, role)

    return {
        "code": 0,
        "data": {
            "access_token": new_access_token,
            "token_type": "bearer",
        },
    }


@router.get("/me", response_model=dict)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "code": 0,
        "data": UserInfo.model_validate(current_user).model_dump(),
    }
