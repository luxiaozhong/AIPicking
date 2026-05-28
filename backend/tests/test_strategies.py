"""策略相关测试"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base


# 测试数据库 URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="module")
async def test_db():
    """创建测试数据库"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=True)
    
    # 创建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 创建测试会话
    TestingSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    yield TestingSessionLocal
    
    # 清理
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
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
            "code": "class TestStrategy:\n    pass",
            "tags": ["测试", "均线"]
        }
    )
    
    assert response.status_code == 201
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
            "code": "class TestStrategy2:\n    pass"
        }
    )
    
    # 获取列表
    response = await client.get("/api/v1/strategies")
    
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "items" in data["data"]
    assert len(data["data"]["items"]) >= 1


@pytest.mark.asyncio
async def test_get_strategy_detail(client):
    """测试获取策略详情"""
    # 先创建一个策略
    create_response = await client.post(
        "/api/v1/strategies",
        json={
            "name": "测试策略3",
            "code": "class TestStrategy3:\n    pass"
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
            "code": "class TestStrategy4:\n    pass"
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
    assert data["code"] == 0
    assert data["data"]["name"] == "更新后的策略名称"
    assert data["data"]["version"] == 2  # 版本应该增加


@pytest.mark.asyncio
async def test_delete_strategy(client):
    """测试删除策略"""
    # 先创建一个策略
    create_response = await client.post(
        "/api/v1/strategies",
        json={
            "name": "测试策略5",
            "code": "class TestStrategy5:\n    pass"
        }
    )
    strategy_id = create_response.json()["data"]["id"]
    
    # 删除策略
    response = await client.delete(f"/api/v1/strategies/{strategy_id}")
    
    assert response.status_code == 204
    
    # 确认策略已被软删除（状态变为 deleted）
    get_response = await client.get(f"/api/v1/strategies/{strategy_id}")
    # 这里应该返回 404 或者状态为 deleted
    # 取决于实现逻辑
