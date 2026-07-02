#!/usr/bin/env python3
"""
动量轮动策略 · 2026 全市场批量回测

用法：
    cd backend && source venv/bin/activate
    python TmpScriptsBackTest/backtest_momentum_rotation_2026.py
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime

# Ensure backend is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from app.services.backtest_engine import BacktestEngine

# ── Config ──────────────────────────────────────────────────
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRATEGY_FILE = os.path.join(BACKEND_DIR, "app/strategies/examples/momentum_rotation.py")
START_DATE = "20260101"
END_DATE = "20260701"  # up to today
TOP_N = 10

# Strategy params (全市场，不限制指数)
STRATEGY_CONFIG = {
    "index_codes": "980080",
    "N": TOP_N,
    "mom_fast": 20,
    "mom_slow": 60,
    "mom_fast_weight": 0.6,
    "vol_short": 5,
    "vol_long": 20,
    "volume_weight": 0.4,
}

# ── Load strategy ───────────────────────────────────────────
with open(STRATEGY_FILE) as f:
    code = f.read()

engine = BacktestEngine(code, {}, config=STRATEGY_CONFIG)
print(f"策略加载完成, REQUIRED_DATA={engine.required_data}")

# ── Run batch ───────────────────────────────────────────────
print(f"回测区间: {START_DATE} ~ {END_DATE}")
results = engine.run_batch(START_DATE, END_DATE, track_days=[3, 7, 15])

# ── Summary ─────────────────────────────────────────────────
completed = [r for r in results if r.get("status") == "completed"]
failed = [r for r in results if r.get("status") == "failed"]

print(f"\n总交易日: {len(results)}, 成功: {len(completed)}, 失败: {len(failed)}")

if not completed:
    print("无成功回测结果")
    sys.exit(1)

# Aggregate
total_recs = 0
all_returns_3d = []
all_returns_7d = []
all_returns_15d = []
win_3d = 0
win_7d = 0
win_15d = 0
daily_returns_15d = []  # avg 15d return per day(avg of recs)
daily_pick_rates = []

for r in completed:
    s = r.get("summary", {})
    recs = r.get("recommendations", [])
    total_recs += s.get("total_recommendations", 0)
    daily_pick_rates.append(s.get("pick_rate", 0))

    if s.get("avg_return_15d") is not None:
        daily_returns_15d.append(s["avg_return_15d"])

    for rec in recs:
        if rec.get("return_3d") is not None:
            all_returns_3d.append(rec["return_3d"])
            if rec["return_3d"] > 0:
                win_3d += 1
        if rec.get("return_7d") is not None:
            all_returns_7d.append(rec["return_7d"])
            if rec["return_7d"] > 0:
                win_7d += 1
        if rec.get("return_15d") is not None:
            all_returns_15d.append(rec["return_15d"])
            if rec["return_15d"] > 0:
                win_15d += 1

print(f"\n{'='*60}")
print(f"动量轮动 · 2026 全市场回测汇总 (截止 {END_DATE})")
print(f"{'='*60}")
print(f"回测天数:          {len(completed)}")
print(f"总推荐次数:        {total_recs}")
print(f"日均入选率:        {sum(daily_pick_rates)/len(daily_pick_rates)*100:.2f}%" if daily_pick_rates else "N/A")
print()

if all_returns_3d:
    import statistics
    print(f"3日收益均值:       {statistics.mean(all_returns_3d):.2f}%")
    print(f"3日收益中位数:     {statistics.median(all_returns_3d):.2f}%")
    print(f"3日胜率:           {win_3d/len(all_returns_3d)*100:.1f}%")
    print()
if all_returns_7d:
    import statistics
    print(f"7日收益均值:       {statistics.mean(all_returns_7d):.2f}%")
    print(f"7日收益中位数:     {statistics.median(all_returns_7d):.2f}%")
    print(f"7日胜率:           {win_7d/len(all_returns_7d)*100:.1f}%")
    print()
if all_returns_15d:
    import statistics
    print(f"15日收益均值:      {statistics.mean(all_returns_15d):.2f}%")
    print(f"15日收益中位数:    {statistics.median(all_returns_15d):.2f}%")
    print(f"15日胜率:          {win_15d/len(all_returns_15d)*100:.1f}%")
    print()

# Best/worst
if daily_returns_15d:
    best_idx = max(range(len(daily_returns_15d)), key=lambda i: daily_returns_15d[i])
    worst_idx = min(range(len(daily_returns_15d)), key=lambda i: daily_returns_15d[i])
    print(f"最佳单日(15d均值): {completed[best_idx]['cutoff_date']} → {daily_returns_15d[best_idx]:.2f}%")
    print(f"最差单日(15d均值): {completed[worst_idx]['cutoff_date']} → {daily_returns_15d[worst_idx]:.2f}%")

# ── Per-month breakdown ──────────────────────────────────────
print(f"\n{'─'*60}")
print("月度表现:")
monthly = defaultdict(list)
for r in completed:
    m = r["cutoff_date"][:6]
    s = r.get("summary", {})
    if s.get("avg_return_15d") is not None:
        monthly[m].append(s["avg_return_15d"])

for m in sorted(monthly):
    vals = monthly[m]
    import statistics
    avg = statistics.mean(vals)
    wr = sum(1 for v in vals if v > 0) / len(vals) * 100
    print(f"  {m}: {len(vals)}天, 均值={avg:.2f}%, 胜率={wr:.0f}%")
