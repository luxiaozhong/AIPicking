"""
超跌反弹策略 批量回测脚本（2020-2023）
==============================================
加载全部数据一次，按日切片运行策略，生成 HTML 报表。

用法: cd backend && source venv/bin/activate && python tmpScriptsBackTest/batch_backtest_2020_2023.py
"""

import sys
import os
import importlib.util
from datetime import datetime, timedelta
from collections import defaultdict

backend_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, backend_dir)

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.models.stock_tables import Stock, Daily

_sync_engine = create_engine(settings.SYNC_DATABASE_URL)
SyncSession = sessionmaker(bind=_sync_engine)

YEAR_START = "20200101"
YEAR_END = "20231231"
DATA_START = "20190701"  # 180天前
DATA_END = "20240215"    # 15天缓冲

INDICES = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000688.SH": "科创50",
}


def load_all_data():
    """一次性加载所有数据"""
    session = SyncSession()
    print("加载 stocks...")
    stmt = select(
        Stock.ts_code, Stock.symbol, Stock.name, Stock.market,
        Stock.industry_l1, Stock.industry_l2, Stock.industry_l3,
        Stock.concepts, Stock.total_shares, Stock.float_shares
    ).where(Stock.ts_code.isnot(None), Stock.ts_code != "")
    stocks_data = [dict(row._mapping) for row in session.execute(stmt)]

    print(f"加载 daily ({DATA_START} ~ {DATA_END})...")
    daily_stmt = select(
        Daily.ts_code, Daily.trade_date, Daily.open, Daily.high,
        Daily.low, Daily.close, Daily.vol, Daily.amount,
        Daily.adj_close, Daily.market_cap, Daily.circ_market_cap
    ).where(
        Daily.trade_date.between(DATA_START, DATA_END)
    ).order_by(Daily.ts_code, Daily.trade_date)
    daily_rows = [dict(row._mapping) for row in session.execute(daily_stmt)]

    session.close()

    daily_data = defaultdict(list)
    for row in daily_rows:
        daily_data[row["ts_code"]].append(row)

    print(f"  stocks: {len(stocks_data)}, daily ts_codes: {len(daily_data)}")
    return stocks_data, dict(daily_data)


def get_trading_days(daily_data):
    """获取所有交易日（从 399006.SZ 取）"""
    if "399006.SZ" not in daily_data:
        return []
    days = sorted(set(r["trade_date"] for r in daily_data["399006.SZ"]))
    return [d for d in days if YEAR_START <= d <= YEAR_END]


def precompute_market_oversold(daily_data, trading_days):
    """预计算每个交易日的大盘择时结果"""
    if "399006.SZ" not in daily_data:
        return set()

    rows = daily_data["399006.SZ"]
    date_close = {r["trade_date"]: r["close"] for r in rows if r.get("close") and r["close"] > 0}

    oversold = set()
    closes = []
    dates = []
    for d in sorted(date_close.keys()):
        if d < YEAR_START:
            dates.append(d)
            closes.append(date_close[d])

    for d in trading_days:
        if d not in date_close:
            continue
        dates.append(d)
        closes.append(date_close[d])
        if len(closes) >= 20:
            ma20 = sum(closes[-20:]) / 20
            close = closes[-1]
            if ma20 > 0:
                dev = (ma20 - close) / ma20 * 100
                if dev >= 1.5:
                    oversold.add(d)

    return oversold


def slice_daily(daily_data, cutoff_date):
    """按截止日切片"""
    sliced = {}
    for code, rows in daily_data.items():
        filtered = [r for r in rows if r["trade_date"] <= cutoff_date]
        if filtered:
            sliced[code] = filtered
    return sliced


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


def fmt(v):
    return f"{v:+.2f}%" if v is not None else "-"


