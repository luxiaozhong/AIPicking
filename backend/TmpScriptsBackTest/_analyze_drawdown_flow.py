#!/usr/bin/env python3
"""
M5Top3 V1 回撤期资金流特征分析

分析每个回撤期内：
1. 策略净值变化
2. 980080 指数整体资金流（所有成分股主力净流入合计）
3. 持仓股的资金流
4. 持仓股的分数分布

生成 HTML 报告：双轴图（净值 + 资金流）+ 回撤期高亮
"""

from __future__ import annotations
import json, os
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timedelta
import psycopg2
from dotenv import load_dotenv

_ENV_DIR = Path(__file__).resolve().parent.parent
for f in (".env", ".env.production"):
    p = _ENV_DIR / f
    if p.exists():
        load_dotenv(p, override=True)


def _pg():
    u = os.getenv("DATABASE_URL", "")
    if not u:
        u = f"postgresql://{os.getenv('DB_USER','aipicking')}:{os.getenv('DB_PASSWORD','')}@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}/{os.getenv('DB_NAME','aipicking')}"
    u = u.replace("+asyncpg", "").replace("+psycopg2", "")
    if "://" not in u:
        u = f"postgresql://{u}"
    r = urlparse(u)
    return psycopg2.connect(
        host=r.hostname or "localhost",
        port=r.port or 5432,
        user=r.username or "aipicking",
        password=r.password or "",
        dbname=r.path.lstrip("/") or "aipicking",
    )


ST, CM = 0.001, 0.0003
SELL_C = ST + CM
BUY_C = CM

LOOKBACK = 5
TOP_N = 3
INDEX_CODE = "980080"
BT_START = "2026-01-01"
BT_END = "2026-06-26"
DATA_START = "2025-11-01"
DATA_END = "2026-06-27"


