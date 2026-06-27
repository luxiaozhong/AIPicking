#!/usr/bin/env python3
"""
grow_with_money · 每日调仓回测 · T+1 开盘 + 最低分数过滤（V2）

与 V1 的区别：增加 --min-score 参数，低于指定分数的股票不买入。
其余同 V1：T+1 开盘价成交。

策略：每个交易日从指数成分股中按过去 M 日主力净流入排名取 Top N，
等权买入。已在持仓且未跌出前 N 不动（省换手）。

支持 --stop-loss：每日检查，个股跌破成本价 -8% 则止损卖出。
支持 --min-score：最低主力净流入（万），低于此值不买入。

用法：
    python TmpScriptsBackTest/backtest_grow_with_money_daily_v2.py
    python TmpScriptsBackTest/backtest_grow_with_money_daily_v2.py --top 3 5 --min-score 50000
    python TmpScriptsBackTest/backtest_grow_with_money_daily_v2.py --bt-start 2025-06-01 --data-start 2025-04-01
"""

from __future__ import annotations
import argparse, json, os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import psycopg2
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

def run(top_n, lookback, index_code="980080", stop_loss_pct=0,
        bt_start="2025-01-01", bt_end="2026-06-19",
        data_start="2024-12-01", data_end="2026-06-30",
        min_score=0):
    conn = _pg(); cur = conn.cursor()

    cur.execute("SELECT ts_code FROM index_constituents WHERE index_code=%s", (index_code,))
    raw_set = {r[0] for r in cur.fetchall()}

    cur.execute("SELECT DISTINCT trade_date FROM daily WHERE trade_date>=%s AND trade_date<=%s ORDER BY trade_date",
                (data_start, data_end))
    all_td = [r[0] for r in cur.fetchall()]

    cur.execute("""SELECT DISTINCT sff.ts_code FROM daily_stock_fund_flow sff
        JOIN stocks s ON s.ts_code=sff.ts_code
        WHERE sff.trade_date>=%s AND sff.trade_date<=%s
        AND s.type='stock' AND s.name NOT LIKE '%%ST%%'""",
        (data_start, data_end))
    match_ts = [r[0] for r in cur.fetchall() if r[0].split(".")[0] in raw_set]

    # ── Load close + open prices ──────────────────────────────
    cur.execute(
        "SELECT ts_code,trade_date,open,close FROM daily "
        "WHERE ts_code=ANY(%s) AND trade_date>=%s AND trade_date<=%s "
        "ORDER BY ts_code,trade_date",
        (match_ts, data_start, data_end))
    pr = {}; pr_open = {}
    for c,d,o,v in cur.fetchall():
        pr.setdefault(d,{})[c]=v
        pr_open.setdefault(d,{})[c]=o

    # ── Forward-fill close + tradability ──────────────────────
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

    # ── Forward-fill open prices ──────────────────────────────
    last_open = {}
    for td_ in all_td:
        op_day = pr_open.get(td_, {})
        for c in match_ts:
            if c in op_day:
                last_open[c] = op_day[c]
            elif c in last_open:
                pr_open.setdefault(td_, {})[c] = last_open[c]

    # ── Fund flow ─────────────────────────────────────────────
    cur.execute(
        "SELECT ts_code,trade_date,main_net_flow FROM daily_stock_fund_flow "
        "WHERE ts_code=ANY(%s) AND trade_date>=%s AND trade_date<=%s",
        (match_ts, data_start, data_end))
    ff = {}
    for c,d,v in cur.fetchall(): ff.setdefault(d,{})[c]=float(v or 0)
    conn.close()

    nav, cash = 1000.0, 0.0
    holdings = {}; cost_basis = {}; points = []; stop_cnt = 0; last_nav = nav
    bt = [d for d in all_td if bt_start<=d<=bt_end]
    if len(bt) < 2:
        print("❌ 回测区间至少需要 2 个交易日（T+1 需要次日开盘价）")
        return []
    sl = stop_loss_pct>0

    label = f"grow_with_money V2 · {index_code} · M={lookback} · Top {top_n} · T+1开盘"
    if min_score > 0: label += f" · 最低{min_score/1e4:.0f}亿"
    if sl: label += f" · 止损{stop_loss_pct*100:.0f}%"
    print(f"\n{'='*100}\n  {label}\n{'='*100}")
    print(f"{'日期':<12} {'净值':>10} {'日收益':>8} {'持仓':>5} {'保留':>5} {'卖出':>5} {'买入':>5} {'换手%':>7} {'费用':>8}")

    pending_ranking = None  # 当日收盘后计算的排名，次日开盘执行

    for i, td in enumerate(bt):
        px_close = pr.get(td, {})     # 当日收盘价 → NAV
        px_open = pr_open.get(td, {}) # 当日开盘价 → 执行昨日决策
        if not px_close: continue
        tradable = is_tradable.get(td, {})

        # ── 执行昨日决策（当日开盘价）──────────────────────
        sold_today = 0; kept_suspended = 0; bought_today = 0
        keep_c = set()
        tv = 0.0; ct = 0.0

        if pending_ranking is not None:
            tgt = {s["ts_code"] for s in pending_ranking}
            old = set(holdings.keys())

            if not holdings:
                # 首次建仓（当日开盘价买入）
                tradable_ranking = [s for s in pending_ranking
                                    if tradable.get(s["ts_code"]) and px_open.get(s["ts_code"], 0) > 0]
                if tradable_ranking:
                    n = len(tradable_ranking); w = 1.0/n
                    for s in tradable_ranking:
                        p = px_open[s["ts_code"]]
                        holdings[s["ts_code"]] = (1000.0 * w * (1 - BUY_C)) / p
                        cost_basis[s["ts_code"]] = p
                        ct += 1000.0 * w * BUY_C
                    cash = 0
                    bought_today = len(tradable_ranking)
                    tv = 1000.0
            else:
                # 调仓
                sell_c = old - tgt; buy_c = tgt - old; keep_c = old & tgt

                # 卖出
                sg = 0
                for c in list(sell_c):
                    if not tradable.get(c):
                        kept_suspended += 1; keep_c.add(c); continue
                    p = px_open.get(c, 0)
                    if p > 0:
                        sg += holdings[c] * p
                        del holdings[c]
                        if c in cost_basis: del cost_basis[c]
                        sold_today += 1
                cash += sg * (1 - SELL_C)
                ct += sg * SELL_C

                # 买入
                bct = 0.0
                actual_buys = [c for c in buy_c if tradable.get(c) and px_open.get(c, 0) > 0]
                if actual_buys and cash > 0:
                    ca = cash / len(actual_buys)
                    for c in actual_buys:
                        p = px_open[c]
                        holdings[c] = (ca * (1 - BUY_C)) / p
                        cost_basis[c] = p
                        bct += ca * BUY_C; cash -= ca
                        bought_today += 1
                ct += bct
                tv = sg + (cash + bct if actual_buys else 0)

        # ── 止损检查（当日收盘价）─────────────────────────
        if sl and holdings:
            for code, sh in list(holdings.items()):
                if not tradable.get(code): continue
                p = px_close.get(code, 0); cb = cost_basis.get(code, 0)
                if p > 0 and cb > 0 and (p/cb - 1) < -stop_loss_pct:
                    cash += sh * p * (1 - SELL_C)
                    del holdings[code], cost_basis[code]
                    stop_cnt += 1

        # ── 当日收盘净值 ──────────────────────────────────
        sv = sum(holdings[c] * px_close.get(c, 0) for c in holdings if px_close.get(c, 0) > 0)
        prev_nav = nav
        nav = sv + cash

        # ── 计算次日排名 ──────────────────────────────────
        idx = all_td.index(td)
        pre = all_td[max(0, idx - lookback + 1):idx + 1]
        if len(pre) >= lookback:
            fs = {}
            for pd_ in pre:
                for c, v in ff.get(pd_, {}).items():
                    fs[c] = fs.get(c, 0) + v
            pending_ranking = sorted(
                [{"ts_code": k, "flow_m": v} for k, v in fs.items() if v > 0 and v >= min_score * 10000],
                key=lambda x: x["flow_m"], reverse=True)[:top_n]
        else:
            pending_ranking = None

        # ── 输出 ──────────────────────────────────────────
        dr = (nav / last_nav - 1) * 100 if last_nav > 0 and last_nav != nav else 0
        is_fri = datetime.strptime(td, "%Y-%m-%d").weekday() == 4

        if i == 0:
            print(f"{td:<12} {nav:>10.2f} {'—':>8} {0:>5} {'—':>5} {'—':>5} {'—':>5} {'—':>7} {'—':>8}")
        elif is_fri or i <= 4:
            to = (tv / (prev_nav) * 100) if prev_nav > 0 and tv > 0 else 0
            print(f"{td:<12} {nav:>10.2f} {dr:>7.2f}% {len(holdings):>5} {len(keep_c):>5} {sold_today:>5} {bought_today:>5} {to:>6.1f}% {ct:>8.2f}")

        points.append({"date": td, "nav": round(nav, 2)})
        last_nav = nav

    tr = (nav / 1000 - 1) * 100
    print(f"\n  📊 结果: {bt[0]} ~ {bt[-1]}")
    print(f"  起始: 1000.00 → 截止: {nav:.2f}  |  总收益: {tr:+.2f}%  |  交易日: {len(points)}")
    if sl: print(f"  止损触发: {stop_cnt} 次")
    return points


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--top",type=int,nargs="*",default=[3,5,10])
    p.add_argument("--lookback",type=int,default=5)
    p.add_argument("--stop-loss",action="store_true")
    p.add_argument("--stop-loss-pct",type=float,default=0.08)
    p.add_argument("--rebase-date",type=str,default=None,help="基准日，如 2025-04-07")
    p.add_argument("--index",type=str,default="980080",help="指数代码，如 980080（国证成长100）")
    p.add_argument("--bt-start",type=str,default="2025-01-01",help="回测起始日")
    p.add_argument("--bt-end",type=str,default="2026-06-19",help="回测截止日")
    p.add_argument("--data-start",type=str,default="2024-12-01",help="数据加载起始日")
    p.add_argument("--data-end",type=str,default="2026-06-30",help="数据加载截止日")
    p.add_argument("--min-score",type=float,default=0,help="最低主力净流入（万），低于此值不买入。5亿=50000")
    args = p.parse_args()

    all_r = {}
    CO = {3:'#ff6b6b',5:'#ffd93d',10:'#6bcb77'}
    CS = {3:'#ff9999',5:'#ffee80',10:'#99dd99'}

    for n in args.top:
        print(f"\n{'─'*60}\n  Top {n} (无止损)\n{'─'*60}")
        all_r[str(n)] = run(n, args.lookback, args.index,
                            bt_start=args.bt_start, bt_end=args.bt_end,
                            data_start=args.data_start, data_end=args.data_end,
                            min_score=args.min_score)
        if args.stop_loss:
            print(f"\n{'─'*60}\n  Top {n} (止损 {args.stop_loss_pct*100:.0f}%)\n{'─'*60}")
            all_r[f"{n}_sl"] = run(n, args.lookback, args.index, args.stop_loss_pct,
                                   bt_start=args.bt_start, bt_end=args.bt_end,
                                   data_start=args.data_start, data_end=args.data_end,
                                   min_score=args.min_score)

    if len(all_r)<=1: return

    dates = [pp["date"] for pp in list(all_r.values())[0]]
    series = []
    for n in args.top:
        k=str(n)
        if k in all_r: series.append({"name":f"Top {n}","data":[pp["nav"] for pp in all_r[k]],"color":CO.get(n),"dashed":False})
    if args.stop_loss:
        for n in args.top:
            k=f"{n}_sl"
            if k in all_r: series.append({"name":f"Top {n} 止损","data":[pp["nav"] for pp in all_r[k]],"color":CS.get(n),"dashed":True})

    fns = {}
    for n in args.top:
        k=str(n);
        if k in all_r: fns[k]=all_r[k][-1]["nav"]
        if args.stop_loss:
            k2=f"{n}_sl"
            if k2 in all_r: fns[k2]=all_r[k2][-1]["nav"]

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>grow_with_money V2 · {args.index} · 日频</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#1a1a2e;font-family:-apple-system,sans-serif}}
.container{{max-width:1400px;margin:0 auto;padding:24px}}h1{{color:#e0e0e0;text-align:center;font-size:22px;margin-bottom:6px}}
.sub{{color:#888;text-align:center;font-size:13px;margin-bottom:20px}}#chart{{width:100%;height:700px;background:#16213e;border-radius:12px}}
.stats{{display:grid;grid-template-columns:repeat({len(fns)},1fr);gap:16px;margin-top:20px}}
.card{{background:#16213e;border-radius:10px;padding:20px;text-align:center}}.card h3{{color:#888;font-size:13px;margin-bottom:8px}}
.card .val{{font-size:32px;font-weight:bold}}.card .pct{{font-size:14px;margin-top:4px}}</style></head><body><div class="container">
<h1>grow_with_money V2 · T+1开盘 · {args.index} · 每日调仓 · M={args.lookback}</h1>
<div class="sub">{args.bt_start[:7]} ~ {args.bt_end[:7]} · {len(dates)} 个交易日 · 同股不动 · 已扣交易费用 · T+1开盘价成交</div>
<div id="chart"></div><div class="stats" id="stats"></div></div>
<script>var dates={json.dumps(dates)};var sd={json.dumps(series)};var fn={json.dumps(fns)};
var c=echarts.init(document.getElementById('chart'));
c.setOption({{color:sd.map(function(s){{return s.color}}),
tooltip:{{trigger:'axis',backgroundColor:'rgba(22,33,62,0.95)',borderColor:'#333',textStyle:{{color:'#e0e0e0',fontSize:13}},
formatter:function(p){{var s='<b>'+p[0].axisValue+'</b><br/>';p.forEach(function(x){{s+='<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:'+x.color+';margin-right:6px"></span>'+x.seriesName+': <b>'+x.value.toFixed(2)+'</b> ('+((x.value-1000)/10).toFixed(1)+'%)<br/>'}});return s}}}},
legend:{{data:sd.map(function(s){{return s.name}}),top:10,textStyle:{{color:'#aaa',fontSize:14}},itemWidth:30,itemHeight:3}},
grid:{{left:60,right:40,top:60,bottom:40}},
xAxis:{{type:'category',data:dates,axisLine:{{lineStyle:{{color:'#333'}}}},axisLabel:{{color:'#888',fontSize:10,rotate:45,formatter:function(v){{return v.slice(5)}},interval:Math.floor(dates.length/30)}},splitLine:{{show:false}}}},
yAxis:{{type:'value',name:'净值',nameTextStyle:{{color:'#888',fontSize:12}},axisLabel:{{color:'#888',fontSize:12}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}},min:function(v){{return Math.floor(v.min/100)*100}}}},
series:sd.map(function(s){{return{{name:s.name,type:'line',data:s.data,smooth:true,symbol:'none',lineStyle:{{width:s.dashed?1.5:2,color:s.color,type:s.dashed?'dashed':'solid'}},itemStyle:{{color:s.color}}}}}})
}});
var ss=document.getElementById('stats');
Object.keys(fn).forEach(function(k){{var v=fn[k],p=((v-1000)/10).toFixed(1);var cl='#aaa';
if(k.indexOf('3')==0)cl='#ff6b6b';else if(k.indexOf('5')==0)cl='#ffd93d';else if(k.indexOf('10')==0)cl='#6bcb77';
ss.innerHTML+='<div class="card"><h3>'+k.replace('_sl',' 止损')+'</h3><div class="val" style="color:'+cl+'">'+v.toFixed(2)+'</div><div class="pct" style="color:'+cl+'">'+(p>=0?'+':'')+p+'%</div></div>'}});
window.addEventListener('resize',function(){{c.resize()}});</script></body></html>"""

    idx_slug = args.index.replace(".","_")
    out = Path(__file__).resolve().parent / f"backtest_grow_with_money_{idx_slug}_daily_v2.html"
    with open(out,'w') as f: f.write(html)
    print(f"\n✅ HTML: {out}")

    # ── Rebase 报告（可选） ──────────────────────────────────────────
    if args.rebase_date:
        rebased = {}
        for k, pts in all_r.items():
            base_nav = None; base_pt_date = None
            for pp in pts:
                if pp["date"] == args.rebase_date:
                    base_nav = pp["nav"]; base_pt_date = pp["date"]; break
            if base_nav is None:
                base_d = datetime.strptime(args.rebase_date, "%Y-%m-%d")
                best = min(pts, key=lambda pp: abs((datetime.strptime(pp["date"], "%Y-%m-%d") - base_d).days))
                base_nav = best["nav"]; base_pt_date = best["date"]
                print(f"  ⚠️ {k}: 基准日 {args.rebase_date} 无数据点，用最近日 {base_pt_date} NAV={base_nav:.2f}")
            factor = 1000.0 / base_nav
            rebased[k] = [{"date": pp["date"], "nav": round(pp["nav"] * factor, 2)} for pp in pts]

        rb_series = []
        for n in args.top:
            k = str(n)
            if k in rebased: rb_series.append({"name": f"Top {n}", "data": [pp["nav"] for pp in rebased[k]], "color": CO.get(n), "dashed": False})
        if args.stop_loss:
            for n in args.top:
                k = f"{n}_sl"
                if k in rebased: rb_series.append({"name": f"Top {n} 止损", "data": [pp["nav"] for pp in rebased[k]], "color": CS.get(n), "dashed": True})

        rb_dates = [pp["date"] for pp in list(rebased.values())[0]]
        rb_fns = {}
        for n in args.top:
            k = str(n)
            if k in rebased: rb_fns[k] = rebased[k][-1]["nav"]
            if args.stop_loss:
                k2 = f"{n}_sl"
                if k2 in rebased: rb_fns[k2] = rebased[k2][-1]["nav"]

        rb_html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>grow_with_money V2 · {args.index} · 日频 · Rebase</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#1a1a2e;font-family:-apple-system,sans-serif}}
.container{{max-width:1400px;margin:0 auto;padding:24px}}h1{{color:#e0e0e0;text-align:center;font-size:22px;margin-bottom:6px}}
.sub{{color:#888;text-align:center;font-size:13px;margin-bottom:20px}}#chart{{width:100%;height:700px;background:#16213e;border-radius:12px}}
.stats{{display:grid;grid-template-columns:repeat({len(rb_fns)},1fr);gap:16px;margin-top:20px}}
.card{{background:#16213e;border-radius:10px;padding:20px;text-align:center}}.card h3{{color:#888;font-size:13px;font-weight:normal;margin-bottom:8px}}
.card .val{{font-size:32px;font-weight:bold}}.card .pct{{font-size:14px;margin-top:4px}}</style></head><body><div class="container">
<h1>grow_with_money V2 · T+1开盘 · {args.index} · 每日调仓 · M={args.lookback} · 基准日 {args.rebase_date}=1000</h1>
<div class="sub">{args.bt_start[:7]} ~ {args.bt_end[:7]} · {len(rb_dates)} 个交易日 · 同股不动 · 已扣交易费用 · T+1开盘价成交 · 净值归一化到 {args.rebase_date}</div>
<div id="chart"></div><div class="stats" id="stats"></div></div>
<script>var dates={json.dumps(rb_dates)};var sd={json.dumps(rb_series)};var fn={json.dumps(rb_fns)};
var c=echarts.init(document.getElementById('chart'));
c.setOption({{color:sd.map(function(s){{return s.color}}),
tooltip:{{trigger:'axis',backgroundColor:'rgba(22,33,62,0.95)',borderColor:'#333',textStyle:{{color:'#e0e0e0',fontSize:13}},
formatter:function(p){{var s='<b>'+p[0].axisValue+'</b><br/>';p.forEach(function(x){{s+='<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:'+x.color+';margin-right:6px"></span>'+x.seriesName+': <b>'+x.value.toFixed(2)+'</b> ('+((x.value-1000)/10).toFixed(1)+'%)<br/>'}});return s}}}},
legend:{{data:sd.map(function(s){{return s.name}}),top:10,textStyle:{{color:'#aaa',fontSize:14}},itemWidth:30,itemHeight:3}},
grid:{{left:60,right:40,top:60,bottom:40}},
xAxis:{{type:'category',data:dates,axisLine:{{lineStyle:{{color:'#333'}}}},axisLabel:{{color:'#888',fontSize:10,rotate:45,formatter:function(v){{return v.slice(5)}},interval:Math.floor(dates.length/30)}},splitLine:{{show:false}}}},
yAxis:{{type:'value',name:'净值 (基准日=1000)',nameTextStyle:{{color:'#888',fontSize:12}},axisLabel:{{color:'#888',fontSize:12}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}},min:function(v){{return Math.floor(v.min/100)*100}}}},
series:sd.map(function(s){{return{{name:s.name,type:'line',data:s.data,smooth:true,symbol:'none',lineStyle:{{width:s.dashed?1.5:2,color:s.color,type:s.dashed?'dashed':'solid'}},itemStyle:{{color:s.color}},
markLine:{{silent:true,symbol:'none',lineStyle:{{color:'#666',type:'dashed',width:1}},data:[{{yAxis:1000,label:{{formatter:'基准 1000',color:'#888',fontSize:11}}}}]}}}}}})
}});
var ss=document.getElementById('stats');
Object.keys(fn).forEach(function(k){{var v=fn[k],p=((v-1000)/10).toFixed(1);var cl='#aaa';
if(k.indexOf('3')==0)cl='#ff6b6b';else if(k.indexOf('5')==0)cl='#ffd93d';else if(k.indexOf('10')==0)cl='#6bcb77';
ss.innerHTML+='<div class="card"><h3>'+k.replace('_sl',' 止损')+'</h3><div class="val" style="color:'+cl+'">'+v.toFixed(2)+'</div><div class="pct" style="color:'+cl+'">'+(p>=0?'+':'')+p+'%</div></div>'}});
window.addEventListener('resize',function(){{c.resize()}});</script></body></html>"""
        rb_out = Path(__file__).resolve().parent / f"backtest_grow_with_money_{idx_slug}_daily_v1_rebase.html"
        with open(rb_out, 'w') as f: f.write(rb_html)
        print(f"✅ Rebase HTML: {rb_out}")


if __name__=="__main__": main()
