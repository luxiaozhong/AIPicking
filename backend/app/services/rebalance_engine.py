"""
每日调仓回测引擎

核心流程：
1. 加载全时段数据（日线、资金流、成分股）
2. 逐日迭代：
   a. 开盘：执行前一日计划好的买卖订单
   b. 收盘：记录持仓快照（以收盘价估值）
   c. 盘后：运行策略获取当日 top N → 对比持仓 → 制定次日调仓计划
3. 汇总统计

费用：
- 买入手续费：万 1.5（成交金额 × 0.00015）
- 卖出手续费：万 1.5
- 卖出印花税：千 3（成交金额 × 0.003，仅卖出）

资金分配：尽量平均分配到 N 只股票，全仓买入（扣除手续费后）
"""

import json
from collections import defaultdict
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select, update as sql_update
from sqlalchemy.orm import sessionmaker
from ..config import settings
from ..models.rebalance import RebalanceReport
from ..models.strategy import Strategy
from ..models.stock_tables import Daily
from ..models.base import beijing_now

# ── 费率常量 ──────────────────────────────────────────────
BUY_COMMISSION_RATE = 0.00015   # 万 1.5 买入手续费
SELL_COMMISSION_RATE = 0.00015  # 万 1.5 卖出手续费
STAMP_DUTY_RATE = 0.003         # 千 3 印花税（仅卖出）

# ── 分块加载常量 ──────────────────────────────────────────
CHUNK_SIZE = 20  # 每批加载的交易日数量

_sync_engine = create_engine(settings.SYNC_DATABASE_URL)
SyncSession = sessionmaker(bind=_sync_engine)


def _get_price(day: dict, key: str = "close") -> Optional[float]:
    """获取优先复权价"""
    v = day.get("adj_close")
    if v is not None:
        return v
    return day.get(key)


def _buy_commission(amount: float) -> float:
    return amount * BUY_COMMISSION_RATE


def _sell_cost(gross_amount: float) -> tuple:
    """返回 (commission, stamp_duty, net_proceeds)"""
    commission = gross_amount * SELL_COMMISSION_RATE
    stamp_duty = gross_amount * STAMP_DUTY_RATE
    return commission, stamp_duty, gross_amount - commission - stamp_duty


def _get_trading_days(session, start_fmt: str, end_fmt: str) -> List[str]:
    """获取指定日期范围内的交易日列表（从 daily 表 DISTINCT trade_date）"""
    stmt = (
        select(Daily.trade_date)
        .where(Daily.trade_date.between(start_fmt, end_fmt))
        .distinct()
        .order_by(Daily.trade_date)
    )
    return [r[0] for r in session.execute(stmt)]


