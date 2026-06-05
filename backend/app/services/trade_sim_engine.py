# backend/app/services/trade_sim_engine.py
"""交易模拟引擎

独立于 BacktestEngine，组合复用数据加载和策略执行能力。
核心流程：选股 → 分配资金 → 逐日追踪 → 止损止盈检查 → 统计汇总
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from ..config import settings
from ..models.stock_tables import Daily
from ..factors.trade_sim_stops import StopFactorRegistry

_sync_engine = create_engine(settings.SYNC_DATABASE_URL)
SyncSession = sessionmaker(bind=_sync_engine)


def _get_db():
    return SyncSession()


def _get_price(day: dict) -> Optional[float]:
    """获取优先复权价，0.0 为有效值不会回退到 close"""
    v = day.get("adj_close")
    if v is not None:
        return v
    return day.get("close")


def _get_val(day: dict, key: str, fallback: Any = None) -> Any:
    """获取字段值，None 时使用 fallback"""
    v = day.get(key)
    if v is not None:
        return v
    return fallback


class TradeSimEngine:
    """交易模拟引擎"""

    def __init__(
        self,
        strategy_code: str,
        strategy_params: Dict[str, Any],
        config: Dict[str, Any],
    ):
        self.strategy_code = strategy_code
        self.strategy_params = strategy_params
        self.config = config  # {total_amount, top_n, max_hold_days, stop_factors: [...]}

        # 创建 BacktestEngine 实例来复用策略加载 + 数据加载
        from .backtest_engine import BacktestEngine
        self._backtest_engine = BacktestEngine(
            strategy_code=strategy_code,
            strategy_params=strategy_params,
            config=config,
        )

    def run(self, cutoff_date: str, preloaded: dict = None) -> Dict[str, Any]:
        """主入口，返回 {trades: [...], summary: {...}, total_qualifying, base_stock_count, pick_rate}

        preloaded: 可选，预加载的全时段数据字典（由 run_batch 传入），避免重复查库
        """
        # 1. 选股
        candidates, total_qualifying, base_stock_count = self._get_stock_candidates(cutoff_date, preloaded)
        if not candidates:
            return {
                "trades": [],
                "summary": self._empty_summary(),
                "total_qualifying": total_qualifying,
                "base_stock_count": base_stock_count,
                "pick_rate": round(total_qualifying / base_stock_count, 6) if base_stock_count > 0 else 0.0,
            }

        # 2. 加载追踪数据
        ts_codes = [c["ts_code"] for c in candidates]
        tracking_daily = self._load_tracking_data(ts_codes, cutoff_date)

        # 3. 逐股模拟
        top_n = self.config.get("top_n", 5)
        total_amount = self.config.get("total_amount", 100000)
        allocated = total_amount / top_n
        max_hold_days = self.config.get("max_hold_days", 60)
        stop_factors = self.config.get("stop_factors", [])

        trades = []
        for candidate in candidates:
            ts_code = candidate["ts_code"]
            daily = tracking_daily.get(ts_code, [])
            trade = self._simulate_trade(
                ts_code=ts_code,
                name=candidate.get("name", ts_code),
                score=candidate.get("score", 0),
                allocated_amount=allocated,
                daily=daily,
                stop_factors=stop_factors,
                max_hold_days=max_hold_days,
                cutoff_date=cutoff_date,
            )
            trades.append(trade)

        # 4. 汇总
        summary = self._calculate_summary(trades)
        summary["total_qualifying"] = total_qualifying
        summary["base_stock_count"] = base_stock_count
        summary["pick_rate"] = round(total_qualifying / base_stock_count, 6) if base_stock_count > 0 else 0.0

        return {
            "trades": trades,
            "summary": summary,
            "total_qualifying": total_qualifying,
            "base_stock_count": base_stock_count,
            "pick_rate": summary["pick_rate"],
        }

    def _get_stock_candidates(self, cutoff_date: str, preloaded: dict = None) -> tuple:
        """运行策略选股，按 score 降序取前 N 只。返回 (candidates, total_qualifying, base_stock_count)

        preloaded: 可选，预加载的全时段数据。传入时从中切片当天数据，跳过 _load_data 查库。
        """
        if preloaded is not None:
            # 从预加载数据中切片（批量模式，避免每个交易日重复查库）
            cutoff_date_fmt = datetime.strptime(cutoff_date, "%Y%m%d").strftime("%Y-%m-%d")
            stocks_data = preloaded["stocks"]
            raw_daily = preloaded["daily"]
            # 切片日线到 <= cutoff_date
            daily_data = {}
            for code, rows in raw_daily.items():
                sliced = [r for r in rows if r["trade_date"] <= cutoff_date_fmt]
                if sliced:
                    daily_data[code] = sliced
            # 切片横截面数据到当日
            hot_stocks = [r for r in preloaded.get("hot_stocks", []) if r.get("trade_date") == cutoff_date_fmt]
            hot_themes = [r for r in preloaded.get("hot_themes", []) if r.get("trade_date") == cutoff_date_fmt]
            loaded = {
                **preloaded,
                "daily": daily_data,
                "hot_stocks": hot_stocks,
                "hot_themes": hot_themes,
            }
        else:
            loaded = self._backtest_engine._load_data(cutoff_date)

        stocks_data = loaded["stocks"]
        daily_data = loaded["daily"]

        # 应用板块过滤
        filtered_stocks, filtered_daily, base_stock_count = self._backtest_engine._apply_board_filter(
            stocks_data, daily_data
        )

        strategy_input = {
            "cutoff_date": cutoff_date,
            **loaded,
            "stocks": filtered_stocks,
            "daily": filtered_daily,
            "config": self.config,
        }

        try:
            recommendations = self._backtest_engine.strategy_func(strategy_input)
        except Exception as e:
            raise RuntimeError(f"策略执行失败: {e}")

        if not recommendations or not isinstance(recommendations, list):
            return [], 0, base_stock_count

        total_qualifying = len(recommendations)

        # 按 score 降序排序，无 score 按名称排序
        recommendations.sort(
            key=lambda x: (x.get("score") is not None, x.get("score", 0), x.get("name", "")),
            reverse=True,
        )

        top_n = self.config.get("top_n", 5)
        return recommendations[:top_n], total_qualifying, base_stock_count

    def _load_tracking_data(self, ts_codes: List[str], cutoff_date: str) -> dict:
        """加载截止日后所有日线数据（含30日历史用于MA等指标计算）"""
        # 往前取30天用于MA10等需要历史数据的指标
        cutoff_dt = datetime.strptime(cutoff_date, "%Y%m%d")
        pre_date = (cutoff_dt - timedelta(days=40)).strftime("%Y-%m-%d")

        session = _get_db()
        try:
            stmt = select(
                Daily.ts_code, Daily.trade_date, Daily.open, Daily.high,
                Daily.low, Daily.close, Daily.adj_close, Daily.vol, Daily.amount,
            ).where(
                Daily.ts_code.in_(ts_codes),
                Daily.trade_date > pre_date,
            ).order_by(Daily.ts_code, Daily.trade_date)

            rows = [dict(row._mapping) for row in session.execute(stmt)]
        finally:
            session.close()

        result = {}
        for row in rows:
            ts_code = row["ts_code"]
            if ts_code not in result:
                result[ts_code] = []
            result[ts_code].append({
                "trade_date": row["trade_date"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "adj_close": row["adj_close"],
                "vol": row["vol"],
                "amount": row["amount"],
            })
        return result

    def _simulate_trade(
        self,
        ts_code: str,
        name: str,
        score: float,
        allocated_amount: float,
        daily: list,
        stop_factors: list,
        max_hold_days: int,
        cutoff_date: str = "",
    ) -> dict:
        """模拟单只股票的一笔交易

        daily 包含截止日前约30天+截止日后所有日线数据。
        买入日为 daily 中第一个 trade_date > cutoff_date 的交易日。
        """
        # DB 统一用 YYYY-MM-DD，cutoff_date 输入为 YYYYMMDD
        cutoff_date_fmt = f"{cutoff_date[:4]}-{cutoff_date[4:6]}-{cutoff_date[6:8]}"

        # 构建基础 trade 对象
        trade = {
            "ts_code": ts_code,
            "name": name,
            "score": score,
            "allocated_amount": allocated_amount,
            "shares": 0.0,
            "buy_price": None,
            "buy_date": None,
            "sell_price": None,
            "sell_date": None,
            "sell_reason": None,
            "hold_days": 0,
            "return_pct": None,
            "high_price": None,
            "low_price": None,
            "max_drawdown": None,
            "daily_tracking": [],
        }

        if not daily:
            trade["sell_reason"] = "数据缺失（无后续日线）"
            return trade

        # a. 找到买入日：daily 中第一个 trade_date > cutoff_date 的交易日
        buy_idx = None
        for idx, d in enumerate(daily):
            if d["trade_date"] > cutoff_date_fmt:
                buy_idx = idx
                break

        if buy_idx is None:
            trade["sell_reason"] = "数据缺失（无后续日线）"
            return trade

        buy_day = daily[buy_idx]
        buy_price = buy_day.get("open")
        if buy_price is None or buy_price <= 0:
            trade["sell_reason"] = "数据缺失（无开盘价）"
            return trade

        trade["buy_price"] = buy_price
        trade["buy_date"] = buy_day["trade_date"]
        trade["shares"] = allocated_amount / buy_price

        # b. 初始化追踪状态（使用实际日内高低价，而非收盘价）
        high_price = buy_day.get("high") if buy_day.get("high") is not None else buy_price
        low_price = buy_day.get("low") if buy_day.get("low") is not None else buy_price

        # 确定启用的因子（按 config 顺序）
        enabled_factors = [
            sf for sf in stop_factors
            if sf.get("enabled") and sf.get("id")
        ]

        # c. 逐日循环（从买入日开始，i 为 absolute index，hold_i 为持仓天数0-based）
        triggered = False
        for i in range(buy_idx, len(daily)):
            day = daily[i]
            hold_i = i - buy_idx

            close_price = _get_price(day)
            open_price = day.get("open")
            day_high = day.get("high")
            day_low = day.get("low")

            if close_price is None:
                continue

            # 更新极值（使用日内最高/最低价）
            if day_high is not None and day_high > high_price:
                high_price = day_high
            if day_low is not None and day_low < low_price:
                low_price = day_low

            # 计算 MA10（i 为 absolute index，从第0天起算；买入日前已有历史数据）
            ma10 = None
            if i >= 9:
                ma10_closes = []
                for j in range(i - 9, i + 1):
                    c = _get_price(daily[j])
                    if c is not None:
                        ma10_closes.append(c)
                if len(ma10_closes) >= 10:
                    ma10 = sum(ma10_closes) / len(ma10_closes)

            # 计算 MA60（用于止损参考线展示）
            ma60 = None
            if i >= 59:
                ma60_closes = []
                for j in range(i - 59, i + 1):
                    c = _get_price(daily[j])
                    if c is not None:
                        ma60_closes.append(c)
                if len(ma60_closes) >= 60:
                    ma60 = sum(ma60_closes) / len(ma60_closes)

            # 构建追踪记录
            current_return = (close_price - buy_price) / buy_price * 100
            tracking_record = {
                "date": day["trade_date"],
                "open": open_price,
                "close": close_price,
                "high": day_high,
                "low": day_low,
                "ma10": round(ma10, 4) if ma10 else None,
                "prev_low_ref": None,
                "ma10_stop_line": None,
                "ma60_stop_line": None,
                "trailing_stop_line": None,
                "prev_high_target": None,
                "return_pct": round(current_return, 2),
                "status": "holding",
            }

            # 计算止损参考线（用于前端展示）
            for sf in enabled_factors:
                fid = sf.get("id")
                params = sf.get("params", {})
                if fid == "stop_prev_low":
                    ref_days = params.get("ref_days", 20)
                    if i >= ref_days:
                        # 过去 ref_days 天（不含今天）的最低价，与 _check_stop_prev_low 一致
                        ref_low = None
                        for j in range(max(0, i - ref_days), i):
                            p = _get_price(daily[j])
                            if p is not None:
                                if ref_low is None or p < ref_low:
                                    ref_low = p
                        tracking_record["prev_low_ref"] = round(ref_low, 2) if ref_low else None
                elif fid == "stop_ma10_cross" and ma10 is not None:
                    coeff = params.get("coefficient", 0.93)
                    tracking_record["ma10_stop_line"] = round(ma10 * coeff, 4)
                elif fid == "stop_ma60_cross" and ma60 is not None:
                    coeff = params.get("coefficient", 0.97)
                    tracking_record["ma60_stop_line"] = round(ma60 * coeff, 4)
                elif fid == "stop_trailing_drawdown":
                    drawdown_pct = params.get("drawdown_pct", 8.0)
                    # 买入至今最高收盘价
                    highest_since_buy = None
                    for j in range(buy_idx, i + 1):
                        p = _get_price(daily[j])
                        if p is not None:
                            if highest_since_buy is None or p > highest_since_buy:
                                highest_since_buy = p
                    if highest_since_buy is not None:
                        tracking_record["trailing_stop_line"] = round(highest_since_buy * (1 - drawdown_pct / 100), 4)
                elif fid == "take_profit_prev_high":
                    lookback_days = params.get("lookback_days", 60)
                    prev_high = None
                    for j in range(max(0, buy_idx - lookback_days), buy_idx):
                        p = _get_price(daily[j])
                        if p is not None:
                            if prev_high is None or p > prev_high:
                                prev_high = p
                    if prev_high is not None:
                        tracking_record["prev_high_target"] = round(prev_high, 2)

            # 检查止损止盈（含买入当天：若买入日持续暴跌破位，次日止损卖出）
            if not triggered:
                for sf in enabled_factors:
                    fid = sf.get("id")
                    params = sf.get("params", {})
                    try:
                        check_fn = StopFactorRegistry.get_check_fn(fid)
                        # 从买入日到当天的 slice
                        result = check_fn(
                            daily[: i + 1],
                            {"buy_price": buy_price, "buy_date": trade["buy_date"], "buy_idx": buy_idx},
                            params,
                        )
                        if result is not None:
                            # 触发！卖出价 = 次日开盘价（最后一天用收盘价）
                            triggered = True
                            if i + 1 < len(daily):
                                next_open = daily[i + 1].get("open")
                                next_close = _get_price(daily[i + 1])
                                sell_price = next_open if next_open is not None else next_close
                                sell_date = daily[i + 1]["trade_date"]
                            else:
                                sell_price = close_price
                                sell_date = day["trade_date"]

                            trade["sell_price"] = sell_price
                            trade["sell_date"] = sell_date
                            trade["sell_reason"] = result.reason
                            trade["hold_days"] = hold_i + 1
                            trade["return_pct"] = round((sell_price - buy_price) / buy_price * 100, 2)
                            tracking_record["status"] = "stopped" if "止损" in result.reason else "take_profit"
                            break
                    except ValueError:
                        continue

            # 强制平仓检查
            if not triggered and hold_i + 1 >= max_hold_days:
                triggered = True
                sell_price = close_price
                sell_date = day["trade_date"]
                trade["sell_price"] = sell_price
                trade["sell_date"] = sell_date
                trade["sell_reason"] = f"强制平仓（持有超过{max_hold_days}天）"
                trade["hold_days"] = hold_i + 1
                trade["return_pct"] = round((sell_price - buy_price) / buy_price * 100, 2)
                tracking_record["status"] = "force_close"

            trade["daily_tracking"].append(tracking_record)

            # 触发止损/止盈/强制平仓后，停止追踪（持仓已平仓）
            if triggered:
                break

        # 更新极值
        trade["high_price"] = round(high_price, 2)
        trade["low_price"] = round(low_price, 2)
        if trade["buy_price"]:
            trade["max_drawdown"] = round((low_price - trade["buy_price"]) / trade["buy_price"] * 100, 2)

        # 如果始终未触发也未强制平仓（追踪数据不足 max_hold_days 天就结束了）
        if not triggered:
            trade["sell_reason"] = "数据缺失（追踪数据不足）"

        return trade

    def _calculate_summary(self, trades: List[dict]) -> dict:
        """汇总统计"""
        if not trades:
            return self._empty_summary()

        # 只统计有卖出记录的
        closed = [t for t in trades if t["return_pct"] is not None]
        if not closed:
            return self._empty_summary()

        total_trades = len(closed)
        wins = [t for t in closed if t["return_pct"] > 0]
        losses = [t for t in closed if t["return_pct"] <= 0]

        win_count = len(wins)
        lose_count = len(losses)
        win_rate = win_count / total_trades * 100 if total_trades > 0 else 0.0

        all_returns = [t["return_pct"] for t in closed]
        avg_return = sum(all_returns) / len(all_returns)

        avg_win = sum(t["return_pct"] for t in wins) / len(wins) if wins else 0.0
        avg_loss = sum(t["return_pct"] for t in losses) / len(losses) if losses else 0.0

        profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0

        # 最大连续盈亏（按买入日期排序）
        closed_sorted = sorted(closed, key=lambda t: t.get("buy_date", ""))
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0
        for t in closed_sorted:
            if t["return_pct"] > 0:
                current_wins += 1
                current_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_losses)

        # 收益分布
        dist = {"lt_-10": 0, "-10_0": 0, "0_5": 0, "5_10": 0, "gt_10": 0}
        for r in all_returns:
            if r < -10:
                dist["lt_-10"] += 1
            elif r < 0:
                dist["-10_0"] += 1
            elif r < 5:
                dist["0_5"] += 1
            elif r < 10:
                dist["5_10"] += 1
            else:
                dist["gt_10"] += 1

        # 总盈亏金额（每笔 allocated_amount * return_pct / 100 求和）
        total_pnl = sum(
            t.get("allocated_amount", 0) * t.get("return_pct", 0) / 100
            for t in closed
        )

        return {
            "total_trades": total_trades,
            "win_count": win_count,
            "lose_count": lose_count,
            "win_rate": round(win_rate, 2),
            "avg_return": round(avg_return, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_loss_ratio": round(profit_loss_ratio, 2),
            "max_consecutive_wins": max_consecutive_wins,
            "max_consecutive_losses": max_consecutive_losses,
            "total_pnl": round(total_pnl, 2),
            "return_distribution": dist,
        }

    def _empty_summary(self) -> dict:
        return {
            "total_trades": 0,
            "win_count": 0,
            "lose_count": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_loss_ratio": 0.0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "total_pnl": 0.0,
            "total_qualifying": 0,
            "base_stock_count": 0,
            "pick_rate": 0.0,
            "return_distribution": {
                "lt_-10": 0, "-10_0": 0, "0_5": 0, "5_10": 0, "gt_10": 0,
            },
        }

    def run_batch(
        self,
        start_date: str,
        end_date: str,
        progress_callback=None,
    ) -> List[Dict[str, Any]]:
        """批量交易模拟：遍历每个交易日运行交易模拟

        progress_callback: 可选，每完成一个交易日回调 progress_callback(completed_count, total_count)
        """
        # 一次性加载全时段数据（后续每个交易日切片使用，避免重复查库）
        loaded = self._backtest_engine._load_data_range(start_date, end_date)
        daily_data = loaded["daily"]

        # 获取所有交易日
        trading_days = sorted(set(
            row["trade_date"] for rows in daily_data.values() for row in rows
            if start_date <= row["trade_date"] <= end_date
        ))

        results = []
        for cutoff_date in trading_days:
            try:
                # 传入 preloaded 数据，run() 内部切片，不再重复查库
                result = self.run(cutoff_date, preloaded=loaded)
                result["cutoff_date"] = cutoff_date
                result["status"] = "completed"
            except Exception as e:
                result = {
                    "cutoff_date": cutoff_date,
                    "status": "failed",
                    "error_message": str(e),
                }
            results.append(result)

            if progress_callback:
                progress_callback(len(results), len(trading_days))

        return results
