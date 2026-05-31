"""策略相关测试"""

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


@pytest.mark.asyncio
async def test_create_strategy(client):
    """测试创建策略"""
    response = await client.post(
        "/api/v1/strategies",
        json={
            "name": "测试策略",
            "description": "这是一个测试策略",
            "tags": ["测试", "均线"],
            "factor_config": VALID_FACTOR_CONFIG
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["name"] == "测试策略"
    assert "id" in data["data"]


@pytest.mark.asyncio
async def test_get_strategies_list(client):
    """测试获取策略列表"""
    # 先创建一个策略
    await client.post(
        "/api/v1/strategies",
        json={
            "name": "测试策略2",
            "tags": ["测试"],
            "factor_config": VALID_FACTOR_CONFIG
        }
    )

    # 获取列表
    response = await client.get("/api/v1/strategies")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    assert "total" in data


@pytest.mark.asyncio
async def test_get_strategy_detail(client):
    """测试获取策略详情"""
    # 先创建一个策略
    create_response = await client.post(
        "/api/v1/strategies",
        json={
            "name": "测试策略3",
            "tags": ["测试"],
            "factor_config": VALID_FACTOR_CONFIG
        }
    )
    strategy_id = create_response.json()["data"]["id"]

    # 获取详情
    response = await client.get(f"/api/v1/strategies/{strategy_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["id"] == strategy_id


@pytest.mark.asyncio
async def test_update_strategy(client):
    """测试更新策略"""
    # 先创建一个策略
    create_response = await client.post(
        "/api/v1/strategies",
        json={
            "name": "测试策略4",
            "tags": ["测试"],
            "factor_config": VALID_FACTOR_CONFIG
        }
    )
    strategy_id = create_response.json()["data"]["id"]

    # 更新策略
    response = await client.put(
        f"/api/v1/strategies/{strategy_id}",
        json={
            "name": "更新后的策略名称",
            "description": "更新后的描述"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "更新后的策略名称"
    assert data["version"] == 2  # 版本应该增加


@pytest.mark.asyncio
async def test_delete_strategy(client):
    """测试删除策略"""
    # 先创建一个策略
    create_response = await client.post(
        "/api/v1/strategies",
        json={
            "name": "测试策略5",
            "tags": ["测试"],
            "factor_config": VALID_FACTOR_CONFIG
        }
    )
    strategy_id = create_response.json()["data"]["id"]

    # 删除策略
    response = await client.delete(f"/api/v1/strategies/{strategy_id}")

    assert response.status_code == 204
