"""认证服务：JWT 编码/解码、密码哈希、用户 CRUD"""

import logging
import os
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User
from ..models.base import beijing_now
from ..models.strategy import Strategy
from ..models.backtest import BacktestReport, StrategyRun, BatchBacktestReport
from ..models.ai_task import AIStrategyTask
from ..models.ai_factor import AIFactor
from ..config import settings

logger = logging.getLogger(__name__)

# JWT 配置
SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ========== 密码哈希 ==========

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ========== JWT ==========

def create_access_token(user_id: int, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: int, role: str) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "refresh",
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def create_tokens(user_id: int, role: str) -> dict:
    return {
        "access_token": create_access_token(user_id, role),
        "refresh_token": create_refresh_token(user_id, role),
    }


# ========== 用户认证 ==========

async def authenticate_user(db: AsyncSession, username: str, password: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login = beijing_now()
    await db.flush()
    return user


# ========== 用户 CRUD ==========

async def get_users(
    db: AsyncSession, page: int = 1, limit: int = 20, search: Optional[str] = None
) -> tuple[list[User], int]:
    query = select(User)
    count_query = select(func.count(User.id))

    if search:
        query = query.where(User.username.contains(search))
        count_query = count_query.where(User.username.contains(search))

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(query.order_by(User.id).offset(offset).limit(limit))
    users = result.scalars().all()

    return list(users), total


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, username: str, password: str, role: str = "user") -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def update_user(
    db: AsyncSession,
    user_id: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Optional[User]:
    user = await get_user_by_id(db, user_id)
    if not user:
        return None

    if username is not None:
        user.username = username
    if password is not None:
        user.password_hash = hash_password(password)
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active

    await db.flush()
    await db.refresh(user)
    return user


async def deactivate_user(db: AsyncSession, user_id: int) -> bool:
    user = await get_user_by_id(db, user_id)
    if not user:
        return False
    user.is_active = False
    await db.flush()
    return True


async def seed_default_admin(db: AsyncSession) -> User:
    """创建默认管理员账号（如果不存在）。密码通过环境变量 ADMIN_DEFAULT_PASSWORD
    设置，未设置时自动生成随机密码并输出到日志。"""
    result = await db.execute(
        select(User).where(User.role == "admin").limit(1)
    )
    existing_admin = result.scalar_one_or_none()
    if existing_admin:
        return existing_admin

    # 优先使用环境变量，否则生成随机密码
    password = os.getenv("ADMIN_DEFAULT_PASSWORD", "")
    if not password:
        alphabet = string.ascii_letters + string.digits
        password = "".join(secrets.choice(alphabet) for _ in range(16))
        logger.warning(
            "=" * 60 + "\n"
            f"  默认管理员已创建:\n"
            f"    用户名: admin\n"
            f"    密码:   {password}\n"
            f"  ⚠️  请立即登录修改密码！此密码仅在本次日志中显示。\n"
            + "=" * 60
        )

    admin = await create_user(db, "admin", password, role="admin")
    return admin


async def permanent_delete_user(db: AsyncSession, user_id: int, user: Optional[User] = None) -> bool:
    """永久删除用户及其所有关联数据

    若调用方已持有 User 对象，可通过 user 参数传入以避免重复查询。
    """
    if user is None:
        user = await get_user_by_id(db, user_id)
    if not user:
        return False

    # 先删引用 strategies.id 的子表，再删策略本身（否则 PG 外键冲突）
    await db.execute(delete(BacktestReport).where(BacktestReport.user_id == user_id))
    await db.execute(delete(StrategyRun).where(StrategyRun.user_id == user_id))
    await db.execute(delete(BatchBacktestReport).where(BatchBacktestReport.user_id == user_id))
    await db.execute(delete(Strategy).where(Strategy.user_id == user_id))
    await db.execute(delete(AIStrategyTask).where(AIStrategyTask.user_id == user_id))

    await db.execute(
        update(AIFactor).where(AIFactor.created_by == user_id).values(created_by=None)
    )

    await db.delete(user)
    await db.flush()
    return True
