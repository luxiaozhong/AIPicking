"""
Debug script: trace Trend Upstart strategy step by step for 20260526.
"""
import sys
import os
import sqlite3
import pandas as pd
import importlib.util

# Dynamically load the strategy module
strat_path = os.path.join(
    os.path.dirname(__file__),
    "app/strategies/examples/22_Trend_Upstart.py"
)
spec = importlib.util.spec_from_file_location("trend_upstart", strat_path)
strat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strat)

DB_PATH = "/Users/aklu/workbuddy/2026-05-22-21-48-44/data/stock_db.sqlite"
CUTOFF = "20260526"

# ── Load data ──────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Load stocks
stock_rows = conn.execute("SELECT * FROM stocks").fetchall()
stocks = [dict(r) for r in stock_rows]
print(f"Total stocks in DB: {len(stocks)}")

# Load daily data for cutoff date + history
daily_rows = conn.execute(
    "SELECT * FROM daily WHERE trade_date <= ? ORDER BY ts_code, trade_date",
    (CUTOFF,)
).fetchall()
conn.close()

# Group by ts_code
daily = {}
for r in daily_rows:
    d = dict(r)
    ts = d["ts_code"]
    daily.setdefault(ts, []).append(d)

# Filter to only stocks that have data on cutoff date
stocks_with_data = [s for s in stocks if s["ts_code"] in daily]
print(f"Stocks with any daily data: {len(stocks_with_data)}")

# Check which stocks have the cutoff date
stocks_on_cutoff = []
for s in stocks:
    ts = s["ts_code"]
    if ts in daily:
        for row in daily[ts]:
            if row["trade_date"] == CUTOFF:
                stocks_on_cutoff.append(s)
                break
print(f"Stocks with data on {CUTOFF}: {len(stocks_on_cutoff)}")

# ── Step-by-step analysis ─────────────────────────────────
print("\n" + "="*80)
print("STEP-BY-STEP STRATEGY DEBUG: Trend Upstart")
print(f"Cutoff: {CUTOFF}")
print("="*80)

MIN_HISTORY = strat.MIN_HISTORY
CAP_MIN = strat.CAP_MIN
CAP_MAX = strat.CAP_MAX

# Container for detailed tracking
step_results = {
    "total": 0,
    "min_history_fail": [],
    "cap_fail": [],
    "no_big_signal": [],
    "vol_fail": [],
    "gain_fail": [],
    "dd_fail": [],
    "ma_fail": [],
    "score_fail": [],
    "limit_up_excluded": [],
    "sector_fail": [],
    "passed": [],
}

# First compute sector heatmap (needs all stocks)
sector_heatmap = strat.calc_sector_heatmap(daily, stocks, CUTOFF)
print(f"\nSector heatmap (top 5 hot +10, bottom 5 cold -10):")
for ind, score in sorted(sector_heatmap.items(), key=lambda x: -x[1]):
    if score != 0:
        print(f"   {ind}: {score:+d}")

print(f"\nAnalyzing each stock step by step...")

stock_lookup = {s["ts_code"]: s for s in stocks}

