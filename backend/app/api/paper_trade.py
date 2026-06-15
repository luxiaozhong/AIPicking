"""策略模拟盘 API

自动追踪策略推荐 → T+1 开盘价执行 → 每日净值计算。
"""

import json
import asyncio
from datetime import datetime
from collections import defaultdict
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.paper_trade import PaperTrade
from ..models.user_strategy_config import UserStrategyConfig
from ..models.strategy_daily_rec import StrategyDailyRec
from ..models.strategy import Strategy
from ..models.stock_tables import Daily

router = APIRouter()

# ── 费率常量 ────────────────────────────────────────────────

BUY_COMMISSION_RATE = 0.00015    # 万 1.5 买入手续费
SELL_COMMISSION_RATE = 0.00015   # 万 1.5 卖出手续费
STAMP_DUTY_RATE = 0.0005         # 万 5 印花税（仅卖出）

def _lot_size(ts_code: str) -> int:
    """获取每手股数：科创板(688) 为 200 股，其余为 100 股"""
    if ts_code.startswith("688"):
        return 200
    return 100


# ── Schemas ──────────────────────────────────────────────────


class StartRequest(BaseModel):
    strategy_id: int
    initial_capital: float = 500000.0


class ExecuteRequest(BaseModel):
    strategy_id: int
    date: Optional[str] = None  # YYYY-MM-DD，默认今天


class TradeOut(BaseModel):
    id: int
    action: str
    exec_date: str
    rec_date: str
    ts_code: str
    stock_name: str
    shares: int
    price: float
    amount: float
    commission: float
    stamp_duty: float
    net_amount: float


class HoldingOut(BaseModel):
    ts_code: str
    stock_name: str
    shares: int
    avg_cost: float
    cost_basis: float
    last_price: Optional[float] = None
    market_value: float
    unrealized_pnl: float


class StatusResponse(BaseModel):
    strategy_id: int
    initial_capital: float
    cash: float
    holdings: List[HoldingOut]
    total_market_value: float
    total_cost_basis: float
    total_nav: float
    total_return_pct: float
    last_exec_date: Optional[str] = None
    last_rec_date: Optional[str] = None
    trade_count: int


class ExecuteSummary(BaseModel):
    cash_before: float
    cash_after: float
    holdings_before: int
    holdings_after: int
    sell_count: int
    buy_count: int
    total_buy_amount: float
    total_sell_amount: float
    total_commission: float
    total_stamp_duty: float


class ExecuteResponse(BaseModel):
    executed: bool
    rec_date: str
    exec_date: str
    trades: List[TradeOut]
    summary: ExecuteSummary


class NavPoint(BaseModel):
    date: str
    cash: float
    holdings_value: float
    total_value: float
    return_pct: float


class NavResponse(BaseModel):
    strategy_id: int
    initial_capital: float
    nav: List[NavPoint]
    count: int
    message: Optional[str] = None


class TradeListResponse(BaseModel):
    strategy_id: int
    trades: List[TradeOut]
    total: int
    page: int
    page_size: int


# ── Helpers ──────────────────────────────────────────────────


def _beijing_today() -> str:
    """北京时区今天的日期字符串 YYYY-MM-DD"""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


