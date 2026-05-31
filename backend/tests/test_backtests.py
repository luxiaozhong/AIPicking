"""回测相关测试"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.models.base import Base
from app.models.user import User
from app.database import get_db
from app.middleware.auth import get_current_user
from app.services.auth_service import create_user as create_user_svc


# 测试数据库 URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# 最小有效 factor_config
VALID_FACTOR_CONFIG = {
    "buy_signals": {
        "logic": "AND",
        "factors": [{"factor_id": "momentum_rsi", "params": {"period": 14}}]
    },
    "sell_signals": {
        "logic": "AND",
        "factors": []
    },
    "risk_factors": []
}


@pytest_asyncio.fixture
async def test_db():
    """创建测试数据库，覆盖 get_db 和 get_current_user"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        # 创建测试管理员用户
        user = await create_user_svc(session, "testadmin", "test123", role="admin")
        await session.commit()
        await session.refresh(user)

        # 覆盖依赖
        async def override_get_db():
            yield session

        async def override_get_current_user():
            return user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user

        yield session

        app.dependency_overrides.clear()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_db):
    """创建测试客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def create_test_strategy(client):
    """创建测试策略，返回 strategy_id"""
    response = await client.post(
        "/api/v1/strategies",
        json={
            "name": "测试策略_for_backtest",
            "tags": ["测试"],
            "factor_config": VALID_FACTOR_CONFIG
        }
    )
    return response.json()["data"]["id"]


@pytest.mark.asyncio
async def test_create_backtest(client, create_test_strategy):
    """测试提交回测任务"""
    strategy_id = create_test_strategy

    response = await client.post(
        "/api/v1/backtests",
        json={
            "strategy_id": strategy_id,
            "cutoff_date": "20250101",
            "config": {
                "initial_cash": 1000000,
                "commission": 0.0003
            }
        }
    )

    assert response.status_code == 202
    data = response.json()
    assert data["strategy_id"] == strategy_id
    assert data["status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_backtest_list(client, create_test_strategy):
    """测试获取回测报告列表"""
    # 先提交一个回测任务
    strategy_id = create_test_strategy
    await client.post(
        "/api/v1/backtests",
        json={
            "strategy_id": strategy_id,
            "cutoff_date": "20250101"
        }
    )

    # 获取列表
    response = await client.get("/api/v1/backtests")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    assert "total" in data


@pytest.mark.asyncio
async def test_get_backtest_detail(client, create_test_strategy):
    """测试获取回测报告详情"""
    # 先提交一个回测任务
    strategy_id = create_test_strategy
    create_response = await client.post(
        "/api/v1/backtests",
        json={
            "strategy_id": strategy_id,
            "cutoff_date": "20250101"
        }
    )
    backtest_id = create_response.json()["id"]

    # 获取详情
    response = await client.get(f"/api/v1/backtests/{backtest_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == backtest_id
    assert data["strategy_id"] == strategy_id


@pytest.mark.asyncio
async def test_delete_backtest(client, create_test_strategy):
    """测试删除回测报告"""
    # 先提交一个回测任务
    strategy_id = create_test_strategy
    create_response = await client.post(
        "/api/v1/backtests",
        json={
            "strategy_id": strategy_id,
            "cutoff_date": "20250101"
        }
    )
    backtest_id = create_response.json()["id"]

    # 删除回测报告
    response = await client.delete(f"/api/v1/backtests/{backtest_id}")

    assert response.status_code == 204