class RebalanceEngine:
    """每日调仓回测引擎"""

    def __init__(
        self,
        strategy_code: str,
        strategy_params: Dict[str, Any],
        config: Dict[str, Any],
    ):
        self.strategy_code = strategy_code
        self.strategy_params = strategy_params
        self.config = config or {}

        from .backtest_engine import BacktestEngine
        self._backtest_engine = BacktestEngine(
            strategy_code=strategy_code,
            strategy_params=strategy_params,
            config=config,
        )

    def run(
        self,
        start_date: str,
        end_date: str,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """主入口（优化版：分块加载日线 + 资金流预索引 + 策略预计算注入）"""
        N = int(self.config.get("N", 5))
        M = int(self.config.get("M", 20))
        initial_capital = float(self.config.get("initial_capital", 100000))

        start_fmt = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        end_fmt = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
        start_dt = datetime.strptime(start_date, "%Y%m%d")

        session = SyncSession()
        try:
            # ── 1. 加载轻量常驻数据 ──────────────────────────
            stocks_data = self._backtest_engine._load_stocks(session)

            index_constituents_data = []
            if self._backtest_engine._should_load("index_constituents"):
                index_constituents_data = (
                    self._backtest_engine._load_index_constituents(session)
                )

            # ── 2. 加载资金流 + 按日期索引 ────────────────────
            fund_flow_start = (start_dt - timedelta(days=120)).strftime("%Y-%m-%d")
            fund_flow_data = []
            if self._backtest_engine._should_load("fund_flow"):
                fund_flow_data = self._backtest_engine._load_fund_flow(
                    session, fund_flow_start, end_fmt
                )

            flow_by_date = defaultdict(list)
            for r in fund_flow_data:
                flow_by_date[r["trade_date"]].append(r)
            # 释放 fund_flow_data 大列表，后续用 flow_by_date
            del fund_flow_data

            # ── 3. 预计算 raw_code → ts_code 映射（一次性） ───
            raw_to_tscode = {}
            ts_code_to_name = {}
            for s in stocks_data:
                ts_code = s.get("ts_code", "")
                ts_code_to_name[ts_code] = s.get("name", "")
                raw_code = ts_code.split(".")[0] if "." in ts_code else ts_code
                raw_to_tscode[raw_code] = ts_code

            # ── 4. 获取交易日列表 ─────────────────────────────
            all_trading_days = _get_trading_days(session, start_fmt, end_fmt)

            if len(all_trading_days) < 2:
                raise ValueError(
                    f"交易日不足（需要至少2天），实际: {len(all_trading_days)}天"
                )

            # ── 5. 初始化交易状态 ─────────────────────────────
            holdings = {}           # ts_code → {shares, buy_price, buy_cost}
            cash = initial_capital
            pending_sells = []      # ts_code list
            pending_buys = []       # [{ts_code, name}] list
            all_trades = []         # 所有交易记录
            daily_snapshots = []    # 每日快照
            total_fees_paid = 0.0   # 累计手续费 + 印花税

            # 资金流 M 日滚动聚合状态
            valid_dates_all = []                     # ≤today 的全部资金流日期
            flow_aggregated_m = defaultdict(float)   # M 日窗口滚动聚合
            last_day_prices = {}                     # 最后一天收盘价（清仓用）

            # ── 6. 分块加载日线，逐日处理 ─────────────────────
            for chunk_start in range(0, len(all_trading_days), CHUNK_SIZE):
                chunk_end = min(chunk_start + CHUNK_SIZE, len(all_trading_days))
                chunk_dates = all_trading_days[chunk_start:chunk_end]
                is_last_chunk = (chunk_end == len(all_trading_days))

                # 加载本 chunk 的日线数据
                chunk_daily = self._backtest_engine._load_daily_for_dates(
                    session, chunk_dates, stocks_data
                )

                # 构建 O(1) 索引: {date: {ts_code: row}}
                daily_index = defaultdict(dict)
                for ts_code, rows in chunk_daily.items():
                    for r in rows:
                        daily_index[r["trade_date"]][ts_code] = r

                # 逐日处理本 chunk
                for day_idx_offset, today in enumerate(chunk_dates):
                    day_idx = chunk_start + day_idx_offset
                    today_dt = datetime.strptime(today, "%Y-%m-%d")

                    # ── O(1) 获取今日日线 ──
                    today_prices = daily_index.get(today, {})

                    # ── 开盘：执行前一日制定的买卖计划 ──
                    for ts_code in pending_sells:
                        if ts_code not in holdings:
                            continue
                        h = holdings[ts_code]
                        day_info = today_prices.get(ts_code, {})
                        sell_price = day_info.get("open")
                        if sell_price is None or sell_price <= 0:
                            continue
                        gross_amount = h["shares"] * sell_price
                        comm, duty, net_proceeds = _sell_cost(gross_amount)
                        total_fees_paid += comm + duty
                        cash += net_proceeds

                        pnl = net_proceeds - h["buy_cost"]
                        pnl_pct = (
                            (pnl / h["buy_cost"] * 100)
                            if h["buy_cost"] > 0 else 0.0
                        )

                        all_trades.append({
                            "date": today, "ts_code": ts_code,
                            "name": ts_code_to_name.get(ts_code, ts_code),
                            "action": "sell",
                            "price": round(sell_price, 2),
                            "shares": round(h["shares"], 0),
                            "amount": round(gross_amount, 2),
                            "commission": round(comm, 2),
                            "stamp_duty": round(duty, 2),
                            "net_proceeds": round(net_proceeds, 2),
                            "buy_cost": round(h["buy_cost"], 2),
                            "pnl": round(pnl, 2),
                            "pnl_pct": round(pnl_pct, 2),
                            "reason": "调仓移除",
                        })
                        del holdings[ts_code]

                    # 再买入
                    if pending_buys:
                        n_buy = len(pending_buys)
                        per_stock_budget = cash / n_buy

                        for buy_info in pending_buys:
                            ts_code = buy_info["ts_code"]
                            day_info = today_prices.get(ts_code, {})
                            buy_price = day_info.get("open")
                            if buy_price is None or buy_price <= 0:
                                continue
                            shares = int(
                                per_stock_budget
                                / (buy_price * (1 + BUY_COMMISSION_RATE))
                                / 100
                            ) * 100
                            if shares <= 0:
                                continue
                            gross_amount = shares * buy_price
                            comm = _buy_commission(gross_amount)
                            total_cost = gross_amount + comm
                            total_fees_paid += comm

                            cash -= total_cost
                            holdings[ts_code] = {
                                "shares": shares,
                                "buy_price": buy_price,
                                "buy_cost": total_cost,
                            }
                            all_trades.append({
                                "date": today, "ts_code": ts_code,
                                "name": ts_code_to_name.get(ts_code, ts_code),
                                "action": "buy",
                                "price": round(buy_price, 2),
                                "shares": shares,
                                "amount": round(gross_amount, 2),
                                "commission": round(comm, 2),
                                "total_cost": round(total_cost, 2),
                                "reason": (
                                    "初始建仓" if day_idx == 1 else "调仓新增"
                                ),
                            })

                    # ── 收盘：记录持仓快照 ──
                    holdings_value = 0.0
                    holdings_detail = []
                    for ts_code, h in holdings.items():
                        day_info = today_prices.get(ts_code, {})
                        close_price = _get_price(day_info, "close")
                        if close_price is None:
                            close_price = h["buy_price"]
                        mv = h["shares"] * close_price
                        holdings_value += mv
                        holdings_detail.append({
                            "ts_code": ts_code,
                            "name": ts_code_to_name.get(ts_code, ts_code),
                            "shares": h["shares"],
                            "buy_price": round(h["buy_price"], 2),
                            "buy_cost": round(h["buy_cost"], 2),
                            "close_price": round(close_price, 2),
                            "market_value": round(mv, 2),
                            "unrealized_pnl": round(mv - h["buy_cost"], 2),
                            "unrealized_pnl_pct": (
                                round((mv - h["buy_cost"]) / h["buy_cost"] * 100, 2)
                                if h["buy_cost"] > 0 else 0.0
                            ),
                        })

                    total_value = cash + holdings_value
                    prev_total = (
                        daily_snapshots[-1]["total_value"] if daily_snapshots
                        else initial_capital
                    )
                    daily_return = (
                        (total_value - prev_total) / prev_total
                        if prev_total > 0 else 0.0
                    )

                    daily_snapshots.append({
                        "date": today,
                        "holdings": holdings_detail,
                        "cash": round(cash, 2),
                        "total_value": round(total_value, 2),
                        "daily_return_pct": round(daily_return * 100, 4),
                        "action": (
                            "rebalance" if (pending_sells or pending_buys) else "hold"
                        ),
                    })

                    # ── 盘后：运行策略 ──
                    # M 日滚动资金流聚合（O(1) 摊销，仅处理当日新增 + 窗口外移除）
                    if today in flow_by_date:
                        valid_dates_all.append(today)
                        for r in flow_by_date[today]:
                            flow_aggregated_m[r["ts_code"]] += (
                                r.get("main_net_flow") or 0.0
                            )

                    # 移除 M 日窗口外的日期
                    if len(valid_dates_all) > M:
                        dropped_date = valid_dates_all[-(M + 1)]
                        for r in flow_by_date.get(dropped_date, []):
                            flow_aggregated_m[r["ts_code"]] -= (
                                r.get("main_net_flow") or 0.0
                            )

                    strategy_input = {
                        "cutoff_date": today_dt.strftime("%Y%m%d"),
                        "stocks": stocks_data,
                        "daily": chunk_daily,  # 当前 chunk 的日线
                        "fund_flow": (
                            flow_by_date.get(today, [])
                        ),  # 向后兼容（大部分策略不需要全量）
                        "index_constituents": index_constituents_data,
                        "config": self.config,
                        # 预计算注入（策略可选使用）
                        "_raw_to_tscode": raw_to_tscode,
                        "_ts_code_to_name": ts_code_to_name,
                        "_flow_aggregated_m": dict(flow_aggregated_m),
                        "_valid_dates": (
                            valid_dates_all[-M:]
                            if len(valid_dates_all) >= M
                            else list(valid_dates_all)
                        ),
                    }

                    try:
                        picks = self._backtest_engine.strategy_func(strategy_input)
                    except Exception:
                        picks = []

                    if not picks or not isinstance(picks, list):
                        picks = []

                    new_codes = set()
                    for p in picks:
                        tc = p.get("ts_code", "")
                        if tc:
                            new_codes.add(tc)

                    current_codes = set(holdings.keys())

                    if day_idx == 0:
                        pending_sells = []
                        pending_buys = [
                            {"ts_code": tc, "name": ts_code_to_name.get(tc, tc)}
                            for tc in list(new_codes)[:N]
                        ]
                    elif current_codes == new_codes:
                        pending_sells = []
                        pending_buys = []
                    else:
                        to_sell = current_codes - new_codes
                        to_buy = new_codes - current_codes
                        pending_sells = list(to_sell)
                        pending_buys = [
                            {"ts_code": tc, "name": ts_code_to_name.get(tc, tc)}
                            for tc in to_buy
                        ]

                    if progress_callback:
                        progress_callback(day_idx + 1, len(all_trading_days))

                    # 最后一天：缓存收盘价供清仓使用
                    if is_last_chunk and day_idx_offset == len(chunk_dates) - 1:
                        last_day_prices = today_prices

                # 释放本 chunk 的内存
                del chunk_daily, daily_index

            # ── 7. 最后一天：清仓 ──
            for ts_code, h in list(holdings.items()):
                lp = last_day_prices.get(ts_code, {})
                sell_price = _get_price(lp, "close")
                if sell_price is None:
                    sell_price = h["buy_price"]
                gross_amount = h["shares"] * sell_price
                comm, duty, net_proceeds = _sell_cost(gross_amount)
                total_fees_paid += comm + duty
                cash += net_proceeds

                pnl = net_proceeds - h["buy_cost"]
                pnl_pct = (pnl / h["buy_cost"] * 100) if h["buy_cost"] > 0 else 0.0

                all_trades.append({
                    "date": all_trading_days[-1],
                    "ts_code": ts_code,
                    "name": ts_code_to_name.get(ts_code, ts_code),
                    "action": "sell",
                    "price": round(sell_price, 2),
                    "shares": round(h["shares"], 0),
                    "amount": round(gross_amount, 2),
                    "commission": round(comm, 2),
                    "stamp_duty": round(duty, 2),
                    "net_proceeds": round(net_proceeds, 2),
                    "buy_cost": round(h["buy_cost"], 2),
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "reason": "回测结束清仓",
                })
            holdings.clear()

        finally:
            session.close()

        # ── 8. 计算汇总统计 ─────────────────────────────────
        summary = self._calculate_summary(
            daily_snapshots, all_trades, initial_capital,
            len(all_trading_days), total_fees_paid,
        )

        return {
            "daily_snapshots": daily_snapshots,
            "trades": all_trades,
            "summary": summary,
        }

    def _calculate_summary(
        self,
        snapshots: list,
        trades: list,
        initial_capital: float,
        total_trading_days: int,
        total_fees_paid: float,
    ) -> dict:
        if not snapshots:
            return self._empty_summary(initial_capital)

        final_value = snapshots[-1]["total_value"]
        total_return_pct = (final_value - initial_capital) / initial_capital * 100

        if total_trading_days > 0:
            annualized_return = (
                (final_value / initial_capital) ** (252 / total_trading_days) - 1
            ) * 100
        else:
            annualized_return = 0.0

        peak = initial_capital
        max_dd = 0.0
        for s in snapshots:
            tv = s["total_value"]
            if tv > peak:
                peak = tv
            dd = (tv - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd

        daily_returns = [s["daily_return_pct"] for s in snapshots]
        win_days = sum(1 for r in daily_returns if r > 0)
        lose_days = sum(1 for r in daily_returns if r < 0)
        daily_win_rate = win_days / len(daily_returns) * 100 if daily_returns else 0.0

        if len(daily_returns) > 1:
            mean_ret = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
            std_ret = variance ** 0.5
            sharpe = (mean_ret / std_ret * (252 ** 0.5)) if std_ret > 0 else 0.0
        else:
            sharpe = 0.0
            mean_ret = 0.0

        # 换手率
        total_traded = sum(
            t["amount"] for t in trades
            if t["action"] in ("buy", "sell") and t.get("reason") != "回测结束清仓"
        )
        avg_value = sum(s["total_value"] for s in snapshots) / len(snapshots) if snapshots else initial_capital
        turnover = total_traded / avg_value if avg_value > 0 else 0.0

        # 已实现盈亏（不含清仓）
        closed_trades = [t for t in trades if t["action"] == "sell"]
        realized_pnl = sum(t.get("pnl", 0) for t in closed_trades)
        win_trades = sum(1 for t in closed_trades if t.get("pnl", 0) > 0)
        lose_trades = sum(1 for t in closed_trades if t.get("pnl", 0) <= 0)

        return {
            "initial_capital": initial_capital,
            "final_value": round(final_value, 2),
            "total_return_pct": round(total_return_pct, 2),
            "annualized_return_pct": round(annualized_return, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "total_trading_days": total_trading_days,
            "total_trades": len(trades),
            "total_buys": sum(1 for t in trades if t["action"] == "buy"),
            "total_sells": sum(1 for t in trades if t["action"] == "sell"),
            "turnover_rate": round(turnover, 4),
            "avg_daily_return_pct": round(mean_ret, 4),
            "win_days": win_days,
            "lose_days": lose_days,
            "daily_win_rate": round(daily_win_rate, 2),
            "total_fees_paid": round(total_fees_paid, 2),
            "realized_pnl": round(realized_pnl, 2),
            "win_trades": win_trades,
            "lose_trades": lose_trades,
            "benchmark_return_pct": 0.0,  # deprecated
        }

    def _empty_summary(self, initial_capital: float) -> dict:
        return {
            "initial_capital": initial_capital,
            "final_value": initial_capital,
            "total_return_pct": 0.0,
            "annualized_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "total_trading_days": 0,
            "total_trades": 0,
            "total_buys": 0,
            "total_sells": 0,
            "turnover_rate": 0.0,
            "avg_daily_return_pct": 0.0,
            "win_days": 0,
            "lose_days": 0,
            "daily_win_rate": 0.0,
            "total_fees_paid": 0.0,
            "realized_pnl": 0.0,
            "win_trades": 0,
            "lose_trades": 0,
            "benchmark_return_pct": 0.0,
        }
