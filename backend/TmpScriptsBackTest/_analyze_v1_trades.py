#!/usr/bin/env python3
"""M=5 Top3 V1 (T+1 开盘) 逐笔交易分析 · 2026 · 分数 vs 收益率"""
from __future__ import annotations
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2, os
from urllib.parse import urlparse
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

ST, CM = 0.001, 0.0003
SELL_C = ST+CM; BUY_C = CM
INDEX = "980080"
LOOKBACK = 5
TOP_N = 3
BT_START, BT_END = "2026-01-01", "2026-06-26"
DATA_START, DATA_END = "2025-11-01", "2026-06-27"

conn = _pg(); cur = conn.cursor()

cur.execute("SELECT ts_code FROM index_constituents WHERE index_code=%s", (INDEX,))
raw_set = {r[0] for r in cur.fetchall()}

cur.execute("SELECT DISTINCT trade_date FROM daily WHERE trade_date>=%s AND trade_date<=%s ORDER BY trade_date", (DATA_START, DATA_END))
all_td = [r[0] for r in cur.fetchall()]

cur.execute("""SELECT DISTINCT sff.ts_code FROM daily_stock_fund_flow sff
    JOIN stocks s ON s.ts_code=sff.ts_code
    WHERE sff.trade_date>=%s AND sff.trade_date<=%s
    AND s.type='stock' AND s.name NOT LIKE '%%ST%%'""", (DATA_START, DATA_END))
match_ts = [r[0] for r in cur.fetchall() if r[0].split(".")[0] in raw_set]

# Prices
cur.execute("SELECT ts_code,trade_date,open,close FROM daily WHERE ts_code=ANY(%s) AND trade_date>=%s AND trade_date<=%s ORDER BY ts_code,trade_date",
            (match_ts, DATA_START, DATA_END))
pr = {}; pr_open = {}
for c,d,o,v in cur.fetchall():
    pr.setdefault(d,{})[c]=v
    pr_open.setdefault(d,{})[c]=o

# Forward-fill close
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

# Forward-fill open
last_open = {}
for td_ in all_td:
    op_day = pr_open.get(td_, {})
    for c in match_ts:
        if c in op_day: last_open[c] = op_day[c]
        elif c in last_open: pr_open.setdefault(td_, {})[c] = last_open[c]

# Fund flow
cur.execute("SELECT ts_code,trade_date,main_net_flow FROM daily_stock_fund_flow WHERE ts_code=ANY(%s) AND trade_date>=%s AND trade_date<=%s",
            (match_ts, DATA_START, DATA_END))
ff = {}
for c,d,v in cur.fetchall(): ff.setdefault(d,{})[c]=float(v or 0)

# Names
cur.execute("SELECT ts_code, name FROM stocks WHERE ts_code=ANY(%s)", (match_ts,))
names = {r[0]: r[1] for r in cur.fetchall()}
conn.close()

bt = [d for d in all_td if BT_START<=d<=BT_END]
nav, cash = 1000.0, 0.0
holdings = {}; cost_basis = {}; entry_score = {}; entry_date = {}
trades = []  # {entry_date, exit_date, ts_code, name, score, buy_px, sell_px, ret, win}
pending_ranking = None

