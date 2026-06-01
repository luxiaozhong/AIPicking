"""数据库连接和会话管理"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from .config import settings

# 创建异步引擎（PostgreSQL 连接池）
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_size=20,        # 连接池大小
    max_overflow=10,     # 最大溢出连接
    pool_pre_ping=True,  # 连接前检测有效性
    pool_recycle=3600,   # 1小时后回收连接
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


# ====== 同步引擎（psycopg2），用于脚本/迁移/回测引擎 ======

def init_db_sync(pg_conn=None):
    """
    在 PostgreSQL 中创建所有表结构（同步）。

    用法1（传 SQLAlchemy Engine/Connection）：init_db_sync(engine)
    用法2（自动创建连接）：init_db_sync()
    """
    from sqlalchemy import create_engine
    import os
    from .models.base import Base

    if pg_conn is not None:
        # 支持 Engine 或 Connection
        if hasattr(pg_conn, "_run_ddl_visitor"):
            Base.metadata.create_all(pg_conn)
        else:
            raise TypeError(
                "init_db_sync() requires a SQLAlchemy Engine or Connection, "
                f"got {type(pg_conn).__name__}. "
                "Use init_db_sync() without arguments to auto-create an Engine."
            )
    else:
        sync_url = os.getenv("PG_MIGRATE_URL", "")
        if not sync_url:
            # 回退：从 DATABASE_URL 组件构建同步 URL
            db_user = os.getenv("DB_USER", "aipicking")
            db_pass = os.getenv("DB_PASSWORD", "")
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "5432")
            db_name = os.getenv("DB_NAME", "aipicking")
            sync_url = f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
        sync_engine = create_engine(sync_url)
        try:
            Base.metadata.create_all(sync_engine)
        finally:
            sync_engine.dispose()
