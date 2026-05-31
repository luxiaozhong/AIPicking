"""回测引擎核心（新逻辑：截止日推荐 + 后续表现追踪）"""

import ast
import sys
import io
import os
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from ..config import settings
from ..models.stock_tables import Stock, Daily, DailySectorFlow

# 同步引擎（用于 thread pool 中的回测）
_sync_engine = create_engine(settings.SYNC_DATABASE_URL)
SyncSession = sessionmaker(bind=_sync_engine)

# 推荐股票数量上限
MAX_RECOMMENDATIONS = 10


def _get_db():
    """获取同步数据库会话（回测线程中使用）"""
    return SyncSession()


class BacktestEngine:
    """策略回测引擎（新逻辑）

    核心流程：
    1. 加载截止日及之前的所有历史数据
    2. 运行策略代码，选出评分最高的 5-10 只股票
    3. 追踪这些股票在截止日后 N 天的表现（涨跌幅）
    4. 汇总结果
    """

    def __init__(
        self,
        strategy_code: str,
        strategy_params: Dict[str, Any],
        config: dict = None,
    ):
        self.strategy_code = strategy_code
        self.strategy_params = strategy_params
        self.config = config
        self.strategy_func = None
        self._load_strategy()

    def _load_strategy(self) -> None:
        """加载策略代码（安全检查 + 编译）"""
        is_valid, error_msg = self._validate_strategy(self.strategy_code)
        if not is_valid:
            raise ValueError(f"策略代码验证失败: {error_msg}")

        try:
            code_obj = compile(self.strategy_code, "<strategy>", "exec")
        except SyntaxError as e:
            raise ValueError(f"策略代码语法错误: {e}")

        strategy_globals = {"__builtins__": self._get_restricted_builtins()}

        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)

        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()

        try:
            exec(code_obj, strategy_globals)
        except Exception as e:
            sys.stdout = old_stdout
            raise ValueError(f"策略代码执行错误: {e}")

        sys.stdout = old_stdout

        run_func = strategy_globals.get('run')
        strategy_class = strategy_globals.get('Strategy')

        if run_func and callable(run_func):
            self.strategy_func = run_func
        elif strategy_class and callable(strategy_class):
            pd = strategy_globals.get('pd')
            np = strategy_globals.get('np')
            if not pd or not np:
                raise ValueError("策略代码缺少 pandas 或 numpy 导入")

            strategy_instance = strategy_class()

            def make_run_wrapper(pd, np, instance):
                def run_wrapper(data):
                    stocks = data["stocks"]
                    daily = data["daily"]
                    recommendations = []
                    for stock in stocks:
                        ts_code = stock["ts_code"]
                        if ts_code not in daily:
                            continue
                        df = pd.DataFrame(daily[ts_code])
                        if len(df) == 0:
                            continue
                        try:
                            signals = instance.generate_signals(df)
                        except Exception:
                            continue
                        if "buy" in signals.columns and signals["buy"].iloc[-1] == 1:
                            score = 50
                            recommendations.append({
                                "ts_code": ts_code,
                                "name": stock.get("name", ts_code),
                                "score": score,
                                "signal": "买入信号"
                            })
                    recommendations.sort(key=lambda x: x["score"], reverse=True)
                    return recommendations[:MAX_RECOMMENDATIONS]
                return run_wrapper

            self.strategy_func = make_run_wrapper(pd, np, strategy_instance)()
        else:
            raise ValueError("策略代码缺少必需的函数：run(data) 或 Strategy 类")

    def _get_restricted_builtins(self) -> Dict[str, Any]:
        import builtins
        safe_builtins = {}
        safe_list = [
            '__import__', 'abs', 'all', 'any', 'bin', 'bool', 'chr', 'complex',
            'dict', 'dir', 'enumerate', 'filter', 'float', 'format',
            'frozenset', 'hash', 'hex', 'int', 'isinstance', 'issubclass',
            'len', 'list', 'map', 'max', 'min', 'next', 'object',
            'oct', 'ord', 'pow', 'print', 'range', 'repr', 'reversed',
            'round', 'set', 'slice', 'sorted', 'str', 'sum', 'tuple',
            'type', 'zip'
        ]
        for name in safe_list:
            if hasattr(builtins, name):
                safe_builtins[name] = getattr(builtins, name)
        return safe_builtins

    def _validate_strategy(self, code: str) -> Tuple[bool, str]:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"语法错误: {e}"
        FORBIDDEN_IMPORTS = {'os', 'sys', 'subprocess', 'builtins'}
        FORBIDDEN_FUNCS = {'exec', 'eval', 'open', '__import__'}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_IMPORTS:
                        return False, f"禁止导入模块: {alias.name}"
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in FORBIDDEN_FUNCS:
                        return False, f"禁止调用函数: {node.func.id}"
        return True, ""

    def run(
        self,
        cutoff_date: str,
        track_days: List[int] = [3, 7, 15]
    ) -> Dict[str, Any]:
        stocks_data, daily_data, sector_flow_data = self._load_data(cutoff_date)

        ts_code = (self.config or {}).get("ts_code", "").strip()
        if ts_code:
            if ts_code in daily_data:
                daily_data = {ts_code: daily_data[ts_code]}
            else:
                return {"recommendations": [], "summary": self._empty_summary()}

        strategy_input = {
            "cutoff_date": cutoff_date,
            "stocks": stocks_data,
            "daily": daily_data,
            "sector_flow": sector_flow_data,
            "config": self.config or {},
        }

        try:
            recommendations = self.strategy_func(strategy_input)
        except Exception as e:
            raise RuntimeError(f"策略执行失败: {e}")

        if not recommendations or not isinstance(recommendations, list):
            return {"recommendations": [], "summary": self._empty_summary()}

        recommendations = recommendations[:MAX_RECOMMENDATIONS]
        recommendations = self._track_performance(recommendations, cutoff_date, track_days)
        summary = self._calculate_summary(recommendations, track_days)

        return {"recommendations": recommendations, "summary": summary}

    def run_batch(
        self,
        start_date: str,
        end_date: str,
        track_days: List[int] = [3, 7, 15]
    ) -> List[Dict[str, Any]]:
        stocks_data, daily_data, sector_flow_data = self._load_data_range(start_date, end_date)

        trading_days = sorted(set(
            row["trade_date"] for rows in daily_data.values() for row in rows
            if start_date <= row["trade_date"] <= end_date
        ))

        ts_code = (self.config or {}).get("ts_code", "").strip()
        results = []

        for cutoff_date in trading_days:
            daily_result = {
                "cutoff_date": cutoff_date,
                "input": {"cutoff_date": cutoff_date, "config": self.config or {}},
            }
            try:
                sliced_daily = {}
                for code, rows in daily_data.items():
                    sliced_rows = [r for r in rows if r["trade_date"] <= cutoff_date]
                    if sliced_rows:
                        sliced_daily[code] = sliced_rows

                if ts_code:
                    sliced_daily = {ts_code: sliced_daily[ts_code]} if ts_code in sliced_daily else {}

                strategy_input = {
                    "cutoff_date": cutoff_date,
                    "stocks": stocks_data,
                    "daily": sliced_daily,
                    "sector_flow": sector_flow_data,
                    "config": self.config or {},
                }

                recommendations = self.strategy_func(strategy_input)
                if not recommendations or not isinstance(recommendations, list):
                    recommendations = []

                recommendations = recommendations[:MAX_RECOMMENDATIONS]
                recommendations = self._track_performance(recommendations, cutoff_date, track_days)
                summary = self._calculate_summary(recommendations, track_days)

                daily_result["status"] = "completed"
                daily_result["recommendations"] = recommendations
                daily_result["summary"] = summary
            except Exception as e:
                daily_result["status"] = "failed"
                daily_result["error_message"] = str(e)

            results.append(daily_result)

        return results

    def _load_data(self, cutoff_date: str) -> Tuple[List[Dict], Dict[str, List[Dict]], List[Dict]]:
        """从 PostgreSQL 加载历史数据（截止日及之前）"""
        session = _get_db()
        try:
            # 1. 股票基础信息
            stmt = select(
                Stock.ts_code, Stock.symbol, Stock.name, Stock.market,
                Stock.industry_l1, Stock.industry_l2, Stock.industry_l3,
                Stock.concepts, Stock.total_shares, Stock.float_shares
            ).where(Stock.ts_code.isnot(None), Stock.ts_code != "")
            stocks_result = session.execute(stmt)
            stocks_data = [dict(row._mapping) for row in stocks_result]

            # 2. 日期范围
            cutoff_dt = datetime.strptime(cutoff_date, "%Y%m%d")
            start_date = (cutoff_dt - timedelta(days=180)).strftime("%Y%m%d")
            flow_start_date = (cutoff_dt - timedelta(days=30)).strftime("%Y-%m-%d")
            cutoff_date_fmt = cutoff_dt.strftime("%Y-%m-%d")

            # 3. 日线数据
            daily_stmt = select(
                Daily.ts_code, Daily.trade_date, Daily.open, Daily.high,
                Daily.low, Daily.close, Daily.vol, Daily.amount,
                Daily.adj_close, Daily.market_cap, Daily.circ_market_cap
            ).where(
                Daily.trade_date.between(start_date, cutoff_date)
            ).order_by(Daily.ts_code, Daily.trade_date)
            daily_result = session.execute(daily_stmt)
            daily_rows = [dict(row._mapping) for row in daily_result]

            # 4. 板块资金流向
            sector_stmt = select(DailySectorFlow).where(
                DailySectorFlow.trade_date.between(flow_start_date, cutoff_date_fmt)
            ).order_by(DailySectorFlow.trade_date, DailySectorFlow.sector_type, DailySectorFlow.sector_name)
            sector_result = session.execute(sector_stmt)
            sector_flow_data = [dict(row._mapping) for row in sector_result]
        finally:
            session.close()

        # 5. 按 ts_code 分组
        daily_data = {}
        for row in daily_rows:
            ts_code = row["ts_code"]
            if ts_code not in daily_data:
                daily_data[ts_code] = []
            daily_data[ts_code].append({
                "trade_date": row["trade_date"], "open": row["open"],
                "high": row["high"], "low": row["low"], "close": row["close"],
                "vol": row["vol"], "amount": row["amount"],
                "adj_close": row["adj_close"], "market_cap": row["market_cap"],
                "circ_market_cap": row["circ_market_cap"],
            })

        return stocks_data, daily_data, sector_flow_data

    def _load_data_range(self, start_date: str, end_date: str) -> Tuple[List[Dict], Dict[str, List[Dict]], List[Dict]]:
        """加载全时段历史数据"""
        session = _get_db()
        try:
            stmt = select(
                Stock.ts_code, Stock.symbol, Stock.name, Stock.market,
                Stock.industry_l1, Stock.industry_l2, Stock.industry_l3,
                Stock.concepts, Stock.total_shares, Stock.float_shares
            ).where(Stock.ts_code.isnot(None), Stock.ts_code != "")
            stocks_data = [dict(row._mapping) for row in session.execute(stmt)]

            start_dt = datetime.strptime(start_date, "%Y%m%d")
            earliest_date = (start_dt - timedelta(days=180)).strftime("%Y%m%d")
            flow_earliest_date = (start_dt - timedelta(days=30)).strftime("%Y-%m-%d")
            end_date_fmt = datetime.strptime(end_date, "%Y%m%d").strftime("%Y-%m-%d")

            daily_stmt = select(
                Daily.ts_code, Daily.trade_date, Daily.open, Daily.high,
                Daily.low, Daily.close, Daily.vol, Daily.amount,
                Daily.adj_close, Daily.market_cap, Daily.circ_market_cap
            ).where(
                Daily.trade_date.between(earliest_date, end_date)
            ).order_by(Daily.ts_code, Daily.trade_date)
            daily_rows = [dict(row._mapping) for row in session.execute(daily_stmt)]

            sector_stmt = select(DailySectorFlow).where(
                DailySectorFlow.trade_date.between(flow_earliest_date, end_date_fmt)
            ).order_by(DailySectorFlow.trade_date, DailySectorFlow.sector_type, DailySectorFlow.sector_name)
            sector_flow_data = [dict(row._mapping) for row in session.execute(sector_stmt)]
        finally:
            session.close()

        daily_data = {}
        for row in daily_rows:
            ts_code = row["ts_code"]
            if ts_code not in daily_data:
                daily_data[ts_code] = []
            daily_data[ts_code].append({
                "trade_date": row["trade_date"], "open": row["open"],
                "high": row["high"], "low": row["low"], "close": row["close"],
                "vol": row["vol"], "amount": row["amount"],
                "adj_close": row["adj_close"], "market_cap": row["market_cap"],
                "circ_market_cap": row["circ_market_cap"],
            })

        return stocks_data, daily_data, sector_flow_data

    def _track_performance(
        self,
        recommendations: List[Dict],
        cutoff_date: str,
        track_days: List[int]
    ) -> List[Dict]:
        session = _get_db()
        try:
            ts_codes = [r['ts_code'] for r in recommendations]
            if not ts_codes:
                return recommendations

            # 截止日价格
            stmt = select(
                Daily.ts_code, Daily.adj_close, Daily.close
            ).where(
                Daily.ts_code.in_(ts_codes),
                Daily.trade_date == cutoff_date
            )
            cutoff_prices = {}
            for row in session.execute(stmt):
                price = row.adj_close if row.adj_close else row.close
                cutoff_prices[row.ts_code] = price

            # 前一日价格
            prev_day_prices = {}
            for ts_code in ts_codes:
                prev_stmt = select(
                    Daily.adj_close, Daily.close
                ).where(
                    Daily.ts_code == ts_code,
                    Daily.trade_date < cutoff_date
                ).order_by(Daily.trade_date.desc()).limit(1)
                prev_row = session.execute(prev_stmt).first()
                if prev_row:
                    prev_day_prices[ts_code] = (
                        prev_row.adj_close if prev_row.adj_close else prev_row.close
                    )

            # 当日涨跌
            for rec in recommendations:
                ts_code = rec['ts_code']
                cutoff_price = cutoff_prices.get(ts_code)
                prev_price = prev_day_prices.get(ts_code)
                if cutoff_price and prev_price:
                    rec['return_0d'] = round(
                        (cutoff_price - prev_price) / prev_price, 6
                    )
                else:
                    rec['return_0d'] = None

            # 后续表现追踪
            for rec in recommendations:
                ts_code = rec['ts_code']
                cutoff_price = cutoff_prices.get(ts_code)
                if not cutoff_price:
                    for d in track_days:
                        rec[f'return_{d}d'] = None
                    continue

                future_stmt = select(
                    Daily.trade_date, Daily.adj_close, Daily.close
                ).where(
                    Daily.ts_code == ts_code,
                    Daily.trade_date > cutoff_date
                ).order_by(Daily.trade_date).limit(30)
                future_rows = session.execute(future_stmt).all()

                future_prices = {}
                for row in future_rows:
                    price = row.adj_close if row.adj_close else row.close
                    future_prices[row.trade_date] = price

                future_dates = sorted(future_prices.keys())
                for d in track_days:
                    if len(future_dates) >= d:
                        target_price = future_prices[future_dates[d - 1]]
                        rec[f'return_{d}d'] = round(
                            (target_price - cutoff_price) / cutoff_price, 6
                        )
                    else:
                        rec[f'return_{d}d'] = None
        finally:
            session.close()

        return recommendations

    def _calculate_summary(
        self,
        recommendations: List[Dict],
        track_days: List[int]
    ) -> Dict[str, Any]:
        if not recommendations:
            return self._empty_summary()

        summary = {"total_recommendations": len(recommendations)}

        for d in [3, 7, 15]:
            field = f'return_{d}d'
            returns = [r[field] for r in recommendations if r.get(field) is not None]
            if returns:
                avg_return = sum(returns) / len(returns)
                win_rate = sum(1 for r in returns if r > 0) / len(returns)
                best = max(returns)
                worst = min(returns)
            else:
                avg_return = 0.0
                win_rate = 0.0
                best = 0.0
                worst = 0.0

            summary[f'avg_return_{d}d'] = round(avg_return, 6)
            summary[f'win_rate_{d}d'] = round(win_rate, 4)
            summary[f'best_return_{d}d'] = round(best, 6)
            summary[f'worst_return_{d}d'] = round(worst, 6)

        return summary

    def _empty_summary(self) -> Dict[str, Any]:
        return {
            "total_recommendations": 0,
            "avg_return_3d": 0.0, "win_rate_3d": 0.0,
            "best_return_3d": 0.0, "worst_return_3d": 0.0,
            "avg_return_7d": 0.0, "win_rate_7d": 0.0,
            "best_return_7d": 0.0, "worst_return_7d": 0.0,
            "avg_return_15d": 0.0, "win_rate_15d": 0.0,
            "best_return_15d": 0.0, "worst_return_15d": 0.0,
        }

    def run_live(self, cutoff_date: str, ts_code: str = None) -> List[Dict]:
        stocks_data, daily_data, sector_flow_data = self._load_data(cutoff_date)

        if ts_code:
            if ts_code in daily_data:
                daily_data = {ts_code: daily_data[ts_code]}
            else:
                return []

        strategy_input = {
            "cutoff_date": cutoff_date,
            "stocks": stocks_data,
            "daily": daily_data,
            "sector_flow": sector_flow_data,
            "config": self.config or {},
        }

        try:
            recommendations = self.strategy_func(strategy_input)
        except Exception as e:
            raise RuntimeError(f"策略执行失败: {e}")

        if not recommendations or not isinstance(recommendations, list):
            return []

        return recommendations[:MAX_RECOMMENDATIONS]