for i, td in enumerate(bt):
    px_close = pr.get(td, {}); px_open = pr_open.get(td, {})
    tradable = is_tradable.get(td, {})

    # ── Execute at today's open ──────────────────────────
    if pending_ranking is not None:
        tgt = {s["ts_code"]: s["flow_m"] for s in pending_ranking}
        tgt_set = set(tgt.keys())

        if not holdings:
            tradable_ranking = [(s["ts_code"], s["flow_m"]) for s in pending_ranking
                                if tradable.get(s["ts_code"]) and px_open.get(s["ts_code"], 0) > 0]
            if tradable_ranking:
                n = len(tradable_ranking); w = 1.0/n
                for code, sc in tradable_ranking:
                    p = px_open[code]
                    holdings[code] = (1000.0 * w * (1 - BUY_C)) / p
                    cost_basis[code] = p
                    entry_score[code] = sc
                    entry_date[code] = td
                cash = 0
        else:
            old = set(holdings.keys())
            sell_c = old - tgt_set; buy_c = tgt_set - old

            sg = 0
            for c in list(sell_c):
                if not tradable.get(c): continue
                p = px_open.get(c, 0)
                if p > 0:
                    ret = (p / cost_basis[c] - 1) * (1 - SELL_C)  # net return after fees
                    trades.append({
                        "entry_date": entry_date[c], "exit_date": td,
                        "ts_code": c, "name": names.get(c, c),
                        "score": entry_score[c],
                        "buy_px": cost_basis[c], "sell_px": p,
                        "ret": ret, "win": ret > 0,
                    })
                    sg += holdings[c] * p
                    del holdings[c], cost_basis[c], entry_score[c], entry_date[c]
            cash += sg * (1 - SELL_C)

            bct = 0.0
            actual_buys = [c for c in buy_c if tradable.get(c) and px_open.get(c, 0) > 0]
            if actual_buys and cash > 0:
                ca = cash / len(actual_buys)
                for c in actual_buys:
                    p = px_open[c]
                    holdings[c] = (ca * (1 - BUY_C)) / p
                    cost_basis[c] = p
                    entry_score[c] = tgt[c]
                    entry_date[c] = td
                    bct += ca * BUY_C; cash -= ca
            cash -= bct  # deduct buy fees from cash

    # NAV
    sv = sum(holdings[c] * px_close.get(c, 0) for c in holdings if px_close.get(c, 0) > 0)
    nav = sv + cash

    # Ranking
    idx = all_td.index(td)
    pre = all_td[max(0, idx - LOOKBACK + 1):idx + 1]
    if len(pre) >= LOOKBACK:
        fs = {}
        for pd_ in pre:
            for c, v in ff.get(pd_, {}).items(): fs[c] = fs.get(c, 0) + v
        pending_ranking = sorted(
            [{"ts_code": k, "flow_m": v} for k, v in fs.items() if v > 0],
            key=lambda x: x["flow_m"], reverse=True)[:TOP_N]

# Close remaining positions at last day's close
for c in list(holdings.keys()):
    p = pr.get(bt[-1], {}).get(c, cost_basis.get(c, 0))
    if p > 0:
        ret = (p / cost_basis[c] - 1) * (1 - SELL_C)
        trades.append({
            "entry_date": entry_date[c], "exit_date": bt[-1],
            "ts_code": c, "name": names.get(c, c),
            "score": entry_score[c],
            "buy_px": cost_basis[c], "sell_px": p,
            "ret": ret, "win": ret > 0,
        })

print(f"总交易: {len(trades)} 笔, 胜率: {sum(1 for t in trades if t['win'])/len(trades)*100:.1f}%")
print(f"平均收益: {sum(t['ret'] for t in trades)/len(trades)*100:+.2f}%")
print(f"最大盈利: {max(t['ret'] for t in trades)*100:+.2f}%, 最大亏损: {min(t['ret'] for t in trades)*100:+.2f}%")

# ── Score decile analysis ─────────────────────────────
trades.sort(key=lambda t: t["score"])
n = len(trades); ds = n // 5
score_groups = []
for d in range(5):
    start = d * ds; end = n if d == 4 else (d + 1) * ds
    group = trades[start:end]
    rets = [t["ret"] for t in group]
    score_groups.append({
        "label": f"D{d+1}",
        "range": f"{group[0]['score']/1e4:.0f}万 ~ {group[-1]['score']/1e4:.0f}万",
        "count": len(group),
        "avg_ret": sum(rets) / len(rets) * 100,
        "winrate": sum(1 for r in rets if r > 0) / len(rets) * 100,
    })

print(f"\n分数五分位分析:")
print(f"{'分位':<6} {'分数范围':<28} {'笔数':>5} {'平均收益':>10} {'胜率':>8}")
for g in score_groups:
    print(f"{g['label']:<6} {g['range']:<28} {g['count']:>5} {g['avg_ret']:>9.2f}% {g['winrate']:>7.1f}%")

# ── Scatter data ──────────────────────────────────────
scatter = [{"x": t["score"], "y": round(t["ret"] * 100, 2),
            "name": t["name"], "entry": t["entry_date"], "exit": t["exit_date"],
            "win": t["win"]} for t in trades]

