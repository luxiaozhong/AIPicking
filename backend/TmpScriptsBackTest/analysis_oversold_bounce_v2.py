"""
超跌反弹策略 历史信号表现分析 v2
==============================================
直接使用后端 BacktestEngine 的数据加载 + 实际策略代码，确保结果与回测一致。
输出全部符合条件的股票（不限制 Top-N）。

用法: cd backend && source venv/bin/activate && python ../analysis_oversold_bounce_v2.py
"""

import sys
import os
import importlib.util
from datetime import datetime, timedelta
from collections import defaultdict

# 确保 backend 在 path 中
backend_dir = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, backend_dir)

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.models.stock_tables import Stock, Daily

# ── 同步引擎（与 BacktestEngine 完全一致）──
_sync_engine = create_engine(settings.SYNC_DATABASE_URL)
SyncSession = sessionmaker(bind=_sync_engine)

# ── 配置 ──
TARGET_DATES = [
    ("20260202", "2026-02-02"),
    ("20260205", "2026-02-05"),
    ("20260206", "2026-02-06"),
    ("20260305", "2026-03-05"),
    ("20260306", "2026-03-06"),
    ("20260309", "2026-03-09"),
    ("20260323", "2026-03-23"),
    ("20260331", "2026-03-31"),
    ("20260402", "2026-04-02"),
    ("20260403", "2026-04-03"),
    ("20260407", "2026-04-07"),
]

INDICES = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000688.SH": "科创50",
}


def load_data_like_backtest(cutoff_date_str):
    """完全模拟 BacktestEngine._load_data() 的数据加载"""
    session = SyncSession()
    try:
        cutoff_dt = datetime.strptime(cutoff_date_str, "%Y%m%d")
        start_date = (cutoff_dt - timedelta(days=180)).strftime("%Y%m%d")

        # 1. 股票基础信息（与 _load_data 完全一致）
        stmt = select(
            Stock.ts_code, Stock.symbol, Stock.name, Stock.market,
            Stock.industry_l1, Stock.industry_l2, Stock.industry_l3,
            Stock.concepts, Stock.total_shares, Stock.float_shares
        ).where(Stock.ts_code.isnot(None), Stock.ts_code != "")
        stocks_result = session.execute(stmt)
        stocks_data = [dict(row._mapping) for row in stocks_result]

        # 2. 日线数据（与 _load_data 完全一致）
        daily_stmt = select(
            Daily.ts_code, Daily.trade_date, Daily.open, Daily.high,
            Daily.low, Daily.close, Daily.vol, Daily.amount,
            Daily.adj_close, Daily.market_cap, Daily.circ_market_cap
        ).where(
            Daily.trade_date.between(start_date, cutoff_date_str)
        ).order_by(Daily.ts_code, Daily.trade_date)
        daily_result = session.execute(daily_stmt)
        daily_rows = [dict(row._mapping) for row in daily_result]

        # 按 ts_code 分组
        daily_data = defaultdict(list)
        for row in daily_rows:
            daily_data[row["ts_code"]].append(row)

        return {"stocks": stocks_data, "daily": dict(daily_data)}
    finally:
        session.close()


