"""FastAPI 应用入口"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .database import init_db

# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    description="A 股量化交易平台",
    version="0.1.0",
    debug=settings.DEBUG
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    await init_db()

    # 创建默认管理员账号
    from .database import async_session
    from .services.auth_service import seed_default_admin
    session = await async_session()
    try:
        admin = await seed_default_admin(session)
        await session.commit()
        print(f"默认管理员账号已就绪: {admin.username}")
    finally:
        await session.close()

    # 预置内置策略
    from .seed_strategies import seed_strategies
    session = await async_session()
    try:
        await seed_strategies(session, admin_user_id=admin.id)
        await session.commit()
    finally:
        await session.close()

    print("数据库已初始化")

    # 加载教育内容
    from .services.education_service import EducationService
    EducationService.instance().load()

    # 种子 900002 临时观察指数元数据（幂等）
    from .services.watchlist_service import ensure_index_info
    session = await async_session()
    try:
        await ensure_index_info(session)
        print("临时观察指数 900002 元数据已就绪")
    finally:
        await session.close()


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": f"欢迎使用 {settings.APP_NAME} API",
        "version": "0.1.0",
        "docs": "/docs",
        "openapi": "/openapi.json"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


# 导入并注册 API 路由
from .api import strategies, backtests, batch_backtests, factors, ai, auth, users, stocks, education, ratings, comments, financials, trade_sims, market_heat, fund_flow, rebalance, strategy_tracker, paper_trade, watchlist
app.include_router(strategies.router, prefix="/api/v1/strategies", tags=["strategies"])
app.include_router(ratings.router, prefix="/api/v1/strategies", tags=["ratings"])
app.include_router(comments.router, prefix="/api/v1/strategies", tags=["comments"])
app.include_router(batch_backtests.router, prefix="/api/v1/backtests/batch", tags=["batch-backtests"])
app.include_router(trade_sims.router, prefix="/api/v1/trade-sims", tags=["trade-sims"])
app.include_router(backtests.router, prefix="/api/v1/backtests", tags=["backtests"])
app.include_router(factors.router, prefix="/api/v1", tags=["factors"])
app.include_router(ai.router, prefix="/api/v1", tags=["ai"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(stocks.router, prefix="/api/v1/stocks", tags=["stocks"])
app.include_router(education.router, prefix="/api/v1/education", tags=["education"])
app.include_router(financials.router, prefix="/api/v1", tags=["financials"])
app.include_router(market_heat.router, prefix="/api/v1/market-heat", tags=["market-heat"])
app.include_router(fund_flow.router, prefix="/api/v1/fund-flow", tags=["fund-flow"])
app.include_router(watchlist.router, prefix="/api/v1/watchlist", tags=["watchlist"])
app.include_router(rebalance.router, prefix="/api/v1/rebalance", tags=["调仓回测"])
app.include_router(strategy_tracker.router, prefix="/api/v1/strategy-tracker", tags=["策略跟踪"])
app.include_router(paper_trade.router, prefix="/api/v1/paper-trade", tags=["模拟盘"])
