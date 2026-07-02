#!/usr/bin/env python3
"""
动量轮动 · 周频调仓回测 · 980080

策略：每周五从国证成长100成分股中按价格动量+成交量排名取 Top N，等权买入。
已在持仓且未跌出前 N 不动（省换手）。

用法：
    cd backend && source venv/bin/activate
    python TmpScriptsBackTest/backtest_momentum_rotation_rebalance.py
    python TmpScriptsBackTest/backtest_momentum_rotation_rebalance.py --top 5 10
    python TmpScriptsBackTest/backtest_momentum_rotation_rebalance.py --bt-start 2025-01-01
"""

from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import numpy as np
import psycopg2, psycopg2.extras
from dotenv import load_dotenv

_ENV_DIR = Path(__file__).resolve().parent.parent
for f in (".env", ".env.production"):
    p = _ENV_DIR / f
    if p.exists(): load_dotenv(p, override=True)

def _pg():
    u = os.getenv("DATABASE_URL","")
    if not u: u = f"postgresql://{os.getenv('DB_USER','aipicking')}:{os.getenv('DB_PASSWORD','')}@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}/{os.getenv('DB_NAME','aipicking')}"
    u = u.replace("+asyncpg","").replace("+psycopg2","")
    if "://" not in u: u = f"postgresql://{u}"
    r = urlparse(u)
    return psycopg2.connect(host=r.hostname or "localhost",port=r.port or 5432,user=r.username or "aipicking",password=r.password or "",dbname=r.path.lstrip("/") or "aipicking")

HOLIDAYS = {
    2025: {"0101","0128","0129","0130","0131","0203","0204","0404","0405","0406","0501","0502","0503","0504","0505","0531","0601","0602","1001","1002","1003","1004","1005","1006","1007","1008"},
    2026: {"0101","0217","0218","0219","0220","0221","0222","0223","0405","0406","0407","0501","0502","0503","0504","0505","0625","0626","0627","0929","0930","1001","1002","1003","1004","1005","1006","1007"},
}
ST, CM = 0.001, 0.0003
SELL_C = ST + CM; BUY_C = CM

def _td(d): return not (d.weekday()>=5 or d.strftime("%m%d") in HOLIDAYS.get(d.year,set()))

def gen_fridays(s, e):
    """Generate Friday rebalance dates, falling back to next trading day if holiday."""
    d = datetime.strptime(s,"%Y-%m-%d")
    while d.weekday()!=4: d+=timedelta(days=1)
    end = datetime.strptime(e,"%Y-%m-%d")
    out = []
    while d<=end:
        if _td(d): out.append(d.strftime("%Y-%m-%d"))
        else:
            nd=d+timedelta(days=1)
            for _ in range(7):
                if _td(nd): out.append(nd.strftime("%Y-%m-%d")); break
                nd+=timedelta(days=1)
        d+=timedelta(days=7)
    return out


def momentum_score(closes, vols, mom_fast=20, mom_slow=60, mom_fast_weight=0.6,
                   vol_short=5, vol_long=20):
    """Calculate raw momentum + volume scores for a single stock."""
    if len(closes) < max(mom_slow, vol_long):
        return None

    # Momentum
    ret_fast = (closes[-1] / closes[-mom_fast] - 1) * 100 if closes[-mom_fast] != 0 else 0
    ret_slow = (closes[-1] / closes[-mom_slow] - 1) * 100 if closes[-mom_slow] != 0 else 0
    mom_raw = mom_fast_weight * ret_fast + (1 - mom_fast_weight) * ret_slow

    # Volume ratio
    avg_short = np.mean(vols[-vol_short:])
    avg_long = np.mean(vols[-vol_long:])
    vol_ratio = avg_short / avg_long if avg_long > 0 else 1.0

    return mom_raw, vol_ratio


