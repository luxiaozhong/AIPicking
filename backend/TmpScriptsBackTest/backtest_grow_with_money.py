#!/usr/bin/env python3
"""
grow_with_money · 周频调仓回测 · 980080

策略：每周五从国证成长100成分股中按过去 M 日主力净流入排名取 Top N，
等权买入。已在持仓且未跌出前 N 不动（省换手）。

支持 --stop-loss：每日检查，个股跌破成本价 -8% 则止损卖出。

用法：
    python TmpScriptsBackTest/backtest_grow_with_money.py
    python TmpScriptsBackTest/backtest_grow_with_money.py --top 3 5 10 --stop-loss
"""

from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
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

def gen_fridays(s,e):
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

def run(top_n, lookback, stop_loss_pct=0):
    conn = _pg()
    cur = conn.cursor()

    rebal_dates = gen_fridays("2025-01-01","2026-06-19")
    # 980080 raw codes
    cur.execute("SELECT ts_code FROM index_constituents WHERE index_code='980080'")
    raw_set = {r[0] for r in cur.fetchall()}

    # All trading days
    cur.execute("SELECT DISTINCT trade_date FROM daily WHERE trade_date>='2024-12-01' AND trade_date<='2026-06-30' ORDER BY trade_date")
    all_td = [r[0] for r in cur.fetchall()]

    # Map rebal dates to actual trading days
    def nxt(tgt):
        for t in all_td:
            if t>=tgt: return t
        return None
    rebal_td_set = set()
    for rd in rebal_dates:
        nt = nxt(rd)
        if nt: rebal_td_set.add(nt)

    # Find 980080 matching ts_codes
    cur.execute("""
        SELECT DISTINCT sff.ts_code FROM daily_stock_fund_flow sff
        JOIN stocks s ON s.ts_code=sff.ts_code
        WHERE sff.trade_date>='2024-12-01' AND sff.trade_date<='2026-06-30'
          AND s.type='stock' AND s.name NOT LIKE '%%ST%%'
    """)
    all_fc = [r[0] for r in cur.fetchall()]
    match_ts = [t for t in all_fc if t.split(".")[0] in raw_set]

    # Load all prices
    cur.execute("SELECT ts_code,trade_date,close FROM daily WHERE ts_code=ANY(%s) AND trade_date>='2024-12-01' AND trade_date<='2026-06-30' ORDER BY ts_code,trade_date",(match_ts,))
    pr = {}
    for c,d,v in cur.fetchall(): pr.setdefault(d,{})[c]=v

    # ── Forward-fill prices + tradability marker ──────────────────
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

    # Load all fund flow
    cur.execute("SELECT ts_code,trade_date,main_net_flow FROM daily_stock_fund_flow WHERE ts_code=ANY(%s) AND trade_date>='2024-12-01' AND trade_date<='2026-06-30'",(match_ts,))
    ff = {}
    for c,d,v in cur.fetchall(): ff.setdefault(d,{})[c]=float(v or 0)
    conn.close()

    nav, cash = 1000.0, 0.0
    holdings = {}   # {code: shares}
    cost_basis = {} # {code: price}
    points = []
    stop_cnt = 0
    last_nav = nav

    bt = [d for d in all_td if "2025-01-01"<=d<="2026-06-19"]
    sl = stop_loss_pct>0

    label = f"grow_with_money · 980080 · M={lookback} · Top {top_n} · 每周五"
    if sl: label += f" · 止损{stop_loss_pct*100:.0f}%"
    print(f"\n{'='*100}\n  {label}\n{'='*100}")
    print(f"{'日期':<12} {'净值':>10} {'周收益':>8} {'持仓':>5} {'保留':>5} {'卖出':>5} {'买入':>5} {'换手%':>7} {'费用':>8}")

    for td in bt:
        px = pr.get(td,{})
        if not px: continue
        is_reb = td in rebal_td_set

        # ── Daily stop-loss check (skip if suspended) ────────
        tradable = is_tradable.get(td, {})
        if sl and holdings:
            for code, sh in list(holdings.items()):
                if not tradable.get(code): continue
                p = px.get(code,0)
                cb = cost_basis.get(code,0)
                if p>0 and cb>0 and (p/cb-1)<-stop_loss_pct:
                    cash += sh*p*(1-SELL_C)
                    del holdings[code], cost_basis[code]
                    stop_cnt += 1

        # NAV update
        sv = sum(holdings[c]*px.get(c,0) for c in holdings if px.get(c,0)>0)
        nav = sv + cash

        if not is_reb:
            if td==bt[-1]: points.append({"date":td,"nav":round(nav,2)})
            continue

        # ── Rebalance ──────────────────────────────────────
        idx = all_td.index(td)
        pre = all_td[max(0,idx-lookback+1):idx+1]
        if len(pre)<lookback: continue

        fs = {}
        for pd_ in pre:
            for c,v in ff.get(pd_,{}).items(): fs[c]=fs.get(c,0)+v
        ranking = sorted([{"ts_code":k,"flow_m":v} for k,v in fs.items() if v>0],key=lambda x:x["flow_m"],reverse=True)[:top_n]
        if not ranking: continue
        tgt = {s["ts_code"] for s in ranking}

        if not holdings and cash==0:
            # Initial — use fixed 1000 as starting capital
            start_nav = 1000.0
            tradable_ranking = [s for s in ranking if tradable.get(s["ts_code"])]
            if not tradable_ranking: continue
            n = len(tradable_ranking); w = 1.0/n
            for s in tradable_ranking:
                p = px.get(s["ts_code"],0)
                if p>0:
                    holdings[s["ts_code"]] = (start_nav*w)/p
                    cost_basis[s["ts_code"]] = p
            cash = 0; nav = start_nav
            print(f"{td:<12} {nav:>10.2f} {'—':>8} {len(holdings):>5} {'—':>5} {'—':>5} {len(holdings):>5} {'—':>7} {'—':>8}")
            points.append({"date":td,"nav":round(nav,2)}); last_nav=nav
            continue

        old = set(holdings.keys())
        sell_c = old - tgt; buy_c = tgt - old; keep_c = old & tgt
        sold_today = 0; kept_suspended = 0

        # Sell removed (skip if suspended — can't sell a halted stock)
        sg = 0
        for c in list(sell_c):
            if not tradable.get(c):
                kept_suspended += 1
                keep_c.add(c)
                continue
            p = px.get(c,0)
            if p>0: sg += holdings[c]*p
            del holdings[c]
            if c in cost_basis: del cost_basis[c]
            sold_today += 1
        cash += sg*(1-SELL_C)

        # Buy new (skip if suspended, redistribute cash to tradable targets)
        bct = 0.0
        actual_buys = [c for c in buy_c if tradable.get(c)]
        if actual_buys and cash>0:
            ca = cash/len(actual_buys)
            for c in actual_buys:
                p = px.get(c,0)
                if p>0:
                    holdings[c] = (ca*(1-BUY_C))/p
                    cost_basis[c] = p
                    bct += ca*BUY_C
                    cash -= ca

        nav = sum(holdings[c]*px.get(c,0) for c in holdings if px.get(c,0)>0) + cash
        tv = sg + (cash+bct if actual_buys else 0)
        to = (tv/(sv+cash)*100) if (sv+cash)>0 else 0
        ct = sg*SELL_C + bct
        wr = (nav/last_nav-1)*100 if last_nav>0 else 0

        print(f"{td:<12} {nav:>10.2f} {wr:>7.2f}% {len(holdings):>5} {len(keep_c):>5} {sold_today:>5} {len(actual_buys):>5} {to:>6.1f}% {ct:>8.2f}")
        points.append({"date":td,"nav":round(nav,2)}); last_nav=nav

    tr = (nav/1000-1)*100
    print(f"\n  📊 结果: {bt[0]} ~ {bt[-1]}")
    print(f"  起始: 1000.00 → 截止: {nav:.2f}  |  总收益: {tr:+.2f}%  |  调仓: {len(points)-1} 次")
    if sl: print(f"  止损触发: {stop_cnt} 次")
    return points


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--top",type=int,nargs="*",default=[3,5,10])
    p.add_argument("--lookback",type=int,default=5)
    p.add_argument("--stop-loss",action="store_true")
    p.add_argument("--stop-loss-pct",type=float,default=0.08)
    args = p.parse_args()

    all_r = {}
    CO = {3:'#ff6b6b',5:'#ffd93d',10:'#6bcb77'}
    CS = {3:'#ff9999',5:'#ffee80',10:'#99dd99'}

    for n in args.top:
        print(f"\n{'─'*60}\n  Top {n} (无止损)\n{'─'*60}")
        all_r[str(n)] = run(n, args.lookback)
        if args.stop_loss:
            print(f"\n{'─'*60}\n  Top {n} (止损 {args.stop_loss_pct*100:.0f}%)\n{'─'*60}")
            all_r[f"{n}_sl"] = run(n, args.lookback, args.stop_loss_pct)

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
        k=str(n)
        if k in all_r: fns[k]=all_r[k][-1]["nav"]
        if args.stop_loss:
            k2=f"{n}_sl"
            if k2 in all_r: fns[k2]=all_r[k2][-1]["nav"]

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>grow_with_money · 980080 · 周频</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#1a1a2e;font-family:-apple-system,sans-serif}}
.container{{max-width:1400px;margin:0 auto;padding:24px}}h1{{color:#e0e0e0;text-align:center;font-size:22px;margin-bottom:6px}}
.sub{{color:#888;text-align:center;font-size:13px;margin-bottom:20px}}#chart{{width:100%;height:700px;background:#16213e;border-radius:12px}}
.stats{{display:grid;grid-template-columns:repeat({len(fns)},1fr);gap:16px;margin-top:20px}}
.card{{background:#16213e;border-radius:10px;padding:20px;text-align:center}}.card h3{{color:#888;font-size:13px;font-weight:normal;margin-bottom:8px}}
.card .val{{font-size:32px;font-weight:bold}}.card .pct{{font-size:14px;margin-top:4px}}</style></head><body><div class="container">
<h1>grow_with_money · 980080（国证成长100）· 每周五调仓 · M={args.lookback}</h1>
<div class="sub">2025-01 ~ 2026-06 · {len(dates)} 个数据点 · 同股不动 · 已扣交易费用</div>
<div id="chart"></div><div class="stats" id="stats"></div></div>
<script>var dates={json.dumps(dates)};var sd={json.dumps(series)};var fn={json.dumps(fns)};
var c=echarts.init(document.getElementById('chart'));
c.setOption({{color:sd.map(function(s){{return s.color}}),
tooltip:{{trigger:'axis',backgroundColor:'rgba(22,33,62,0.95)',borderColor:'#333',textStyle:{{color:'#e0e0e0',fontSize:13}},
formatter:function(p){{var s='<b>'+p[0].axisValue+'</b><br/>';p.forEach(function(x){{s+='<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:'+x.color+';margin-right:6px"></span>'+x.seriesName+': <b>'+x.value.toFixed(2)+'</b> ('+((x.value-1000)/10).toFixed(1)+'%)<br/>'}});return s}}}},
legend:{{data:sd.map(function(s){{return s.name}}),top:10,textStyle:{{color:'#aaa',fontSize:14}},itemWidth:30,itemHeight:3}},
grid:{{left:60,right:40,top:60,bottom:40}},
xAxis:{{type:'category',data:dates,axisLine:{{lineStyle:{{color:'#333'}}}},axisLabel:{{color:'#888',fontSize:10,rotate:45,formatter:function(v){{return v.slice(5)}},interval:Math.floor(dates.length/25)}},splitLine:{{show:false}}}},
yAxis:{{type:'value',name:'净值',nameTextStyle:{{color:'#888',fontSize:12}},axisLabel:{{color:'#888',fontSize:12}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}},min:function(v){{return Math.floor(v.min/100)*100}}}},
series:sd.map(function(s){{return{{name:s.name,type:'line',data:s.data,smooth:true,symbol:'none',lineStyle:{{width:s.dashed?1.5:2,color:s.color,type:s.dashed?'dashed':'solid'}},itemStyle:{{color:s.color}}}}}})
}});
var ss=document.getElementById('stats');
Object.keys(fn).forEach(function(k){{var v=fn[k],p=((v-1000)/10).toFixed(1);var cl='#aaa';
if(k.indexOf('3')==0)cl='#ff6b6b';else if(k.indexOf('5')==0)cl='#ffd93d';else if(k.indexOf('10')==0)cl='#6bcb77';
ss.innerHTML+='<div class="card"><h3>'+k.replace('_sl',' 止损')+'</h3><div class="val" style="color:'+cl+'">'+v.toFixed(2)+'</div><div class="pct" style="color:'+cl+'">'+(p>=0?'+':'')+p+'%</div></div>'}});
window.addEventListener('resize',function(){{c.resize()}});</script></body></html>"""

    out = Path(__file__).resolve().parent/"backtest_grow_with_money.html"
    with open(out,'w') as f: f.write(html)
    print(f"\n✅ HTML: {out}")


if __name__=="__main__": main()