# ── Score distribution histogram ──────────────────────
all_scores = [t["score"] for t in trades]
score_min, score_max = min(all_scores), max(all_scores)
bin_count = 20; bin_w = (score_max - score_min) / bin_count
bins = []
for b in range(bin_count):
    lo = score_min + b * bin_w; hi = lo + bin_w
    group = [t for t in trades if lo <= t["score"] < hi]
    if group:
        rets = [t["ret"] for t in group]
        bins.append({"lo": lo, "hi": hi, "count": len(group),
                     "avg_ret": sum(rets)/len(rets)*100,
                     "winrate": sum(1 for r in rets if r>0)/len(rets)*100})

# ── HTML ──────────────────────────────────────────────
html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>M=5 Top3 V1 · 2026 · 逐笔交易分析</title>
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
</style></head><body><div class="container">
<h1>M=5 Top3 V1 (T+1 开盘) · 2026 逐笔交易分析</h1>
<div class="sub">{INDEX} · {BT_START} ~ {BT_END} · {len(trades)} 笔交易 · 平均收益 {sum(t['ret'] for t in trades)/len(trades)*100:+.2f}% · 胜率 {sum(1 for t in trades if t['win'])/len(trades)*100:.1f}%</div>

<div class="stats-grid">
<div class="stat-card"><div class="label">总交易笔数</div><div class="val">{len(trades)}</div></div>
<div class="stat-card"><div class="label">胜率</div><div class="val" style="color:{'#ff6b6b' if sum(1 for t in trades if t['win'])/len(trades)>.5 else '#6bcb77'}">{sum(1 for t in trades if t['win'])/len(trades)*100:.1f}%</div></div>
<div class="stat-card"><div class="label">平均收益</div><div class="val" style="color:{'#ff6b6b' if sum(t['ret'] for t in trades)/len(trades)>0 else '#6bcb77'}">{sum(t['ret'] for t in trades)/len(trades)*100:+.2f}%</div></div>
<div class="stat-card"><div class="label">盈亏比</div><div class="val">{sum(t['ret'] for t in trades if t['win'])/max(1,sum(1 for t in trades if t['win']))*100:.1f}% / {sum(t['ret'] for t in trades if not t['win'])/max(1,sum(1 for t in trades if not t['win']))*100:.1f}%</div></div>
</div>

<h2>一、分数 vs 收益率 散点图</h2>
<div class="chart-full" id="chart-scatter"></div>

<h2>二、分数五分位 收益 & 胜率</h2>
<div class="row">
<div class="chart" id="chart-decile-bar"></div>
<div class="chart" id="chart-decile-winrate"></div>
</div>

<h2>三、分数分布直方图（含各区间平均收益）</h2>
<div class="chart-full" id="chart-hist"></div>

<table>
<tr><th>分位</th><th>分数范围</th><th>笔数</th><th>平均收益</th><th>胜率</th></tr>
{"".join(f'<tr><td>{g["label"]}</td><td>{g["range"]}</td><td>{g["count"]}</td><td class="{"pos" if g["avg_ret"]>0 else "neg"}">{g["avg_ret"]:+.2f}%</td><td>{g["winrate"]:.1f}%</td></tr>' for g in score_groups)}
</table>

</div>
<script>
// Scatter
var c1 = echarts.init(document.getElementById('chart-scatter'));
c1.setOption({{
    tooltip: {{trigger:'item',formatter:function(p){{return p.data.name+'<br/>入场: '+p.data.entry+'<br/>出场: '+p.data.exit+'<br/>分数: '+(p.data[0]/1e4).toFixed(0)+'万<br/>收益: '+p.data[1].toFixed(2)+'%'}}}},
    grid: {{left:80,right:40,top:20,bottom:50}},
    xAxis: {{type:'value',name:'累计主力净流入 (万)',nameTextStyle:{{color:'#888'}},axisLabel:{{color:'#888',formatter:function(v){{return (v/1e4).toFixed(0)}}}}}},
    yAxis: {{type:'value',name:'收益率 (%)',nameTextStyle:{{color:'#888'}},axisLabel:{{color:'#888',formatter:function(v){{return v.toFixed(0)+'%'}}}}}},
    series: [{{
        type:'scatter',
        data:{json.dumps([[t["x"], t["y"]] for t in scatter])},
        symbolSize: function(data) {{ return Math.max(6, Math.min(16, Math.abs(data[1]) * 2 + 4)); }},
        itemStyle: {{color: function(p) {{ return (p.data[1]>=0 ? 'rgba(255,107,107,0.7)' : 'rgba(107,203,119,0.7)'); }}}},
    }}]
}});

