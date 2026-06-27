#!/usr/bin/env python3
"""
grow_with_money · 选股因子分析
从「主力资金流分数」和「市值」两个维度分析选股质量：
- 分数越高 → 前向收益越高？
- 大市值 vs 小市值 → 胜率有差异？
- 分数 × 市值的交互效应？

用法：
    python TmpScriptsBackTest/backtest_grow_with_money_analysis.py
    python TmpScriptsBackTest/backtest_grow_with_money_analysis.py --index 980080 --top-k 20 --lookback 5
    python TmpScriptsBackTest/backtest_grow_with_money_analysis.py --bt-start 2025-06-01 --bt-end 2026-06-19 --data-start 2025-04-01 --data-end 2026-06-30
"""

from __future__ import annotations
import argparse, json, os, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
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
        host=r.hostname or "localhost", port=r.port or 5432,
        user=r.username or "aipicking", password=r.password or "",
        dbname=r.path.lstrip("/") or "aipicking",
    )


def load_data(index_code: str, data_start: str = "2024-12-01", data_end: str = "2026-06-30"):
    """Load all required data from DB. Returns (all_td, match_ts, pr, ff, mcaps, names)."""
    conn = _pg()
    cur = conn.cursor()

    # ── Trading days ────────────────────────────────────────────
    cur.execute(
        "SELECT DISTINCT trade_date FROM daily "
        "WHERE trade_date>=%s AND trade_date<=%s ORDER BY trade_date",
        (data_start, data_end),
    )
    all_td = [r[0] for r in cur.fetchall()]

    # ── Index constituents ──────────────────────────────────────
    cur.execute("SELECT ts_code FROM index_constituents WHERE index_code=%s", (index_code,))
    raw_set = {r[0] for r in cur.fetchall()}
    if not raw_set:
        print(f"❌ 指数 {index_code} 在 index_constituents 表中无数据")
        sys.exit(1)

    # ── Matching ts_codes (ST filtered) ────────────────────────
    cur.execute(
        """SELECT DISTINCT sff.ts_code FROM daily_stock_fund_flow sff
        JOIN stocks s ON s.ts_code=sff.ts_code
        WHERE sff.trade_date>=%s AND sff.trade_date<=%s
          AND s.type='stock' AND s.name NOT LIKE '%%ST%%'""",
        (data_start, data_end),
    )
    match_ts = [r[0] for r in cur.fetchall() if r[0].split(".")[0] in raw_set]
    print(f"  指数 {index_code}: {len(raw_set)} 成分股, {len(match_ts)} 只参与回测")

    # ── Stock names ─────────────────────────────────────────────
    cur.execute("SELECT ts_code, name FROM stocks WHERE ts_code=ANY(%s)", (match_ts,))
    names = {r[0]: r[1] for r in cur.fetchall()}

    # ── Prices ──────────────────────────────────────────────────
    cur.execute(
        "SELECT ts_code, trade_date, close FROM daily "
        "WHERE ts_code=ANY(%s) AND trade_date>=%s AND trade_date<=%s "
        "ORDER BY ts_code, trade_date",
        (match_ts, data_start, data_end),
    )
    pr: dict[str, dict[str, float]] = {}
    for c, d, v in cur.fetchall():
        pr.setdefault(d, {})[c] = v

    # Forward-fill prices
    last_px: dict[str, float] = {}
    for td_ in all_td:
        px_day = pr.get(td_, {})
        for c in match_ts:
            if c in px_day:
                last_px[c] = px_day[c]
            elif c in last_px:
                pr.setdefault(td_, {})[c] = last_px[c]

    # ── Float shares (for market cap = float_shares × close) ───
    cur.execute(
        "SELECT ts_code, float_shares FROM stocks WHERE ts_code=ANY(%s)",
        (match_ts,),
    )
    float_shares = {r[0]: float(r[1]) if r[1] else 0.0 for r in cur.fetchall()}
    # Compute market cap per stock per day on-the-fly: cap = float_shares × close

    # ── Fund flow ───────────────────────────────────────────────
    cur.execute(
        "SELECT ts_code, trade_date, main_net_flow FROM daily_stock_fund_flow "
        "WHERE ts_code=ANY(%s) AND trade_date>=%s AND trade_date<=%s",
        (match_ts, data_start, data_end),
    )
    ff: dict[str, dict[str, float]] = {}
    for c, d, v in cur.fetchall():
        ff.setdefault(d, {})[c] = float(v or 0)
    conn.close()

    return all_td, match_ts, pr, ff, float_shares, names


