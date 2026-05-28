"""回测相关测试"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.async.io import AsyncSession, create_async_engine
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


@pytest.fixture
async def create_test_strategy(client):
    """创建测试策略"""
    response = await client.post(
        "/api/v1/strategies",
        json={
            "name": "测试策略_for_backtest",
            "code": "class TestStrategy:\n    pass"
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
            "params": {"short_window": 5, "long_window": 20},
            "config": {
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
                "initial_cash": 1000000,
                "commission": 0.0003
            }
        }
    )
    
    assert response.status_code == 202
    data = response.json()
    assert data["code"] == 0
    assert "id" in data["data"]
    assert data["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_get_backtest_list(client, create_test_strategy):
    """测试获取回测报告列表"""
    # 先提交一个回测任务
    strategy_id = create_test_strategy
    await client.post(
        "/api/v1/backtests",
        json={
            "strategy_id": strategy_id,
            "params": {},
            "config": {
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
                "initial_cash": 1000000,
                "commission": 0.0003
            }
        }
    )
    
    # 获取列表
    response = await client.get("/api/v1/backtests")
    
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "items" in data["data"]
    assert len(data["data"]["items"]) >= 1


@pytest.mark.asyncio
async def test_get_backtest_detail(client, create_test_strategy):
    """测试获取回测报告详情"""
    # 先提交一个回测任务
    strategy_id = create_test_strategy
    create_response = await client.post(
        "/api/v1/backtests",
        json={
            "strategy_id": strategy_id,
            "params": {},
            "config": {
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
                "initial_cash": 1000000,
                "commission": 0.0003
            }
        }
    )
    backtest_id = create_response.json()["data"]["id"]
    
    # 获取详情
    response = await client.get(f"/api/v1/backtests/{backtest_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["id"] == backtest_id


@pytest.mark.asyncio
async def test_delete_backtest(client, create_test_strategy):
    """测试删除回测报告"""
    # 先提交一个回测任务
    strategy_id = create_test_strategy
    create_response = await client.post(
        "/api/v1/backtests",
        json={
            "strategy_id": strategy_id,
            "params": {},
            "config": {
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
                "initial_cash": 1000000,
                "commission": 0.0003
            }
        }
    )
    backtest_id = create_response.json()["data"]["id"]
    
    # 删除回测报告
    response = await client.delete(f"/api/v1/backtests/{backtest_id}")
    
    assert response.status_code == 204
