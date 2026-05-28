"""数据库连接和会话管理"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from .config import settings

# 创建异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True
)

# 创建异步会话工厂
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db() -> AsyncSession:
    """依赖注入：获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def async_session():
    """创建新的异步会话（用于后台任务）"""
    return AsyncSessionLocal()


async def init_db():
    """初始化数据库（创建表）"""
    from sqlalchemy.ext.asyncio import AsyncEngine
    from .models.base import Base
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