def forward_return(all_td, pr, ts_code, base_date, days):
    """Compute forward return: (price at base_date+days) / price at base_date - 1"""
    try:
        idx = all_td.index(base_date)
    except ValueError:
        return None
    fwd_idx = idx + days
    if fwd_idx >= len(all_td):
        return None
    fwd_date = all_td[fwd_idx]
    p0 = pr.get(base_date, {}).get(ts_code)
    p1 = pr.get(fwd_date, {}).get(ts_code)
    if p0 and p1 and p0 > 0:
        return (p1 / p0) - 1
    return None


def analyze(index_code: str = "980080", top_k: int = 20, lookback: int = 5,
            bt_start: str = "2025-01-01", bt_end: str = "2026-06-19",
            data_start: str = "2024-12-01", data_end: str = "2026-06-30"):
    all_td, match_ts, pr, ff, float_shares, names = load_data(index_code, data_start, data_end)

    bt = [d for d in all_td if bt_start <= d <= bt_end]
    print(f"  回测区间: {bt[0]} ~ {bt[-1]}, {len(bt)} 个交易日")

    # ── Collect picks + forward returns ──────────────────────────
    records = []  # [{date, rank, ts_code, name, score, cap, ret_1d, ret_5d, ret_20d}]

    for i, td in enumerate(bt):
        px = pr.get(td, {})
        if not px:
            continue

        # Compute ranking (same as strategy)
        idx = all_td.index(td)
        pre = all_td[max(0, idx - lookback + 1):idx + 1]
        if len(pre) < lookback:
            continue

        fs: dict[str, float] = {}
        for pd_ in pre:
            for c, v in ff.get(pd_, {}).items():
                fs[c] = fs.get(c, 0) + v
        ranking = sorted(
            [{"ts_code": k, "flow_m": v} for k, v in fs.items() if v > 0],
            key=lambda x: x["flow_m"], reverse=True,
        )[:top_k]
        if not ranking:
            continue

        for rank, s in enumerate(ranking, 1):
            code = s["ts_code"]
            score = s["flow_m"]
            cap = float_shares.get(code, 0) * px.get(code, 0) if float_shares.get(code, 0) > 0 else None
            records.append({
                "date": td,
                "rank": rank,
                "ts_code": code,
                "name": names.get(code, code),
                "score": score,
                "cap": cap,
                "ret_1d": forward_return(all_td, pr, code, td, 1),
                "ret_5d": forward_return(all_td, pr, code, td, 5),
                "ret_20d": forward_return(all_td, pr, code, td, 20),
            })

    print(f"  共收集 {len(records)} 条选股记录 ({len(bt)} 天 × Top {top_k})")

    # Count records with valid forward returns
    valid_1d = sum(1 for r in records if r["ret_1d"] is not None)
    valid_5d = sum(1 for r in records if r["ret_5d"] is not None)
    valid_20d = sum(1 for r in records if r["ret_20d"] is not None)
    cap_avail = sum(1 for r in records if r["cap"] is not None)
    print(f"  有效: 1d={valid_1d}, 5d={valid_5d}, 20d={valid_20d}, 市值={cap_avail}")

    return records, bt[0], bt[-1]


def quartile_analysis(records, col, col_label, ret_cols=("ret_1d", "ret_5d", "ret_20d")):
    """Group records by col quartile, compute stats."""
    valid = [r for r in records if r[col] is not None]
    if not valid:
        return None
    valid.sort(key=lambda x: x[col])
    n = len(valid)
    q_size = n // 4
    quartiles = []
    for q in range(4):
        start = q * q_size
        end = n if q == 3 else (q + 1) * q_size
        group = valid[start:end]
        val_min = group[0][col]
        val_max = group[-1][col]
        stats = {
            "label": f"Q{q+1}",
            "range": f"{fmt_num(val_min)} ~ {fmt_num(val_max)}",
            "count": len(group),
        }
        for rc in ret_cols:
            vals = [r[rc] for r in group if r[rc] is not None]
            if vals:
                stats[f"{rc}_avg"] = sum(vals) / len(vals)
                stats[f"{rc}_winrate"] = sum(1 for v in vals if v > 0) / len(vals)
                stats[f"{rc}_count"] = len(vals)
            else:
                stats[f"{rc}_avg"] = None
                stats[f"{rc}_winrate"] = None
                stats[f"{rc}_count"] = 0
        quartiles.append(stats)
    return quartiles