for ts_code in sorted(daily.keys()):
    rows = daily[ts_code]
    if not rows:
        continue

    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    df = df.sort_values("trade_date")

    # Only analyze stocks that have the cutoff date as the last day
    if df.iloc[-1]["trade_date"] != pd.to_datetime(CUTOFF, format="%Y%m%d"):
        continue

    step_results["total"] += 1

    stock = stock_lookup.get(ts_code, {})
    name = stock.get("name", ts_code)
    industry = stock.get("industry_l1", "??")

    # ── Step 0: Min history ──
    if len(df) < MIN_HISTORY:
        step_results["min_history_fail"].append((ts_code, name, f"only {len(df)} days"))
        continue

    # ── Step 1: Market cap ──
    market_cap = df.iloc[-1].get("market_cap")
    if pd.isna(market_cap) or market_cap < CAP_MIN or market_cap > CAP_MAX:
        cap_str = f"{market_cap:.0f}M" if not pd.isna(market_cap) else "no data"
        step_results["cap_fail"].append((ts_code, name, cap_str, industry))
        continue

    # ── Run check_trend_upstart for detailed breakdown ──
    result = strat.check_trend_upstart(df)
    details = result["details"]

    # ── Step 2: Big up signal ──
    if not details.get("today_big") and not details.get("cluster_big"):
        step_results["no_big_signal"].append((
            ts_code, name,
            f"today_up={details.get('today_up',0):.1f}%, "
            f"recent_bigs={details.get('recent_bigs',0)}/3"
        ))
        continue

    # ── Step 3: Volume ──
    if not details.get("vol_expand") and not details.get("shrink_limit"):
        step_results["vol_fail"].append((
            ts_code, name,
            f"vol_ratio={details.get('vol_ratio',0):.2f}x, "
            f"today_up={details.get('today_up',0):.1f}%",
            details
        ))
        continue

    # ── Step 4: Recent gain range ──
    if not details.get("gain_ok"):
        step_results["gain_fail"].append((
            ts_code, name,
            f"recent_gain={details.get('recent_gain','?')}",
            details
        ))
        continue

    # ── Step 5: Max drawdown ──
    if not details.get("dd_ok"):
        step_results["dd_fail"].append((
            ts_code, name,
            f"max_dd={details.get('max_dd','?')}",
            details
        ))
        continue

    # ── Step 6: MA bull alignment ──
    if not details.get("ma_bull"):
        step_results["ma_fail"].append((
            ts_code, name,
            f"MA5={details.get('ma5',0):.2f} MA10={details.get('ma10',0):.2f} "
            f"price={df.iloc[-1]['close']:.2f}",
            details
        ))
        continue

    # ── Step 7: Score check (before sector) ──
    if result["score"] < 40:
        step_results["score_fail"].append((
            ts_code, name,
            f"score={result['score']}, breakdown={result['breakdown']}",
            details
        ))
        continue

    # ── Step 8: Limit up filter ──
    today_up_pct = details.get("today_up", 0)
    if today_up_pct >= 9.5:
        step_results["limit_up_excluded"].append((
            ts_code, name,
            f"limit_up {details.get('today_up',0):.1f}%",
            details
        ))
        continue

    # ── Step 9: Sector adjustment ──
    sector_bonus = 0
    if industry and sector_heatmap and industry in sector_heatmap:
        sector_bonus = sector_heatmap[industry]

    adjusted_score = result["score"] + sector_bonus
    if adjusted_score < 40:
        step_results["sector_fail"].append((
            ts_code, name,
            f"raw={result['score']} + sector={sector_bonus:+d} = {adjusted_score}",
            details
        ))
        continue

    # ── Passed! ──
    step_results["passed"].append((
        ts_code, name, result["score"], adjusted_score,
        details.get("signal_text", ""), industry, sector_bonus
    ))


# ── Print summary ──────────────────────────────────────────
print("\n" + "="*80)
print("RESULTS SUMMARY")
print("="*80)

total = step_results["total"]
print(f"\nTotal analyzed (min history + on cutoff): {total}")

steps = [
    ("MIN_HISTORY (<30 days)", "min_history_fail"),
    ("MARKET CAP (300-5000yi)", "cap_fail"),
    ("BIG UP SIGNAL (today>5% or 3d/2yang)", "no_big_signal"),
    ("VOLUME CONFIRM (vol_ratio>1.2x or shrink_limit)", "vol_fail"),
    ("RECENT GAIN RANGE (-10%~+20%)", "gain_fail"),
    ("MAX DRAWDOWN (<15%)", "dd_fail"),
    ("MA BULL (MA5>MA10 & price>MA5)", "ma_fail"),
    ("SCORE >= 40 (before sector)", "score_fail"),
    ("LIMIT UP EXCLUDE (>=9.5%)", "limit_up_excluded"),
    ("SECTOR ADJUST (score still >=40)", "sector_fail"),
    ("PASSED ALL!", "passed"),
]

remaining = total
for label, key in steps:
    count = len(step_results[key])
    if key == "passed":
        print(f"\n  PASSED: {count}")
    else:
        remaining_after = remaining - count
        pct = count/total*100 if total > 0 else 0
        print(f"  {label}: {count} failed ({pct:.1f}%), remaining: {remaining_after}")
        remaining = remaining_after

# ── Print detail for each step ─────────────────────────────
print("\n" + "="*80)
print("DETAIL BY FILTER STEP (showing samples)")
print("="*80)

detail_steps = [
    ("MARKET CAP FAILED (first 30)", "cap_fail"),
    ("NO BIG UP SIGNAL (first 30)", "no_big_signal"),
    ("VOLUME FAILED (all)", "vol_fail"),
    ("RECENT GAIN FAILED (all)", "gain_fail"),
    ("MAX DRAWDOWN FAILED (all)", "dd_fail"),
    ("MA BULL FAILED (all)", "ma_fail"),
    ("SCORE < 40 FAILED (all)", "score_fail"),
    ("LIMIT UP EXCLUDED (all)", "limit_up_excluded"),
    ("SECTOR ADJUST FAILED (all)", "sector_fail"),
]

