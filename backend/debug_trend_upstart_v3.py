"""
Debug script v3: Full pipeline with market_cap fallback to total_shares * close.
"""
import sys
import os
import sqlite3
import pandas as pd
import importlib.util

strat_path = os.path.join(
    os.path.dirname(__file__),
    "app/strategies/examples/22_Trend_Upstart.py"
)
spec = importlib.util.spec_from_file_location("trend_upstart", strat_path)
strat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strat)

DB_PATH = "/Users/aklu/workbuddy/2026-05-22-21-48-44/data/stock_db.sqlite"
CUTOFF = "20260526"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

stock_rows = conn.execute("SELECT * FROM stocks").fetchall()
stocks = [dict(r) for r in stock_rows]

daily_rows = conn.execute(
    "SELECT * FROM daily WHERE trade_date <= ? ORDER BY ts_code, trade_date",
    (CUTOFF,)
).fetchall()
conn.close()

daily = {}
for r in daily_rows:
    d = dict(r)
    daily.setdefault(d["ts_code"], []).append(d)

stock_lookup = {s["ts_code"]: s for s in stocks}

# Compute sector heatmap first
sector_heatmap = strat.calc_sector_heatmap(daily, stocks, CUTOFF)

print("="*80)
print(f"FULL PIPELINE TRACE with computed market_cap (total_shares * close / 1e8)")
print(f"Cutoff: {CUTOFF}")
print("="*80)

CAP_MIN = strat.CAP_MIN
CAP_MAX = strat.CAP_MAX
MIN_HISTORY = strat.MIN_HISTORY

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

for ts_code in sorted(daily.keys()):
    rows = daily[ts_code]
    if not rows:
        continue

    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    df = df.sort_values("trade_date")

    if df.iloc[-1]["trade_date"] != pd.to_datetime(CUTOFF, format="%Y%m%d"):
        continue

    step_results["total"] += 1
    stock = stock_lookup.get(ts_code, {})
    name = stock.get("name", ts_code)
    industry = stock.get("industry_l1", "??")

    # Step 0: Min history
    if len(df) < MIN_HISTORY:
        step_results["min_history_fail"].append((ts_code, name, len(df), industry))
        continue

    # Step 1: Market cap (with fallback computation)
    market_cap = df.iloc[-1].get("market_cap")
    if pd.isna(market_cap):
        # Fallback: compute from total_shares * close
        total_shares = stock.get("total_shares", 0) or 0
        close_price = df.iloc[-1]["close"]
        if total_shares > 0:
            market_cap = total_shares * close_price / 1e8  # Convert to 亿

    if pd.isna(market_cap) or market_cap < CAP_MIN or market_cap > CAP_MAX:
        cap_str = f"{market_cap:.0f}亿" if not pd.isna(market_cap) else "N/A"
        step_results["cap_fail"].append((ts_code, name, cap_str, industry))
        continue

    # Run strategy check
    result = strat.check_trend_upstart(df)
    details = result["details"]

    # Step 2: Big up signal
    if not details.get("today_big") and not details.get("cluster_big"):
        step_results["no_big_signal"].append((
            ts_code, name,
            f"today={details.get('today_up',0):.1f}%, recent_bigs={details.get('recent_bigs',0)}",
            industry, market_cap
        ))
        continue

    # Step 3: Volume
    if not details.get("vol_expand") and not details.get("shrink_limit"):
        step_results["vol_fail"].append((
            ts_code, name,
            f"vr={details.get('vol_ratio',0):.2f}x today={details.get('today_up',0):.1f}%",
            industry, details
        ))
        continue

    # Step 4: Recent gain
    if not details.get("gain_ok"):
        step_results["gain_fail"].append((
            ts_code, name, f"gain={details.get('recent_gain','?')}", industry, details
        ))
        continue

    # Step 5: Max drawdown
    if not details.get("dd_ok"):
        step_results["dd_fail"].append((
            ts_code, name, f"dd={details.get('max_dd','?')}", industry, details
        ))
        continue

    # Step 6: MA bull
    if not details.get("ma_bull"):
        step_results["ma_fail"].append((
            ts_code, name,
            f"MA5={details.get('ma5',0):.2f} MA10={details.get('ma10',0):.2f} p={df.iloc[-1]['close']:.2f}",
            industry, details
        ))
        continue

    # Step 7: Score
    if result["score"] < 40:
        step_results["score_fail"].append((
            ts_code, name,
            f"score={result['score']} bd={result['breakdown']}",
            industry, details
        ))
        continue

    # Step 8: Limit up
    today_up_pct = details.get("today_up", 0)
    if today_up_pct >= 9.5:
        step_results["limit_up_excluded"].append((
            ts_code, name, f"limit_up={today_up_pct:.1f}%", industry, details
        ))
        continue

    # Step 9: Sector
    sector_bonus = sector_heatmap.get(industry, 0) if industry else 0
    adj_score = result["score"] + sector_bonus
    if adj_score < 40:
        step_results["sector_fail"].append((
            ts_code, name,
            f"raw={result['score']}+sector={sector_bonus:+d}={adj_score}",
            industry, details
        ))
        continue

    step_results["passed"].append((
        ts_code, name, result["score"], adj_score,
        details.get("signal_text", ""), industry, sector_bonus, market_cap
    ))