def fmt_num(v):
    if v is None:
        return "N/A"
    if abs(v) >= 1e8:
        return f"{v/1e8:.1f}亿"
    if abs(v) >= 1e4:
        return f"{v/1e4:.0f}万"
    if abs(v) >= 1000:
        return f"{v:.0f}"
    if abs(v) >= 1:
        return f"{v:.1f}"
    return f"{v:.4f}"


def fmt_pct(v):
    if v is None:
        return "N/A"
    return f"{v*100:+.2f}%"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--index", type=str, default="980080")
    p.add_argument("--top-k", type=int, default=20)
    p.add_argument("--lookback", type=int, default=5)
    p.add_argument("--bt-start", type=str, default="2025-01-01", help="回测起始日")
    p.add_argument("--bt-end", type=str, default="2026-06-19", help="回测截止日")
    p.add_argument("--data-start", type=str, default="2024-12-01", help="数据加载起始日")
    p.add_argument("--data-end", type=str, default="2026-06-30", help="数据加载截止日")
    args = p.parse_args()

    print(f"\n{'='*80}")
    print(f"  grow_with_money 选股因子分析 · {args.index} · Top {args.top_k} · M={args.lookback}")
    print(f"{'='*80}")

    records, start_date, end_date = analyze(args.index, args.top_k, args.lookback,
                                                 args.bt_start, args.bt_end,
                                                 args.data_start, args.data_end)

    # ── 1. Score Quartile Analysis ───────────────────────────────
    sq = quartile_analysis(records, "score", "主力净流入")
    print(f"\n{'─'*60}")
    print("  分数四分位分析（按累计主力净流入）")
    if sq:
        print(f"  {'分位':<6} {'范围':<24} {'样本':>6} {'1日均收益':>10} {'5日均收益':>10} {'20日均收益':>10} {'1日胜率':>8} {'5日胜率':>8}")
        for s in sq:
            print(f"  {s['label']:<6} {s['range']:<24} {s['count']:>6} "
                  f"{fmt_pct(s['ret_1d_avg']):>10} {fmt_pct(s['ret_5d_avg']):>10} {fmt_pct(s['ret_20d_avg']):>10} "
                  f"{s['ret_1d_winrate']*100:>7.1f}% {s['ret_5d_winrate']*100:>7.1f}%")

    # ── 2. Market Cap Quartile Analysis ──────────────────────────
    mq = quartile_analysis(records, "cap", "流通市值")
    print(f"\n{'─'*60}")
    print("  市值四分位分析（按流通市值）")
    if mq:
        print(f"  {'分位':<6} {'范围':<24} {'样本':>6} {'1日均收益':>10} {'5日均收益':>10} {'20日均收益':>10} {'1日胜率':>8} {'5日胜率':>8}")
        for s in mq:
            print(f"  {s['label']:<6} {s['range']:<24} {s['count']:>6} "
                  f"{fmt_pct(s['ret_1d_avg']):>10} {fmt_pct(s['ret_5d_avg']):>10} {fmt_pct(s['ret_20d_avg']):>10} "
                  f"{s['ret_1d_winrate']*100:>7.1f}% {s['ret_5d_winrate']*100:>7.1f}%")

    # ── 3. Score × Cap Interaction ───────────────────────────────
    # Build heatmap data
    valid_both = [r for r in records if r["score"] is not None and r["cap"] is not None]
    if valid_both:
        valid_both.sort(key=lambda x: x["score"])
        n = len(valid_both)
        qs = n // 4
        score_bins = [
            valid_both[0]["score"], valid_both[qs]["score"],
            valid_both[2*qs]["score"], valid_both[3*qs]["score"],
            valid_both[-1]["score"] + 1
        ]
        valid_both.sort(key=lambda x: x["cap"])
        cap_bins = [
            valid_both[0]["cap"], valid_both[qs]["cap"],
            valid_both[2*qs]["cap"], valid_both[3*qs]["cap"],
            valid_both[-1]["cap"] + 1
        ]
        heatmap = [[None] * 4 for _ in range(4)]
        heatmap_cnt = [[0] * 4 for _ in range(4)]
        for r in records:
            if r["score"] is None or r["cap"] is None or r["ret_5d"] is None:
                continue
            si = 3
            for j in range(1, 4):
                if r["score"] < score_bins[j]:
                    si = j - 1; break
            ci = 3
            for j in range(1, 4):
                if r["cap"] < cap_bins[j]:
                    ci = j - 1; break
            if heatmap[si][ci] is None:
                heatmap[si][ci] = []
            heatmap[si][ci].append(r["ret_5d"])
            heatmap_cnt[si][ci] += 1

        hm_data = []
        for si in range(4):
            for ci in range(4):
                vals = heatmap[si][ci]
                hm_data.append({
                    "score_q": si, "cap_q": ci,
                    "avg": sum(vals) / len(vals) if vals else 0,
                    "count": len(vals) if vals else 0,
                    "winrate": sum(1 for v in vals if v > 0) / len(vals) if vals else 0,
                })

    # ── Generate HTML Report ─────────────────────────────────────
    # Prepare series data
    # Scatter: score vs ret_5d
    scatter_points = []
    for r in records:
        if r["score"] is not None and r["ret_5d"] is not None:
            scatter_points.append({
                "x": r["score"],
                "y": round(r["ret_5d"] * 100, 2),
                "rank": r["rank"],
                "name": r["name"],
                "date": r["date"],
            })

    # Simple linear regression for score vs ret_5d
    if scatter_points:
        xs = [p["x"] for p in scatter_points]
        ys = [p["y"] for p in scatter_points]
        n_pts = len(xs)
        mx = sum(xs) / n_pts
        my = sum(ys) / n_pts
        num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n_pts))
        den = sum((x - mx) ** 2 for x in xs)
        slope = num / den if den else 0
        intercept = my - slope * mx
        r2 = (num / (den ** 0.5 * sum((y - my) ** 2 for y in ys) ** 0.5)) ** 2 if den else 0
        x1 = min(xs); x2 = max(xs)
        reg_line = [{"x": x1, "y": round(slope * x1 + intercept, 2)},
                     {"x": x2, "y": round(slope * x2 + intercept, 2)}]

    # Cap scatter
    cap_scatter = []
    for r in records:
        if r["cap"] is not None and r["ret_5d"] is not None and r["cap"] > 0:
            cap_scatter.append({
                "x": r["cap"],
                "y": round(r["ret_5d"] * 100, 2),
                "name": r["name"],
                "date": r["date"],
            })

    # Score decile bars
    valid_score = [r for r in records if r["score"] is not None and r["ret_5d"] is not None]
    valid_score.sort(key=lambda x: x["score"])
    n = len(valid_score)
    decile_size = n // 10
    decile_bars = []
    for d in range(10):
        start = d * decile_size
        end = n if d == 9 else (d + 1) * decile_size
        group = valid_score[start:end]
        rets = [r["ret_5d"] for r in group]
        decile_bars.append({
            "label": f"D{d+1}",
            "avg_ret": round(sum(rets) / len(rets) * 100, 3),
            "winrate": round(sum(1 for v in rets if v > 0) / len(rets) * 100, 1),
        })

    # Cap decile bars
    valid_cap = [r for r in records if r["cap"] is not None and r["ret_5d"] is not None and r["cap"] > 0]
    valid_cap.sort(key=lambda x: x["cap"])
    n = len(valid_cap)
    decile_size = n // 10
    cap_decile_bars = []
    for d in range(10):
        start = d * decile_size
        end = n if d == 9 else (d + 1) * decile_size
        group = valid_cap[start:end]
        rets = [r["ret_5d"] for r in group]
        cap_decile_bars.append({
            "label": f"D{d+1}",
            "avg_ret": round(sum(rets) / len(rets) * 100, 3),
            "winrate": round(sum(1 for v in rets if v > 0) / len(rets) * 100, 1),
        })

    # Quartile tables
    sq_json = json.dumps(sq or [], ensure_ascii=False)
    mq_json = json.dumps(mq or [], ensure_ascii=False)
    hm_json = json.dumps(hm_data, ensure_ascii=False)

    # Correlations
    corr_score_5d = None
    if scatter_points:
        xs = [p["x"] for p in scatter_points]
        ys = [p["y"] for p in scatter_points]
        n_pts = len(xs)
        mx = sum(xs) / n_pts
        my = sum(ys) / n_pts
        sdx = (sum((x - mx) ** 2 for x in xs) / n_pts) ** 0.5
        sdy = (sum((y - my) ** 2 for y in ys) / n_pts) ** 0.5
        if sdx > 0 and sdy > 0:
            corr_score_5d = sum((xs[i] - mx) * (ys[i] - my) for i in range(n_pts)) / (n_pts * sdx * sdy)

    corr_cap_5d = None
    if cap_scatter:
        xs = [p["x"] for p in cap_scatter]
        ys = [p["y"] for p in cap_scatter]
        n_pts = len(xs)
        mx = sum(xs) / n_pts
        my = sum(ys) / n_pts
        sdx = (sum((x - mx) ** 2 for x in xs) / n_pts) ** 0.5
        sdy = (sum((y - my) ** 2 for y in ys) / n_pts) ** 0.5
        if sdx > 0 and sdy > 0:
            corr_cap_5d = sum((xs[i] - mx) * (ys[i] - my) for i in range(n_pts)) / (n_pts * sdx * sdy)

    # Build rank-based average return (rank 1 vs rank 20)
    rank_stats = []
    for rk in range(1, args.top_k + 1):
        group = [r for r in records if r["rank"] == rk and r["ret_5d"] is not None]
        if group:
            rets = [r["ret_5d"] for r in group]
            rank_stats.append({
                "rank": rk,
                "avg_ret": round(sum(rets) / len(rets) * 100, 3),
                "winrate": round(sum(1 for v in rets if v > 0) / len(rets) * 100, 1),
            })

    idx_slug = args.index.replace(".", "_")
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>grow_with_money 因子分析 · {args.index}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#1a1a2e;font-family:-apple-system,sans-serif;color:#e0e0e0;padding:24px}}
.container{{max-width:1400px;margin:0 auto}}
h1{{text-align:center;font-size:22px;margin-bottom:4px}}
h2{{font-size:18px;margin:32px 0 12px;padding-bottom:8px;border-bottom:1px solid #333}}
.sub{{color:#888;text-align:center;font-size:13px;margin-bottom:24px}}
.row{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.chart{{width:100%;height:500px;background:#16213e;border-radius:12px}}
.chart-full{{width:100%;height:500px;background:#16213e;border-radius:12px;margin-bottom:20px}}
.stats-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
.stat-card{{background:#16213e;border-radius:10px;padding:16px;text-align:center}}
.stat-card .label{{color:#888;font-size:12px;margin-bottom:4px}}
.stat-card .val{{font-size:28px;font-weight:bold}}
.stat-card .sub{{color:#888;font-size:11px;margin-top:2px}}
table{{width:100%;border-collapse:collapse;margin:12px 0 24px;font-size:13px}}
th{{background:#1a3a5c;padding:10px 12px;text-align:center;font-weight:600}}
td{{padding:8px 12px;text-align:center;border-bottom:1px solid #222}}
tr:hover td{{background:rgba(255,255,255,0.03)}}
.pos{{color:#ff6b6b}} .neg{{color:#6bcb77}}
.insight{{background:#16213e;border-left:3px solid #ffd93d;padding:12px 16px;margin:16px 0;border-radius:0 8px 8px 0;font-size:14px;line-height:1.8}}
</style></head><body><div class="container">
<h1>grow_with_money 选股因子分析</h1>
<div class="sub">{args.index} · Top {args.top_k} · M={args.lookback} · {start_date} ~ {end_date} · {len(records)} 条选股记录 · 数据: {args.data_start}~{args.data_end}</div>

<div class="stats-grid">
<div class="stat-card"><div class="label">分数-收益相关性</div><div class="val" style="color:{'#ff6b6b' if (corr_score_5d or 0) > 0 else '#6bcb77'}">{corr_score_5d or 'N/A'}</div><div class="sub">Pearson r: score vs 5d ret</div></div>
<div class="stat-card"><div class="label">市值-收益相关性</div><div class="val" style="color:{'#ff6b6b' if (corr_cap_5d or 0) > 0 else '#6bcb77'}">{corr_cap_5d or 'N/A'}</div><div class="sub">Pearson r: cap vs 5d ret</div></div>
<div class="stat-card"><div class="label">R² (分数→收益)</div><div class="val">{r2:.4f}</div><div class="sub">线性回归决定系数</div></div>
<div class="stat-card"><div class="label">有效样本</div><div class="val">{len([r for r in records if r['ret_5d'] is not None])}</div><div class="sub">有5日前向收益</div></div>
</div>

<h2>一、主力资金流分数 vs 前向收益</h2>
<div class="chart-full" id="chart-score-scatter"></div>

<div class="row">
<div class="chart" id="chart-score-decile"></div>
<div class="chart" id="chart-rank-line"></div>
</div>

<div class="insight">
<strong>📊 解读</strong><br>
• <strong>散点图</strong>：每个点代表一次选股，X=累计主力净流入（分数），Y=5日前向收益（%）。红线为线性回归趋势线。<br>
• <strong>十分位柱状图</strong>：将选股按分数从低到高分成10组，D1=最低分，D10=最高分。柱高=组内平均5日收益。<br>
• <strong>排名折线</strong>：Rank 1=当日资金流入最强股，Rank 20=第20名。观察收益是否随排名下降而衰减。
</div>

<table>
<tr><th>分位</th><th>分数范围</th><th>样本</th><th>1日均收益</th><th>5日均收益</th><th>20日均收益</th><th>1日胜率</th><th>5日胜率</th></tr>
""" + "".join(
        f'<tr><td>{s["label"]}</td><td>{s["range"]}</td><td>{s["count"]}</td>'
        f'<td class="{"pos" if (s.get("ret_1d_avg") or 0) > 0 else "neg"}">{fmt_pct(s.get("ret_1d_avg"))}</td>'
        f'<td class="{"pos" if (s.get("ret_5d_avg") or 0) > 0 else "neg"}">{fmt_pct(s.get("ret_5d_avg"))}</td>'
        f'<td class="{"pos" if (s.get("ret_20d_avg") or 0) > 0 else "neg"}">{fmt_pct(s.get("ret_20d_avg"))}</td>'
        f'<td>{s.get("ret_1d_winrate", 0)*100:.1f}%</td>'
        f'<td>{s.get("ret_5d_winrate", 0)*100:.1f}%</td></tr>'
        for s in (sq or [])
    ) + """
</table>

<h2>二、市值 vs 前向收益</h2>
<div class="row">
<div class="chart" id="chart-cap-scatter"></div>
<div class="chart" id="chart-cap-decile"></div>
</div>

<div class="insight">
<strong>📊 解读</strong><br>
• <strong>市值散点图</strong>：X=流通市值（元），Y=5日前向收益（%）。观察市值大小与收益的分布关系。<br>
• <strong>市值十分位</strong>：D1=最小盘，D10=最大盘。看资金流策略在不同市值区间的有效性。
</div>

<table>
<tr><th>分位</th><th>市值范围</th><th>样本</th><th>1日均收益</th><th>5日均收益</th><th>20日均收益</th><th>1日胜率</th><th>5日胜率</th></tr>
""" + "".join(
        f'<tr><td>{s["label"]}</td><td>{s["range"]}</td><td>{s["count"]}</td>'
        f'<td class="{"pos" if (s.get("ret_1d_avg") or 0) > 0 else "neg"}">{fmt_pct(s.get("ret_1d_avg"))}</td>'
        f'<td class="{"pos" if (s.get("ret_5d_avg") or 0) > 0 else "neg"}">{fmt_pct(s.get("ret_5d_avg"))}</td>'
        f'<td class="{"pos" if (s.get("ret_20d_avg") or 0) > 0 else "neg"}">{fmt_pct(s.get("ret_20d_avg"))}</td>'
        f'<td>{s.get("ret_1d_winrate", 0)*100:.1f}%</td>'
        f'<td>{s.get("ret_5d_winrate", 0)*100:.1f}%</td></tr>'
        for s in (mq or [])
    ) + """
</table>

<h2>三、分数 × 市值 交互效应</h2>
<div class="chart-full" id="chart-heatmap"></div>
<div class="insight">
<strong>📊 解读</strong><br>
• <strong>热力图</strong>：行=分数四分位（Q1低分→Q4高分），列=市值四分位（Q1小盘→Q4大盘）。颜色越红=5日均收益越高。<br>
• 如果热力图右上角（高分+大盘）或左上角（高分+小盘）有明显的红色聚集，说明存在交互效应。
</div>

</div>

<script>
var c_ss = echarts.init(document.getElementById('chart-score-scatter'));
c_ss.setOption({
    tooltip: {{trigger:'item',formatter:function(p){{return p.data.name+'<br/>'+p.data.date+'<br/>分数: '+p.data[0].toFixed(0)+'<br/>5日收益: '+p.data[1].toFixed(2)+'%'}}}},
    grid: {{left:80,right:40,top:20,bottom:50}},
    xAxis: {{type:'value',name:'累计主力净流入',nameTextStyle:{{color:'#888'}},axisLabel:{{color:'#888',formatter:function(v){{return (v/1e4).toFixed(0)+'万'}}}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}}}},
    yAxis: {{type:'value',name:'5日前向收益 (%)',nameTextStyle:{{color:'#888'}},axisLabel:{{color:'#888',formatter:function(v){{return v.toFixed(0)+'%'}}}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}}}},
    series: [
        {{type:'scatter',data:{json.dumps([[p["x"],p["y"]] for p in scatter_points])},symbolSize:4,itemStyle:{{color:'rgba(100,180,255,0.4)'}}}},
        {{type:'line',data:{json.dumps([[p["x"],p["y"]] for p in reg_line])},lineStyle:{{color:'#ff6b6b',width:2,type:'solid'}},symbol:'none',name:'趋势线'}}
    ]
}});

var c_sd = echarts.init(document.getElementById('chart-score-decile'));
c_sd.setOption({{
    tooltip: {{trigger:'axis'}},
    grid: {{left:50,right:50,top:20,bottom:40}},
    xAxis: {{type:'category',data:{json.dumps([d["label"] for d in decile_bars])},axisLabel:{{color:'#888'}}}},
    yAxis: {{type:'value',name:'5日均收益 (%)',nameTextStyle:{{color:'#888'}},axisLabel:{{color:'#888',formatter:function(v){{return v.toFixed(1)+'%'}}}}}},
    series: [
        {{type:'bar',data:{json.dumps([d["avg_ret"] for d in decile_bars])},
         itemStyle:{{color:function(p){{return p.value>=0?'#ff6b6b':'#6bcb77'}}}},
         markLine:{{silent:true,symbol:'none',lineStyle:{{color:'#666',type:'dashed'}},data:[{{yAxis:0}}]}}}}
    ]
}});

var c_rank = echarts.init(document.getElementById('chart-rank-line'));
c_rank.setOption({{
    tooltip: {{trigger:'axis'}},
    grid: {{left:50,right:50,top:20,bottom:40}},
    xAxis: {{type:'category',data:{json.dumps([r["rank"] for r in rank_stats])},name:'排名',nameTextStyle:{{color:'#888'}},axisLabel:{{color:'#888'}}}},
    yAxis: {{type:'value',name:'5日均收益 (%)',nameTextStyle:{{color:'#888'}},axisLabel:{{color:'#888',formatter:function(v){{return v.toFixed(1)+'%'}}}}}},
    series: [
        {{type:'line',data:{json.dumps([r["avg_ret"] for r in rank_stats])},smooth:true,lineStyle:{{color:'#ffd93d',width:2}},symbol:'circle',symbolSize:4,itemStyle:{{color:'#ffd93d'}},name:'平均收益'}},
        {{type:'line',data:{json.dumps([r["winrate"] for r in rank_stats])},smooth:true,lineStyle:{{color:'#6bcb77',width:2}},symbol:'diamond',symbolSize:4,itemStyle:{{color:'#6bcb77'}},name:'胜率 (%)'}}
    ]
}});

var c_cs = echarts.init(document.getElementById('chart-cap-scatter'));
c_cs.setOption({
    tooltip: {{trigger:'item',formatter:function(p){{return p.data.name+'<br/>'+p.data.date+'<br/>市值: '+(p.data[0]/1e8).toFixed(1)+'亿<br/>5日收益: '+p.data[1].toFixed(2)+'%'}}}},
    grid: {{left:80,right:40,top:20,bottom:50}},
    xAxis: {{type:'value',name:'流通市值',nameTextStyle:{{color:'#888'}},axisLabel:{{color:'#888',formatter:function(v){{return (v/1e8).toFixed(0)+'亿'}}}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}}}},
    yAxis: {{type:'value',name:'5日前向收益 (%)',nameTextStyle:{{color:'#888'}},axisLabel:{{color:'#888',formatter:function(v){{return v.toFixed(0)+'%'}}}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}}}},
    series: [{{type:'scatter',data:{json.dumps([[p["x"],p["y"]] for p in cap_scatter])},symbolSize:4,itemStyle:{{color:'rgba(255,180,100,0.4)'}}}}]
}});

var c_cd = echarts.init(document.getElementById('chart-cap-decile'));
c_cd.setOption({{
    tooltip: {{trigger:'axis'}},
    grid: {{left:50,right:50,top:20,bottom:40}},
    xAxis: {{type:'category',data:{json.dumps([d["label"] for d in cap_decile_bars])},axisLabel:{{color:'#888'}}}},
    yAxis: {{type:'value',name:'5日均收益 (%)',nameTextStyle:{{color:'#888'}},axisLabel:{{color:'#888',formatter:function(v){{return v.toFixed(1)+'%'}}}}}},
    series: [
        {{type:'bar',data:{json.dumps([d["avg_ret"] for d in cap_decile_bars])},
         itemStyle:{{color:function(p){{return p.value>=0?'#ff6b6b':'#6bcb77'}}}},
         markLine:{{silent:true,symbol:'none',lineStyle:{{color:'#666',type:'dashed'}},data:[{{yAxis:0}}]}}}}
    ]
}});

var c_hm = echarts.init(document.getElementById('chart-heatmap'));
var hm_data = {json.dumps(hm_data)};
c_hm.setOption({{
    tooltip: {{trigger:'item',formatter:function(p){{return '分数 '+['Q1','Q2','Q3','Q4'][p.data[0]]+' × 市值 '+['Q1','Q2','Q3','Q4'][p.data[1]]+'<br/>5日均收益: '+(p.data[2]*100).toFixed(2)+'%<br/>胜率: '+(p.data[3]*100).toFixed(1)+'%<br/>样本: '+p.data[4]}}}},
    grid: {{left:100,right:80,top:20,bottom:40}},
    xAxis: {{type:'category',data:['Q1 小盘','Q2 中小盘','Q3 中大盘','Q4 大盘'],position:'top',axisLabel:{{color:'#888',fontSize:13}}}},
    yAxis: {{type:'category',data:['Q4 高分','Q3 中高分','Q2 中低分','Q1 低分'],axisLabel:{{color:'#888',fontSize:13}}}},
    visualMap: {{min:-3,max:3,calculable:true,orient:'vertical',right:0,top:'center',inRange:{{color:['#6bcb77','#222','#ff6b6b']}},text:['高','低'],textStyle:{{color:'#888'}}}},
    series: [{{
        type:'heatmap',
        data: hm_data.map(function(d){{return [d.cap_q, d.score_q, Math.max(-5, Math.min(5, d.avg*100))]}}),
        label: {{show:true,formatter:function(p){{var d=hm_data[p.data[0]*4+p.data[1]];return (d.avg*100).toFixed(2)+'%\\n'+d.count+'个'}},fontSize:13,color:'#e0e0e0'}},
        emphasis: {{itemStyle:{{shadowBlur:10,shadowColor:'rgba(0,0,0,0.5)'}}}}
    }}]
}});

window.addEventListener('resize',function(){{c_ss.resize();c_sd.resize();c_rank.resize();c_cs.resize();c_cd.resize();c_hm.resize()}});
</script></body></html>"""

    out = Path(__file__).resolve().parent / f"backtest_grow_with_money_{idx_slug}_analysis.html"
    with open(out, "w") as f:
        f.write(html)
    print(f"\n✅ 分析报告: {out}")


if __name__ == "__main__":
    main()
