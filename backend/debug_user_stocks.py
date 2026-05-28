"""
Analyze specific user-requested stocks with Trend Upstart strategy (22_Trend_Upstart.py).
Shows full scoring breakdown step by step.
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
CUTOFF = "20260527"

# ── Target stocks ───────────────────────────────────────────
TARGETS = {
    "300088.SZ": "长信科技",
    "688519.SH": "南亚新材",
    # "002079.SZ": "苏州固锝" -- NOT IN DATABASE
}

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Verify target stocks exist
for ts_code, name in TARGETS.items():
    row = conn.execute("SELECT * FROM stocks WHERE ts_code = ?", (ts_code,)).fetchone()
    if row:
        print(f"FOUND: {ts_code} {name}")
    else:
        print(f"MISSING FROM DB: {ts_code} {name}")

# Check if 002079.SZ exists
row = conn.execute("SELECT * FROM stocks WHERE ts_code = '002079.SZ'").fetchone()
if not row:
    print("\nNOTE: 苏州固锝 (002079.SZ) is NOT in the stock database. Cannot analyze.\n")

# Load all stocks (needed for sector heatmap)
stock_rows = conn.execute("SELECT * FROM stocks").fetchall()
stocks = [dict(r) for r in stock_rows]

# Load daily data
daily_rows = conn.execute(
    "SELECT * FROM daily WHERE trade_date <= ? ORDER BY ts_code, trade_date",
    (CUTOFF,)
).fetchall()
conn.close()

daily = {}
for r in daily_rows:
    d = dict(r)
    ts = d["ts_code"]
    daily.setdefault(ts, []).append(d)

stock_lookup = {s["ts_code"]: s for s in stocks}

# Compute sector heatmap
sector_heatmap = strat.calc_sector_heatmap(daily, stocks, CUTOFF)

print("=" * 90)
print(f"TREND UPSTART STRATEGY - SCORING BREAKDOWN")
print(f"Cutoff date: {CUTOFF}")
print("=" * 90)

for ts_code, name in TARGETS.items():
    if ts_code not in daily:
        print(f"\n{ts_code} {name}: NO DAILY DATA")
        continue

    stock = stock_lookup.get(ts_code, {})
    industry = stock.get("industry_l1", "??")
    total_shares = stock.get("total_shares", 0) or 0

    rows = daily[ts_code]
    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    df = df.sort_values("trade_date")

    print(f"\n{'─' * 90}")
    print(f"STOCK: {ts_code} {name} | Industry: {industry} | Total Shares: {total_shares:,}")
    print(f"{'─' * 90}")

    if df.iloc[-1]["trade_date"] != pd.to_datetime(CUTOFF, format="%Y%m%d"):
        print(f"  WARNING: Last date is {df.iloc[-1]['trade_date'].strftime('%Y%m%d')}, not {CUTOFF}")
        continue

    if len(df) < strat.MIN_HISTORY:
        print(f"  FAIL: Only {len(df)} days of data (need {strat.MIN_HISTORY})")
        continue

    # ── Market cap ──────────────────────────────────────────
    close_price = df.iloc[-1]["close"]
    market_cap = total_shares * close_price / 1e8 if total_shares > 0 else 0
    cap_status = "PASS" if strat.CAP_MIN <= market_cap <= strat.CAP_MAX else "FAIL"
    print(f"\n  [Market Cap] {market_cap:.0f} 亿 (range: {strat.CAP_MIN}-{strat.CAP_MAX}) -> {cap_status}")
    if cap_status == "FAIL":
        print(f"  RESULT: EXCLUDED (market cap out of range)")
        continue

    # ── Run full check_trend_upstart ────────────────────────
    result = strat.check_trend_upstart(df)
    details = result["details"]
    breakdown = result["breakdown"]
    raw_score = result["score"]

    # ── Print details section-by-section ─────────────────────
    print(f"\n  ── Gate 1: BIG UP SIGNAL (大阳线信号) ──")
    print(f"    Today up:            {details.get('today_up', '?'):.2f}%")
    print(f"    Today big (>5%):     {details.get('today_big', False)}")
    print(f"    Recent bigs (3d):    {details.get('recent_bigs', 0)}/3 (need >= {strat.BIG_UP_COUNT})")
    print(f"    Cluster big:         {details.get('cluster_big', False)}")
    big_signal = details.get("today_big") or details.get("cluster_big")
    print(f"    => Gate result:      {'PASS' if big_signal else 'FAIL'}  "
          f"(score contribution: {breakdown.get('big_signal', 0)})")

    if not big_signal:
        print(f"\n  RESULT: FAILED at Gate 1 (no big up signal)")
        continue

    print(f"\n  ── Gate 2: VOLUME CONFIRMATION (量能确认) ──")
    vol_ratio = details.get("vol_ratio", 0)
    print(f"    Vol ratio (today/5d):  {vol_ratio:.2f}x")
    print(f"    Vol expand (>1.2x):    {details.get('vol_expand', False)}")
    print(f"    Is limit up (>9.5%):   {details.get('today_up', 0) > strat.LIMIT_UP_PCT * 100}")
    print(f"    Shrink limit:          {details.get('shrink_limit', False)}")
    vol_ok = details.get("vol_expand") or details.get("shrink_limit")
    print(f"    => Gate result:        {'PASS' if vol_ok else 'FAIL'}  "
          f"(score contribution: {breakdown.get('volume', 0)})")

    if not vol_ok:
        print(f"\n  RESULT: FAILED at Gate 2 (volume not confirmed)")
        continue

    print(f"\n  ── Gate 3: RECENT GAIN RANGE (近10日涨幅) ──")
    recent_gain_str = details.get("recent_gain", "?")
    print(f"    Recent 10d gain:     {recent_gain_str}")
    gain_ok = details.get("gain_ok", False)
    print(f"    Range required:      {strat.RECENT_GAIN_MIN*100:.0f}% to {strat.RECENT_GAIN_MAX*100:.0f}%")
    print(f"    => Gate result:      {'PASS' if gain_ok else 'FAIL'}  "
          f"(score contribution: {breakdown.get('recent_gain', 0)})")

    if not gain_ok:
        print(f"\n  RESULT: FAILED at Gate 3 (recent gain out of range)")
        continue

    print(f"\n  ── Gate 4: MAX DRAWDOWN (最大回撤) ──")
    print(f"    20d low price:       {details.get('low_price', '?'):.2f}")
    print(f"    Max drawdown:        {details.get('max_dd', '?')}")
    dd_ok = details.get("dd_ok", False)
    print(f"    Threshold:           < {strat.MAX_DRAWDOWN*100:.0f}%")
    print(f"    => Gate result:      {'PASS' if dd_ok else 'FAIL'}  "
          f"(score contribution: {breakdown.get('drawdown', 0)})")

    if not dd_ok:
        print(f"\n  RESULT: FAILED at Gate 4 (drawdown too high)")
        continue

    print(f"\n  ── Gate 5: MA BULL ALIGNMENT (均线多头排列) ──")
    ma5 = details.get("ma5", 0)
    ma10 = details.get("ma10", 0)
    ma20 = details.get("ma20", 0)
    price = df.iloc[-1]["close"]
    print(f"    MA5:                 {ma5:.2f}")
    print(f"    MA10:                {ma10:.2f}")
    print(f"    MA20:                {ma20:.2f}")
    print(f"    Close price:         {price:.2f}")
    print(f"    MA5 > MA10:          {details.get('ma_bull', False)} (price={price:.2f} > MA5={ma5:.2f}: {price > ma5})")
    print(f"    MA5 > MA10 > MA20:   {details.get('ma_strict', False)}")
    print(f"    MA20 rising:         {details.get('ma20_up', False)}")
    ma_ok = details.get("ma_bull", False)
    print(f"    => Gate result:      {'PASS' if ma_ok else 'FAIL'}  "
          f"(score contribution: {breakdown.get('ma', 0)})")

    if not ma_ok:
        print(f"\n  RESULT: FAILED at Gate 5 (MA not bull-aligned)")
        continue

    print(f"\n  ── Gate 6: MACD (加分项) ──")
    print(f"    DIF:                 {details.get('macd_dif', '?'):.4f}")
    print(f"    DEA:                 {details.get('macd_dea', '?'):.4f}")
    print(f"    Golden cross:        {details.get('macd_golden', False)}")
    print(f"    Above zero:          {details.get('macd_zero', False)}")
    print(f"    => Score:            +{breakdown.get('macd', 0)}")

    print(f"\n  ── Gate 7: RSI (加分项) ──")
    rsi_val = details.get("rsi", 0)
    print(f"    RSI:                 {rsi_val:.1f}")
    print(f"    RSI < 80:            {details.get('rsi_ok', True)}")
    print(f"    => Score:            +{breakdown.get('rsi', 0)}")

    # ── Raw score breakdown ──────────────────────────────────
    print(f"\n  ── RAW SCORE BREAKDOWN ──")
    for k, v in breakdown.items():
        print(f"    {k:20s}: +{v}")
    print(f"    {'TOTAL RAW':20s}: {raw_score} (need >= 40)")

    # ── Limit up filter ─────────────────────────────────────
    today_up_pct = details.get("today_up", 0)
    if today_up_pct >= 9.5:
        print(f"\n  LIMIT UP FILTER: EXCLUDED (today_up={today_up_pct:.1f}% >= 9.5%)")
        continue

    # ── Sector adjustment ───────────────────────────────────
    sector_bonus = 0
    if industry and sector_heatmap and industry in sector_heatmap:
        sector_bonus = sector_heatmap[industry]

    print(f"\n  ── SECTOR ADJUSTMENT ──")
    print(f"    Industry:            {industry}")
    if sector_heatmap:
        print(f"    Sector bonus:        {sector_bonus:+d}")
        # Show where the sector sits in heatmap
        ranked = sorted(sector_heatmap.items(), key=lambda x: x[1], reverse=True)
        for i, (ind, sc) in enumerate(ranked):
            if ind == industry:
                print(f"    Sector rank:         #{i+1}/{len(ranked)} (hot/warm/cold)")
                break
    else:
        print(f"    Sector heatmap:      not enough data (<3 sectors or <3 stocks/sector)")

    adjusted_score = raw_score + sector_bonus
    passed = adjusted_score >= 40

    print(f"\n  ╔══════════════════════════════════════════════════╗")
    print(f"  ║  RAW SCORE:     {raw_score:3d}                          ║")
    print(f"  ║  SECTOR BONUS:  {sector_bonus:+3d}                          ║")
    print(f"  ║  FINAL SCORE:   {adjusted_score:3d}                          ║")
    print(f"  ║  RESULT:        {'PASSED - Would be recommended' if passed else 'FAILED - Below threshold (40)'}  ║")
    print(f"  ╚══════════════════════════════════════════════════╝")

    if passed:
        signal = details.get("signal_text", "")
        print(f"\n  Signal: {signal}")
        print(f"  Would appear in top {strat.TOP_PICKS} recommendations if among highest scores.")

print("\n" + "=" * 90)
print("DONE")
print("=" * 90)
