"""用户管理相关测试"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_db
from app.models.base import Base
from app.models.user import User
from app.services.auth_service import (
    create_access_token, create_user as create_user_svc,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def client_and_db():
    """创建测试客户端 + 数据库会话（共享同一会话）"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        async def override_get_db():
            try:
                yield session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, session

        app.dependency_overrides.clear()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _auth_header(user_id: int, role: str = "admin") -> dict:
    token = create_access_token(user_id, role)
    return {"Authorization": f"Bearer {token}"}


async def _create_admin(session, username="admin_test", password="admin123") -> User:
    """Helper: create an admin user and return it."""
    admin = await create_user_svc(session, username, password, role="admin")
    await session.commit()
    await session.refresh(admin)
    return admin


@pytest.mark.asyncio
async def test_permanent_delete_user_success(client_and_db):
    """测试永久删除用户"""
    client, db = client_and_db

    admin = await _create_admin(db)
    user = await create_user_svc(db, "testuser", "password123", role="user")
    await db.commit()

    response = await client.delete(
        f"/api/v1/users/{user.id}/permanent",
        headers=_auth_header(admin.id),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "已永久删除" in data["message"]

    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == user.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_permanent_delete_nonexistent_user(client_and_db):
    """测试删除不存在的用户返回 404"""
    client, db = client_and_db
    admin = await _create_admin(db)

    response = await client.delete(
        "/api/v1/users/99999/permanent",
        headers=_auth_header(admin.id),
    )
    assert response.status_code == 404
    assert "不存在" in response.json()["detail"]


@pytest.mark.asyncio
async def test_permanent_delete_self(client_and_db):
    """测试不能删除自己"""
    client, db = client_and_db
    admin = await _create_admin(db)

    response = await client.delete(
        f"/api/v1/users/{admin.id}/permanent",
        headers=_auth_header(admin.id),
    )
    assert response.status_code == 400
    assert "不能删除自己" in response.json()["detail"]


@pytest.mark.asyncio
async def test_permanent_delete_default_admin(client_and_db):
    """测试不能删除默认 admin"""
    client, db = client_and_db

    # 创建默认 admin 用户（被保护的目标）
    default_admin = await create_user_svc(db, "admin", "admin123", role="admin")
    await db.commit()

    # 创建另一个管理员来执行删除
    other_admin = await create_user_svc(db, "otheradmin", "123456", role="admin")
    await db.commit()

    response = await client.delete(
        f"/api/v1/users/{default_admin.id}/permanent",
        headers=_auth_header(other_admin.id),
    )
    assert response.status_code == 400
    assert "默认管理员" in response.json()["detail"]


@pytest.mark.asyncio
async def test_permanent_delete_with_cascade(client_and_db):
    """测试级联删除"""
    from app.models.strategy import Strategy
    from app.models.backtest import BacktestReport, StrategyRun, BatchBacktestReport
    from app.models.ai_task import AIStrategyTask
    from app.models.ai_factor import AIFactor

    client, db = client_and_db

    admin = await _create_admin(db)
    user = await create_user_svc(db, "cascadetest", "123456", role="user")
    await db.commit()

    strategy = Strategy(name="test_strategy", user_id=user.id)
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)

    backtest = BacktestReport(strategy_id=strategy.id, user_id=user.id, cutoff_date="20260101")
    run = StrategyRun(strategy_id=strategy.id, user_id=user.id, cutoff_date="20260101", recommendations="[]")
    batch = BatchBacktestReport(strategy_id=strategy.id, user_id=user.id, start_date="20260101", end_date="20260110")
    task = AIStrategyTask(user_id=user.id, task_type="stock_reference", task_id="task-001")
    factor = AIFactor(factor_id="test_f_001", name="test_factor", category="momentum", created_by=user.id)
    db.add_all([backtest, run, batch, task, factor])
    await db.commit()

    response = await client.delete(
        f"/api/v1/users/{user.id}/permanent",
        headers=_auth_header(admin.id),
    )
    assert response.status_code == 200

    from sqlalchemy import select as sel

    assert (await db.execute(sel(Strategy).where(Strategy.user_id == user.id))).scalar_one_or_none() is None
    assert (await db.execute(sel(BacktestReport).where(BacktestReport.user_id == user.id))).scalar_one_or_none() is None
    assert (await db.execute(sel(StrategyRun).where(StrategyRun.user_id == user.id))).scalar_one_or_none() is None
    assert (await db.execute(sel(BatchBacktestReport).where(BatchBacktestReport.user_id == user.id))).scalar_one_or_none() is None
    assert (await db.execute(sel(AIStrategyTask).where(AIStrategyTask.user_id == user.id))).scalar_one_or_none() is None

    factor_result = await db.execute(sel(AIFactor).where(AIFactor.factor_id == "test_f_001"))
    factor_record = factor_result.scalar_one_or_none()
    assert factor_record is not None
    assert factor_record.created_by is None

    assert (await db.execute(sel(User).where(User.id == user.id))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_permanent_delete_requires_admin(client_and_db):
    """测试非管理员不能删除"""
    client, db = client_and_db

    admin = await _create_admin(db)
    user = await create_user_svc(db, "regular", "123456", role="user")
    await db.commit()

    response = await client.delete(
        f"/api/v1/users/{admin.id}/permanent",
        headers=_auth_header(user.id, role="user"),
    )
    assert response.status_code == 403
