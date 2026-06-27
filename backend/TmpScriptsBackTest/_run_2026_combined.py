#!/usr/bin/env python3
"""
一次性跑 2026 年 daily 回测：lookback=1/3/5 × Top=3/5，合并到一张图。
"""
from __future__ import annotations
import json, sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from TmpScriptsBackTest.backtest_grow_with_money_daily import run

LOOKBACKS = [1, 3, 5]
TOPS = [3, 5]
BT_START = "2026-01-01"
BT_END = "2026-06-26"
DATA_START = "2025-11-01"
DATA_END = "2026-06-27"

COLORS = {
    (1, 3): "#ff6b6b", (1, 5): "#ff9999",
    (3, 3): "#ffd93d", (3, 5): "#ffee80",
    (5, 3): "#6bcb77", (5, 5): "#99dd99",
}

all_pts = {}
for lb in LOOKBACKS:
    for top in TOPS:
        key = f"M={lb} Top{top}"
        print(f"\n▶ {key}")
        pts = run(top, lb, "980080", 0,
                  bt_start=BT_START, bt_end=BT_END,
                  data_start=DATA_START, data_end=DATA_END)
        all_pts[key] = pts

# Use the longest series as x-axis
ref_key = max(all_pts, key=lambda k: len(all_pts[k]))
dates = [p["date"] for p in all_pts[ref_key]]

series = []
for lb in LOOKBACKS:
    for top in TOPS:
        key = f"M={lb} Top{top}"
        pts = all_pts[key]
        nav_map = {p["date"]: p["nav"] for p in pts}
        # Align to reference dates, forward-fill
        data = []
        last = 1000.0
        for d in dates:
            if d in nav_map:
                last = nav_map[d]
            data.append(round(last, 2))
        series.append({
            "name": key,
            "data": data,
            "color": COLORS.get((lb, top), "#aaa"),
            "dashed": top == 5,
        })

fns = {}
for lb in LOOKBACKS:
    for top in TOPS:
        key = f"M={lb} Top{top}"
        fns[key] = all_pts[key][-1]["nav"]

n = len(fns)
html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>grow_with_money · 2026 · 日频 · 多参数对比</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#1a1a2e;font-family:-apple-system,sans-serif}}
.container{{max-width:1400px;margin:0 auto;padding:24px}}
h1{{color:#e0e0e0;text-align:center;font-size:22px;margin-bottom:6px}}
.sub{{color:#888;text-align:center;font-size:13px;margin-bottom:20px}}
#chart{{width:100%;height:700px;background:#16213e;border-radius:12px}}
.stats{{display:grid;grid-template-columns:repeat({n},1fr);gap:16px;margin-top:20px}}
.card{{background:#16213e;border-radius:10px;padding:20px;text-align:center}}
.card h3{{color:#888;font-size:12px;font-weight:normal;margin-bottom:8px}}
.card .val{{font-size:28px;font-weight:bold}}
.card .pct{{font-size:14px;margin-top:4px}}
</style></head><body><div class="container">
<h1>grow_with_money · 980080 · 每日调仓 · 2026</h1>
<div class="sub">M=1/3/5 × Top=3/5 · {BT_START} ~ {BT_END} · {len(dates)} 个交易日 · 已扣交易费用</div>
<div id="chart"></div><div class="stats" id="stats"></div></div>
<script>
var dates={json.dumps(dates)};
var sd={json.dumps(series)};
var fn={json.dumps(fns)};
var c=echarts.init(document.getElementById('chart'));
c.setOption({{
    color: sd.map(function(s){{return s.color}}),
    tooltip: {{
        trigger:'axis',
        backgroundColor:'rgba(22,33,62,0.95)',
        borderColor:'#333',
        textStyle:{{color:'#e0e0e0',fontSize:13}},
        formatter: function(p) {{
            var s='<b>'+p[0].axisValue+'</b><br/>';
            p.forEach(function(x){{
                s+='<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:'+x.color+';margin-right:6px"></span>'
                  +x.seriesName+': <b>'+x.value.toFixed(2)+'</b> ('+((x.value-1000)/10).toFixed(1)+'%)<br/>'
            }});
            return s
        }}
    }},
    legend: {{data:sd.map(function(s){{return s.name}}),top:10,textStyle:{{color:'#aaa',fontSize:13}},itemWidth:30,itemHeight:3}},
    grid: {{left:60,right:40,top:60,bottom:40}},
    xAxis: {{type:'category',data:dates,axisLine:{{lineStyle:{{color:'#333'}}}},axisLabel:{{color:'#888',fontSize:10,rotate:45,formatter:function(v){{return v.slice(5)}},interval:Math.floor(dates.length/20)}},splitLine:{{show:false}}}},
    yAxis: {{type:'value',name:'净值',nameTextStyle:{{color:'#888',fontSize:12}},axisLabel:{{color:'#888',fontSize:12}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}},min:function(v){{return Math.floor(v.min/100)*100}}}},
    series: sd.map(function(s){{return{{name:s.name,type:'line',data:s.data,smooth:true,symbol:'none',lineStyle:{{width:s.dashed?1.5:2,color:s.color,type:s.dashed?'dashed':'solid'}},itemStyle:{{color:s.color}}}}}})
}});
var ss=document.getElementById('stats');
var keys=Object.keys(fn);
var colors={json.dumps({k: COLORS.get((lb, top), "#aaa") for (lb, top), k in zip([(lb, t) for lb in LOOKBACKS for t in TOPS], [f"M={lb} Top{t}" for lb in LOOKBACKS for t in TOPS])})};
keys.forEach(function(k){{
    var v=fn[k],p=((v-1000)/10).toFixed(1);
    ss.innerHTML+='<div class="card"><h3>'+k+'</h3><div class="val" style="color:'+colors[k]+'">'+v.toFixed(2)+'</div><div class="pct" style="color:'+colors[k]+'">'+(p>=0?'+':'')+p+'%</div></div>'
}});
window.addEventListener('resize',function(){{c.resize()}});
</script></body></html>"""

out = Path(__file__).resolve().parent / "backtest_grow_with_money_980080_daily_2026_combined.html"
with open(out, 'w') as f:
    f.write(html)
print(f"\n✅ {out}")
