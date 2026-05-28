"""回测引擎核心（新逻辑：截止日推荐 + 后续表现追踪）"""

import ast
import sqlite3
import sys
import io
import os
import json
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timedelta


from ..config import settings
STOCK_DB_PATH = settings.STOCK_DB_PATH

# 推荐股票数量上限
MAX_RECOMMENDATIONS = 10


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
        """
        初始化回测引擎

        参数:
            strategy_code: 策略代码（Python 文件内容）
            strategy_params: 策略参数（预留，暂未使用）
            config: 策略自定义配置（如目标股票代码），会传入 strategy_input
        """
        self.strategy_code = strategy_code
        self.strategy_params = strategy_params
        self.config = config
        self.strategy_func = None
        
        # 加载策略
        self._load_strategy()
    
    def _load_strategy(self) -> None:
        """加载策略代码（安全检查 + 编译）"""
        # 1. AST 安全检查
        is_valid, error_msg = self._validate_strategy(self.strategy_code)
        if not is_valid:
            raise ValueError(f"策略代码验证失败: {error_msg}")
        
        # 2. 编译策略代码
        try:
            code_obj = compile(self.strategy_code, "<strategy>", "exec")
        except SyntaxError as e:
            raise ValueError(f"策略代码语法错误: {e}")
        
        # 3. 执行代码，获取 run 函数
        strategy_globals = {
            "__builtins__": self._get_restricted_builtins(),
        }
        
        # 添加 app 目录到 sys.path，使 factors 模块可以被导入
        # __file__ = .../backend/app/services/backtest_engine.py
        # app_dir = .../backend/app
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
        
        # 4. 查找 run 函数或 Strategy 类（兼容新旧两种格式）
        run_func = strategy_globals.get('run')
        strategy_class = strategy_globals.get('Strategy')
        
        if run_func and callable(run_func):
            # 新格式：run(data) 函数
            self.strategy_func = run_func
        elif strategy_class and callable(strategy_class):
            # 旧格式：Strategy 类 → 创建包装函数适配新接口
            pd = strategy_globals.get('pd')
            np = strategy_globals.get('np')
            if not pd or not np:
                raise ValueError("策略代码缺少 pandas 或 numpy 导入")
            
            strategy_instance = strategy_class()
            
            def make_run_wrapper(pd, np, instance):
                def run_wrapper(data):
                    """包装旧格式策略的 wrapper"""
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
        """获取受限的内置函数（安全沙箱）"""
        import builtins
        
        safe_builtins = {}
        safe_list = [
            '__import__',  # 允许 import 语句
            'abs', 'all', 'any', 'bin', 'bool', 'chr', 'complex',
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
        """验证策略代码安全性（禁止危险操作）"""
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
        """
        执行回测（核心方法）
        
        参数:
            cutoff_date: 截止日，格式 YYYYMMDD
            track_days: 追踪天数列表，默认 [3, 7, 15]
        
        返回:
            {
                "recommendations": [...],  # 推荐股票列表
                "summary": {...}            # 汇总指标
            }
        """
        # 1. 加载截止日及之前的历史数据
        stocks_data, daily_data, sector_flow_data = self._load_data(cutoff_date)

        # 如果 config 指定了 ts_code，裁剪到只含该股票
        ts_code = (self.config or {}).get("ts_code", "").strip()
        if ts_code:
            if ts_code in daily_data:
                daily_data = {ts_code: daily_data[ts_code]}
            else:
                return {
                    "recommendations": [],
                    "summary": self._empty_summary()
                }

        # 2. 构造策略输入数据
        strategy_input = {
            "cutoff_date": cutoff_date,
            "stocks": stocks_data,       # list[dict]，股票基础信息
            "daily": daily_data,          # dict[ts_code] -> list[dict]，日线数据
            "sector_flow": sector_flow_data,  # list[dict]，板块资金流向
            "config": self.config or {},  # 策略自定义配置
        }

        # 3. 运行策略，获取推荐股票
        try:
            recommendations = self.strategy_func(strategy_input)
        except Exception as e:
            raise RuntimeError(f"策略执行失败: {e}")

        if not recommendations or not isinstance(recommendations, list):
            return {
                "recommendations": [],
                "summary": self._empty_summary()
            }

        # 4. 限制推荐数量
        recommendations = recommendations[:MAX_RECOMMENDATIONS]
        
        # 5. 追踪推荐股票在截止日后的表现
        recommendations = self._track_performance(
            recommendations, cutoff_date, track_days
        )
        
        # 6. 汇总结果
        summary = self._calculate_summary(recommendations, track_days)
        
        return {
            "recommendations": recommendations,
            "summary": summary
        }

    def run_batch(
        self,
        start_date: str,
        end_date: str,
        track_days: List[int] = [3, 7, 15]
    ) -> List[Dict[str, Any]]:
        """
        执行批量回测

        参数:
            start_date: 起始日期，格式 YYYYMMDD
            end_date: 结束日期，格式 YYYYMMDD
            track_days: 追踪天数列表

        返回:
            list[dict]，每天一条结果
        """
        # 1. 加载全时段数据
        stocks_data, daily_data, sector_flow_data = self._load_data_range(start_date, end_date)

        # 2. 获取日期范围内的所有交易日
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
                # 裁剪 daily 到 cutoff_date 及之前
                sliced_daily = {}
                for code, rows in daily_data.items():
                    sliced_rows = [r for r in rows if r["trade_date"] <= cutoff_date]
                    if sliced_rows:
                        sliced_daily[code] = sliced_rows

                # 如果指定了 ts_code，只保留该股票
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
        """
        从 stock_db.sqlite 加载历史数据（截止日及之前）

        返回:
            (stocks_data, daily_data, sector_flow_data)
            - stocks_data: list[dict]，每只股票基础信息
            - daily_data: dict[ts_code] -> list[dict]，每个股票的日线数据（截止日前 120 天）
            - sector_flow_data: list[dict]，板块资金流向数据
        """
        conn = sqlite3.connect(STOCK_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # 1. 加载股票基础信息
        cur.execute("""
            SELECT ts_code, symbol, name, market,
                   industry_l1, industry_l2, industry_l3,
                   concepts, total_shares, float_shares
            FROM stocks
            WHERE ts_code IS NOT NULL AND ts_code != ''
        """)
        stocks_rows = cur.fetchall()
        stocks_data = [dict(row) for row in stocks_rows]
        
        # 2. 计算数据起始日（截止日前 120 个交易日，约 6 个月）
        cutoff_dt = datetime.strptime(cutoff_date, "%Y%m%d")
        start_dt = cutoff_dt - timedelta(days=180)  # 多取一些自然日，确保有 120 个交易日
        start_date = start_dt.strftime("%Y%m%d")
        flow_start_dt = cutoff_dt - timedelta(days=30)
        flow_start_date = flow_start_dt.strftime("%Y%m%d")

        # 3. 加载日线数据（截止日及之前）
        cur.execute(f"""
            SELECT ts_code, trade_date, open, high, low, close,
                   vol, amount, adj_close, market_cap, circ_market_cap
            FROM daily
            WHERE trade_date BETWEEN '{start_date}' AND '{cutoff_date}'
            ORDER BY ts_code, trade_date
        """)
        daily_rows = cur.fetchall()

        # 3b. 加载板块资金流向数据
        cur.execute(f"""
            SELECT trade_date, sector_code, sector_name, sector_type,
                   change_pct, main_inflow, main_inflow_pct,
                   retail_inflow, retail_inflow_pct,
                   net_inflow, big_order_inflow, big_order_inflow_pct,
                   mid_order_inflow, mid_order_inflow_pct
            FROM sector_flow
            WHERE trade_date BETWEEN '{flow_start_date}' AND '{cutoff_date}'
            ORDER BY trade_date, sector_type, sector_name
        """)
        sector_flow_rows = cur.fetchall()
        sector_flow_data = [dict(row) for row in sector_flow_rows]

        conn.close()

        # 4. 按 ts_code 分组
        daily_data = {}
        for row in daily_rows:
            ts_code = row['ts_code']
            if ts_code not in daily_data:
                daily_data[ts_code] = []
            daily_data[ts_code].append({
                "trade_date": row['trade_date'],
                "open": row['open'],
                "high": row['high'],
                "low": row['low'],
                "close": row['close'],
                "vol": row['vol'],
                "amount": row['amount'],
                "adj_close": row['adj_close'],
                "market_cap": row['market_cap'],
                "circ_market_cap": row['circ_market_cap'],
            })
        
        return stocks_data, daily_data, sector_flow_data

    def _load_data_range(self, start_date: str, end_date: str) -> Tuple[List[Dict], Dict[str, List[Dict]], List[Dict]]:
        """
        加载全时段历史数据（用于批量回测）

        加载 start_date - 180 天到 end_date 的完整数据，后续按天切片。
        """
        conn = sqlite3.connect(STOCK_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1. 加载股票基础信息
        cur.execute("""
            SELECT ts_code, symbol, name, market,
                   industry_l1, industry_l2, industry_l3,
                   concepts, total_shares, float_shares
            FROM stocks
            WHERE ts_code IS NOT NULL AND ts_code != ''
        """)
        stocks_data = [dict(row) for row in cur.fetchall()]

        # 2. 计算数据起始日
        start_dt = datetime.strptime(start_date, "%Y%m%d")
        earliest_dt = start_dt - timedelta(days=180)
        earliest_date = earliest_dt.strftime("%Y%m%d")

        flow_start_dt = datetime.strptime(start_date, "%Y%m%d")
        flow_earliest_dt = flow_start_dt - timedelta(days=30)
        flow_earliest_date = flow_earliest_dt.strftime("%Y%m%d")

        # 3. 加载日线数据（从 earliest 到 end_date）
        cur.execute(f"""
            SELECT ts_code, trade_date, open, high, low, close,
                   vol, amount, adj_close, market_cap, circ_market_cap
            FROM daily
            WHERE trade_date BETWEEN '{earliest_date}' AND '{end_date}'
            ORDER BY ts_code, trade_date
        """)
        daily_rows = cur.fetchall()

        # 4. 加载板块资金流向
        cur.execute(f"""
            SELECT trade_date, sector_code, sector_name, sector_type,
                   change_pct, main_inflow, main_inflow_pct,
                   retail_inflow, retail_inflow_pct,
                   net_inflow, big_order_inflow, big_order_inflow_pct,
                   mid_order_inflow, mid_order_inflow_pct
            FROM sector_flow
            WHERE trade_date BETWEEN '{flow_earliest_date}' AND '{end_date}'
            ORDER BY trade_date, sector_type, sector_name
        """)
        sector_flow_data = [dict(row) for row in cur.fetchall()]

        conn.close()

        # 5. 按 ts_code 分组
        daily_data = {}
        for row in daily_rows:
            ts_code = row['ts_code']
            if ts_code not in daily_data:
                daily_data[ts_code] = []
            daily_data[ts_code].append({
                "trade_date": row['trade_date'],
                "open": row['open'],
                "high": row['high'],
                "low": row['low'],
                "close": row['close'],
                "vol": row['vol'],
                "amount": row['amount'],
                "adj_close": row['adj_close'],
                "market_cap": row['market_cap'],
                "circ_market_cap": row['circ_market_cap'],
            })

        return stocks_data, daily_data, sector_flow_data

    def _track_performance(
        self,
        recommendations: List[Dict],
        cutoff_date: str,
        track_days: List[int]
    ) -> List[Dict]:
        """
        追踪推荐股票在截止日后的表现

        参数:
            recommendations: 推荐股票列表（run 函数返回）
            cutoff_date: 截止日
            track_days: 追踪天数列表

        返回:
            补充了 return_Xd 字段的推荐股票列表
        """
        conn = sqlite3.connect(STOCK_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cutoff_dt = datetime.strptime(cutoff_date, "%Y%m%d")

        # 获取截止日收盘价（用 adj_close，优先；没有则用 close）
        cur.execute(f"""
            SELECT ts_code, adj_close, close
            FROM daily
            WHERE ts_code IN ({','.join(['?']*len(recommendations))})
              AND trade_date = ?
        """, [r['ts_code'] for r in recommendations] + [cutoff_date])

        cutoff_prices = {}
        for row in cur.fetchall():
            price = row['adj_close'] if row['adj_close'] else row['close']
            cutoff_prices[row['ts_code']] = price

        # 获取截止日前一个交易日的收盘价（计算当日涨跌）
        cur.execute(f"""
            SELECT d.ts_code, d.adj_close, d.close
            FROM daily d
            INNER JOIN (
                SELECT ts_code, MAX(trade_date) AS max_date
                FROM daily
                WHERE ts_code IN ({','.join(['?']*len(recommendations))})
                  AND trade_date < ?
                GROUP BY ts_code
            ) latest ON d.ts_code = latest.ts_code AND d.trade_date = latest.max_date
        """, [r['ts_code'] for r in recommendations] + [cutoff_date])

        prev_day_prices = {}
        for row in cur.fetchall():
            price = row['adj_close'] if row['adj_close'] else row['close']
            prev_day_prices[row['ts_code']] = price

        # 计算当日涨跌
        for rec in recommendations:
            ts_code = rec['ts_code']
            cutoff_price = cutoff_prices.get(ts_code)
            prev_price = prev_day_prices.get(ts_code)
            if cutoff_price and prev_price:
                rec['return_0d'] = round((cutoff_price - prev_price) / prev_price, 6)
            else:
                rec['return_0d'] = None

        # 对每个追踪天数，获取对应交易日的收盘价
        for rec in recommendations:
            ts_code = rec['ts_code']
            cutoff_price = cutoff_prices.get(ts_code)

            if not cutoff_price:
                # 没有截止日价格，跳过
                for d in track_days:
                    rec[f'return_{d}d'] = None
                continue

            # 获取该股票截止日后的所有交易日数据
            cur.execute(f"""
                SELECT trade_date, adj_close, close
                FROM daily
                WHERE ts_code = ?
                  AND trade_date > ?
                ORDER BY trade_date
                LIMIT 30  -- 最多取 30 个交易日（约 1.5 个月）
            """, (ts_code, cutoff_date))

            future_prices = {}
            for row in cur.fetchall():
                trade_date = row['trade_date']
                price = row['adj_close'] if row['adj_close'] else row['close']
                future_prices[trade_date] = price

            # 计算每只追踪天数的涨跌幅
            future_dates = sorted(future_prices.keys())

            for d in track_days:
                # 找到第 d 个交易日（如果有足够数据）
                if len(future_dates) >= d:
                    target_date = future_dates[d - 1]
                    target_price = future_prices[target_date]
                    return_pct = (target_price - cutoff_price) / cutoff_price
                    rec[f'return_{d}d'] = round(return_pct, 6)
                else:
                    rec[f'return_{d}d'] = None

        conn.close()

        return recommendations
    
    def _calculate_summary(
        self,
        recommendations: List[Dict],
        track_days: List[int]
    ) -> Dict[str, Any]:
        """
        计算汇总指标
        """
        if not recommendations:
            return self._empty_summary()

        summary = {
            "total_recommendations": len(recommendations),
        }

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
        """返回空的汇总指标"""
        return {
            "total_recommendations": 0,
            "avg_return_3d": 0.0,
            "win_rate_3d": 0.0,
            "best_return_3d": 0.0,
            "worst_return_3d": 0.0,
            "avg_return_7d": 0.0,
            "win_rate_7d": 0.0,
            "best_return_7d": 0.0,
            "worst_return_7d": 0.0,
            "avg_return_15d": 0.0,
            "win_rate_15d": 0.0,
            "best_return_15d": 0.0,
            "worst_return_15d": 0.0,
        }
    
    def run_live(self, cutoff_date: str, ts_code: str = None) -> List[Dict]:
        """
        执行策略（同步，用于"执行策略"功能）

        参数:
            cutoff_date: 截止日，格式 YYYYMMDD（通常为今日）
            ts_code: 可选，目标股票代码。传入时只分析该股票，大幅提升速度。

        返回:
            推荐股票列表（不含后续表现追踪）
        """
        # 1. 加载数据
        stocks_data, daily_data, sector_flow_data = self._load_data(cutoff_date)

        # 如果指定了 ts_code，裁剪到只含该股票
        if ts_code:
            if ts_code in daily_data:
                daily_data = {ts_code: daily_data[ts_code]}
            else:
                return []

        # 2. 运行策略
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
