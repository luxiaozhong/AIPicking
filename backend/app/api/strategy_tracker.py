"""当前策略跟踪 API"""

import json
import os
import asyncio
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user_holding import UserHolding
from ..models.strategy_daily_rec import StrategyDailyRec
from ..models.user_strategy_config import UserStrategyConfig
from ..models.strategy import Strategy
from ..models.stock_tables import Daily

router = APIRouter()


# ── Request schemas ──────────────────────────────────────────


class HoldingItem(BaseModel):
    ts_code: str
    stock_name: str = ""
    shares: int = 0
    buy_price: float = 0.0


class SaveHoldingsRequest(BaseModel):
    strategy_id: int
    date: str  # YYYY-MM-DD
    holdings: List[HoldingItem]
    initial_capital: float = 500000.0  # 初始本金，默认 50 万


# ── Response schemas ─────────────────────────────────────────


class RecommendationOut(BaseModel):
    ts_code: str
    name: str
    score: float
    signal: str


class RecommendationsResponse(BaseModel):
    strategy_id: int
    strategy_name: str
    requested_date: str  # 用户请求的日期
    trade_date: str  # 实际使用的交易日 YYYY-MM-DD
    cached: bool  # 是否来自缓存
    recommendations: List[RecommendationOut]
    total: int


# ── Helpers ──────────────────────────────────────────────────


def _ymd_to_yyyymmdd(date_str: str) -> str:
    """YYYY-MM-DD → YYYYMMDD"""
    return date_str.replace("-", "")


def _yyyymmdd_to_ymd(date_str: str) -> str:
    """YYYYMMDD → YYYY-MM-DD"""
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str