# ── Summary ─────────────────────────────────────────────────
print(f"\nTotal stocks on cutoff: {step_results['total']}")

steps = [
    ("MIN_HISTORY (<30d)", "min_history_fail"),
    ("MARKET CAP (computed, 300-5000亿)", "cap_fail"),
    ("BIG UP SIGNAL (today>5% or 3d/2yang)", "no_big_signal"),
    ("VOLUME CONFIRM", "vol_fail"),
    ("RECENT GAIN (-10%~+20%)", "gain_fail"),
    ("MAX DRAWDOWN (<15%)", "dd_fail"),
    ("MA BULL (MA5>MA10 & price>MA5)", "ma_fail"),
    ("SCORE >= 40", "score_fail"),
    ("LIMIT UP EXCLUDE (>=9.5%)", "limit_up_excluded"),
    ("SECTOR ADJUST (>=40)", "sector_fail"),
    ("✅ PASSED", "passed"),
]

remaining = step_results["total"]
for label, key in steps:
    count = len(step_results[key])
    if key == "passed":
        print(f"\n  {label}: {count}")
    else:
        remaining_after = remaining - count
        print(f"  {label}: {count} failed ({count/max(step_results['total'],1)*100:.1f}%), remain {remaining_after}")
        remaining = remaining_after

# ── Detail per step ─────────────────────────────────────────
print("\n" + "="*80)
print("DETAIL BY STEP")
print("="*80)

# Market cap - show distribution
cap_items = step_results["cap_fail"]
too_small = [x for x in cap_items if x[2] != "N/A" and float(x[2].replace("亿","")) < CAP_MIN]
too_large = [x for x in cap_items if x[2] != "N/A" and float(x[2].replace("亿","")) > CAP_MAX]
no_data = [x for x in cap_items if x[2] == "N/A"]
print(f"\nMARKET CAP FAILED ({len(cap_items)}): too_small={len(too_small)}, too_large={len(too_large)}, no_data={len(no_data)}")

# Big signal - show top by today_up
no_sig = sorted(step_results["no_big_signal"], key=lambda x: -x[4])
print(f"\nBIG SIGNAL FAILED ({len(no_sig)}), showing top 20 by market cap:")
for item in no_sig[:20]:
    print(f"  {item[0]} {item[1]}: {item[2]} | cap={item[4]:.0f}亿 | {item[3]}")

# Volume fail
vol_items = step_results["vol_fail"]
print(f"\nVOLUME FAILED ({len(vol_items)}):")
for item in vol_items[:20]:
    print(f"  {item[0]} {item[1]}: {item[2]} | {item[3]}")

# Gain fail
print(f"\nRECENT GAIN FAILED ({len(step_results['gain_fail'])}):")
for item in step_results["gain_fail"][:20]:
    print(f"  {item[0]} {item[1]}: {item[2]} | {item[3]}")

# DD fail
print(f"\nMAX DRAWDOWN FAILED ({len(step_results['dd_fail'])}):")
for item in step_results["dd_fail"][:20]:
    print(f"  {item[0]} {item[1]}: {item[2]} | {item[3]}")

# MA fail
print(f"\nMA BULL FAILED ({len(step_results['ma_fail'])}):")
for item in step_results["ma_fail"][:20]:
    print(f"  {item[0]} {item[1]}: {item[2]} | {item[3]}")

# Score fail
print(f"\nSCORE < 40 FAILED ({len(step_results['score_fail'])}):")
for item in step_results["score_fail"][:20]:
    print(f"  {item[0]} {item[1]}: {item[2]} | {item[3]}")

# Limit up
print(f"\nLIMIT UP EXCLUDED ({len(step_results['limit_up_excluded'])}):")
for item in step_results["limit_up_excluded"][:10]:
    print(f"  {item[0]} {item[1]}: {item[2]} | {item[3]}")

# Sector fail
print(f"\nSECTOR ADJUST FAILED ({len(step_results['sector_fail'])}):")
for item in step_results["sector_fail"][:10]:
    print(f"  {item[0]} {item[1]}: {item[2]} | {item[3]}")

# PASSED
print(f"\n{'='*80}")
print(f"✅ PASSED ALL: {len(step_results['passed'])} stocks")
print(f"{'='*80}")
for item in step_results["passed"]:
    ts_code, name, score, adj_score, signal, industry, bonus, mcap = item
    print(f"  {ts_code} {name}: {signal} | cap={mcap:.0f}亿 | score={score}{bonus:+d}={adj_score} | {industry}")

# Industry distribution for big signal failures
print(f"\n{'='*80}")
print("BIG SIGNAL FAILURES - by industry (top 15)")
from collections import Counter
ind_counter = Counter(item[3] for item in step_results["no_big_signal"])
for ind, cnt in ind_counter.most_common(15):
    print(f"  {ind}: {cnt}")

print("\nDone.")