def main():
    conn = _pg()
    cur = conn.cursor()

    # ── 成分股 ────────────────────────────────────────────────
    cur.execute(
        "SELECT ts_code FROM index_constituents WHERE index_code=%s", (INDEX_CODE,)
    )
    raw_set = {r[0] for r in cur.fetchall()}

    # ── 交易日历 ──────────────────────────────────────────────
    cur.execute(
        "SELECT DISTINCT trade_date FROM daily WHERE trade_date>=%s AND trade_date<=%s ORDER BY trade_date",
        (DATA_START, DATA_END),
    )
    all_td = [r[0] for r in cur.fetchall()]

    # ── 匹配的股票（非ST、stock类型、在成分股中）────────────
    cur.execute(
        """SELECT DISTINCT sff.ts_code FROM daily_stock_fund_flow sff
        JOIN stocks s ON s.ts_code=sff.ts_code
        WHERE sff.trade_date>=%s AND sff.trade_date<=%s
        AND s.type='stock' AND s.name NOT LIKE '%%ST%%'""",
        (DATA_START, DATA_END),
    )
    match_ts = [r[0] for r in cur.fetchall() if r[0].split(".")[0] in raw_set]

    # ── 股价 ──────────────────────────────────────────────────
    cur.execute(
        "SELECT ts_code,trade_date,open,close FROM daily "
        "WHERE ts_code=ANY(%s) AND trade_date>=%s AND trade_date<=%s "
        "ORDER BY ts_code,trade_date",
        (match_ts, DATA_START, DATA_END),
    )
    pr = {}
    pr_open = {}
    for c, d, o, v in cur.fetchall():
        pr.setdefault(d, {})[c] = v
        pr_open.setdefault(d, {})[c] = o

    # ── forward-fill close ────────────────────────────────────
    is_tradable = {}
    last_px = {}
    for td_ in all_td:
        px_day = pr.get(td_, {})
        is_tradable[td_] = {}
        for c in match_ts:
            if c in px_day:
                last_px[c] = px_day[c]
                is_tradable[td_][c] = True
            elif c in last_px:
                pr.setdefault(td_, {})[c] = last_px[c]
                is_tradable[td_][c] = False

    # ── forward-fill open ─────────────────────────────────────
    last_open = {}
    for td_ in all_td:
        op_day = pr_open.get(td_, {})
        for c in match_ts:
            if c in op_day:
                last_open[c] = op_day[c]
            elif c in last_open:
                pr_open.setdefault(td_, {})[c] = last_open[c]

    # ── 资金流 ────────────────────────────────────────────────
    cur.execute(
        "SELECT ts_code,trade_date,main_net_flow FROM daily_stock_fund_flow "
        "WHERE ts_code=ANY(%s) AND trade_date>=%s AND trade_date<=%s",
        (match_ts, DATA_START, DATA_END),
    )
    ff = {}  # {date: {code: float}}
    for c, d, v in cur.fetchall():
        ff.setdefault(d, {})[c] = float(v or 0)

    # ── 股票名称 ──────────────────────────────────────────────
    cur.execute(
        "SELECT ts_code,name FROM stocks WHERE ts_code=ANY(%s)", (match_ts,)
    )
    stock_names = {r[0]: r[1] for r in cur.fetchall()}
    conn.close()

    # ═══════════════════════════════════════════════════════════
    #  运行 V1 回测（M=5, Top 3, T+1 开盘）
    # ═══════════════════════════════════════════════════════════

    nav, cash = 1000.0, 0.0
    holdings = {}
    cost_basis = {}
    pending_ranking = None
    bt = [d for d in all_td if BT_START <= d <= BT_END]

    # 每日记录
    daily_records = []  # [{date, nav, positions, index_flow, pos_flow, ...}]

    # ── 计算每日指数级资金流（所有 match_ts 的 main_net_flow 合计）──
    idx_daily_flow = {}  # {date: total_flow}
    for d, flows in ff.items():
        idx_daily_flow[d] = sum(flows.values())

    for i, td in enumerate(bt):
        px_close = pr.get(td, {})
        px_open = pr_open.get(td, {})
        if not px_close:
            continue
        tradable = is_tradable.get(td, {})

        # ── 执行昨日决策 ─────────────────────────────────────
        kept_codes = set()
        bought_today = 0
        sold_today = 0

        # 记录当天买入/卖出的股票代码
        bought_codes = []
        sold_codes = []

        if pending_ranking is not None:
            tgt = {s["ts_code"] for s in pending_ranking}
            old = set(holdings.keys())

            if not holdings:
                tradable_ranking = [
                    s
                    for s in pending_ranking
                    if tradable.get(s["ts_code"]) and px_open.get(s["ts_code"], 0) > 0
                ]
                if tradable_ranking:
                    n = len(tradable_ranking)
                    w = 1.0 / n
                    for s in tradable_ranking:
                        p = px_open[s["ts_code"]]
                        holdings[s["ts_code"]] = (1000.0 * w * (1 - BUY_C)) / p
                        cost_basis[s["ts_code"]] = p
                    cash = 0
                    bought_today = len(tradable_ranking)
                    bought_codes = [s["ts_code"] for s in tradable_ranking]
            else:
                sell_c = old - tgt
                buy_c = tgt - old
                keep_c = old & tgt
                kept_codes = keep_c

                # 卖出
                sg = 0
                for c in list(sell_c):
                    if not tradable.get(c):
                        kept_codes.add(c)
                        continue
                    p = px_open.get(c, 0)
                    if p > 0:
                        sg += holdings[c] * p
                        sold_codes.append(c)
                        del holdings[c]
                        if c in cost_basis:
                            del cost_basis[c]
                        sold_today += 1
                cash += sg * (1 - SELL_C)

                # 买入
                bct = 0.0
                actual_buys = [
                    c for c in buy_c if tradable.get(c) and px_open.get(c, 0) > 0
                ]
                if actual_buys and cash > 0:
                    ca = cash / len(actual_buys)
                    for c in actual_buys:
                        p = px_open[c]
                        holdings[c] = (ca * (1 - BUY_C)) / p
                        cost_basis[c] = p
                        bct += ca * BUY_C
                        cash -= ca
                        bought_today += 1
                        bought_codes.append(c)
                elif not actual_buys:
                    pass  # cash stays idle

        # ── 当日收盘净值 ──────────────────────────────────────
        sv = sum(
            holdings[c] * px_close.get(c, 0)
            for c in holdings
            if px_close.get(c, 0) > 0
        )
        nav = sv + cash

        # ── 计算当日持仓资金流（持仓股的 main_net_flow 之和）──
        ff_today = ff.get(td, {})
        pos_flow = sum(ff_today.get(c, 0) for c in holdings)

        # ── 持仓股分数 ────────────────────────────────────────
        pos_scores = {}
        if pending_ranking is not None:
            score_map = {s["ts_code"]: s["flow_m"] for s in pending_ranking}
            for c in holdings:
                pos_scores[c] = score_map.get(c, 0)

        # ── 当日排名（所有股票分数）───────────────────────────
        idx_ = all_td.index(td)
        pre = all_td[max(0, idx_ - LOOKBACK + 1) : idx_ + 1]
        if len(pre) >= LOOKBACK:
            fs = {}
            for pd_ in pre:
                for c, v in ff.get(pd_, {}).items():
                    fs[c] = fs.get(c, 0) + v
            pending_ranking = sorted(
                [{"ts_code": k, "flow_m": v} for k, v in fs.items() if v > 0],
                key=lambda x: x["flow_m"],
                reverse=True,
            )[:TOP_N]
        else:
            pending_ranking = None

        daily_records.append(
            {
                "date": td,
                "nav": round(nav, 2),
                "holdings": list(holdings.keys()),
                "pos_flow": round(pos_flow, 2),
                "idx_flow": round(idx_daily_flow.get(td, 0), 2),
                "pos_flow_5d": 0,  # filled below
                "idx_flow_5d": 0,  # filled below
                "num_pos": len(holdings),
                "pos_scores": dict(pos_scores),
                "bought": bought_codes,
                "sold": sold_codes,
                "kept": list(kept_codes),
                "cash": round(cash, 2),
            }
        )

    # ── 计算 5 日累计资金流 ──────────────────────────────────
    for i, rec in enumerate(daily_records):
        d = rec["date"]
        start_i = max(0, i - 4)
        rec["idx_flow_5d"] = round(sum(daily_records[j]["idx_flow"] for j in range(start_i, i + 1)), 2)
        rec["pos_flow_5d"] = round(sum(daily_records[j]["pos_flow"] for j in range(start_i, i + 1)), 2)

    # ═══════════════════════════════════════════════════════════
    #  识别回撤期
    # ═══════════════════════════════════════════════════════════

    # 回撤：从最近峰值下跌 >= 3%，持续到恢复至峰值（或新峰值）
    DRAWDOWN_THRESHOLD = -0.03  # 净值从峰值跌 3% 算进入回撤

    peak = 1000.0
    peak_date = bt[0]
    in_drawdown = False
    drawdown_start = None
    drawdown_trough = None
    drawdown_trough_nav = float("inf")
    drawdown_phases = []  # [{start, end, peak_date, peak_nav, trough_date, trough_nav, max_dd}]

    for rec in daily_records:
        dd = rec["nav"] / peak - 1  # drawdown from peak

        if not in_drawdown:
            if rec["nav"] > peak:
                peak = rec["nav"]
                peak_date = rec["date"]
            elif dd <= DRAWDOWN_THRESHOLD:
                # Enter drawdown
                in_drawdown = True
                drawdown_start = rec["date"]
                drawdown_trough = rec["date"]
                drawdown_trough_nav = rec["nav"]
        else:
            if rec["nav"] > drawdown_trough_nav:
                drawdown_trough_nav = rec["nav"]
                drawdown_trough = rec["date"]
            if rec["nav"] >= peak:
                # Recovered
                dd_pct = round((drawdown_trough_nav / peak - 1) * 100, 2)
                drawdown_phases.append(
                    {
                        "start": drawdown_start,
                        "end": rec["date"],
                        "peak_date": peak_date,
                        "peak_nav": round(peak, 2),
                        "trough_date": drawdown_trough,
                        "trough_nav": round(drawdown_trough_nav, 2),
                        "max_dd_pct": dd_pct,
                        "days": (datetime.strptime(rec["date"], "%Y-%m-%d") - datetime.strptime(drawdown_start, "%Y-%m-%d")).days + 1,
                    }
                )
                in_drawdown = False
                peak = rec["nav"]
                peak_date = rec["date"]
                drawdown_start = None
                drawdown_trough = None
                drawdown_trough_nav = float("inf")

    # 如果结束时仍在回撤
    if in_drawdown:
        dd_pct = round((drawdown_trough_nav / peak - 1) * 100, 2)
        drawdown_phases.append(
            {
                "start": drawdown_start,
                "end": daily_records[-1]["date"],
                "peak_date": peak_date,
                "peak_nav": round(peak, 2),
                "trough_date": drawdown_trough,
                "trough_nav": round(drawdown_trough_nav, 2),
                "max_dd_pct": dd_pct,
                "days": (datetime.strptime(daily_records[-1]["date"], "%Y-%m-%d") - datetime.strptime(drawdown_start, "%Y-%m-%d")).days + 1,
            }
        )

    # ── 为每个回撤期统计资金流 ──────────────────────────────
    for dp in drawdown_phases:
        dd_recs = [
            r
            for r in daily_records
            if dp["start"] <= r["date"] <= dp["end"]
        ]
        # 回撤前期（从峰值日到回撤开始前）
        pre_recs = [
            r
            for r in daily_records
            if dp["peak_date"] <= r["date"] < dp["start"]
        ]
        # 指数资金流
        dp["avg_idx_flow"] = round(sum(r["idx_flow"] for r in dd_recs) / len(dd_recs) / 1e8, 2) if dd_recs else 0
        dp["total_idx_flow"] = round(sum(r["idx_flow"] for r in dd_recs) / 1e8, 2)
        # 持仓资金流
        dp["avg_pos_flow"] = round(sum(r["pos_flow"] for r in dd_recs) / len(dd_recs) / 1e8, 2) if dd_recs else 0
        dp["total_pos_flow"] = round(sum(r["pos_flow"] for r in dd_recs) / 1e8, 2)
        # 换手次数
        buys = sum(len(r["bought"]) for r in dd_recs)
        sells = sum(len(r["sold"]) for r in dd_recs)
        dp["total_trades"] = buys + sells
        # 回撤前峰值期资金流
        dp["pre_peak_idx_flow_5d"] = round(sum(r["idx_flow"] for r in pre_recs[-5:]) / 1e8, 2) if len(pre_recs) >= 5 else 0
        # 平均持仓数
        dp["avg_positions"] = round(sum(r["num_pos"] for r in dd_recs) / len(dd_recs), 1) if dd_recs else 0

    # ═══════════════════════════════════════════════════════════
    #  整体统计：回撤期 vs 非回撤期的资金流对比
    # ═══════════════════════════════════════════════════════════

    dd_dates = set()
    for dp in drawdown_phases:
        d = dp["start"]
        while d <= dp["end"]:
            dd_dates.add(d)
            d = (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    dd_records = [r for r in daily_records if r["date"] in dd_dates]
    non_dd_records = [r for r in daily_records if r["date"] not in dd_dates]

    def avg_flow(recs, key):
        if not recs:
            return 0
        return sum(r[key] for r in recs) / len(recs) / 1e8

    stats = {
        "dd_days": len(dd_dates),
        "non_dd_days": len(daily_records) - len(dd_dates),
        "dd_avg_idx_flow": round(avg_flow(dd_records, "idx_flow"), 2),
        "non_dd_avg_idx_flow": round(avg_flow(non_dd_records, "idx_flow"), 2),
        "dd_avg_pos_flow": round(avg_flow(dd_records, "pos_flow"), 2),
        "non_dd_avg_pos_flow": round(avg_flow(non_dd_records, "pos_flow"), 2),
        "dd_avg_idx_flow_5d": round(avg_flow(dd_records, "idx_flow_5d"), 2),
        "non_dd_avg_idx_flow_5d": round(avg_flow(non_dd_records, "idx_flow_5d"), 2),
        "dd_avg_positions": round(sum(r["num_pos"] for r in dd_records) / len(dd_records), 1) if dd_records else 0,
        "non_dd_avg_positions": round(sum(r["num_pos"] for r in non_dd_records) / len(non_dd_records), 1) if non_dd_records else 0,
    }

    # ── 控制台输出 ────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  M5Top3 V1 回撤期资金流分析 · {BT_START} ~ {BT_END}")
    print(f"{'='*80}")
    print(f"\n📊 共识别 {len(drawdown_phases)} 个回撤期（>3% from peak）:\n")

    for i, dp in enumerate(drawdown_phases):
        print(f"  {i+1}. {dp['start']} → {dp['end']} ({dp['days']}天)")
        print(f"     峰值: {dp['peak_date']} NAV={dp['peak_nav']:.2f} → 谷底: {dp['trough_date']} NAV={dp['trough_nav']:.2f} ({dp['max_dd_pct']}%)")
        print(f"     日均指数资金流: {dp['avg_idx_flow']:.2f}亿  总指数资金流: {dp['total_idx_flow']:.2f}亿")
        print(f"     日均持仓资金流: {dp['avg_pos_flow']:.2f}亿  平均持仓数: {dp['avg_positions']}")
        print(f"     换手次数: {dp['total_trades']}")

    print(f"\n{'='*80}")
    print(f"  回撤期 vs 非回撤期 资金流对比")
    print(f"{'='*80}")
    print(f"  回撤期天数: {stats['dd_days']}  |  非回撤期天数: {stats['non_dd_days']}")
    print(f"  日均指数资金流: 回撤期 {stats['dd_avg_idx_flow']:.2f}亿 vs 非回撤期 {stats['non_dd_avg_idx_flow']:.2f}亿")
    print(f"  日均持仓资金流: 回撤期 {stats['dd_avg_pos_flow']:.2f}亿 vs 非回撤期 {stats['non_dd_avg_pos_flow']:.2f}亿")
    print(f"  5日累计指数资金流: 回撤期 {stats['dd_avg_idx_flow_5d']:.2f}亿 vs 非回撤期 {stats['non_dd_avg_idx_flow_5d']:.2f}亿")
    print(f"  平均持仓数: 回撤期 {stats['dd_avg_positions']} vs 非回撤期 {stats['non_dd_avg_positions']}")

    # ═══════════════════════════════════════════════════════════
    #  生成 HTML 报告
    # ═══════════════════════════════════════════════════════════

    dates = [r["date"] for r in daily_records]
    navs = [r["nav"] for r in daily_records]
    idx_flows = [r["idx_flow"] / 1e8 for r in daily_records]  # 亿
    pos_flows = [r["pos_flow"] / 1e8 for r in daily_records]
    idx_flows_5d = [r["idx_flow_5d"] / 1e8 for r in daily_records]
    pos_flows_5d = [r["pos_flow_5d"] / 1e8 for r in daily_records]

    # 回撤期 markAreas
    mark_areas = []
    for dp in drawdown_phases:
        mark_areas.append([
            {"xAxis": dp["start"]},
            {"xAxis": dp["end"]},
        ])

    # 回撤期详情表格
    dd_rows = ""
    for i, dp in enumerate(drawdown_phases):
        dd_rows += f"""<tr>
        <td>{i+1}</td><td>{dp['start']}</td><td>{dp['end']}</td><td>{dp['days']}</td>
        <td>{dp['peak_date']}</td><td>{dp['peak_nav']:.2f}</td>
        <td>{dp['trough_date']}</td><td>{dp['trough_nav']:.2f}</td>
        <td style="color:#ff6b6b">{dp['max_dd_pct']}%</td>
        <td>{dp['avg_idx_flow']:.2f}亿</td><td>{dp['total_idx_flow']:.2f}亿</td>
        <td>{dp['avg_pos_flow']:.2f}亿</td><td>{dp['avg_positions']}</td><td>{dp['total_trades']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>M5Top3 V1 回撤期资金流分析</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#1a1a2e;font-family:-apple-system,sans-serif;color:#e0e0e0}}
.container{{max-width:1600px;margin:0 auto;padding:24px}}
h1{{text-align:center;font-size:22px;margin-bottom:6px}}
.sub{{color:#888;text-align:center;font-size:13px;margin-bottom:20px}}
h2{{font-size:18px;margin:30px 0 16px;padding-bottom:8px;border-bottom:1px solid #333}}
#chart_nav_flow,#chart_5d_flow{{width:100%;height:600px;background:#16213e;border-radius:12px;margin-bottom:24px}}
.summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:20px 0}}
.scard{{background:#16213e;border-radius:10px;padding:20px;text-align:center}}
.scard h3{{color:#888;font-size:12px;margin-bottom:8px}}
.scard .val{{font-size:26px;font-weight:bold}}
.scard .subval{{font-size:13px;color:#888;margin-top:4px}}
.dd-table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:16px}}
.dd-table th{{background:#16213e;color:#888;padding:10px 8px;text-align:left;border-bottom:2px solid #333;white-space:nowrap}}
.dd-table td{{padding:8px;border-bottom:1px solid #222;white-space:nowrap}}
.dd-table tr:hover td{{background:rgba(255,255,255,0.03)}}
.badge-red{{background:#ff6b6b;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px}}
.badge-green{{background:#6bcb77;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px}}
</style></head><body><div class="container">

<h1>🔍 M5Top3 V1 回撤期资金流分析</h1>
<div class="sub">980080 国证成长100 · T+1开盘 · M=5 Top3 · {BT_START} ~ {BT_END} · {len(daily_records)} 个交易日</div>

<!-- 摘要卡片 -->
<div class="summary">
<div class="scard"><h3>回撤期次数</h3><div class="val" style="color:#ff6b6b">{len(drawdown_phases)}</div><div class="subval">从峰值跌>3%计</div></div>
<div class="scard"><h3>回撤期日均指数资金流</h3><div class="val" style="color:{'#ff6b6b' if stats['dd_avg_idx_flow'] < 0 else '#6bcb77'}">{stats['dd_avg_idx_flow']:.2f}亿</div><div class="subval">非回撤期: {stats['non_dd_avg_idx_flow']:.2f}亿</div></div>
<div class="scard"><h3>回撤期日均持仓资金流</h3><div class="val" style="color:{'#ff6b6b' if stats['dd_avg_pos_flow'] < 0 else '#6bcb77'}">{stats['dd_avg_pos_flow']:.2f}亿</div><div class="subval">非回撤期: {stats['non_dd_avg_pos_flow']:.2f}亿</div></div>
<div class="scard"><h3>回撤期平均持仓数</h3><div class="val">{stats['dd_avg_positions']}</div><div class="subval">非回撤期: {stats['non_dd_avg_positions']}</div></div>
</div>

<!-- 图1: 净值 + 指数资金流（双轴） -->
<h2>📈 净值曲线 + 指数资金流叠加</h2>
<div id="chart_nav_flow"></div>

<!-- 图2: 净值 + 5日累计指数资金流 -->
<h2>📊 净值曲线 + 5日累计指数资金流</h2>
<div id="chart_5d_flow"></div>

<!-- 回撤期详情表 -->
<h2>📋 回撤期详情</h2>
<table class="dd-table">
<thead><tr>
<th>#</th><th>开始</th><th>结束</th><th>天数</th>
<th>峰值日</th><th>峰值净值</th><th>谷底日</th><th>谷底净值</th><th>最大回撤</th>
<th>日均指数流</th><th>总指数流</th><th>日均持仓流</th><th>均持仓</th><th>换手</th>
</tr></thead>
<tbody>{dd_rows}</tbody></table>

</div>

<script>
var dates = {json.dumps(dates)};
var navs = {json.dumps(navs)};
var idx_flows = {json.dumps(idx_flows)};
var pos_flows = {json.dumps(pos_flows)};
var idx_flows_5d = {json.dumps(idx_flows_5d)};

var drawdownAreas = {json.dumps(mark_areas)};
var ddData = drawdownAreas.map(function(a) {{
    return [{{xAxis: a[0].xAxis, itemStyle: {{color: 'rgba(255,107,107,0.12)'}}}} ,
            {{xAxis: a[1].xAxis}}];
}});

// ── 图1: 净值 + 资金流双轴 ──────────────────────────
var c1 = echarts.init(document.getElementById('chart_nav_flow'));
c1.setOption({{
    color: ['#ffd93d', '#6bcb77', '#ff6b6b'],
    tooltip: {{
        trigger: 'axis',
        backgroundColor: 'rgba(22,33,62,0.95)',
        borderColor: '#333',
        textStyle: {{color:'#e0e0e0',fontSize:13}},
        formatter: function(p) {{
            var s = '<b>' + p[0].axisValue + '</b><br/>';
            p.forEach(function(x) {{
                s += '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:'+x.color+';margin-right:6px"></span>'+x.seriesName+': <b>'+x.value.toFixed(2)+'</b><br/>';
            }});
            return s;
        }}
    }},
    legend: {{data:['净值','日指数资金流(亿)','日持仓资金流(亿)'],top:10,textStyle:{{color:'#aaa',fontSize:13}}}},
    grid: {{left:70,right:70,top:70,bottom:40}},
    xAxis: {{
        type:'category',data:dates,
        axisLine:{{lineStyle:{{color:'#333'}}}},
        axisLabel:{{color:'#888',fontSize:10,rotate:45,formatter:function(v){{return v.slice(5)}},interval:Math.floor(dates.length/20)}},
        splitLine:{{show:false}}
    }},
    yAxis: [
        {{type:'value',name:'净值',nameTextStyle:{{color:'#ffd93d',fontSize:12}},axisLabel:{{color:'#ffd93d',fontSize:11}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}}}},
        {{type:'value',name:'资金流(亿)',nameTextStyle:{{color:'#888',fontSize:12}},axisLabel:{{color:'#888',fontSize:11}},splitLine:{{show:false}}}}
    ],
    series: [
        {{
            name:'净值',type:'line',data:navs,yAxisIndex:0,
            smooth:true,symbol:'none',lineStyle:{{width:2.5,color:'#ffd93d'}},
            markArea: {{silent:true,data: ddData}}
        }},
        {{
            name:'日指数资金流(亿)',type:'bar',data:idx_flows.map(function(v){{return v>0?'+'+v.toFixed(1):v.toFixed(1)}}),yAxisIndex:1,
            itemStyle: {{color: function(p){{return p.value>=0?'rgba(107,203,119,0.6)':'rgba(255,107,107,0.6)'}}}}
        }},
        {{
            name:'日持仓资金流(亿)',type:'line',data:pos_flows,yAxisIndex:1,
            smooth:true,symbol:'none',lineStyle:{{width:1.5,color:'#ff6b6b',type:'dashed'}}
        }}
    ]
}});

// ── 图2: 净值 + 5日累计资金流 ────────────────────────
var c2 = echarts.init(document.getElementById('chart_5d_flow'));
c2.setOption({{
    color: ['#ffd93d', '#4ecdc4'],
    tooltip: {{
        trigger:'axis',backgroundColor:'rgba(22,33,62,0.95)',borderColor:'#333',
        textStyle:{{color:'#e0e0e0',fontSize:13}},
        formatter: function(p) {{
            var s = '<b>' + p[0].axisValue + '</b><br/>';
            p.forEach(function(x) {{
                s += '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:'+x.color+';margin-right:6px"></span>'+x.seriesName+': <b>'+x.value.toFixed(2)+'</b><br/>';
            }});
            return s;
        }}
    }},
    legend: {{data:['净值','5日累计指数资金流(亿)'],top:10,textStyle:{{color:'#aaa',fontSize:13}}}},
    grid: {{left:70,right:70,top:70,bottom:40}},
    xAxis: {{
        type:'category',data:dates,
        axisLine:{{lineStyle:{{color:'#333'}}}},
        axisLabel:{{color:'#888',fontSize:10,rotate:45,formatter:function(v){{return v.slice(5)}},interval:Math.floor(dates.length/20)}},
        splitLine:{{show:false}}
    }},
    yAxis: [
        {{type:'value',name:'净值',nameTextStyle:{{color:'#ffd93d',fontSize:12}},axisLabel:{{color:'#ffd93d',fontSize:11}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}}}},
        {{type:'value',name:'5日累计资金流(亿)',nameTextStyle:{{color:'#888',fontSize:12}},axisLabel:{{color:'#888',fontSize:11}},splitLine:{{show:false}}}}
    ],
    series: [
        {{
            name:'净值',type:'line',data:navs,yAxisIndex:0,
            smooth:true,symbol:'none',lineStyle:{{width:2.5,color:'#ffd93d'}},
            markArea: {{silent:true,data: ddData}}
        }},
        {{
            name:'5日累计指数资金流(亿)',type:'line',data:idx_flows_5d,yAxisIndex:1,
            smooth:true,symbol:'none',lineStyle:{{width:1.5,color:'#4ecdc4'}},
            areaStyle: {{color: new echarts.graphic.LinearGradient(0,0,0,1,[
                {{offset:0,color:'rgba(78,205,196,0.25)'}},
                {{offset:1,color:'rgba(78,205,196,0.02)'}}
            ])}}
        }}
    ]
}});

window.addEventListener('resize',function(){{c1.resize();c2.resize()}});
</script></body></html>"""

    out = Path(__file__).resolve().parent / "backtest_drawdown_flow_analysis.html"
    with open(out, "w") as f:
        f.write(html)
    print(f"\n✅ HTML 报告: {out}")


if __name__ == "__main__":
    main()