async def _find_nearest_trading_day(db: AsyncSession, date: str) -> Optional[str]:
    """找到 ≤ date 的最近一个交易日"""
    result = await db.execute(
        select(Daily.trade_date)
        .where(Daily.trade_date <= date)
        .order_by(Daily.trade_date.desc())
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


async def _find_next_trading_day(db: AsyncSession, after_date: str) -> Optional[str]:
    """找到 > after_date 的下一个交易日"""
    result = await db.execute(
        select(Daily.trade_date)
        .where(Daily.trade_date > after_date)
        .order_by(Daily.trade_date.asc())
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


async def _get_config(db: AsyncSession, user_id: int, strategy_id: int) -> UserStrategyConfig:
    """获取或创建用户策略配置"""
    result = await db.execute(
        select(UserStrategyConfig).where(
            UserStrategyConfig.user_id == user_id,
            UserStrategyConfig.strategy_id == strategy_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        config = UserStrategyConfig(
            user_id=user_id,
            strategy_id=strategy_id,
            initial_capital=500000.0,
        )
        db.add(config)
        await db.flush()
    return config


async def _get_all_trades(
    db: AsyncSession, user_id: int, strategy_id: int
) -> List[PaperTrade]:
    """获取所有交易记录（按执行日排序）"""
    result = await db.execute(
        select(PaperTrade)
        .where(
            PaperTrade.user_id == user_id,
            PaperTrade.strategy_id == strategy_id,
        )
        .order_by(PaperTrade.exec_date.asc(), PaperTrade.id.asc())
    )
    return list(result.scalars().all())


async def _compute_holdings(
    db: AsyncSession, user_id: int, strategy_id: int
) -> List[dict]:
    """从交易记录推导当前持仓"""
    trades = await _get_all_trades(db, user_id, strategy_id)

    # {ts_code: {stock_name, shares, total_cost}}
    positions: dict = {}
    for t in trades:
        if t.ts_code not in positions:
            positions[t.ts_code] = {
                "ts_code": t.ts_code,
                "stock_name": t.stock_name,
                "shares": 0,
                "total_cost": 0.0,  # 买入总成本（含手续费）
            }
        if t.action == "buy":
            positions[t.ts_code]["shares"] += t.shares
            positions[t.ts_code]["total_cost"] += t.amount + t.commission
            positions[t.ts_code]["stock_name"] = t.stock_name
        else:  # sell
            positions[t.ts_code]["shares"] -= t.shares
            # 按比例减成本（简化：FIFO，直接减平均成本）
            if positions[t.ts_code]["shares"] > 0:
                avg = positions[t.ts_code]["total_cost"] / (
                    positions[t.ts_code]["shares"] + t.shares
                )
                positions[t.ts_code]["total_cost"] -= avg * t.shares
            else:
                positions[t.ts_code]["total_cost"] = 0.0

    # 只保留正持仓
    active = [p for p in positions.values() if p["shares"] > 0]

    # 计算 avg_cost
    for p in active:
        p["avg_cost"] = round(p["total_cost"] / p["shares"], 2) if p["shares"] > 0 else 0.0
        p["cost_basis"] = round(p["total_cost"], 2)
        p["last_price"] = None
        p["market_value"] = 0.0
        p["unrealized_pnl"] = 0.0

    # 获取最新收盘价
    if active:
        today = _beijing_today()
        trade_date = await _find_nearest_trading_day(db, today)
        if trade_date:
            codes = [p["ts_code"] for p in active]
            price_result = await db.execute(
                select(Daily.ts_code, Daily.close)
                .where(Daily.trade_date == trade_date, Daily.ts_code.in_(codes))
            )
            prices = {row.ts_code: float(row.close or 0) for row in price_result}
            for p in active:
                p["last_price"] = prices.get(p["ts_code"])
                if p["last_price"]:
                    p["market_value"] = round(p["shares"] * p["last_price"], 2)
                    p["unrealized_pnl"] = round(
                        p["market_value"] - p["cost_basis"], 2
                    )

    return active


# ── POST /start ──────────────────────────────────────────────


@router.post("/start")
async def start_paper_trade(
    data: StartRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """初始化（或更新）模拟盘本金"""
    config = await _get_config(db, current_user.id, data.strategy_id)
    config.initial_capital = data.initial_capital
    await db.commit()
    return {
        "strategy_id": data.strategy_id,
        "initial_capital": data.initial_capital,
        "message": "本金已设置，点击「执行调仓」开始模拟交易",
    }


# ── GET /status ──────────────────────────────────────────────


@router.get("/status")
async def get_status(
    strategy_id: int = Query(..., description="策略 ID"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """当前账户状态：现金 + 持仓 + 市值"""
    config = await _get_config(db, current_user.id, strategy_id)

    # 现金
    trades = await _get_all_trades(db, current_user.id, strategy_id)
    cash = config.initial_capital + sum(t.net_amount for t in trades)

    # 持仓
    holdings = await _compute_holdings(db, current_user.id, strategy_id)

    total_market_value = sum(h["market_value"] for h in holdings)
    total_cost_basis = sum(h["cost_basis"] for h in holdings)
    total_nav = cash + total_market_value
    total_return_pct = (
        round((total_nav - config.initial_capital) / config.initial_capital * 100, 4)
        if config.initial_capital > 0
        else 0.0
    )

    last_trade = trades[-1] if trades else None

    return {
        "strategy_id": strategy_id,
        "initial_capital": config.initial_capital,
        "cash": round(cash, 2),
        "holdings": holdings,
        "total_market_value": round(total_market_value, 2),
        "total_cost_basis": round(total_cost_basis, 2),
        "total_nav": round(total_nav, 2),
        "total_return_pct": total_return_pct,
        "last_exec_date": last_trade.exec_date if last_trade else None,
        "last_rec_date": last_trade.rec_date if last_trade else None,
        "trade_count": len(trades),
    }


# ── POST /execute ────────────────────────────────────────────


@router.post("/execute")
async def execute_paper_trade(
    data: ExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """执行一次调仓

    1. 找到 T 日（≤ 请求日期的最近交易日）
    2. 获取 T 日策略推荐 Top 3
    3. 找到 T+1 日（> T 的下一个交易日）
    4. 以 T+1 开盘价卖出全部持仓
    5. 以 T+1 开盘价等权买入 Top 3
    """
    user_id = current_user.id
    requested_date = data.date or _beijing_today()

    # ── Step 1: 获取配置 ──
    config = await _get_config(db, user_id, data.strategy_id)

    # ── Step 2: 找 T 日 ──
    T = await _find_nearest_trading_day(db, requested_date)
    if not T:
        raise HTTPException(400, "没有找到最近的交易日")

    # ── Step 3: 找 T+1 日（含向前回溯）──
    today_str = _beijing_today()
    T_plus_1 = await _find_next_trading_day(db, T)

    if not T_plus_1 or T_plus_1 > today_str:
        # T+1 不存在或尚未发生，向前回溯找最近一个有效的 T/T+1 对
        original_T = T
        prev_result = await db.execute(
            select(Daily.trade_date)
            .where(Daily.trade_date < T)
            .order_by(Daily.trade_date.desc())
        )
        found = False
        for (prev_T,) in prev_result:
            next_day = await _find_next_trading_day(db, prev_T)
            if next_day and next_day <= today_str:
                T = prev_T
                T_plus_1 = next_day
                found = True
                break

        if not found:
            if not T_plus_1:
                raise HTTPException(
                    400,
                    f"未找到 {original_T} 之后的下一个交易日，请确认已同步最新数据",
                )
            else:
                raise HTTPException(
                    400,
                    f"T+1 执行日 {T_plus_1} 尚未发生（今天是 {today_str}），无法执行",
                )

    # ── Step 4: 防重复 ──
    existing = await db.execute(
        select(PaperTrade).where(
            PaperTrade.user_id == user_id,
            PaperTrade.strategy_id == data.strategy_id,
            PaperTrade.rec_date == T,
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"推荐日 {T} 已执行过调仓，请勿重复操作")

    # ── Step 5: 获取 T 日推荐 ──
    cutoff = T.replace("-", "")
    rec_result = await db.execute(
        select(StrategyDailyRec).where(
            StrategyDailyRec.strategy_id == data.strategy_id,
            StrategyDailyRec.cutoff_date == cutoff,
        ).limit(1)
    )
    rec_row = rec_result.scalar_one_or_none()
    if not rec_row:
        raise HTTPException(400, f"日期 {T} 无策略推荐数据，请先刷新推荐")

    try:
        all_recs = json.loads(rec_row.recommendations)
    except json.JSONDecodeError:
        raise HTTPException(500, "推荐数据解析失败")

    if not all_recs:
        raise HTTPException(400, f"日期 {T} 策略未返回推荐")

    top3 = all_recs[:3]

    # ── Step 6: 获取 T+1 开盘价 ──
    new_codes = [r["ts_code"] for r in top3]
    current_holdings = await _compute_holdings(db, user_id, data.strategy_id)
    old_codes = [h["ts_code"] for h in current_holdings]
    all_codes = list(set(new_codes + old_codes))

    open_result = await db.execute(
        select(Daily.ts_code, Daily.open)
        .where(Daily.trade_date == T_plus_1, Daily.ts_code.in_(all_codes))
    )
    open_prices = {}
    for row in open_result:
        val = float(row.open) if row.open else 0.0
        if val > 0:
            open_prices[row.ts_code] = val

    # 校验价格完整性
    missing_new = [c for c in new_codes if c not in open_prices]
    missing_old = [c for c in old_codes if c not in open_prices]
    if missing_new:
        raise HTTPException(400, f"T+1 ({T_plus_1}) 缺少新股开盘价: {missing_new}")
    if missing_old:
        raise HTTPException(400, f"T+1 ({T_plus_1}) 缺少旧股开盘价: {missing_old}")

    # ── Step 7: 计算可用现金 ──
    all_trades = await _get_all_trades(db, user_id, data.strategy_id)
    cash = config.initial_capital + sum(t.net_amount for t in all_trades)
    cash_before = round(cash, 2)

    trades_to_insert: List[PaperTrade] = []

    # ── Step 8: 卖出全部持仓 ──
    for h in current_holdings:
        price = open_prices[h["ts_code"]]
        gross = round(h["shares"] * price, 2)
        commission = round(gross * SELL_COMMISSION_RATE, 2)
        stamp = round(gross * STAMP_DUTY_RATE, 2)
        net = round(gross - commission - stamp, 2)
        cash += net

        trades_to_insert.append(PaperTrade(
            user_id=user_id,
            strategy_id=data.strategy_id,
            action="sell",
            exec_date=T_plus_1,
            rec_date=T,
            ts_code=h["ts_code"],
            stock_name=h["stock_name"],
            shares=h["shares"],
            price=price,
            amount=gross,
            commission=commission,
            stamp_duty=stamp,
            net_amount=net,
        ))

    sell_count = len(current_holdings)

    # ── Step 9: 等权买入 Top 3 ──
    per_stock_budget = cash / 3.0
    buy_count = 0

    for rec in top3:
        code = rec["ts_code"]
        price = open_prices[code]
        if price <= 0:
            continue

        # shares = floor(budget / (price * (1 + commission_rate)))
        lot = _lot_size(code)
        raw_shares = int(per_stock_budget / (price * (1 + BUY_COMMISSION_RATE)))
        shares = (raw_shares // lot) * lot

        if shares < lot:
            continue  # 不够买一手，跳过

        gross = round(shares * price, 2)
        commission = round(gross * BUY_COMMISSION_RATE, 2)
        net = round(-(gross + commission), 2)  # 现金流出
        cash += net

        trades_to_insert.append(PaperTrade(
            user_id=user_id,
            strategy_id=data.strategy_id,
            action="buy",
            exec_date=T_plus_1,
            rec_date=T,
            ts_code=code,
            stock_name=rec.get("name", code),
            shares=shares,
            price=price,
            amount=gross,
            commission=commission,
            stamp_duty=0.0,
            net_amount=net,
        ))
        buy_count += 1

    # ── Step 10: 校验 & 保存 ──
    if not trades_to_insert:
        raise HTTPException(400, "无有效交易生成，请检查推荐和资金")

    buy_ts = [t for t in trades_to_insert if t.action == "buy"]
    if not buy_ts and sell_count > 0:
        raise HTTPException(400, "卖出成功但所有新股资金不足（不够买一手），请检查资金")

    db.add_all(trades_to_insert)
    await db.commit()

    # 刷新获取 IDs
    for t in trades_to_insert:
        await db.refresh(t)

    # ── Build response ──
    sell_trades = [t for t in trades_to_insert if t.action == "sell"]
    buy_trades = [t for t in trades_to_insert if t.action == "buy"]

    total_buy_amount = sum(t.amount for t in buy_trades)
    total_sell_amount = sum(t.amount for t in sell_trades)
    total_commission = sum(t.commission for t in trades_to_insert)
    total_stamp_duty = sum(t.stamp_duty for t in trades_to_insert)

    # 最新持仓数
    final_holdings = await _compute_holdings(db, user_id, data.strategy_id)

    return {
        "executed": True,
        "rec_date": T,
        "exec_date": T_plus_1,
        "trades": [
            {
                "id": t.id,
                "action": t.action,
                "exec_date": t.exec_date,
                "rec_date": t.rec_date,
                "ts_code": t.ts_code,
                "stock_name": t.stock_name,
                "shares": t.shares,
                "price": t.price,
                "amount": t.amount,
                "commission": t.commission,
                "stamp_duty": t.stamp_duty,
                "net_amount": t.net_amount,
            }
            for t in trades_to_insert
        ],
        "summary": {
            "cash_before": cash_before,
            "cash_after": round(cash, 2),
            "holdings_before": len(current_holdings),
            "holdings_after": len(final_holdings),
            "sell_count": sell_count,
            "buy_count": buy_count,
            "total_buy_amount": round(total_buy_amount, 2),
            "total_sell_amount": round(total_sell_amount, 2),
            "total_commission": round(total_commission, 2),
            "total_stamp_duty": round(total_stamp_duty, 2),
        },
    }


# ── GET /nav ─────────────────────────────────────────────────


@router.get("/nav")
async def get_nav(
    strategy_id: int = Query(..., description="策略 ID"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """模拟盘净值历史（逐日回放）"""
    user_id = current_user.id
    config = await _get_config(db, user_id, strategy_id)

    # 获取所有交易
    trades = await _get_all_trades(db, user_id, strategy_id)
    if not trades:
        return {
            "strategy_id": strategy_id,
            "initial_capital": config.initial_capital,
            "nav": [],
            "count": 0,
            "message": "暂无交易记录",
        }

    # 确定日期范围
    first_date = start_date or trades[0].exec_date
    last_date = end_date or _beijing_today()

    # 获取日期范围内所有交易日
    days_result = await db.execute(
        select(Daily.trade_date)
        .where(Daily.trade_date >= first_date, Daily.trade_date <= last_date)
        .distinct()
        .order_by(Daily.trade_date.asc())
    )
    all_dates = [row[0] for row in days_result]

    if not all_dates:
        return {
            "strategy_id": strategy_id,
            "initial_capital": config.initial_capital,
            "nav": [],
            "count": 0,
            "message": "日期范围内无交易日",
        }

    # 按执行日建立交易索引
    trades_by_date: dict = defaultdict(list)
    all_ts_codes: set = set()
    for t in trades:
        trades_by_date[t.exec_date].append(t)
        all_ts_codes.add(t.ts_code)

    # 批量查询所有日期的收盘价
    close_result = await db.execute(
        select(Daily.trade_date, Daily.ts_code, Daily.close)
        .where(
            Daily.trade_date.in_(all_dates),
            Daily.ts_code.in_(list(all_ts_codes)),
        )
    )
    close_index: dict = defaultdict(dict)
    for row in close_result:
        close_index[row.trade_date][row.ts_code] = float(row.close or 0)

    # 逐日回放
    positions: dict = {}  # {ts_code: shares}
    cash = config.initial_capital
    nav_points = []

    for date in all_dates:
        # 应用当日交易
        for t in trades_by_date.get(date, []):
            if t.action == "buy":
                positions[t.ts_code] = positions.get(t.ts_code, 0) + t.shares
            else:  # sell
                positions[t.ts_code] = positions.get(t.ts_code, 0) - t.shares
                if positions[t.ts_code] <= 0:
                    positions.pop(t.ts_code, None)
            cash += t.net_amount

        # 清理零持仓
        positions = {k: v for k, v in positions.items() if v > 0}

        # 估值
        holdings_value = 0.0
        day_prices = close_index.get(date, {})
        for ts_code, shares in positions.items():
            price = day_prices.get(ts_code, 0)
            holdings_value += shares * price

        total_value = cash + holdings_value
        return_pct = (
            round((total_value - config.initial_capital) / config.initial_capital * 100, 4)
            if config.initial_capital > 0
            else 0.0
        )

        nav_points.append({
            "date": date,
            "cash": round(cash, 2),
            "holdings_value": round(holdings_value, 2),
            "total_value": round(total_value, 2),
            "return_pct": return_pct,
        })

    return {
        "strategy_id": strategy_id,
        "initial_capital": config.initial_capital,
        "nav": nav_points,
        "count": len(nav_points),
    }


# ── GET /trades ──────────────────────────────────────────────


@router.get("/trades")
async def get_trades(
    strategy_id: int = Query(..., description="策略 ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """交易历史（分页）"""
    user_id = current_user.id

    # 总数
    count_result = await db.execute(
        select(func.count(PaperTrade.id)).where(
            PaperTrade.user_id == user_id,
            PaperTrade.strategy_id == strategy_id,
        )
    )
    total = count_result.scalar() or 0

    # 分页查询
    offset = (page - 1) * page_size
    result = await db.execute(
        select(PaperTrade)
        .where(
            PaperTrade.user_id == user_id,
            PaperTrade.strategy_id == strategy_id,
        )
        .order_by(PaperTrade.exec_date.desc(), PaperTrade.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    trades = result.scalars().all()

    return {
        "strategy_id": strategy_id,
        "trades": [
            {
                "id": t.id,
                "action": t.action,
                "exec_date": t.exec_date,
                "rec_date": t.rec_date,
                "ts_code": t.ts_code,
                "stock_name": t.stock_name,
                "shares": t.shares,
                "price": t.price,
                "amount": t.amount,
                "commission": t.commission,
                "stamp_duty": t.stamp_duty,
                "net_amount": t.net_amount,
            }
            for t in trades
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ── DELETE /reset ────────────────────────────────────────────


@router.delete("/reset")
async def reset_paper_trade(
    strategy_id: int = Query(..., description="策略 ID"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """清空所有模拟交易记录（本金保留）"""
    result = await db.execute(
        delete(PaperTrade).where(
            PaperTrade.user_id == current_user.id,
            PaperTrade.strategy_id == strategy_id,
        )
    )
    await db.commit()
    return {
        "strategy_id": strategy_id,
        "message": "交易记录已清空，本金不变",
        "deleted_count": result.rowcount,
    }
