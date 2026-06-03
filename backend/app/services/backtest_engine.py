"""回测引擎核心（新逻辑：截止日推荐 + 后续表现追踪）"""

import ast
import re
import sys
import io
import os
from typing import Dict, List, Any, Tuple, Optional, Set
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from ..config import settings
from ..models.stock_tables import (
    Stock, Daily, DailySectorFlow,
    DailyHotStock, DailyHotTheme, DailyDragonTiger, DailyDragonTigerSeat,
)
from ..models.financial import FinancialReport

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
        self.required_data: Optional[Set[str]] = None  # None = 加载全部（向后兼容）
        self._load_strategy()

    def _parse_required_data(self, code: str) -> Optional[Set[str]]:
        """从策略代码中解析 REQUIRED_DATA 声明。

        策略代码中可声明：
            REQUIRED_DATA = ["dragon_tiger", "sector_flow"]

        支持的数据源：
            - sector_flow  → daily_sector_flow 表
            - hot_stocks   → daily_hot_stock 表
            - hot_themes   → daily_hot_theme 表
            - dragon_tiger → daily_dragon_tiger + daily_dragon_tiger_seats 表

        返回 None 表示未声明 REQUIRED_DATA（向后兼容，加载全部数据）。
        返回空 set 表示声明了但不需要任何额外数据。
        """
        pattern = r'REQUIRED_DATA\s*=\s*\[(.*?)\]'
        match = re.search(pattern, code)
        if match is None:
            return None  # 未声明，加载全部
        inner = match.group(1)
        if not inner.strip():
            return set()
        items = re.findall(r'"([^"]*)"', inner)
        return set(items)

    def _should_load(self, source: str) -> bool:
        """判断是否需要加载某个数据源"""
        if self.required_data is None:
            return True  # 向后兼容：未声明则加载全部
        return source in self.required_data

    def _load_strategy(self) -> None:
        """加载策略代码（安全检查 + 编译）"""
        is_valid, error_msg = self._validate_strategy(self.strategy_code)
        if not is_valid:
            raise ValueError(f"策略代码验证失败: {error_msg}")

        # 解析 REQUIRED_DATA（在 exec 之前，用 regex 解析更可靠）
        self.required_data = self._parse_required_data(self.strategy_code)

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

    def _apply_board_filter(
        self,
        stocks_data: List[Dict],
        daily_data: Dict[str, List[Dict]],
    ) -> Tuple[List[Dict], Dict[str, List[Dict]], int]:
        """按 config.board_filter 过滤 stocks 和 daily，返回 (filtered_stocks, filtered_daily, base_count)"""
        board_filter = (self.config or {}).get("board_filter")
        if not board_filter or not isinstance(board_filter, list) or len(board_filter) == 0:
            # 未设置板块过滤，默认全板块
            board_filter = ["60", "00", "688", "689", "300", "301"]

        def _matches_board(ts_code: str) -> bool:
            return any(ts_code.startswith(prefix) for prefix in board_filter)

        filtered_stocks = [s for s in stocks_data if _matches_board(s["ts_code"])]
        # daily_data 按板块前缀独立过滤，不依赖 stocks_data
        # （daily 表包含退市/摘牌股票，这些股票不在 stocks 表但策略仍需要）
        filtered_daily = {
            code: rows for code, rows in daily_data.items()
            if _matches_board(code)
        }

        return filtered_stocks, filtered_daily, len(filtered_stocks)

    def run(
        self,
        cutoff_date: str,
        track_days: List[int] = [3, 7, 15]
    ) -> Dict[str, Any]:
        loaded = self._load_data(cutoff_date)
        stocks_data = loaded["stocks"]
        daily_data = loaded["daily"]

        ts_code = (self.config or {}).get("ts_code", "").strip()

        # 单股诊断模式：不应用板块过滤
        if ts_code:
            if ts_code in daily_data:
                daily_data = {ts_code: daily_data[ts_code]}
            else:
                return {"recommendations": [], "summary": self._empty_summary()}
            base_stock_count = 1
        else:
            # 应用板块过滤
            stocks_data, daily_data, base_stock_count = self._apply_board_filter(
                stocks_data, daily_data
            )

        strategy_input = {
            "cutoff_date": cutoff_date,
            **loaded,
            "stocks": stocks_data,
            "daily": daily_data,
            "config": self.config or {},
        }

        try:
            recommendations = self.strategy_func(strategy_input)
        except Exception as e:
            raise RuntimeError(f"策略执行失败: {e}")

        if not recommendations or not isinstance(recommendations, list):
            return {"recommendations": [], "summary": self._empty_summary()}

        # 截断前统计
        total_qualifying = len(recommendations)
        recommendations = recommendations[:MAX_RECOMMENDATIONS]
        recommendations = self._track_performance(recommendations, cutoff_date, track_days)
        summary = self._calculate_summary(recommendations, track_days)

        # 写入板块统计
        summary["total_qualifying"] = total_qualifying
        summary["base_stock_count"] = base_stock_count
        summary["pick_rate"] = round(
            total_qualifying / base_stock_count, 6
        ) if base_stock_count > 0 else 0.0

        return {"recommendations": recommendations, "summary": summary}

    def run_batch(
        self,
        start_date: str,
        end_date: str,
        track_days: List[int] = [3, 7, 15]
    ) -> List[Dict[str, Any]]:
        loaded = self._load_data_range(start_date, end_date)
        stocks_data = loaded["stocks"]
        daily_data = loaded["daily"]

        trading_days = sorted(set(
            row["trade_date"] for rows in daily_data.values() for row in rows
            if start_date <= row["trade_date"] <= end_date
        ))

        ts_code = (self.config or {}).get("ts_code", "").strip()
        results = []

        for cutoff_date in trading_days:
            cutoff_date_fmt = datetime.strptime(cutoff_date, "%Y%m%d").strftime("%Y-%m-%d")
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
                    base_stock_count = 1
                    filtered_stocks = stocks_data  # 单股模式不应用板块过滤
                else:
                    # 应用板块过滤（stocks_data 在循环外已全量加载）
                    filtered_stocks, sliced_daily, base_stock_count = self._apply_board_filter(
                        stocks_data, sliced_daily
                    )

                # 切片横截面数据到当日
                sliced_hot_stocks = [r for r in loaded["hot_stocks"] if r.get("trade_date") == cutoff_date_fmt]
                sliced_hot_themes = [r for r in loaded["hot_themes"] if r.get("trade_date") == cutoff_date_fmt]

                strategy_input = {
                    "cutoff_date": cutoff_date,
                    "stocks": filtered_stocks,
                    "daily": sliced_daily,
                    "daily_sector_flow": loaded["daily_sector_flow"],
                    "hot_stocks": sliced_hot_stocks,
                    "hot_themes": sliced_hot_themes,
                    "dragon_tiger": loaded["dragon_tiger"],
                    "dragon_tiger_seats": loaded["dragon_tiger_seats"],
                    "financials": loaded["financials"],
                    "config": self.config or {},
                }

                recommendations = self.strategy_func(strategy_input)
                if not recommendations or not isinstance(recommendations, list):
                    recommendations = []

                # 0 入选日跳过
                if len(recommendations) == 0:
                    continue

                # 截断前统计
                total_qualifying = len(recommendations)
                recommendations = recommendations[:MAX_RECOMMENDATIONS]
                recommendations = self._track_performance(recommendations, cutoff_date, track_days)
                summary = self._calculate_summary(recommendations, track_days)

                summary["total_qualifying"] = total_qualifying
                summary["base_stock_count"] = base_stock_count
                summary["pick_rate"] = round(
                    total_qualifying / base_stock_count, 6
                ) if base_stock_count > 0 else 0.0

                daily_result["status"] = "completed"
                daily_result["recommendations"] = recommendations
                daily_result["summary"] = summary
            except Exception as e:
                daily_result["status"] = "failed"
                daily_result["error_message"] = str(e)

            results.append(daily_result)

        return results

    def _load_data(self, cutoff_date: str) -> Dict[str, Any]:
        """从 PostgreSQL 加载历史数据（截止日及之前），返回完整 strategy_input 数据"""
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

            # 4. 板块资金流向（按需）
            daily_sector_flow_data = []
            if self._should_load("sector_flow"):
                sector_stmt = select(DailySectorFlow.__table__).where(
                    DailySectorFlow.trade_date.between(flow_start_date, cutoff_date_fmt)
                ).order_by(DailySectorFlow.trade_date, DailySectorFlow.sector_type, DailySectorFlow.sector_name)
                sector_result = session.execute(sector_stmt)
                daily_sector_flow_data = [dict(row._mapping) for row in sector_result]

            # 5. 热门股（按需）
            hot_stocks_data = []
            if self._should_load("hot_stocks"):
                hot_stock_stmt = select(DailyHotStock.__table__).where(
                    DailyHotStock.trade_date == cutoff_date_fmt
                ).order_by(DailyHotStock.sort_order)
                hot_stocks_data = [dict(row._mapping) for row in session.execute(hot_stock_stmt)]

            # 6. 热门题材（按需）
            hot_themes_data = []
            if self._should_load("hot_themes"):
                hot_theme_stmt = select(DailyHotTheme.__table__).where(
                    DailyHotTheme.trade_date == cutoff_date_fmt
                ).order_by(DailyHotTheme.stock_count.desc())
                hot_themes_data = [dict(row._mapping) for row in session.execute(hot_theme_stmt)]

            # 7. 龙虎榜（按需）
            dragon_tiger_data = []
            dragon_tiger_seats_data = []
            if self._should_load("dragon_tiger"):
                dt_stmt = select(DailyDragonTiger.__table__).where(
                    DailyDragonTiger.trade_date.between(flow_start_date, cutoff_date_fmt)
                ).order_by(DailyDragonTiger.trade_date.desc())
                dragon_tiger_data = [dict(row._mapping) for row in session.execute(dt_stmt)]

                dt_seat_stmt = select(DailyDragonTigerSeat.__table__).where(
                    DailyDragonTigerSeat.trade_date.between(flow_start_date, cutoff_date_fmt)
                ).order_by(DailyDragonTigerSeat.trade_date, DailyDragonTigerSeat.stock_code, DailyDragonTigerSeat.rank)
                dragon_tiger_seats_data = [dict(row._mapping) for row in session.execute(dt_seat_stmt)]

            # 8. 基本面数据（按需）
            financials_data = []
            if self._should_load("financials"):
                fin_stmt = select(
                    FinancialReport.ts_code, FinancialReport.report_date,
                    FinancialReport.report_type, FinancialReport.pub_date,
                    FinancialReport.eps, FinancialReport.bvps, FinancialReport.roe,
                    FinancialReport.gross_margin, FinancialReport.net_margin,
                    FinancialReport.net_profit, FinancialReport.net_profit_yoy,
                    FinancialReport.revenue, FinancialReport.revenue_yoy,
                    FinancialReport.debt_to_assets, FinancialReport.current_ratio,
                    FinancialReport.quick_ratio, FinancialReport.cf_operating,
                    FinancialReport.cf_ratio, FinancialReport.total_assets,
                    FinancialReport.total_liabilities, FinancialReport.shareholders_equity,
                ).where(
                    FinancialReport.pub_date <= cutoff_date_fmt,
                    FinancialReport.pub_date.isnot(None),
                ).order_by(FinancialReport.ts_code, FinancialReport.report_date.desc())
                financials_data = [dict(row._mapping) for row in session.execute(fin_stmt)]
        finally:
            session.close()

        # 按 ts_code 分组日线
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

        return {
            "stocks": stocks_data,
            "daily": daily_data,
            "daily_sector_flow": daily_sector_flow_data,
            "hot_stocks": hot_stocks_data,
            "hot_themes": hot_themes_data,
            "dragon_tiger": dragon_tiger_data,
            "dragon_tiger_seats": dragon_tiger_seats_data,
            "financials": financials_data,
        }

    def _load_data_range(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """加载全时段历史数据，返回完整 strategy_input 数据"""
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

            # 板块资金流向（按需）
            daily_sector_flow_data = []
            if self._should_load("sector_flow"):
                sector_stmt = select(DailySectorFlow.__table__).where(
                    DailySectorFlow.trade_date.between(flow_earliest_date, end_date_fmt)
                ).order_by(DailySectorFlow.trade_date, DailySectorFlow.sector_type, DailySectorFlow.sector_name)
                daily_sector_flow_data = [dict(row._mapping) for row in session.execute(sector_stmt)]

            # 热门股（按需）
            hot_stocks_data = []
            if self._should_load("hot_stocks"):
                hot_stock_stmt = select(DailyHotStock.__table__).where(
                    DailyHotStock.trade_date.between(flow_earliest_date, end_date_fmt)
                ).order_by(DailyHotStock.trade_date, DailyHotStock.sort_order)
                hot_stocks_data = [dict(row._mapping) for row in session.execute(hot_stock_stmt)]

            # 热门题材（按需）
            hot_themes_data = []
            if self._should_load("hot_themes"):
                hot_theme_stmt = select(DailyHotTheme.__table__).where(
                    DailyHotTheme.trade_date.between(flow_earliest_date, end_date_fmt)
                ).order_by(DailyHotTheme.trade_date, DailyHotTheme.stock_count.desc())
                hot_themes_data = [dict(row._mapping) for row in session.execute(hot_theme_stmt)]

            # 龙虎榜 + 席位（按需）
            dragon_tiger_data = []
            dragon_tiger_seats_data = []
            if self._should_load("dragon_tiger"):
                dt_stmt = select(DailyDragonTiger.__table__).where(
                    DailyDragonTiger.trade_date.between(flow_earliest_date, end_date_fmt)
                ).order_by(DailyDragonTiger.trade_date.desc())
                dragon_tiger_data = [dict(row._mapping) for row in session.execute(dt_stmt)]

                dt_seat_stmt = select(DailyDragonTigerSeat.__table__).where(
                    DailyDragonTigerSeat.trade_date.between(flow_earliest_date, end_date_fmt)
                ).order_by(DailyDragonTigerSeat.trade_date, DailyDragonTigerSeat.stock_code, DailyDragonTigerSeat.rank)
                dragon_tiger_seats_data = [dict(row._mapping) for row in session.execute(dt_seat_stmt)]

            # 基本面数据（按需，加载 end_date 之前发布的全部财报）
            financials_data = []
            if self._should_load("financials"):
                fin_stmt = select(
                    FinancialReport.ts_code, FinancialReport.report_date,
                    FinancialReport.report_type, FinancialReport.pub_date,
                    FinancialReport.eps, FinancialReport.bvps, FinancialReport.roe,
                    FinancialReport.gross_margin, FinancialReport.net_margin,
                    FinancialReport.net_profit, FinancialReport.net_profit_yoy,
                    FinancialReport.revenue, FinancialReport.revenue_yoy,
                    FinancialReport.debt_to_assets, FinancialReport.current_ratio,
                    FinancialReport.quick_ratio, FinancialReport.cf_operating,
                    FinancialReport.cf_ratio, FinancialReport.total_assets,
                    FinancialReport.total_liabilities, FinancialReport.shareholders_equity,
                ).where(
                    FinancialReport.pub_date <= end_date_fmt,
                    FinancialReport.pub_date.isnot(None),
                ).order_by(FinancialReport.ts_code, FinancialReport.report_date.desc())
                financials_data = [dict(row._mapping) for row in session.execute(fin_stmt)]
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

        return {
            "stocks": stocks_data,
            "daily": daily_data,
            "daily_sector_flow": daily_sector_flow_data,
            "hot_stocks": hot_stocks_data,
            "hot_themes": hot_themes_data,
            "dragon_tiger": dragon_tiger_data,
            "dragon_tiger_seats": dragon_tiger_seats_data,
            "financials": financials_data,
        }

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
            "total_qualifying": 0,
            "base_stock_count": 0,
            "pick_rate": 0.0,
            "avg_return_3d": 0.0, "win_rate_3d": 0.0,
            "best_return_3d": 0.0, "worst_return_3d": 0.0,
            "avg_return_7d": 0.0, "win_rate_7d": 0.0,
            "best_return_7d": 0.0, "worst_return_7d": 0.0,
            "avg_return_15d": 0.0, "win_rate_15d": 0.0,
            "best_return_15d": 0.0, "worst_return_15d": 0.0,
        }

    def run_live(self, cutoff_date: str, ts_code: str = None) -> List[Dict]:
        loaded = self._load_data(cutoff_date)
        daily_data = loaded["daily"]

        if ts_code:
            if ts_code in daily_data:
                daily_data = {ts_code: daily_data[ts_code]}
            else:
                return []

        strategy_input = {
            "cutoff_date": cutoff_date,
            **loaded,
            "daily": daily_data,
            "config": self.config or {},
        }

        try:
            recommendations = self.strategy_func(strategy_input)
        except Exception as e:
            raise RuntimeError(f"策略执行失败: {e}")

        if not recommendations or not isinstance(recommendations, list):
            return []

        return recommendations[:MAX_RECOMMENDATIONS]