for label, key in detail_steps:
    items = step_results[key]
    if not items:
        print(f"\n--- {label}: 0 ---")
        continue
    print(f"\n--- {label}: {len(items)} ---")
    for item in items[:30]:
        ts_code, name = item[0], item[1]
        desc = item[2]
        extra = ""
        if key == "cap_fail":
            extra = f" | industry={item[3]}"
        print(f"  {ts_code} {name}: {desc}{extra}")

# ── Print passed stocks ────────────────────────────────────
print(f"\n{'='*80}")
print(f"PASSED ALL FILTERS: {len(step_results['passed'])} stocks")
print(f"{'='*80}")
if step_results["passed"]:
    for item in step_results["passed"]:
        ts_code, name, score, adj_score, signal, industry, bonus = item
        print(f"  {ts_code} {name}: raw={score} + sector={bonus:+d} = {adj_score} "
              f"| {signal} | industry={industry}")
else:
    print("  NONE - no stocks passed all filters!")

# ── Near-miss analysis ─────────────────────────────────────
print(f"\n{'='*80}")
print("NEAR-MISS ANALYSIS")
print(f"{'='*80}")

# Check stocks with today_up close to 5%
print("\nStocks with today_up >= 4.0% but < 5.0% (just missed big up signal):")
no_sig = step_results["no_big_signal"]
near_5 = []
for item in no_sig:
    desc = item[2]
    if "today_up=" in desc:
        try:
            pct_str = desc.split("today_up=")[1].split("%")[0]
            pct = float(pct_str)
            if 4.0 <= pct < 5.0:
                near_5.append((item[0], item[1], pct, desc))
        except:
            pass
near_5.sort(key=lambda x: -x[2])
if near_5:
    for item in near_5[:20]:
        print(f"  {item[0]} {item[1]}: {item[2]:.1f}%")
else:
    print("  (none)")

# Check stocks with vol_ratio close to 1.2
print("\nStocks that passed big signal but had vol_ratio 1.0-1.2 (just missed volume):")
# Need to re-run for these
vol_near_miss = []
for ts_code in sorted(daily.keys()):
    rows = daily[ts_code]
    if not rows:
        continue
    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    df = df.sort_values("trade_date")
    if df.iloc[-1]["trade_date"] != pd.to_datetime(CUTOFF, format="%Y%m%d"):
        continue
    if len(df) < MIN_HISTORY:
        continue
    market_cap = df.iloc[-1].get("market_cap")
    if pd.isna(market_cap) or market_cap < CAP_MIN or market_cap > CAP_MAX:
        continue

    result = strat.check_trend_upstart(df)
    details = result["details"]

    # Must have passed big signal
    if not details.get("today_big") and not details.get("cluster_big"):
        continue
    # But failed volume
    vol_ratio = details.get("vol_ratio", 0)
    if details.get("vol_expand") or details.get("shrink_limit"):
        continue  # already passed
    if 1.0 <= vol_ratio < 1.2:
        stock = stock_lookup.get(ts_code, {})
        name = stock.get("name", ts_code)
        vol_near_miss.append((ts_code, name, vol_ratio, details.get("today_up", 0)))

vol_near_miss.sort(key=lambda x: -x[2])
if vol_near_miss:
    for item in vol_near_miss[:20]:
        print(f"  {item[0]} {item[1]}: vol_ratio={item[2]:.2f}x, today_up={item[3]:.1f}%")
else:
    print("  (none)")

# Distribution of big signal failures
print(f"\nDistribution of today_up for stocks that ran check_trend_upstart:")
from collections import Counter
up_buckets = Counter()
for item in step_results["no_big_signal"]:
    desc = item[2]
    if "today_up=" in desc:
        try:
            pct_str = desc.split("today_up=")[1].split("%")[0]
            pct = float(pct_str)
            bucket = f"{int(pct//1)}%"
            up_buckets[bucket] += 1
        except:
            pass
for bucket in sorted(up_buckets.keys(), key=lambda x: float(x.replace('%',''))):
    print(f"  {bucket}: {up_buckets[bucket]} stocks")

# Check: how many stocks have today_up > 5%?
print(f"\nStocks with today_up >= 5.0% (should trigger big signal):")
big_count = 0
for ts_code in sorted(daily.keys()):
    rows = daily[ts_code]
    if not rows:
        continue
    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    df = df.sort_values("trade_date")
    if df.iloc[-1]["trade_date"] != pd.to_datetime(CUTOFF, format="%Y%m%d"):
        continue

    pct_chg = (df.iloc[-1]["close"] / df.iloc[-2]["close"] - 1) * 100 if len(df) >= 2 else 0
    if pct_chg >= 5.0:
        big_count += 1
print(f"  Total: {big_count} stocks")

print("\nDone.")
