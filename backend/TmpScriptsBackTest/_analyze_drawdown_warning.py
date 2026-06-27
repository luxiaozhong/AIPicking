#!/usr/bin/env python3
"""
回撤前期资金流预警分析

核心问题：回撤发生前，资金流是否已经出现了可观测的恶化信号？

分析维度：
1. 每个回撤前 5 天的指数资金流趋势（是否在减速/转负）
2. 价格-资金流背离：净值创新高但资金流走弱
3. 持仓股分数 gap：Top 3 vs #4-10 的分数差异是否收窄
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

    cur.execute("SELECT ts_code FROM index_constituents WHERE index_code=%s", (INDEX_CODE,))
    raw_set = {r[0] for r in cur.fetchall()}

    cur.execute(
        "SELECT DISTINCT trade_date FROM daily WHERE trade_date>=%s AND trade_date<=%s ORDER BY trade_date",
        (DATA_START, DATA_END),
    )
    all_td = [r[0] for r in cur.fetchall()]

    cur.execute(
        """SELECT DISTINCT sff.ts_code FROM daily_stock_fund_flow sff
        JOIN stocks s ON s.ts_code=sff.ts_code
        WHERE sff.trade_date>=%s AND sff.trade_date<=%s
        AND s.type='stock' AND s.name NOT LIKE '%%ST%%'""",
        (DATA_START, DATA_END),
    )
    match_ts = [r[0] for r in cur.fetchall() if r[0].split(".")[0] in raw_set]

    cur.execute(
        "SELECT ts_code,trade_date,open,close FROM daily "
        "WHERE ts_code=ANY(%s) AND trade_date>=%s AND trade_date<=%s "
        "ORDER BY ts_code,trade_date",
        (match_ts, DATA_START, DATA_END),
    )
    pr = {}; pr_open = {}
    for c, d, o, v in cur.fetchall():
        pr.setdefault(d, {})[c] = v
        pr_open.setdefault(d, {})[c] = o

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

    last_open = {}
    for td_ in all_td:
        op_day = pr_open.get(td_, {})
        for c in match_ts:
            if c in op_day:
                last_open[c] = op_day[c]
            elif c in last_open:
                pr_open.setdefault(td_, {})[c] = last_open[c]

    cur.execute(
        "SELECT ts_code,trade_date,main_net_flow FROM daily_stock_fund_flow "
        "WHERE ts_code=ANY(%s) AND trade_date>=%s AND trade_date<=%s",
        (match_ts, DATA_START, DATA_END),
    )
    ff = {}
    for c, d, v in cur.fetchall():
        ff.setdefault(d, {})[c] = float(v or 0)
    conn.close()

    # ── 每日指数总资金流 ────────────────────────────────────
    idx_daily_flow = {}
    for d, flows in ff.items():
        idx_daily_flow[d] = sum(flows.values())

    # ═══════════════════════════════════════════════════════════
    #  运行 V1 回测，同时记录完整状态
    # ═══════════════════════════════════════════════════════════

    nav, cash = 1000.0, 0.0
    holdings = {}
    cost_basis = {}
    pending_ranking = None
    bt = [d for d in all_td if BT_START <= d <= BT_END]
    daily_records = []

    for i, td in enumerate(bt):
        px_close = pr.get(td, {})
        px_open = pr_open.get(td, {})
        if not px_close:
            continue
        tradable = is_tradable.get(td, {})

        if pending_ranking is not None:
            tgt = {s["ts_code"] for s in pending_ranking}
            old = set(holdings.keys())

            if not holdings:
                tradable_ranking = [
                    s for s in pending_ranking
                    if tradable.get(s["ts_code"]) and px_open.get(s["ts_code"], 0) > 0
                ]
                if tradable_ranking:
                    n = len(tradable_ranking); w = 1.0 / n
                    for s in tradable_ranking:
                        p = px_open[s["ts_code"]]
                        holdings[s["ts_code"]] = (1000.0 * w * (1 - BUY_C)) / p
                        cost_basis[s["ts_code"]] = p
                    cash = 0
            else:
                sell_c = old - tgt; buy_c = tgt - old; keep_c = old & tgt
                sg = 0
                for c in list(sell_c):
                    if not tradable.get(c): continue
                    p = px_open.get(c, 0)
                    if p > 0:
                        sg += holdings[c] * p
                        del holdings[c]
                        if c in cost_basis: del cost_basis[c]
                cash += sg * (1 - SELL_C)
                bct = 0.0
                actual_buys = [c for c in buy_c if tradable.get(c) and px_open.get(c, 0) > 0]
                if actual_buys and cash > 0:
                    ca = cash / len(actual_buys)
                    for c in actual_buys:
                        p = px_open[c]
                        holdings[c] = (ca * (1 - BUY_C)) / p
                        cost_basis[c] = p
                        bct += ca * BUY_C; cash -= ca

        sv = sum(holdings[c] * px_close.get(c, 0) for c in holdings if px_close.get(c, 0) > 0)
        nav = sv + cash

        # ── 计算当日全部股票的分数和 Top 3/10 ─────────────
        idx_ = all_td.index(td)
        pre = all_td[max(0, idx_ - LOOKBACK + 1):idx_ + 1]
        all_scores = {}
        top3_score = top5_score = top10_score = 0
        score_gap_3_5 = score_gap_3_10 = 0

        if len(pre) >= LOOKBACK:
            fs = {}
            for pd_ in pre:
                for c, v in ff.get(pd_, {}).items():
                    fs[c] = fs.get(c, 0) + v
            sorted_scores = sorted(
                [{"ts_code": k, "flow_m": v} for k, v in fs.items() if v > 0],
                key=lambda x: x["flow_m"], reverse=True,
            )
            all_scores = {s["ts_code"]: s["flow_m"] for s in sorted_scores}

            pending_ranking = sorted_scores[:TOP_N]
            if len(sorted_scores) >= 3:
                top3_score = sorted_scores[2]["flow_m"]  # #3 score
            if len(sorted_scores) >= 5:
                top5_score = sorted_scores[4]["flow_m"]
            if len(sorted_scores) >= 10:
                top10_score = sorted_scores[9]["flow_m"]
            score_gap_3_5 = top3_score - top5_score if top5_score > 0 else 0
            score_gap_3_10 = top3_score - top10_score if top10_score > 0 else 0
        else:
            pending_ranking = None

        pos_flow = sum(ff.get(td, {}).get(c, 0) for c in holdings)

        daily_records.append({
            "date": td,
            "nav": round(nav, 2),
            "idx_flow": round(idx_daily_flow.get(td, 0), 2),
            "pos_flow": round(pos_flow, 2),
            "num_pos": len(holdings),
            "top3_score": top3_score,
            "top5_score": top5_score,
            "top10_score": top10_score,
            "score_gap_3_5": score_gap_3_5,
            "score_gap_3_10": score_gap_3_10,
            "holdings": list(holdings.keys()),
        })

    # ── 5日累计 + 前5日累计 ─────────────────────────────────
    for i, rec in enumerate(daily_records):
        start_i = max(0, i - 4)
        rec["idx_flow_5d"] = round(sum(daily_records[j]["idx_flow"] for j in range(start_i, i + 1)), 2)

    # ═══════════════════════════════════════════════════════════
    #  识别显著回撤期（从峰值跌 >3%，且谷底低于峰值）
    # ═══════════════════════════════════════════════════════════

    peak = 1000.0
    peak_date = bt[0]
    peak_idx = 0
    in_drawdown = False
    drawdown_start = None
    drawdown_start_idx = 0
    drawdown_trough_nav = float("inf")
    drawdown_trough_idx = 0
    drawdown_phases = []

    for i, rec in enumerate(daily_records):
        if rec["nav"] > peak:
            if in_drawdown and rec["nav"] >= peak:
                # Recovered
                dd_pct = round((drawdown_trough_nav / peak - 1) * 100, 2)
                if dd_pct < -1:  # only record >1% drawdowns
                    drawdown_phases.append({
                        "start": drawdown_start,
                        "start_idx": drawdown_start_idx,
                        "end": rec["date"],
                        "peak_date": peak_date,
                        "peak_idx": peak_idx,
                        "peak_nav": round(peak, 2),
                        "trough_date": daily_records[drawdown_trough_idx]["date"],
                        "trough_nav": round(drawdown_trough_nav, 2),
                        "max_dd_pct": dd_pct,
                    })
                in_drawdown = False
                drawdown_trough_nav = float("inf")
            peak = rec["nav"]
            peak_date = rec["date"]
            peak_idx = i
        elif rec["nav"] < peak:
            dd = (rec["nav"] / peak - 1)
            if not in_drawdown and dd <= -0.03:
                in_drawdown = True
                drawdown_start = rec["date"]
                drawdown_start_idx = i
                drawdown_trough_nav = rec["nav"]
                drawdown_trough_idx = i
            elif in_drawdown and rec["nav"] < drawdown_trough_nav:
                drawdown_trough_nav = rec["nav"]
                drawdown_trough_idx = i

    # ═══════════════════════════════════════════════════════════
    #  分析每个回撤前 5 天的预警信号
    # ═══════════════════════════════════════════════════════════

    print(f"\n{'='*90}")
    print(f"  🔔 回撤前资金流预警分析 · M5Top3 V1 · {BT_START} ~ {BT_END}")
    print(f"{'='*90}")
    print(f"\n  共识别 {len(drawdown_phases)} 个显著回撤期（>3% from peak, 且 trough<peak）\n")

    for i, dp in enumerate(drawdown_phases):
        # 回撤前 10 天数据
        pre_start = max(0, dp["start_idx"] - 10)
        pre_data = daily_records[pre_start:dp["start_idx"]]
        # 回撤期数据
        dd_data = daily_records[dp["start_idx"]:dp["start_idx"] + min(dp.get("days", 30), 30)]

        # 前 5 天（距回撤最近）
        pre5 = pre_data[-5:] if len(pre_data) >= 5 else pre_data
        # 再前 5 天（更早期）
        pre10_5 = pre_data[-10:-5] if len(pre_data) >= 10 else []

        avg_flow_pre5 = sum(r["idx_flow"] for r in pre5) / len(pre5) / 1e8 if pre5 else 0
        avg_flow_pre10_5 = sum(r["idx_flow"] for r in pre10_5) / len(pre10_5) / 1e8 if pre10_5 else 0

        # 资金流加速度：前 5 天 vs 再前 5 天
        flow_accel = avg_flow_pre5 - avg_flow_pre10_5 if pre10_5 else 0

        # 最近5天中负流出的天数
        neg_days_pre5 = sum(1 for r in pre5 if r["idx_flow"] < 0)

        # 前5天资金流转负的时点
        first_neg = None
        for r in pre5:
            if r["idx_flow"] < 0:
                first_neg = r["date"]
                break

        # 评分 gap（Top3 vs Top5/10）
        avg_gap_pre5 = sum(r["score_gap_3_5"] for r in pre5) / len(pre5) / 1e8 if pre5 else 0
        avg_gap_pre10_5 = sum(r["score_gap_3_5"] for r in pre10_5) / len(pre10_5) / 1e8 if pre10_5 else 0
        gap_shrink = avg_gap_pre5 < avg_gap_pre10_5 if pre10_5 else False

        # 日均指数资金流
        dd_flow_avg = sum(r["idx_flow"] for r in dd_data) / len(dd_data) / 1e8 if dd_data else 0

        print(f"  ┌─ 回撤 #{i+1}: {dp['start']} → {dp['end']} ─────────────────────────────┐")
        print(f"  │ 峰值: {dp['peak_date']} NAV={dp['peak_nav']:.2f} → 谷底: {dp['trough_date']} NAV={dp['trough_nav']:.2f} ({dp['max_dd_pct']}%)")
        print(f"  │")
        print(f"  │ 📊 回撤前 10→5 天 资金流: 日均 {avg_flow_pre10_5:+.2f}亿")
        print(f"  │ 📊 回撤前 5→0 天 资金流: 日均 {avg_flow_pre5:+.2f}亿  {'⚠️ 加速恶化' if flow_accel < -5 else '🔻 走弱' if flow_accel < 0 else '➡️ 平稳' if flow_accel < 5 else '🟢 走强'}")
        print(f"  │ 📊 前5天中负流天数: {neg_days_pre5}/5  {'❗ 首次转负: '+first_neg if first_neg else ''}")
        print(f"  │ 📊 前5天指数 5日累计流: {pre5[-1]['idx_flow_5d']/1e8:+.2f}亿" if pre5 else "  │")
        print(f"  │")
        print(f"  │ 🎯 前10→5天 Top3/5 分数 Gap: {avg_gap_pre10_5:.1f}亿 → 前5→0天: {avg_gap_pre5:.1f}亿 {'⚠️ Gap 收窄' if gap_shrink else ''}")
        print(f"  │")
        print(f"  │ 📉 回撤期间: 日均指数流 {dd_flow_avg:+.2f}亿")
        print(f"  └{'─'*70}┘\n")

    # ── 汇总统计 ──────────────────────────────────────────────
    print(f"  {'='*90}")
    print(f"  📋 汇总：回撤前预警信号命中率")
    print(f"  {'='*90}")

    pre_signals = []
    for i, dp in enumerate(drawdown_phases):
        pre_start = max(0, dp["start_idx"] - 10)
        pre_data = daily_records[pre_start:dp["start_idx"]]
        pre5 = pre_data[-5:] if len(pre_data) >= 5 else pre_data
        pre10_5 = pre_data[-10:-5] if len(pre_data) >= 10 else []

        avg_flow_pre5 = sum(r["idx_flow"] for r in pre5) / len(pre5) / 1e8 if pre5 else 0
        avg_flow_pre10_5 = sum(r["idx_flow"] for r in pre10_5) / len(pre10_5) / 1e8 if pre10_5 else 0
        neg_days_pre5 = sum(1 for r in pre5 if r["idx_flow"] < 0)

        flags = []
        if avg_flow_pre5 < -10:
            flags.append("日均流出>10亿")
        if avg_flow_pre5 < avg_flow_pre10_5 - 5 and pre10_5:
            flags.append("资金流加速恶化")
        if neg_days_pre5 >= 4:
            flags.append(f"{neg_days_pre5}/5天净流出")
        if neg_days_pre5 >= 3:
            flags.append(f"{neg_days_pre5}/5天净流出")

        had_warning = len(flags) > 0
        pre_signals.append({
            "dd": f"{dp['start']}→{dp['end']}",
            "dd_pct": dp["max_dd_pct"],
            "pre5_flow": round(avg_flow_pre5, 1),
            "pre10_5_flow": round(avg_flow_pre10_5, 1),
            "neg_days": neg_days_pre5,
            "flags": flags,
            "had_warning": had_warning,
        })

    warned = sum(1 for s in pre_signals if s["had_warning"])
    print(f"\n  {warned}/{len(pre_signals)} 个回撤在前 5 天有可观测的预警信号：\n")
    for s in pre_signals:
        status = "⚠️ 有预警" if s["had_warning"] else "✓ 无预警"
        print(f"  {s['dd']} ({s['dd_pct']}%) | 前5天日均: {s['pre5_flow']:+.1f}亿 | 前10-5天: {s['pre10_5_flow']:+.1f}亿 | 负流: {s['neg_days']}/5天 | {status}")
        if s["flags"]:
            print(f"     → {' · '.join(s['flags'])}")

    # 检查所有交易日：前5天资金流向 vs 后一天涨跌
    print(f"\n  {'='*90}")
    print(f"  📋 全部交易日：前5天资金流 vs 次日策略涨跌")
    print(f"  {'='*90}")

    up_days = []; down_days = []
    for i in range(5, len(daily_records)):
        next_day_nav = daily_records[i]["nav"]
        today_nav = daily_records[i - 1]["nav"]
        ret = (next_day_nav / today_nav - 1) * 100
        prev_5d_flow = daily_records[i - 1]["idx_flow_5d"] / 1e8

        if ret > 0:
            up_days.append(prev_5d_flow)
        else:
            down_days.append(prev_5d_flow)

    print(f"\n  次日上涨({len(up_days)}天): 前5天指数资金流均值 = {sum(up_days)/len(up_days):+.1f}亿")
    print(f"  次日下跌({len(down_days)}天): 前5天指数资金流均值 = {sum(down_days)/len(down_days):+.1f}亿")

    # 按资金流分位统计次日涨跌概率
    flows_5d = [daily_records[i - 1]["idx_flow_5d"] / 1e8 for i in range(5, len(daily_records))]
    rets = [(daily_records[i]["nav"] / daily_records[i - 1]["nav"] - 1) * 100 for i in range(5, len(daily_records))]

    # 分三组
    sorted_flows = sorted(flows_5d)
    n = len(sorted_flows)
    low_thresh = sorted_flows[n // 3]
    high_thresh = sorted_flows[2 * n // 3]

    low_group = [rets[i] for i in range(len(rets)) if flows_5d[i] <= low_thresh]
    mid_group = [rets[i] for i in range(len(rets)) if low_thresh < flows_5d[i] <= high_thresh]
    high_group = [rets[i] for i in range(len(rets)) if flows_5d[i] > high_thresh]

    print(f"\n  按前5天指数资金流三分位:")
    print(f"  低位组(≤{low_thresh:.0f}亿): {len(low_group)}天, 次日均收益 {sum(low_group)/len(low_group):+.2f}%, 上涨概率 {sum(1 for r in low_group if r>0)/len(low_group)*100:.1f}%")
    print(f"  中位组({low_thresh:.0f}~{high_thresh:.0f}亿): {len(mid_group)}天, 次日均收益 {sum(mid_group)/len(mid_group):+.2f}%, 上涨概率 {sum(1 for r in mid_group if r>0)/len(mid_group)*100:.1f}%")
    print(f"  高位组(>{high_thresh:.0f}亿): {len(high_group)}天, 次日均收益 {sum(high_group)/len(high_group):+.2f}%, 上涨概率 {sum(1 for r in high_group if r>0)/len(high_group)*100:.1f}%")


if __name__ == "__main__":
    main()
