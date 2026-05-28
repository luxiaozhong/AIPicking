"""
Debug script v2: trace the 14 stocks that pass market cap filter through all steps.
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

# The 14 stocks that pass market cap
target_codes = [
    "688981.SH", "688525.SH", "688521.SH", "688506.SH",
    "688234.SH", "688047.SH", "688702.SH", "688469.SH",
    "688141.SH", "688220.SH", "688820.SH", "688322.SH",
    "688387.SH", "688808.SH",
]

# Load daily data for these stocks
placeholders = ",".join("?" * len(target_codes))
daily_rows = conn.execute(
    f"SELECT * FROM daily WHERE ts_code IN ({placeholders}) AND trade_date <= ? ORDER BY ts_code, trade_date",
    target_codes + [CUTOFF]
).fetchall()

# Load stock info
stock_rows = conn.execute(
    f"SELECT * FROM stocks WHERE ts_code IN ({placeholders})",
    target_codes
).fetchall()
conn.close()

daily = {}
for r in daily_rows:
    d = dict(r)
    daily.setdefault(d["ts_code"], []).append(d)

stock_lookup = {s["ts_code"]: dict(s) for s in stock_rows}

print("="*80)
print(f"DETAILED TRACE: 14 stocks that pass market_cap 300-5000 on {CUTOFF}")
print("="*80)

for ts_code in target_codes:
    rows = daily.get(ts_code, [])
    stock = stock_lookup.get(ts_code, {})
    name = stock.get("name", ts_code)
    industry = stock.get("industry_l1", "??")

    print(f"\n{'─'*70}")
    print(f"Stock: {ts_code} {name} | Industry: {industry}")

    if not rows:
        print("  NO DAILY DATA")
        continue

    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    df = df.sort_values("trade_date")

    if df.iloc[-1]["trade_date"] != pd.to_datetime(CUTOFF, format="%Y%m%d"):
        print(f"  Last date is {df.iloc[-1]['trade_date'].strftime('%Y%m%d')}, not on cutoff")
        continue

    print(f"  History: {len(df)} days ({df.iloc[0]['trade_date'].strftime('%Y%m%d')} ~ {df.iloc[-1]['trade_date'].strftime('%Y%m%d')})")
    market_cap = df.iloc[-1].get("market_cap")
    print(f"  Market cap: {market_cap:.1f}亿")

    if len(df) < strat.MIN_HISTORY:
        print(f"  ❌ FAIL: Only {len(df)} days (need {strat.MIN_HISTORY})")
        continue

    result = strat.check_trend_upstart(df)
    d = result["details"]

    # Print all details
    print(f"  Today close: {df.iloc[-1]['close']:.2f}, open: {df.iloc[-1]['open']:.2f}")
    print(f"  Today pct_chg: {d.get('today_up', '?'):.1f}%" if isinstance(d.get('today_up'), (int, float)) else f"  Today pct_chg: {d.get('today_up', '?')}")
    print(f"  Recent 3d big candles: {d.get('recent_bigs', '?')}")

    # Step 1: Big signal
    today_big = d.get("today_big", False)
    cluster_big = d.get("cluster_big", False)
    if not today_big and not cluster_big:
        print(f"  ❌ FAIL: No big up signal (today_big={today_big}, cluster_big={cluster_big})")
        continue
    print(f"  ✅ Big signal: today_big={today_big}, cluster_big={cluster_big}")

    # Step 2: Volume
    vol_ratio = d.get("vol_ratio", 0)
    vol_expand = d.get("vol_expand", False)
    shrink_limit = d.get("shrink_limit", False)
    print(f"  Vol ratio: {vol_ratio:.2f}x (vol={df.iloc[-1]['vol']:.0f}, ma5_vol={df.iloc[-1].get('vol_ma5', 0):.0f})")
    if not vol_expand and not shrink_limit:
        print(f"  ❌ FAIL: Volume not confirmed (vol_expand={vol_expand}, shrink_limit={shrink_limit})")
        continue
    print(f"  ✅ Volume: vol_expand={vol_expand}, shrink_limit={shrink_limit}")

    # Step 3: Recent gain
    recent_gain = d.get("recent_gain", "?")
    gain_ok = d.get("gain_ok", False)
    print(f"  Recent 10d gain: {recent_gain}")
    if not gain_ok:
        print(f"  ❌ FAIL: Recent gain out of range (-10%~+20%)")
        continue
    print(f"  ✅ Recent gain in range")

    # Step 4: Max drawdown
    max_dd = d.get("max_dd", "?")
    low_price = d.get("low_price", "?")
    dd_ok = d.get("dd_ok", False)
    print(f"  20d low: {low_price}, max_dd from low: {max_dd}")
    if not dd_ok:
        print(f"  ❌ FAIL: Max drawdown >= 15%")
        continue
    print(f"  ✅ Drawdown OK")

    # Step 5: MA bull
    ma5 = d.get("ma5", 0)
    ma10 = d.get("ma10", 0)
    ma20 = d.get("ma20", 0)
    ma_bull = d.get("ma_bull", False)
    ma_strict = d.get("ma_strict", False)
    ma20_up = d.get("ma20_up", False)
    price = df.iloc[-1]["close"]
    print(f"  MA5={ma5:.2f}, MA10={ma10:.2f}, MA20={ma20:.2f}, price={price:.2f}")
    print(f"  MA bull: {ma_bull}, MA strict: {ma_strict}, MA20 rising: {ma20_up}")
    if not ma_bull:
        print(f"  ❌ FAIL: MA not bull")
        continue
    print(f"  ✅ MA bull")

    # Step 6: MACD & RSI
    print(f"  MACD: DIF={d.get('macd_dif', 0):.4f}, DEA={d.get('macd_dea', 0):.4f}")
    print(f"  MACD golden: {d.get('macd_golden', False)}, zero above: {d.get('macd_zero', False)}")
    print(f"  RSI: {d.get('rsi', 0):.1f}, rsi_ok: {d.get('rsi_ok', False)}")

    # Step 7: Score
    print(f"  Score: {result['score']}, breakdown: {result['breakdown']}")
    print(f"  Signal: {d.get('signal_text', '')}")

    if result["score"] < 40:
        print(f"  ❌ FAIL: Score < 40")
        continue
    print(f"  ✅ Score >= 40")

    # Step 8: Limit up
    today_up_pct = d.get("today_up", 0)
    if today_up_pct >= 9.5:
        print(f"  ❌ EXCLUDED: Limit up {today_up_pct:.1f}%")
        continue
    print(f"  ✅ Not limit up")

    # Step 9: Sector
    print(f"  ✅✅ WOULD PASS ALL FILTERS! Score={result['score']}")

print("\n" + "="*80)
print("DONE")