def safe_avg(perfs, key):
    vals = [p[key] for p in perfs if p.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


def generate_html(all_results, all_index_data, forward_prices, index_forward,
                  total_stocks, oversold_days, trading_days_list):
    """生成 HTML 报表"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
                    perf[label] = round((fd["close"] - signal_close) / signal_close * 100, 2)
                    perf[f"{label}_date"] = fd["date"]
                else:
                    perf[label] = None
                    perf[f"{label}_date"] = None

            stock_performances.append(perf)

    total_picked = len(stock_performances)
    all_7d = [p["ret_7d"] for p in stock_performances if p["ret_7d"] is not None]
    all_15d = [p["ret_15d"] for p in stock_performances if p["ret_15d"] is not None]

    year_groups = [
        ("2020年", [d for d in sorted(all_results.keys()) if d.startswith("2020")]),
        ("2021年", [d for d in sorted(all_results.keys()) if d.startswith("2021")]),
        ("2022年", [d for d in sorted(all_results.keys()) if d.startswith("2022")]),
        ("2023年", [d for d in sorted(all_results.keys()) if d.startswith("2023")]),
    ]

    signal_days = sorted(all_results.keys())

    CSS = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1300px; margin: 0 auto; padding: 20px; background: #f8f9fa; color: #333; }
        h1 { color: #1a1a2e; border-bottom: 3px solid #e74c3c; padding-bottom: 10px; }
        h2 { color: #1a1a2e; border-bottom: 2px solid #ddd; padding-bottom: 8px; margin-top: 40px; }
        h3 { color: #2c3e50; margin-top: 30px; }
        h4 { color: #34495e; margin-top: 25px; padding: 8px 12px; background: #ecf0f1; border-radius: 4px; }
        .meta { background: #fff; padding: 15px; border-radius: 8px; margin-bottom: 30px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .meta p { margin: 4px 0; color: #666; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 6px; overflow: hidden; font-size: 12px; }
        th { background: #1a1a2e; color: #fff; padding: 8px 10px; text-align: center; font-weight: 600; font-size: 12px; white-space: nowrap; }
        td { padding: 6px 10px; text-align: center; border-bottom: 1px solid #eee; font-size: 12px; }
        tr:hover { background: #f0f4ff; }
        .pos { color: #e74c3c; font-weight: 600; }
        .neg { color: #27ae60; font-weight: 600; }
        .summary-box { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
        .stat-card { background: #fff; padding: 15px 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }
        .stat-card .label { font-size: 12px; color: #999; text-transform: uppercase; }
        .stat-card .value { font-size: 24px; font-weight: 700; color: #1a1a2e; margin: 5px 0; }
        .stat-card .sub { font-size: 12px; color: #666; }
        tr.total-row { font-weight: 700; background: #fff3cd !important; }
        tr.year-total { font-weight: 700; background: #e8f4fd !important; }
    </style>
    """

    html = []
    html.append("<!DOCTYPE html><html><head><meta charset='utf-8'>")
    html.append("<title>超跌反弹策略 2020-2023 批量回测报告</title>")
    html.append(CSS)
    html.append("</head><body>")

    html.append("<h1>📊 超跌反弹策略 2020-2023 批量回测报告</h1>")
    html.append("<div class='meta'>")
    html.append(f"<p><strong>生成时间：</strong>{now_str}</p>")
    html.append(f"<p><strong>回测范围：</strong>2020-01-01 ~ 2023-12-31（{len(trading_days_list)} 个交易日）</p>")
    html.append(f"<p><strong>大盘择时：</strong>创业板指收盘低于MA20≥1.5%（{len(oversold_days)}天超跌 / {len(trading_days_list)}天，占比 {len(oversold_days)/len(trading_days_list)*100:.1f}%）</p>")
    html.append(f"<p><strong>股票池：</strong>创业板(300/301) + 科创板(688/689)，共 {total_stocks} 只</p>")
    html.append(f"<p><strong>有信号的交易日：</strong>{len(signal_days)} 天</p>")
    html.append("</div>")

    html.append("<h2>📈 关键指标</h2>")
    html.append("<div class='summary-box'>")
    html.append(f"<div class='stat-card'><div class='label'>有信号交易日</div><div class='value'>{len(signal_days)}</div><div class='sub'>/ {len(oversold_days)} 超跌天</div></div>")
    html.append(f"<div class='stat-card'><div class='label'>总信号数</div><div class='value'>{total_picked}</div><div class='sub'>日均 {total_picked/max(len(signal_days),1):.1f} 条</div></div>")
    avg7_val = sum(all_7d) / len(all_7d) if all_7d else 0
    up7 = sum(1 for v in all_7d if v > 0) if all_7d else 0
    html.append(f"<div class='stat-card'><div class='label'>7日平均收益</div><div class='value' style='color:#{'e74c3c' if avg7_val>=0 else '27ae60'}'>{avg7_val:+.2f}%</div><div class='sub'>上涨率 {up7}/{len(all_7d)} ({up7/len(all_7d)*100:.0f}%)</div></div>")
    avg15_val = sum(all_15d) / len(all_15d) if all_15d else 0
    up15 = sum(1 for v in all_15d if v > 0) if all_15d else 0
    html.append(f"<div class='stat-card'><div class='label'>15日平均收益</div><div class='value' style='color:#{'e74c3c' if avg15_val>=0 else '27ae60'}'>{avg15_val:+.2f}%</div><div class='sub'>上涨率 {up15}/{len(all_15d)} ({up15/len(all_15d)*100:.0f}%)</div></div>")
    if all_7d:
        html.append(f"<div class='stat-card'><div class='label'>7日最大盈利</div><div class='value' style='color:#e74c3c'>{max(all_7d):+.2f}%</div><div class='sub'>最大亏损 {min(all_7d):+.2f}%</div></div>")
        html.append(f"<div class='stat-card'><div class='label'>15日最大盈利</div><div class='value' style='color:#e74c3c'>{max(all_15d):+.2f}%</div><div class='sub'>最大亏损 {min(all_15d):+.2f}%</div></div>")
    html.append("</div>")

    # ── 一、按年汇总 ──
    html.append("<h2>一、按年汇总</h2>")
    html.append("<table><thead><tr>")
    for h in ["年份", "有信号天数", "总信号数", "日均信号", "平均当日涨跌", "平均7日涨跌", "平均15日涨跌", "上涨占比(7日)", "上涨占比(15日)"]:
        html.append(f"<th>{h}</th>")
    html.append("</tr></thead><tbody>")

    for year_label, dates in year_groups:
        year_perfs = [p for p in stock_performances if p["signal_date"] in dates]
        n = len(year_perfs)
        n_days = len(dates)
        if n == 0:
            html.append(f"<tr><td>{year_label}</td><td>{n_days}</td><td>0</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>")
            continue

        a0 = safe_avg(year_perfs, "ret_0d")
        a7 = safe_avg(year_perfs, "ret_7d")
        a15 = safe_avg(year_perfs, "ret_15d")
        u7 = sum(1 for p in year_perfs if p.get("ret_7d") is not None and p["ret_7d"] > 0)
        u15 = sum(1 for p in year_perfs if p.get("ret_15d") is not None and p["ret_15d"] > 0)
        c7 = sum(1 for p in year_perfs if p.get("ret_7d") is not None)
        c15 = sum(1 for p in year_perfs if p.get("ret_15d") is not None)

        html.append("<tr class='year-total'>")
        html.append(f"<td><strong>{year_label}</strong></td>")
        html.append(f"<td>{n_days}</td>")
        html.append(f"<td><strong>{n}</strong></td>")
        html.append(f"<td>{n/max(n_days,1):.1f}</td>")
        html.append(f"<td class='{'pos' if (a0 or 0)>=0 else 'neg'}'>{fmt(a0)}</td>")
        html.append(f"<td class='{'pos' if (a7 or 0)>=0 else 'neg'}'>{fmt(a7)}</td>")
        html.append(f"<td class='{'pos' if (a15 or 0)>=0 else 'neg'}'>{fmt(a15)}</td>")
        html.append(f"<td>{u7}/{c7} ({u7/c7*100:.0f}%)</td>" if c7 > 0 else "<td>-</td>")
        html.append(f"<td>{u15}/{c15} ({u15/c15*100:.0f}%)</td>" if c15 > 0 else "<td>-</td>")
        html.append("</tr>")

    html.append("<tr class='total-row'>")
    html.append(f"<td><strong>合计</strong></td><td><strong>{len(signal_days)}</strong></td><td><strong>{total_picked}</strong></td>")
    html.append(f"<td><strong>{total_picked/max(len(signal_days),1):.1f}</strong></td>")
    a0_all = safe_avg(stock_performances, "ret_0d")
    a7_all = safe_avg(stock_performances, "ret_7d")
    a15_all = safe_avg(stock_performances, "ret_15d")
    c7_all = sum(1 for p in stock_performances if p.get("ret_7d") is not None)
    c15_all = sum(1 for p in stock_performances if p.get("ret_15d") is not None)
    html.append(f"<td class='{'pos' if (a0_all or 0)>=0 else 'neg'}'><strong>{fmt(a0_all)}</strong></td>")
    html.append(f"<td class='{'pos' if (a7_all or 0)>=0 else 'neg'}'><strong>{fmt(a7_all)}</strong></td>")
    html.append(f"<td class='{'pos' if (a15_all or 0)>=0 else 'neg'}'><strong>{fmt(a15_all)}</strong></td>")
    html.append(f"<td><strong>{up7}/{c7_all} ({up7/c7_all*100:.0f}%)</strong></td>")
    html.append(f"<td><strong>{up15}/{c15_all} ({up15/c15_all*100:.0f}%)</strong></td>")
    html.append("</tr></tbody></table>")

    # ── 二、按日详细汇总 ──
    html.append("<h2>二、每日汇总</h2>")

    month_order = sorted(set(d[:6] for d in signal_days))
    for month_key in month_order:
        month_dates = [d for d in signal_days if d.startswith(month_key)]
        month_label = f"{month_key[:4]}年{int(month_key[4:6])}月"
        html.append(f"<h3>{month_label}（{len(month_dates)}天）</h3>")
        html.append("<table><thead><tr>")
        for h in ["信号日", "选出数", "占比", "平均当日涨跌", "平均7日涨跌", "平均15日涨跌", "上涨占比(7日)", "上涨占比(15日)"]:
            html.append(f"<th>{h}</th>")
        html.append("</tr></thead><tbody>")

        for d in month_dates:
            date_perfs = [p for p in stock_performances if p["signal_date"] == d]
            n = len(date_perfs)
            pct = f"{n/total_stocks*100:.2f}%"

            a0 = safe_avg(date_perfs, "ret_0d")
            a7 = safe_avg(date_perfs, "ret_7d")
            a15 = safe_avg(date_perfs, "ret_15d")
            u7_d = sum(1 for p in date_perfs if p.get("ret_7d") is not None and p["ret_7d"] > 0)
            u15_d = sum(1 for p in date_perfs if p.get("ret_15d") is not None and p["ret_15d"] > 0)
            c7_d = sum(1 for p in date_perfs if p.get("ret_7d") is not None)
            c15_d = sum(1 for p in date_perfs if p.get("ret_15d") is not None)

            html.append("<tr>")
            html.append(f"<td>{d[:4]}-{d[4:6]}-{d[6:8]}</td>")
            html.append(f"<td><strong>{n}</strong></td>")
            html.append(f"<td>{pct}</td>")
            html.append(f"<td class='{'pos' if (a0 or 0)>=0 else 'neg'}'>{fmt(a0)}</td>")
            html.append(f"<td class='{'pos' if (a7 or 0)>=0 else 'neg'}'>{fmt(a7)}</td>")
            html.append(f"<td class='{'pos' if (a15 or 0)>=0 else 'neg'}'>{fmt(a15)}</td>")
            html.append(f"<td>{u7_d}/{c7_d} ({u7_d/c7_d*100:.0f}%)</td>" if c7_d > 0 else "<td>-</td>")
            html.append(f"<td>{u15_d}/{c15_d} ({u15_d/c15_d*100:.0f}%)</td>" if c15_d > 0 else "<td>-</td>")
            html.append("</tr>")

        html.append("</tbody></table>")

    # ── 三、评分与收益关系 ──
    html.append("<h2>三、评分与收益关系</h2>")
    html.append("<table><thead><tr><th>评分区间</th><th>数量</th><th>占比</th><th>平均7日收益</th><th>平均15日收益</th></tr></thead><tbody>")
    for lo, hi, label in [(0, 65, "60以下"), (65, 75, "65-75"), (75, 85, "75-85"), (85, 200, "85以上")]:
        bucket = [p for p in stock_performances if lo <= p["score"] < hi]
        if bucket:
            b7 = [p["ret_7d"] for p in bucket if p["ret_7d"] is not None]
            b15 = [p["ret_15d"] for p in bucket if p["ret_15d"] is not None]
            avg7 = sum(b7) / len(b7) if b7 else 0
            avg15 = sum(b15) / len(b15) if b15 else 0
            html.append("<tr>")
            html.append(f"<td>{label}</td><td>{len(bucket)}</td><td>{len(bucket)/total_picked*100:.1f}%</td>")
            html.append(f"<td class='{'pos' if avg7>=0 else 'neg'}'>{avg7:+.2f}%</td>")
            html.append(f"<td class='{'pos' if avg15>=0 else 'neg'}'>{avg15:+.2f}%</td>")
            html.append("</tr>")
    html.append("</tbody></table>")

    # ── 四、大盘择时分布 ──
    html.append("<h2>四、大盘择时分析</h2>")
    html.append("<table><thead><tr><th>年份</th><th>交易日</th><th>超跌天</th><th>超跌占比</th><th>有信号天</th><th>信号率</th></tr></thead><tbody>")
    for year in ["2020", "2021", "2022", "2023"]:
        all_days_year = sum(1 for d in trading_days_list if d.startswith(year))
        o_days = sum(1 for d in oversold_days if d.startswith(year))
        s_days = sum(1 for d in signal_days if d.startswith(year))
        html.append("<tr>")
        html.append(f"<td>{year}年</td><td>{all_days_year}</td><td>{o_days}</td>")
        html.append(f"<td>{o_days/all_days_year*100:.1f}%</td>" if all_days_year > 0 else "<td>-</td>")
        html.append(f"<td>{s_days}</td>")
        html.append(f"<td>{s_days/o_days*100:.1f}%</td>" if o_days > 0 else "<td>-</td>")
        html.append("</tr>")
    html.append("</tbody></table>")

    html.append("</body></html>")

    output_path = os.path.join(os.path.dirname(__file__), "oversold-bounce-2020-2023-report.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html))
    print(f"\nHTML 报表已生成: {output_path}")


def load_strategy_module():
    strategy_path = os.path.join(backend_dir, "app", "strategies", "examples", "oversold_bounce.py")
    spec = importlib.util.spec_from_file_location("oversold_bounce_strategy", strategy_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    print("=" * 60)
    print("超跌反弹策略 2020-2023 批量回测")
    print("=" * 60)

    # 1. 加载全部数据
    stocks_data, daily_data = load_all_data()

    # 2. 获取交易日
    trading_days = get_trading_days(daily_data)
    print(f"交易日: {len(trading_days)} 天")

    # 3. 预计算大盘择时
    oversold_days = precompute_market_oversold(daily_data, trading_days)
    print(f"超跌天: {len(oversold_days)} 天 ({len(oversold_days)/len(trading_days)*100:.1f}%)")

    # 4. 加载策略
    strategy = load_strategy_module()
    original_top = strategy.TOP_PICKS
    strategy.TOP_PICKS = 99999

    total_cy_kc = sum(1 for s in stocks_data
                      if s["ts_code"].startswith(("300", "301", "688", "689")))

    all_results = {}
    all_index_data = {}
    processed = 0
    signal_days_count = 0

    sorted_oversold = sorted(oversold_days)

    for cutoff_date in sorted_oversold:
        processed += 1

        sliced = slice_daily(daily_data, cutoff_date)

        strategy_input = {
            "cutoff_date": cutoff_date,
            "stocks": stocks_data,
            "daily": sliced,
            "config": {},
        }

        try:
            recommendations = strategy.run(strategy_input)
        except Exception as e:
            print(f"  {cutoff_date} 策略执行错误: {e}")
            recommendations = []

        if not recommendations:
            if processed % 20 == 0:
                print(f"  [{processed}/{len(sorted_oversold)}] {cutoff_date}: 0只")
            continue

        signal_days_count += 1

        for r in recommendations:
            rows = sliced.get(r["ts_code"], [])
            r["_close"] = rows[-1].get("close") if rows else None

        all_results[cutoff_date] = recommendations

        idx_info = {}
        for idx_code, idx_name in INDICES.items():
            idx_rows = sliced.get(idx_code, [])
            idx_info[idx_code] = {
                "name": idx_name,
                "signal_date": cutoff_date,
                "signal_close": idx_rows[-1].get("close") if idx_rows else None,
            }
        all_index_data[cutoff_date] = idx_info

        if processed % 10 == 0:
            print(f"  [{processed}/{len(sorted_oversold)}] {cutoff_date}: {len(recommendations)}只 (累计信号天: {signal_days_count})")

    strategy.TOP_PICKS = original_top

    print(f"\n总计: {signal_days_count} 个有信号的交易日, {sum(len(v) for v in all_results.values())} 条信号")

    # 5. 获取前向价格
    print("获取前向价格...")
    session = SyncSession()

    forward_prices = {}
    for cutoff_date, recs in all_results.items():
        codes = [r["ts_code"] for r in recs]
        fp = get_forward_prices(session, codes, cutoff_date, [0, 7, 15])
        for code, days_data in fp.items():
            forward_prices[(cutoff_date, code)] = days_data

    index_forward = {}
    for cutoff_date in all_results:
        for idx_code in INDICES:
            fp = get_forward_prices(session, [idx_code], cutoff_date, [0, 7, 15])
            index_forward[(cutoff_date, idx_code)] = fp.get(idx_code, {})

    session.close()

    # 6. 生成 HTML
    print("生成 HTML 报表...")
    generate_html(all_results, all_index_data, forward_prices, index_forward,
                  total_cy_kc, oversold_days, trading_days)

    print("完成!")


if __name__ == "__main__":
    main()