def run(top_n, index_code="980080", bt_start="2025-01-01", bt_end="2026-07-01",
        data_start="2024-09-01", data_end="2026-07-01",
        mom_fast=20, mom_slow=60, mom_fast_weight=0.6,
        vol_short=5, vol_long=20, volume_weight=0.4):
    """Run weekly rebalance backtest."""

    conn = _pg()
    cur = conn.cursor()

    # ── Stock pool: index constituents ──────────────────────
    cur.execute("SELECT ts_code FROM index_constituents WHERE index_code=%s", (index_code,))
    raw_set = {r[0].split(".")[0] for r in cur.fetchall()}
    print(f"指数 {index_code} 成分股: {len(raw_set)}")

    # ── Trading days ────────────────────────────────────────
    cur.execute("SELECT DISTINCT trade_date FROM daily WHERE trade_date>=%s AND trade_date<=%s ORDER BY trade_date",
                (data_start, data_end))
    all_td = [r[0] for r in cur.fetchall()]

    # ── Rebalance Fridays ───────────────────────────────────
    rebal_dates = gen_fridays(bt_start, bt_end)
    def nxt(tgt):
        for t in all_td:
            if t>=tgt: return t
        return None
    rebal_td_set = set()
    for rd in rebal_dates:
        nt = nxt(rd)
        if nt: rebal_td_set.add(nt)
    print(f"调仓日: {len(rebal_td_set)} 个")

    # ── Match constituents to actual stocks ─────────────────
    cur.execute("""
        SELECT DISTINCT s.ts_code FROM stocks s
        WHERE s.type='stock' AND s.name NOT LIKE '%%ST%%'
    """)
    all_stocks = {r[0] for r in cur.fetchall()}
    match_ts = sorted(t for t in all_stocks if t.split(".")[0] in raw_set)
    print(f"匹配股票: {len(match_ts)}")

    # ── Load daily OHLCV ────────────────────────────────────
    cur.execute("""
        SELECT ts_code, trade_date, open, high, low, close, vol
        FROM daily WHERE ts_code=ANY(%s) AND trade_date>=%s AND trade_date<=%s
        ORDER BY ts_code, trade_date
    """, (match_ts, data_start, data_end))

    # Build per-stock arrays
    from collections import defaultdict
    stock_data = defaultdict(lambda: {"dates": [], "opens": [], "highs": [], "lows": [], "closes": [], "vols": []})
    for ts, td, o, h, l, c, v in cur.fetchall():
        d = stock_data[ts]
        d["dates"].append(td)
        d["opens"].append(o)
        d["highs"].append(h)
        d["lows"].append(l)
        d["closes"].append(c)
        d["vols"].append(float(v or 0))

    # ── Price lookup (for NAV) ──────────────────────────────
    pr = {}
    for ts, sd in stock_data.items():
        for i, dt in enumerate(sd["dates"]):
            pr.setdefault(dt, {})[ts] = float(sd["closes"][i])

    # Forward-fill for suspended stocks
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

    # ── Index benchmark ─────────────────────────────────────
    idx_ts = f"{index_code}.SZ"
    cur.execute("SELECT trade_date, close FROM daily WHERE ts_code=%s AND trade_date>=%s AND trade_date<=%s ORDER BY trade_date",
                (idx_ts, data_start, data_end))
    idx_rows = cur.fetchall()
    if not idx_rows:
        # Try .SH
        cur.execute("SELECT trade_date, close FROM daily WHERE ts_code=%s AND trade_date>=%s AND trade_date<=%s ORDER BY trade_date",
                    (f"{index_code}.SH", data_start, data_end))
        idx_rows = cur.fetchall()
    idx_prices = {r[0]: float(r[1]) for r in idx_rows}
    print(f"指数基准数据: {len(idx_prices)} 条 (ts_code={idx_ts if idx_rows else f'{index_code}.SH'})")

    conn.close()

    # ── Portfolio simulation ────────────────────────────────
    INITIAL_CAPITAL = 1_000_000.0
    nav = INITIAL_CAPITAL
    cash = INITIAL_CAPITAL
    holdings = {}    # {ts_code: shares}
    cost_basis = {}  # {ts_code: price}
    points = []
    min_bars = max(mom_slow, vol_long)
    label = f"动量轮动 · {index_code} · Top {top_n} · 每周五"
    print(f"\n{'='*100}\n  {label}\n{'='*100}")
    print(f"{'日期':<12} {'净值':>12} {'周收益':>8} {'持仓':>5} {'保留':>5} {'卖出':>5} {'买入':>5} {'换手%':>7} {'费用':>8}")

    bt = [d for d in all_td if bt_start<=d<=bt_end]
    last_nav = INITIAL_CAPITAL

    for td in bt:
        px = pr.get(td, {})
        if not px: continue
        is_reb = td in rebal_td_set
        tradable = is_tradable.get(td, {})

        # NAV update
        sv = sum(holdings[c]*px.get(c,0) for c in holdings if px.get(c,0)>0)
        nav = sv + cash

        if not is_reb:
            if td == bt[-1]:
                points.append({"date": td, "nav": round(nav, 2)})
            continue

        # ── Score all stocks on this date ────────────────────
        scores = []
        for ts in match_ts:
            sd = stock_data[ts]
            # Find the index up to td
            if td not in sd["dates"]:
                continue
            idx = sd["dates"].index(td) + 1  # +1 because we want up to and including td
            if idx < min_bars:
                continue

            closes = np.array(sd["closes"][:idx], dtype=float)
            vols = np.array(sd["vols"][:idx], dtype=float)

            result = momentum_score(closes, vols, mom_fast, mom_slow, mom_fast_weight,
                                    vol_short, vol_long)
            if result is None:
                continue
            mom_raw, vol_ratio = result
            scores.append({"ts_code": ts, "mom_raw": mom_raw, "vol_ratio": vol_ratio})

        if not scores:
            continue

        # Z-score
        mom_arr = np.array([s["mom_raw"] for s in scores])
        vol_arr = np.array([s["vol_ratio"] for s in scores])
        mom_mean, mom_std = np.mean(mom_arr), np.std(mom_arr)
        vol_mean, vol_std = np.mean(vol_arr), np.std(vol_arr)

        for s in scores:
            mz = (s["mom_raw"] - mom_mean) / mom_std if mom_std > 0 else 0
            vz = (s["vol_ratio"] - vol_mean) / vol_std if vol_std > 0 else 0
            s["score"] = (1 - volume_weight) * mz + volume_weight * vz

        scores.sort(key=lambda x: x["score"], reverse=True)
        ranking = scores[:top_n]
        tgt = {s["ts_code"] for s in ranking}

        # ── Initial buy ──────────────────────────────────────
        if not holdings and cash > 0:
            tradable_ranking = [s for s in ranking if tradable.get(s["ts_code"])]
            if not tradable_ranking: continue
            n = len(tradable_ranking); w = 1.0 / n
            for s in tradable_ranking:
                p = px.get(s["ts_code"], 0)
                if p > 0:
                    holdings[s["ts_code"]] = (cash * w) / p
                    cost_basis[s["ts_code"]] = p
            cash = 0
            nav = sum(holdings[c]*px.get(c,0) for c in holdings)
            print(f"{td:<12} {nav:>12,.0f} {'—':>8} {len(holdings):>5} {'—':>5} {'—':>5} {len(holdings):>5} {'—':>7} {'—':>8}")
            points.append({"date": td, "nav": round(nav, 2)})
            last_nav = nav
            continue

        # ── Rebalance ────────────────────────────────────────
        old = set(holdings.keys())
        sell_c = old - tgt
        buy_c = tgt - old
        keep_c = old & tgt
        sold_today = 0

        # Sell removed
        sg = 0.0
        for c in list(sell_c):
            if not tradable.get(c):
                keep_c.add(c)
                continue
            p = px.get(c, 0)
            if p > 0: sg += holdings[c] * p
            del holdings[c]
            if c in cost_basis: del cost_basis[c]
            sold_today += 1
        cash += sg * (1 - SELL_C)

        # Buy new
        bct = 0.0
        actual_buys = [c for c in buy_c if tradable.get(c)]
        if actual_buys and cash > 0:
            ca = cash / len(actual_buys)
            for c in actual_buys:
                p = px.get(c, 0)
                if p > 0:
                    holdings[c] = (ca * (1 - BUY_C)) / p
                    cost_basis[c] = p
                    bct += ca * BUY_C
                    cash -= ca

        nav = sum(holdings[c]*px.get(c,0) for c in holdings if px.get(c,0)>0) + cash
        tv = sg + (cash + bct if actual_buys else 0)
        to = (tv / (sv + cash) * 100) if (sv + cash) > 0 else 0
        ct = sg * SELL_C + bct
        wr = (nav / last_nav - 1) * 100 if last_nav > 0 else 0

        print(f"{td:<12} {nav:>12,.0f} {wr:>7.2f}% {len(holdings):>5} {len(keep_c):>5} {sold_today:>5} {len(actual_buys):>5} {to:>6.1f}% {ct:>8.2f}")
        points.append({"date": td, "nav": round(nav, 2)})
        last_nav = nav

    tr = (nav / INITIAL_CAPITAL - 1) * 100
    print(f"\n  📊 结果: {bt[0]} ~ {bt[-1]}")
    print(f"  起始: {INITIAL_CAPITAL:,.0f} → 截止: {nav:,.0f}  |  总收益: {tr:+.2f}%  |  调仓: {len(points)-1} 次")

    # ── Index benchmark NAV ──────────────────────────────────
    bench_points = []
    if idx_prices:
        first_date = bt[0] if bt else None
        base_close = idx_prices.get(first_date) if first_date else None
        if not base_close and first_date:
            # find closest non-null
            for d in sorted(idx_prices.keys()):
                if d <= first_date:
                    base_close = idx_prices[d]
        if base_close and base_close > 0:
            for d in [p["date"] for p in points]:
                close = idx_prices.get(d)
                if close is not None and close > 0:
                    bench_points.append({
                        "date": d, "nav": round(INITIAL_CAPITAL * close / base_close, 2)
                    })
        if bench_points:
            bench_tr = (bench_points[-1]["nav"] / INITIAL_CAPITAL - 1) * 100
            idx_name = f"{index_code} 指数"
            print(f"  指数基准: {INITIAL_CAPITAL:,.0f} → {bench_points[-1]['nav']:,.0f}  |  总收益: {bench_tr:+.2f}%")

    return points, bench_points, idx_name if bench_points else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, nargs="*", default=[5, 10])
    p.add_argument("--index", type=str, default="980080")
    p.add_argument("--bt-start", type=str, default="2025-01-01")
    p.add_argument("--bt-end", type=str, default="2026-07-01")
    p.add_argument("--data-start", type=str, default="2024-09-01")
    p.add_argument("--data-end", type=str, default="2026-07-01")
    args = p.parse_args()

    CO = {5: '#ff6b6b', 10: '#6bcb77', 15: '#4ecdc4'}
    all_r = {}
    all_bench = {}
    idx_name = None

    for n in args.top:
        print(f"\n{'─'*60}\n  Top {n}\n{'─'*60}")
        pts, bench, name = run(n, args.index,
                               bt_start=args.bt_start, bt_end=args.bt_end,
                               data_start=args.data_start, data_end=args.data_end)
        all_r[str(n)] = pts
        if bench and not all_bench:
            all_bench = bench
            idx_name = name

    if len(all_r) <= 1:
        return

    dates = [pp["date"] for pp in list(all_r.values())[0]]
    series = []
    for n in args.top:
        k = str(n)
        if k in all_r:
            series.append({"name": f"Top {n}", "data": [pp["nav"] for pp in all_r[k]], "color": CO.get(n, '#aaa'), "dashed": False})

    # Add benchmark series
    if all_bench:
        series.append({"name": idx_name or "指数基准", "data": [pp["nav"] for pp in all_bench], "color": "#f0c040", "dashed": True})

    fns = {str(n): all_r[str(n)][-1]["nav"] for n in args.top}
    if all_bench:
        fns[idx_name] = all_bench[-1]["nav"]

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>动量轮动 · {args.index} · 周频</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#1a1a2e;font-family:-apple-system,sans-serif}}
.container{{max-width:1400px;margin:0 auto;padding:24px}}h1{{color:#e0e0e0;text-align:center;font-size:22px;margin-bottom:6px}}
.sub{{color:#888;text-align:center;font-size:13px;margin-bottom:20px}}#chart{{width:100%;height:700px;background:#16213e;border-radius:12px}}
.stats{{display:grid;grid-template-columns:repeat({len(fns)},1fr);gap:16px;margin-top:20px}}
.card{{background:#16213e;border-radius:10px;padding:20px;text-align:center}}.card h3{{color:#888;font-size:13px;font-weight:normal;margin-bottom:8px}}
.card .val{{font-size:32px;font-weight:bold}}.card .pct{{font-size:14px;margin-top:4px}}</style></head><body><div class="container">
<h1>动量轮动 · {args.index} · 每周五调仓 · 量价动量</h1>
<div class="sub">{args.bt_start[:7]} ~ {args.bt_end[:7]} · {len(dates)} 个周频数据点 · 同股不动 · 已扣交易费用 · 起始 100万</div>
<div id="chart"></div><div class="stats" id="stats"></div></div>
<script>var dates={json.dumps(dates)};var sd={json.dumps(series)};var fn={json.dumps(fns)};
var c=echarts.init(document.getElementById('chart'));
c.setOption({{color:sd.map(function(s){{return s.color}}),
tooltip:{{trigger:'axis',backgroundColor:'rgba(22,33,62,0.95)',borderColor:'#333',textStyle:{{color:'#e0e0e0',fontSize:13}},
formatter:function(p){{var s='<b>'+p[0].axisValue+'</b><br/>';p.forEach(function(x){{var pct=((x.value-1000000)/10000).toFixed(1);s+='<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:'+x.color+';margin-right:6px"></span>'+x.seriesName+': <b>'+x.value.toLocaleString()+'</b> ('+(pct>=0?'+':'')+pct+'%)<br/>'}});return s}}}},
legend:{{data:sd.map(function(s){{return s.name}}),top:10,textStyle:{{color:'#aaa',fontSize:14}},itemWidth:30,itemHeight:3}},
grid:{{left:80,right:40,top:60,bottom:40}},
xAxis:{{type:'category',data:dates,axisLine:{{lineStyle:{{color:'#333'}}}},axisLabel:{{color:'#888',fontSize:10,rotate:45,formatter:function(v){{return v.slice(5)}},interval:Math.floor(dates.length/25)}},splitLine:{{show:false}}}},
yAxis:{{type:'value',name:'净值',nameTextStyle:{{color:'#888',fontSize:12}},axisLabel:{{color:'#888',fontSize:12}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}}}},
series:sd.map(function(s){{return{{name:s.name,type:'line',data:s.data,smooth:true,symbol:'none',lineStyle:{{width:s.dashed?1.5:2,color:s.color,type:s.dashed?'dashed':'solid'}},itemStyle:{{color:s.color}}}}}})
}});
var ss=document.getElementById('stats');
Object.keys(fn).forEach(function(k){{var v=fn[k],p=((v-1000000)/10000).toFixed(1);var cl='#aaa';
if(k=='5')cl='#ff6b6b';else if(k=='10')cl='#6bcb77';else cl='#f0c040';
ss.innerHTML+='<div class="card"><h3>'+k+'</h3><div class="val" style="color:'+cl+'">'+v.toLocaleString()+'</div><div class="pct" style="color:'+cl+'">'+(p>=0?'+':'')+p+'%</div></div>'}});
window.addEventListener('resize',function(){{c.resize()}});</script></body></html>"""

    out = Path(__file__).resolve().parent / "backtest_momentum_rotation_rebalance.html"
    with open(out, 'w') as f: f.write(html)
    print(f"\n✅ HTML: {out}")


if __name__ == "__main__":
    main()