def load_strategy_module():
    """直接 import 策略模块"""
    strategy_path = os.path.join(backend_dir, "app", "strategies", "examples", "oversold_bounce.py")
    spec = importlib.util.spec_from_file_location("oversold_bounce_strategy", strategy_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_forward_prices(session, ts_codes, signal_date_str, calendar_days_list):
    """获取前向价格"""
    signal_dt = datetime.strptime(signal_date_str, "%Y%m%d")
    max_days = max(calendar_days_list)
    end_dt = signal_dt + timedelta(days=max_days + 10)

    result = {code: {} for code in ts_codes}

    for code in ts_codes:
        daily_stmt = select(
            Daily.ts_code, Daily.trade_date, Daily.open, Daily.high,
            Daily.low, Daily.close, Daily.vol, Daily.amount
        ).where(
            Daily.ts_code == code,
            Daily.trade_date > signal_date_str,
            Daily.trade_date <= end_dt.strftime("%Y%m%d")
        ).order_by(Daily.trade_date)
        rows = session.execute(daily_stmt).fetchall()

        for days in calendar_days_list:
            target_dt = signal_dt + timedelta(days=days)
            target_str = target_dt.strftime("%Y%m%d")
            found = None
            for row in rows:
                if row.trade_date >= target_str:
                    found = row
                    break
            if found:
                result[code][days] = {
                    "date": found.trade_date,
                    "close": float(found.close) if found.close else None,
                    "open": float(found.open) if found.open else None,
                }
            else:
                result[code][days] = None

    return result


def main():
    print("=" * 80)
    print("超跌反弹策略 历史信号表现分析 v2（使用实际策略代码）")
    print("=" * 80)

    # 加载策略模块
    strategy = load_strategy_module()
    print(f"策略模块已加载: {strategy.__file__}")

    session = SyncSession()

    # ── 统计总股票池 ──
    total_stmt = select(Stock.ts_code).where(
        (Stock.ts_code.like("300%")) | (Stock.ts_code.like("301%"))
        | (Stock.ts_code.like("688%")) | (Stock.ts_code.like("689%"))
    )
    total_stocks = len(session.execute(total_stmt).fetchall())
    print(f"创业板+科创板总股票数: {total_stocks}")

    # ── 对每个日期运行策略 ──
    all_results = {}
    all_index_data = {}

    for cutoff_date, cutoff_date_fmt in TARGET_DATES:
        print(f"\n{'─' * 60}")
        print(f"处理日期: {cutoff_date_fmt} ({cutoff_date})")
        print(f"{'─' * 60}")

        # 加载数据
        data = load_data_like_backtest(cutoff_date)
        daily_count = len(data["daily"])
        stock_count = len(data["stocks"])
        print(f"  加载: {stock_count} 只股票, {daily_count} 只有日线数据")

        # ── 调用实际策略 run() ──
        # 先正常调用看返回 top-N 数量
        strategy_input = {
            "cutoff_date": cutoff_date,
            "stocks": data["stocks"],
            "daily": data["daily"],
            "config": {},  # 使用默认参数
        }

        # 获取所有结果：临时修改 TOP_PICKS
        original_top = strategy.TOP_PICKS
        strategy.TOP_PICKS = 99999  # 不限制数量
        try:
            recommendations = strategy.run(strategy_input)
        finally:
            strategy.TOP_PICKS = original_top

        print(f"  策略选出: {len(recommendations)} 只股票")

        if recommendations:
            print(f"  Top 5:")
            for r in recommendations[:5]:
                print(f"    {r['ts_code']} {r['name']:8s} score={r['score']:3d} | {r['signal'][:80]}")

        # 补充 close 和 market_cap 信息到结果中
        for r in recommendations:
            rows = data["daily"].get(r["ts_code"], [])
            if rows:
                r["_close"] = rows[-1].get("close")
                r["_market_cap"] = rows[-1].get("market_cap")
            else:
                r["_close"] = None
                r["_market_cap"] = None

        all_results[cutoff_date] = recommendations

        # ── 获取四大指数当时价格 ──
        index_info = {}
        for idx_code, idx_name in INDICES.items():
            idx_rows = data["daily"].get(idx_code, [])
            if idx_rows:
                idx_info = {
                    "name": idx_name,
                    "signal_date": cutoff_date,
                    "signal_close": idx_rows[-1].get("close"),
                }
            else:
                idx_info = {
                    "name": idx_name,
                    "signal_date": cutoff_date,
                    "signal_close": None,
                }
            index_info[idx_code] = idx_info
        all_index_data[cutoff_date] = index_info

    # ── 收集所有选中股票 ──
    all_picked_codes = set()
    for cutoff_date, recs in all_results.items():
        for r in recs:
            all_picked_codes.add((cutoff_date, r["ts_code"]))

    # ── 获取前向价格 ──
    print(f"\n{'=' * 80}")
    print("获取前向价格...")
    print(f"{'=' * 80}")

    forward_prices = {}
    for cutoff_date, _ in TARGET_DATES:
        codes_for_date = [r["ts_code"] for r in all_results.get(cutoff_date, [])]
        if codes_for_date:
            fp = get_forward_prices(session, codes_for_date, cutoff_date, [0, 7, 15])
            for code, days_data in fp.items():
                forward_prices[(cutoff_date, code)] = days_data

    # ── 获取指数前向价格 ──
    index_forward = {}
    for cutoff_date, _ in TARGET_DATES:
        for idx_code in INDICES:
            fp = get_forward_prices(session, [idx_code], cutoff_date, [0, 7, 15])
            index_forward[(cutoff_date, idx_code)] = fp.get(idx_code, {})

    # ── 计算表现 ──
    print("计算表现...")
    stock_performances = []

    for cutoff_date, recs in all_results.items():
        for r in recs:
            code = r["ts_code"]
            fp = forward_prices.get((cutoff_date, code), {})
            signal_close = r.get("_close")

            perf = {
                "signal_date": cutoff_date,
                "ts_code": code,
                "name": r["name"],
                "score": r["score"],
                "signal_close": signal_close,
                "turnover": r.get("details", {}).get("turnover_rate"),
                "drawdown_pct": r.get("details", {}).get("drawdown_pct"),
                "details": r.get("details", {}),
                "signal": r.get("signal", ""),
            }

            for days, label in [(0, "ret_0d"), (7, "ret_7d"), (15, "ret_15d")]:
                fd = fp.get(days)
                if fd and fd["close"] and signal_close and signal_close > 0:
                    ret = (fd["close"] - signal_close) / signal_close * 100
                    perf[label] = round(ret, 2)
                    perf[f"{label}_date"] = fd["date"]
                else:
                    perf[label] = None
                    perf[f"{label}_date"] = None

            stock_performances.append(perf)

    # ── 计算指数表现 ──
    index_performances = {}
    for cutoff_date, _ in TARGET_DATES:
        info = all_index_data.get(cutoff_date, {})
        for idx_code, idx_info in info.items():
            signal_close = idx_info["signal_close"]
            ifp = index_forward.get((cutoff_date, idx_code), {})
            perf = {"name": idx_info["name"], "signal_date": cutoff_date, "signal_close": signal_close}
            for days, label in [(0, "ret_0d"), (7, "ret_7d"), (15, "ret_15d")]:
                fd = ifp.get(days)
                if fd and fd["close"] and signal_close and signal_close > 0:
                    perf[label] = round((fd["close"] - signal_close) / signal_close * 100, 2)
                    perf[f"{label}_date"] = fd["date"]
                else:
                    perf[label] = None
                    perf[f"{label}_date"] = None
            index_performances[(cutoff_date, idx_code)] = perf

    session.close()

    # ═══════════════════════════════════════════════
    # 生成 HTML 报表
    # ═══════════════════════════════════════════════

    month_groups = [
        ("2026年2月", ["20260202", "20260205", "20260206"]),
        ("2026年3月", ["20260305", "20260306", "20260309", "20260323", "20260331"]),
        ("2026年4月", ["20260402", "20260403", "20260407"]),
    ]

    def fmt(v):
        return f"{v:+.2f}%" if v is not None else "-"

    def color(v):
        """根据正负返回颜色"""
        if v is None:
            return "#999"
        return "#e74c3c" if v >= 0 else "#27ae60"  # 红涨绿跌（A股习惯）

    def safe_avg(perfs, key):
        vals = [p[key] for p in perfs if p.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    CSS = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f8f9fa; color: #333; }
        h1 { color: #1a1a2e; border-bottom: 3px solid #e74c3c; padding-bottom: 10px; }
        h2 { color: #1a1a2e; border-bottom: 2px solid #ddd; padding-bottom: 8px; margin-top: 40px; }
        h3 { color: #2c3e50; margin-top: 30px; }
        h4 { color: #34495e; margin-top: 25px; padding: 8px 12px; background: #ecf0f1; border-radius: 4px; }
        .meta { background: #fff; padding: 15px; border-radius: 8px; margin-bottom: 30px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .meta p { margin: 4px 0; color: #666; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 6px; overflow: hidden; }
        th { background: #1a1a2e; color: #fff; padding: 10px 12px; text-align: center; font-weight: 600; font-size: 13px; }
        td { padding: 8px 12px; text-align: center; border-bottom: 1px solid #eee; font-size: 13px; }
        tr:hover { background: #f0f4ff; }
        .pos { color: #e74c3c; font-weight: 600; }
        .neg { color: #27ae60; font-weight: 600; }
        .summary-box { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
        .stat-card { background: #fff; padding: 15px 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }
        .stat-card .label { font-size: 12px; color: #999; text-transform: uppercase; }
        .stat-card .value { font-size: 24px; font-weight: 700; color: #1a1a2e; margin: 5px 0; }
        .stat-card .sub { font-size: 12px; color: #666; }
        tr.total-row { font-weight: 700; background: #fff3cd !important; }
        .pct-bar { display: inline-block; height: 6px; border-radius: 3px; vertical-align: middle; margin-left: 6px; }
    </style>
    """

    total_picked = len(stock_performances)
    all_7d = [p["ret_7d"] for p in stock_performances if p["ret_7d"] is not None]
    all_15d = [p["ret_15d"] for p in stock_performances if p["ret_15d"] is not None]

    html = []
    html.append("<!DOCTYPE html><html><head><meta charset='utf-8'>")
    html.append("<title>超跌反弹策略 历史信号表现分析报告</title>")
    html.append(CSS)
    html.append("</head><body>")

    # ── 标题与元信息 ──
    html.append("<h1>📊 超跌反弹策略 历史信号表现分析报告</h1>")
    html.append("<div class='meta'>")
    html.append(f"<p><strong>生成时间：</strong>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>")
    html.append("<p><strong>数据来源：</strong>实际策略代码（oversold_bounce.py），完全匹配后端回测结果</p>")
    html.append(f"<p><strong>股票池：</strong>创业板(300/301) + 科创板(688/689)，共 {total_stocks} 只</p>")
    html.append(f"<p><strong>分析日期：</strong>{len(TARGET_DATES)} 个交易日（2026年2月~4月）</p>")
    html.append("</div>")

    # ── 关键指标卡片 ──
    html.append("<h2>📈 关键指标</h2>")
    html.append("<div class='summary-box'>")
    html.append(f"<div class='stat-card'><div class='label'>总信号数</div><div class='value'>{total_picked}</div><div class='sub'>{len(TARGET_DATES)} 个交易日</div></div>")
    html.append(f"<div class='stat-card'><div class='label'>日均信号</div><div class='value'>{total_picked/len(TARGET_DATES):.1f}</div><div class='sub'>条/天</div></div>")
    avg7_val = sum(all_7d) / len(all_7d) if all_7d else 0
    up7 = sum(1 for v in all_7d if v > 0) if all_7d else 0
    html.append(f"<div class='stat-card'><div class='label'>7日平均收益</div><div class='value' style='color:{color(avg7_val)}'>{avg7_val:+.2f}%</div><div class='sub'>上涨率 {up7}/{len(all_7d)} ({up7/len(all_7d)*100:.0f}%)</div></div>")
    avg15_val = sum(all_15d) / len(all_15d) if all_15d else 0
    up15 = sum(1 for v in all_15d if v > 0) if all_15d else 0
    html.append(f"<div class='stat-card'><div class='label'>15日平均收益</div><div class='value' style='color:{color(avg15_val)}'>{avg15_val:+.2f}%</div><div class='sub'>上涨率 {up15}/{len(all_15d)} ({up15/len(all_15d)*100:.0f}%)</div></div>")
    html.append(f"<div class='stat-card'><div class='label'>7日最大盈利</div><div class='value' style='color:#e74c3c'>{max(all_7d):+.2f}%</div><div class='sub'>最大亏损 {min(all_7d):+.2f}%</div></div>" if all_7d else "")
    html.append(f"<div class='stat-card'><div class='label'>15日最大盈利</div><div class='value' style='color:#e74c3c'>{max(all_15d):+.2f}%</div><div class='sub'>最大亏损 {min(all_15d):+.2f}%</div></div>" if all_15d else "")
    html.append("</div>")

    # ── 一、汇总表（含占比列）──
    html.append("<h2>一、每日汇总</h2>")
    html.append("<table><thead><tr>")
    for h in ["月份", "信号日", "选出股票数", "占比", "平均当日涨跌", "平均7日涨跌", "平均15日涨跌", "上涨占比(7日)", "上涨占比(15日)"]:
        html.append(f"<th>{h}</th>")
    html.append("</tr></thead><tbody>")

    for month_label, dates in month_groups:
        for d in dates:
            date_perfs = [p for p in stock_performances if p["signal_date"] == d]
            n = len(date_perfs)
            pct = f"{n / total_stocks * 100:.2f}%" if total_stocks > 0 else "-"

            if n == 0:
                html.append(f"<tr><td>{month_label}</td><td>{d[:4]}-{d[4:6]}-{d[6:8]}</td><td>0</td><td>0%</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>")
                continue

            avg_0d = safe_avg(date_perfs, "ret_0d")
            avg_7d = safe_avg(date_perfs, "ret_7d")
            avg_15d = safe_avg(date_perfs, "ret_15d")
            up_7d_cnt = sum(1 for p in date_perfs if p.get("ret_7d") is not None and p["ret_7d"] > 0)
            up_15d_cnt = sum(1 for p in date_perfs if p.get("ret_15d") is not None and p["ret_15d"] > 0)
            cnt_7d = sum(1 for p in date_perfs if p.get("ret_7d") is not None)
            cnt_15d = sum(1 for p in date_perfs if p.get("ret_15d") is not None)

            html.append("<tr>")
            html.append(f"<td>{month_label}</td>")
            html.append(f"<td>{d[:4]}-{d[4:6]}-{d[6:8]}</td>")
            html.append(f"<td><strong>{n}</strong></td>")
            html.append(f"<td>{pct}</td>")
            html.append(f"<td class='{'pos' if (avg_0d or 0) >= 0 else 'neg'}'>{fmt(avg_0d)}</td>")
            html.append(f"<td class='{'pos' if (avg_7d or 0) >= 0 else 'neg'}'>{fmt(avg_7d)}</td>")
            html.append(f"<td class='{'pos' if (avg_15d or 0) >= 0 else 'neg'}'>{fmt(avg_15d)}</td>")
            up7_str = f"{up_7d_cnt}/{cnt_7d} ({up_7d_cnt/cnt_7d*100:.0f}%)" if cnt_7d > 0 else "-"
            up15_str = f"{up_15d_cnt}/{cnt_15d} ({up_15d_cnt/cnt_15d*100:.0f}%)" if cnt_15d > 0 else "-"
            html.append(f"<td>{up7_str}</td>")
            html.append(f"<td>{up15_str}</td>")
            html.append("</tr>")

    # 总计行
    if total_picked > 0:
        avg_0d_all = safe_avg(stock_performances, "ret_0d")
        avg_7d_all = safe_avg(stock_performances, "ret_7d")
        avg_15d_all = safe_avg(stock_performances, "ret_15d")
        cnt_7d_all = sum(1 for p in stock_performances if p.get("ret_7d") is not None)
        cnt_15d_all = sum(1 for p in stock_performances if p.get("ret_15d") is not None)
        up7_all = sum(1 for p in stock_performances if p.get("ret_7d") is not None and p["ret_7d"] > 0)
        up15_all = sum(1 for p in stock_performances if p.get("ret_15d") is not None and p["ret_15d"] > 0)

        html.append("<tr class='total-row'>")
        html.append(f"<td><strong>合计</strong></td>")
        html.append(f"<td><strong>{len(TARGET_DATES)}天</strong></td>")
        html.append(f"<td><strong>{total_picked}</strong></td>")
        html.append(f"<td><strong>{total_picked/total_stocks*100:.2f}%</strong></td>")
        html.append(f"<td class='{'pos' if (avg_0d_all or 0) >= 0 else 'neg'}'><strong>{fmt(avg_0d_all)}</strong></td>")
        html.append(f"<td class='{'pos' if (avg_7d_all or 0) >= 0 else 'neg'}'><strong>{fmt(avg_7d_all)}</strong></td>")
        html.append(f"<td class='{'pos' if (avg_15d_all or 0) >= 0 else 'neg'}'><strong>{fmt(avg_15d_all)}</strong></td>")
        html.append(f"<td><strong>{up7_all}/{cnt_7d_all} ({up7_all/cnt_7d_all*100:.0f}%)</strong></td>")
        html.append(f"<td><strong>{up15_all}/{cnt_15d_all} ({up15_all/cnt_15d_all*100:.0f}%)</strong></td>")
        html.append("</tr>")
    html.append("</tbody></table>")

    # ── 二、四大指数同期表现 ──
    html.append("<h2>二、四大指数同期表现</h2>")
    html.append("<table><thead><tr>")
    for h in ["信号日", "指数", "当日收盘", "当日涨跌", "7日涨跌", "15日涨跌"]:
        html.append(f"<th>{h}</th>")
    html.append("</tr></thead><tbody>")

    for cutoff_date, _ in TARGET_DATES:
        for idx_code in ["000001.SH", "399001.SZ", "399006.SZ", "000688.SH"]:
            perf = index_performances.get((cutoff_date, idx_code), {})
            name = perf.get("name", idx_code)
            sig_close = perf.get("signal_close")
            close_str = f"{sig_close:.2f}" if isinstance(sig_close, (int, float)) else "-"
            ret_0d = perf.get("ret_0d")
            ret_7d = perf.get("ret_7d")
            ret_15d = perf.get("ret_15d")

            html.append("<tr>")
            html.append(f"<td>{cutoff_date[:4]}-{cutoff_date[4:6]}-{cutoff_date[6:8] if idx_code == '000001.SH' else ''}</td>")
            html.append(f"<td>{name}</td>")
            html.append(f"<td>{close_str}</td>")
            html.append(f"<td class='{'pos' if (ret_0d or 0) >= 0 else 'neg'}'>{fmt(ret_0d)}</td>")
            html.append(f"<td class='{'pos' if (ret_7d or 0) >= 0 else 'neg'}'>{fmt(ret_7d)}</td>")
            html.append(f"<td class='{'pos' if (ret_15d or 0) >= 0 else 'neg'}'>{fmt(ret_15d)}</td>")
            html.append("</tr>")
        # 空行分隔
        html.append("<tr style='height:8px;background:#f8f9fa;'><td colspan='6'></td></tr>")
    html.append("</tbody></table>")

    # ── 三、每日详细选股列表 ──
    html.append("<h2>三、每日选股详细列表</h2>")

    for month_label, dates in month_groups:
        html.append(f"<h3>{month_label}</h3>")
        for d in dates:
            date_perfs = [p for p in stock_performances if p["signal_date"] == d]
            date_str = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            n = len(date_perfs)
            pct = f"{n / total_stocks * 100:.2f}%"
            html.append(f"<h4>{date_str} — {n} 只股票（占比 {pct}）</h4>")

            if n == 0:
                html.append("<p><em>无选出股票</em></p>")
                continue

            html.append("<table><thead><tr>")
            for h in ["#", "代码", "名称", "评分", "回撤%", "换手%", "买入价", "当日涨跌", "7日涨跌", "15日涨跌"]:
                html.append(f"<th>{h}</th>")
            html.append("</tr></thead><tbody>")

            for i, p in enumerate(date_perfs, 1):
                ret_0d = p.get("ret_0d")
                ret_7d = p.get("ret_7d")
                ret_15d = p.get("ret_15d")
                close_val = p.get("signal_close")
                turnover_val = p.get("turnover")
                dd_val = p.get("drawdown_pct")

                html.append("<tr>")
                html.append(f"<td>{i}</td>")
                html.append(f"<td>{p['ts_code']}</td>")
                html.append(f"<td>{p['name']}</td>")
                html.append(f"<td>{p['score']}</td>")
                html.append(f"<td>{dd_val:.1f}%</td>" if dd_val is not None else "<td>-</td>")
                html.append(f"<td>{turnover_val:.1f}%</td>" if turnover_val is not None else "<td>-</td>")
                html.append(f"<td>{close_val:.2f}</td>" if close_val else "<td>-</td>")
                html.append(f"<td class='{'pos' if (ret_0d or 0) >= 0 else 'neg'}'>{fmt(ret_0d)}</td>")
                html.append(f"<td class='{'pos' if (ret_7d or 0) >= 0 else 'neg'}'>{fmt(ret_7d)}</td>")
                html.append(f"<td class='{'pos' if (ret_15d or 0) >= 0 else 'neg'}'>{fmt(ret_15d)}</td>")
                html.append("</tr>")
            html.append("</tbody></table>")

    # ── 四、策略 vs 指数对比 ──
    html.append("<h2>四、策略选股 vs 指数 表现对比</h2>")
    html.append("<table><thead><tr>")
    for h in ["信号日", "选股数", "占比", "策略均7日", "策略均15日", "上证7日", "上证15日", "创业7日", "创业15日", "科创7日", "科创15日"]:
        html.append(f"<th>{h}</th>")
    html.append("</tr></thead><tbody>")

    for cutoff_date, _ in TARGET_DATES:
        date_perfs = [p for p in stock_performances if p["signal_date"] == cutoff_date]
        n = len(date_perfs)
        pct = f"{n / total_stocks * 100:.2f}%"

        strat_7d = safe_avg(date_perfs, "ret_7d")
        strat_15d = safe_avg(date_perfs, "ret_15d")

        def idx_ret(idx_code, days_label):
            p = index_performances.get((cutoff_date, idx_code), {})
            return p.get(days_label)

        date_str = f"{cutoff_date[:4]}-{cutoff_date[4:6]}-{cutoff_date[6:8]}"
        html.append("<tr>")
        html.append(f"<td>{date_str}</td>")
        html.append(f"<td>{n}</td>")
        html.append(f"<td>{pct}</td>")
        html.append(f"<td class='{'pos' if (strat_7d or 0) >= 0 else 'neg'}'>{fmt(strat_7d)}</td>")
        html.append(f"<td class='{'pos' if (strat_15d or 0) >= 0 else 'neg'}'>{fmt(strat_15d)}</td>")
        for idx_code in ["000001.SH", "399006.SZ", "000688.SH"]:
            for dl in ["ret_7d", "ret_15d"]:
                v = idx_ret(idx_code, dl)
                html.append(f"<td class='{'pos' if (v or 0) >= 0 else 'neg'}'>{fmt(v)}</td>")
        html.append("</tr>")
    html.append("</tbody></table>")

    # ── 五、策略表现总结 ──
    html.append("<h2>五、策略表现总结</h2>")

    html.append("<h3>整体统计</h3>")
    html.append("<table><thead><tr><th>指标</th><th>数值</th></tr></thead><tbody>")
    html.append(f"<tr><td>总信号数</td><td><strong>{total_picked}</strong> 条（{len(TARGET_DATES)} 个交易日）</td></tr>")
    html.append(f"<tr><td>日均信号数</td><td>{total_picked / len(TARGET_DATES):.1f} 条</td></tr>")
    if all_7d:
        html.append(f"<tr><td>7日平均收益</td><td class='{'pos' if avg7_val >= 0 else 'neg'}'><strong>{avg7_val:+.2f}%</strong>（{up7}/{len(all_7d)} 上涨，{up7/len(all_7d)*100:.1f}%）</td></tr>")
        html.append(f"<tr><td>15日平均收益</td><td class='{'pos' if avg15_val >= 0 else 'neg'}'><strong>{avg15_val:+.2f}%</strong>（{up15}/{len(all_15d)} 上涨，{up15/len(all_15d)*100:.1f}%）</td></tr>")
        html.append(f"<tr><td>7日最大盈利</td><td class='pos'>{max(all_7d):+.2f}%</td></tr>")
        html.append(f"<tr><td>7日最大亏损</td><td class='neg'>{min(all_7d):+.2f}%</td></tr>")
        html.append(f"<tr><td>15日最大盈利</td><td class='pos'>{max(all_15d):+.2f}%</td></tr>")
        html.append(f"<tr><td>15日最大亏损</td><td class='neg'>{min(all_15d):+.2f}%</td></tr>")
    html.append("</tbody></table>")

    html.append("<h3>评分与收益关系</h3>")
    html.append("<table><thead><tr><th>评分区间</th><th>数量</th><th>占比</th><th>平均7日收益</th><th>平均15日收益</th></tr></thead><tbody>")
    for lo, hi, label in [(0, 65, "60以下"), (65, 75, "65-75"), (75, 85, "75-85"), (85, 200, "85以上")]:
        bucket = [p for p in stock_performances if lo <= p["score"] < hi]
        if bucket:
            b7 = [p["ret_7d"] for p in bucket if p["ret_7d"] is not None]
            b15 = [p["ret_15d"] for p in bucket if p["ret_15d"] is not None]
            avg7 = sum(b7) / len(b7) if b7 else 0
            avg15 = sum(b15) / len(b15) if b15 else 0
            html.append("<tr>")
            html.append(f"<td>{label}</td>")
            html.append(f"<td>{len(bucket)}</td>")
            html.append(f"<td>{len(bucket)/total_picked*100:.1f}%</td>" if total_picked > 0 else "<td>-</td>")
            html.append(f"<td class='{'pos' if avg7 >= 0 else 'neg'}'>{avg7:+.2f}%</td>")
            html.append(f"<td class='{'pos' if avg15 >= 0 else 'neg'}'>{avg15:+.2f}%</td>")
            html.append("</tr>")
    html.append("</tbody></table>")

    html.append("</body></html>")

    # ── 输出 ──
    output_path = os.path.join(os.path.dirname(__file__), "docs", "oversold-bounce-performance-report.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html))

    print(f"\n{'=' * 80}")
    print(f"HTML 报表已生成: {output_path}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