async def _find_nearest_trading_day(
    db: AsyncSession, date: str
) -> Optional[str]:
    """找到 ≤ date 的最近一个交易日"""
    result = await db.execute(
        select(Daily.trade_date)
        .where(Daily.trade_date <= date)
        .order_by(Daily.trade_date.desc())
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


def _run_strategy_sync(
    strategy_code: str, cutoff_yyyymmdd: str, config: dict
) -> list:
    """在同步上下文中执行策略（线程池中调用）"""
    from ..services.backtest_engine import BacktestEngine

    engine = BacktestEngine(
        strategy_code=strategy_code, strategy_params={}, config=config,
    )
    return engine.run_live(cutoff_yyyymmdd)


# ── GET /recommendations ─────────────────────────────────────


@router.get("/recommendations")
async def get_recommendations(
    strategy_id: int = Query(..., description="策略 ID"),
    date: Optional[str] = Query(None, description="期望日期 YYYY-MM-DD，默认今天"),
    m: int = Query(5, description="资金流回顾天数 M"),
    n: int = Query(10, description="推荐数量 N"),
    force_refresh: bool = Query(False, description="强制重新计算，忽略缓存"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取策略每日推荐（带缓存 & 交易日回退）

    - 如果 date 是非交易日，自动回退到最近交易日
    - 每个 (strategy_id, trade_date, M, N) 组合只计算一次，结果缓存
    - 传 force_refresh=true 可强制重新计算
    """
    requested_date = date or datetime.now().strftime("%Y-%m-%d")

    # 1. 找到最近交易日
    trade_date = await _find_nearest_trading_day(db, requested_date)
    if not trade_date:
        return {
            "strategy_id": strategy_id,
            "strategy_name": "",
            "requested_date": requested_date,
            "trade_date": requested_date,
            "cached": False,
            "recommendations": [],
            "total": 0,
            "message": "暂无交易数据",
        }

    cutoff_yyyymmdd = _ymd_to_yyyymmdd(trade_date)
    strategy_config = {"M": m, "N": n}

    # 2. 查缓存（包含 M, N 参数，参数变了不算命中）
    cached = False
    cache_key = json.dumps({"M": m, "N": n}, sort_keys=True)
    if not force_refresh:
        cache_result = await db.execute(
            select(StrategyDailyRec)
            .where(
                StrategyDailyRec.strategy_id == strategy_id,
                StrategyDailyRec.cutoff_date == cutoff_yyyymmdd,
            )
            .limit(1)
        )
        cache_row = cache_result.scalar_one_or_none()
        if cache_row:
            # 检查缓存的 config 是否匹配
            cached_config = getattr(cache_row, 'config', None) or '{}'
            if cached_config == cache_key:
                cached = True
                recs = json.loads(cache_row.recommendations)
                return {
                    "strategy_id": strategy_id,
                    "strategy_name": "",
                    "requested_date": requested_date,
                    "trade_date": trade_date,
                    "cached": True,
                    "recommendations": recs,
                    "total": len(recs),
                }

    # 3. 获取策略代码
    strategy_result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = strategy_result.scalar_one_or_none()
    if not strategy:
        return {
            "strategy_id": strategy_id,
            "strategy_name": "",
            "requested_date": requested_date,
            "trade_date": trade_date,
            "cached": False,
            "recommendations": [],
            "total": 0,
            "message": "策略不存在",
        }

    if strategy.generated_code:
        strategy_code = strategy.generated_code
    elif strategy.file_path and os.path.exists(strategy.file_path):
        with open(strategy.file_path, "r", encoding="utf-8") as f:
            strategy_code = f.read()
    else:
        strategy_code = None

    if not strategy_code:
        return {
            "strategy_id": strategy_id,
            "strategy_name": strategy.name,
            "requested_date": requested_date,
            "trade_date": trade_date,
            "cached": False,
            "recommendations": [],
            "total": 0,
            "message": "策略代码不存在",
        }

    # 4. 在线程池中执行策略
    loop = asyncio.get_running_loop()
    recommendations = await loop.run_in_executor(
        None, _run_strategy_sync, strategy_code, cutoff_yyyymmdd, strategy_config,
    )

    # 5. 缓存结果
    cache_entry = StrategyDailyRec(
        strategy_id=strategy_id,
        cutoff_date=cutoff_yyyymmdd,
        trade_date=trade_date,
        config=cache_key,
        recommendations=json.dumps(recommendations, ensure_ascii=False),
    )
    db.add(cache_entry)
    await db.commit()

    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy.name,
        "requested_date": requested_date,
        "trade_date": trade_date,
        "cached": False,
        "recommendations": recommendations,
        "total": len(recommendations),
    }


# ── GET /latest-trading-day ──────────────────────────────────


@router.get("/latest-trading-day")
async def get_latest_trading_day(
    date: Optional[str] = Query(None, description="参考日期 YYYY-MM-DD，默认今天"),
    db: AsyncSession = Depends(get_db),
):
    """获取 ≤ 指定日期的最近交易日"""
    ref_date = date or datetime.now().strftime("%Y-%m-%d")
    trade_date = await _find_nearest_trading_day(db, ref_date)
    return {
        "requested_date": ref_date,
        "trade_date": trade_date or ref_date,
        "is_trading_day": trade_date == ref_date,
    }


# ── GET /config ─────────────────────────────────────────────


@router.get("/config")
async def get_strategy_config(
    strategy_id: int = Query(..., description="策略 ID"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取用户策略配置（初始本金等）"""
    result = await db.execute(
        select(UserStrategyConfig).where(
            UserStrategyConfig.user_id == current_user.id,
            UserStrategyConfig.strategy_id == strategy_id,
        )
    )
    config = result.scalar_one_or_none()
    return {
        "strategy_id": strategy_id,
        "initial_capital": config.initial_capital if config else 500000.0,
        "has_config": config is not None,
    }


# ── POST /holdings ───────────────────────────────────────────


@router.post("/holdings")
async def save_holdings(
    data: SaveHoldingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """保存某日持仓（先删除该日旧数据，再插入新数据）；同时更新策略本金配置"""
    # 1. 更新本金配置（upsert）
    existing_config = await db.execute(
        select(UserStrategyConfig).where(
            UserStrategyConfig.user_id == current_user.id,
            UserStrategyConfig.strategy_id == data.strategy_id,
        )
    )
    config = existing_config.scalar_one_or_none()
    if config:
        config.initial_capital = data.initial_capital
    else:
        config = UserStrategyConfig(
            user_id=current_user.id,
            strategy_id=data.strategy_id,
            initial_capital=data.initial_capital,
        )
        db.add(config)

    # 2. 删除该日旧持仓
    await db.execute(
        delete(UserHolding).where(
            UserHolding.user_id == current_user.id,
            UserHolding.strategy_id == data.strategy_id,
            UserHolding.date == data.date,
        )
    )

    # 3. 插入新持仓
    for h in data.holdings:
        if not h.ts_code:
            continue
        holding = UserHolding(
            user_id=current_user.id,
            strategy_id=data.strategy_id,
            date=data.date,
            ts_code=h.ts_code,
            stock_name=h.stock_name,
            shares=h.shares,
            buy_price=h.buy_price,
        )
        db.add(holding)

    await db.commit()
    return {
        "message": "保存成功",
        "count": len(data.holdings),
        "initial_capital": data.initial_capital,
    }


# ── GET /holdings ────────────────────────────────────────────


@router.get("/holdings")
async def get_holdings(
    strategy_id: int = Query(..., description="策略 ID"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """查询持仓历史"""
    stmt = (
        select(UserHolding)
        .where(
            UserHolding.user_id == current_user.id,
            UserHolding.strategy_id == strategy_id,
        )
        .order_by(UserHolding.date.desc(), UserHolding.ts_code)
    )
    if start_date:
        stmt = stmt.where(UserHolding.date >= start_date)
    if end_date:
        stmt = stmt.where(UserHolding.date <= end_date)

    result = await db.execute(stmt)
    holdings = result.scalars().all()

    grouped: dict = {}
    for h in holdings:
        if h.date not in grouped:
            grouped[h.date] = []
        grouped[h.date].append({
            "id": h.id,
            "strategy_id": h.strategy_id,
            "date": h.date,
            "ts_code": h.ts_code,
            "stock_name": h.stock_name,
            "shares": h.shares,
            "buy_price": h.buy_price,
            "created_at": h.created_at,
        })

    return {"items": grouped, "total_dates": len(grouped)}


# ── GET /nav ─────────────────────────────────────────────────


@router.get("/nav")
async def get_nav(
    strategy_id: int = Query(...),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """计算账户净值历史

    净值 = 持仓市值 + 现金
    现金 = 初始本金 - 持仓成本 (sum(shares * buy_price))
    初始本金从 user_strategy_configs 表读取，默认 50 万
    """
    # 1. 读取初始本金
    config_result = await db.execute(
        select(UserStrategyConfig).where(
            UserStrategyConfig.user_id == current_user.id,
            UserStrategyConfig.strategy_id == strategy_id,
        )
    )
    config = config_result.scalar_one_or_none()
    initial_capital = config.initial_capital if config else 500000.0

    # 2. 查询持仓
    stmt = select(UserHolding).where(
        UserHolding.user_id == current_user.id,
        UserHolding.strategy_id == strategy_id,
    )
    if start_date:
        stmt = stmt.where(UserHolding.date >= start_date)
    if end_date:
        stmt = stmt.where(UserHolding.date <= end_date)

    result = await db.execute(stmt)
    holdings = result.scalars().all()

    if not holdings:
        return {
            "nav": [],
            "message": "暂无持仓记录",
            "initial_capital": initial_capital,
        }

    # 3. 按日期分组
    holdings_by_date: dict = {}
    all_ts_codes: set = set()
    for h in holdings:
        if h.date not in holdings_by_date:
            holdings_by_date[h.date] = []
        holdings_by_date[h.date].append(h)
        all_ts_codes.add(h.ts_code)

    dates = sorted(holdings_by_date.keys())

    # 4. 批量查询收盘价
    price_stmt = select(Daily.trade_date, Daily.ts_code, Daily.close).where(
        Daily.trade_date.in_(dates),
        Daily.ts_code.in_(list(all_ts_codes)),
    )
    price_result = await db.execute(price_stmt)
    price_rows = price_result.all()

    price_index: dict = {}
    for row in price_rows:
        d = row.trade_date
        if d not in price_index:
            price_index[d] = {}
        price_index[d][row.ts_code] = float(row.close or 0)

    # 5. 逐日计算净值
    nav_points = []
    for date in dates:
        day_holdings = holdings_by_date[date]
        holdings_value = 0.0
        cost_basis = 0.0
        day_prices = price_index.get(date, {})
        for h in day_holdings:
            close_price = day_prices.get(h.ts_code, h.buy_price)
            holdings_value += h.shares * close_price
            cost_basis += h.shares * h.buy_price
        cash = initial_capital - cost_basis
        total_value = holdings_value + cash
        nav_points.append({
            "date": date,
            "holdings_value": round(holdings_value, 2),
            "cost_basis": round(cost_basis, 2),
            "cash": round(cash, 2),
            "total_value": round(total_value, 2),
            "initial_capital": round(initial_capital, 2),
        })

    return {
        "nav": nav_points,
        "count": len(nav_points),
        "initial_capital": initial_capital,
    }