// Decile bar
var c2 = echarts.init(document.getElementById('chart-decile-bar'));
c2.setOption({{
    tooltip: {{trigger:'axis'}},
    grid: {{left:50,right:40,top:20,bottom:40}},
    xAxis: {{type:'category',data:{json.dumps([g["label"] for g in score_groups])},axisLabel:{{color:'#888'}},name:'分数分位 (D1=最低,D5=最高)',nameTextStyle:{{color:'#888'}}}},
    yAxis: {{type:'value',name:'平均收益 (%)',nameTextStyle:{{color:'#888'}},axisLabel:{{color:'#888',formatter:function(v){{return v.toFixed(1)+'%'}}}}}},
    series: [{{
        type:'bar', data:{json.dumps([round(g["avg_ret"], 2) for g in score_groups])},
        itemStyle: {{color: function(p) {{ return p.value>=0 ? '#ff6b6b' : '#6bcb77'; }}}},
        markLine: {{silent:true,symbol:'none',lineStyle:{{color:'#666',type:'dashed'}},data:[{{yAxis:0}}]}}
    }}]
}});

// Winrate line
var c3 = echarts.init(document.getElementById('chart-decile-winrate'));
c3.setOption({{
    tooltip: {{trigger:'axis'}},
    grid: {{left:50,right:40,top:20,bottom:40}},
    xAxis: {{type:'category',data:{json.dumps([g["label"] for g in score_groups])},axisLabel:{{color:'#888'}},name:'分数分位',nameTextStyle:{{color:'#888'}}}},
    yAxis: {{type:'value',name:'胜率 (%)',nameTextStyle:{{color:'#888'}},axisLabel:{{color:'#888',formatter:function(v){{return v.toFixed(0)+'%'}}}},min:0,max:100}},
    series: [{{
        type:'line', data:{json.dumps([g["winrate"] for g in score_groups])}, smooth:true,
        lineStyle: {{color:'#ffd93d',width:2}}, symbol:'circle', symbolSize:8, itemStyle:{{color:'#ffd93d'}},
        markLine: {{silent:true,symbol:'none',lineStyle:{{color:'#666',type:'dashed'}},data:[{{yAxis:50,label:{{formatter:'50%',color:'#888'}}}}]}}
    }}]
}});

// Histogram
var c4 = echarts.init(document.getElementById('chart-hist'));
c4.setOption({{
    tooltip: {{trigger:'axis',formatter:function(p){{var d=p[0].data;return '分数: '+(d[0]/1e4).toFixed(0)+'万 ~ '+(d[1]/1e4).toFixed(0)+'万<br/>笔数: '+d[2]+'<br/>平均收益: '+d[3].toFixed(2)+'%<br/>胜率: '+d[4].toFixed(1)+'%'}}}},
    grid: {{left:60,right:40,top:20,bottom:50}},
    xAxis: {{type:'category',data:{json.dumps([f"{(b['lo']/1e4):.0f}万" for b in bins])},axisLabel:{{color:'#888',rotate:45,fontSize:10}},name:'分数区间',nameTextStyle:{{color:'#888'}}}},
    yAxis: {{type:'value',name:'笔数',nameTextStyle:{{color:'#888'}},axisLabel:{{color:'#888'}}}},
    series: [{{
        type:'bar',
        data:{json.dumps([[b["lo"], b["hi"], b["count"], round(b["avg_ret"], 2), round(b["winrate"], 1)] for b in bins])},
        itemStyle: {{color: function(p) {{ var avg = p.data[3]; return avg>=0 ? 'rgba(255,107,107,0.7)' : 'rgba(107,203,119,0.7)'; }}}},
    }}]
}});

window.addEventListener('resize',function(){{c1.resize();c2.resize();c3.resize();c4.resize()}});
</script></body></html>"""

out = Path(__file__).resolve().parent / "backtest_grow_with_money_980080_v1_trade_analysis.html"
with open(out, 'w') as f: f.write(html)
print(f"\n✅ {out}")
