"""
Final deep-dive: check every gate detail for the most promising dates,
and scan 长信科技 for any triggering dates (ignoring market cap).
"""
import sys, os, sqlite3, pandas as pd, importlib.util

strat_path = os.path.join(os.path.dirname(__file__), "app/strategies/examples/22_Trend_Upstart.py")
spec = importlib.util.spec_from_file_location("trend_upstart", strat_path)
strat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strat)

DB_PATH = "/Users/aklu/workbuddy/2026-05-22-21-48-44/data/stock_db.sqlite"
LATEST = "20260527"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
stock_rows = conn.execute("SELECT * FROM stocks").fetchall()
stocks = [dict(r) for r in stock_rows]
daily_rows = conn.execute(
    "SELECT * FROM daily WHERE trade_date <= ? ORDER BY ts_code, trade_date", (LATEST,)
).fetchall()
conn.close()

daily = {}
for r in daily_rows:
    d = dict(r)
    daily.setdefault(d["ts_code"], []).append(d)

stock_lookup = {s["ts_code"]: s for s in stocks}


def compute_all_indicators(df):
    """Run all indicator calculations from check_trend_upstart and return full details dict."""
    if len(df) < 30:
        return None
    df = df.copy()
    df["ma5"] = df["close"].rolling(5).mean()
    df["ma10"] = df["close"].rolling(10).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["vol_ma5"] = df["vol"].rolling(5).mean()
    df["vol_ma20"] = df["vol"].rolling(20).mean()
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd_dif"] = ema12 - ema26
    df["macd_dea"] = df["macd_dif"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = 2 * (df["macd_dif"] - df["macd_dea"])
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    df["pct_chg"] = df["close"].pct_change() * 100
    return df


def gate_details(df, cutoff_date):
    """Print every gate detail for the cutoff date."""
    df = df[df["trade_date"] <= pd.to_datetime(cutoff_date, format="%Y%m%d")]
    if len(df) < 30:
        print(f"  Not enough data ({len(df)} days)")
        return

    df = compute_all_indicators(df)
    if df is None:
        return

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    price = latest["close"]

    # ── Gate 1: Big Up Signal ──
    today_up = latest["pct_chg"]
    today_big = today_up > 5.0
    recent_n = min(3, len(df) - 1)
    recent_bigs = sum(1 for i in range(1, recent_n + 1) if df.iloc[-i]["pct_chg"] > 5.0)
    cluster_big = recent_bigs >= 2

    print(f"\n  Gate 1 - BIG UP SIGNAL")
    print(f"    Today:    {today_up:+.2f}% {'>' if today_up > 5.0 else '<='} 5%  => {'BIG' if today_big else 'no'}")
    print(f"    3d bigs:  {recent_bigs}/3 >= 2  => {'CLUSTER' if cluster_big else 'no cluster'}")
    print(f"    => {'PASS' if (today_big or cluster_big) else 'FAIL'}")

    if not today_big and not cluster_big:
        return

    # ── Gate 2: Volume ──
    vol_ma5 = latest["vol_ma5"]
    today_vol = latest["vol"]
    vol_ratio = today_vol / vol_ma5 if vol_ma5 > 0 and not pd.isna(vol_ma5) else 0
    vol_expand = vol_ratio > 1.2
    is_limit_up = today_up > 9.5
    shrink_limit = (vol_ratio < 0.8) and is_limit_up

    print(f"\n  Gate 2 - VOLUME CONFIRMATION")
    print(f"    Today vol:     {today_vol:,.0f}")
    print(f"    MA5 vol:       {vol_ma5:,.0f}")
    print(f"    Vol ratio:     {vol_ratio:.2f}x {'(>1.2x)' if vol_expand else ''}")
    vols_5d = [f"{df.iloc[-(i+1)]['vol']:,.0f}" for i in range(5, 0, -1)]
    print(f"    5d avg trend:  {vols_5d}")
    print(f"    Is limit up:   {is_limit_up} (>{9.5}%)")
    print(f"    Shrink limit:  {shrink_limit} (vol<0.8x AND limit_up)")
    print(f"    => {'PASS' if (vol_expand or shrink_limit) else 'FAIL'}")

    if not vol_expand and not shrink_limit:
        return

    # ── Gate 3: Recent Gain ──
    lookback = min(10, len(df) - 1)
    close_10d = df.iloc[-lookback - 1]["close"]
    recent_gain = (price / close_10d - 1) if close_10d > 0 else 0
    gain_ok = -0.10 <= recent_gain <= 0.20
    print(f"\n  Gate 3 - RECENT GAIN RANGE")
    print(f"    Close 10d ago: {close_10d:.2f}")
    print(f"    Recent gain:   {recent_gain*100:+.2f}% (need -10% ~ +20%)")
    print(f"    => {'PASS' if gain_ok else 'FAIL'}")

    if not gain_ok:
        return

    # ── Gate 4: Max Drawdown ──
    low_start = max(0, len(df) - 20)
    segment = df.iloc[low_start:]
    low_idx = segment["close"].idxmin()
    low_price = segment.loc[low_idx, "close"]
    after_low = segment[segment.index >= low_idx]
    peak = 0
    max_dd = 0
    for _, row in after_low.iterrows():
        if row["close"] > peak:
            peak = row["close"]
        dd = (peak - row["close"]) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    dd_ok = max_dd < 0.15
    print(f"\n  Gate 4 - MAX DRAWDOWN")
    print(f"    20d low:       {low_price:.2f} (date: {segment.loc[low_idx, 'trade_date'].strftime('%Y%m%d')})")
    print(f"    Peak after low: {peak:.2f}")
    print(f"    Max DD:        {max_dd*100:.1f}% (<15%)")
    print(f"    => {'PASS' if dd_ok else 'FAIL'}")

    if not dd_ok:
        return

    # ── Gate 5: MA Bull ──
    ma5 = latest["ma5"]
    ma10 = latest["ma10"]
    ma20 = latest["ma20"]
    ma_bull = ma5 > ma10 and price > ma5
    ma_strict = ma5 > ma10 > ma20
    # Check MA20 rising (compare to previous day's MA20, or 2 days ago to be safe)
    ma20_prev = df.iloc[-2]["ma20"]
    ma20_prev2 = df.iloc[-3]["ma20"] if len(df) >= 3 else ma20_prev
    ma20_up = ma20 > ma20_prev or ma20 > ma20_prev2

    print(f"\n  Gate 5 - MA BULL ALIGNMENT")
    print(f"    MA5:           {ma5:.2f}")
    print(f"    MA10:          {ma10:.2f}")
    print(f"    MA20:          {ma20:.2f}")
    print(f"    Price:         {price:.2f}")
    print(f"    MA5 > MA10:    {ma5 > ma10}")
    print(f"    Price > MA5:   {price > ma5}")
    print(f"    MA10 > MA20:   {ma10 > ma20}")
    print(f"    Strict (5>10>20): {ma_strict}")
    print(f"    MA20 prev:     {ma20_prev:.2f} (rising: {ma20 > ma20_prev})")
    print(f"    => {'PASS' if ma_bull else 'FAIL'} (need MA5>MA10 AND price>MA5)")

    if not ma_bull:
        return

    # ── Bonus: MACD ──
    dif = latest["macd_dif"]
    dea = latest["macd_dea"]
    prev_dif = df.iloc[-2]["macd_dif"]
    prev_dea = df.iloc[-2]["macd_dea"]
    macd_golden = prev_dif < prev_dea and dif > dea
    macd_zero = dif > 0 and dea > 0
    print(f"\n  Bonus - MACD")
    print(f"    DIF:           {dif:.4f}")
    print(f"    DEA:           {dea:.4f}")
    print(f"    Golden cross:  {macd_golden}")
    print(f"    Above zero:    {macd_zero}")
    macd_score = 10 if (macd_golden and macd_zero) else (6 if (macd_golden or macd_zero) else 0)
    print(f"    Bonus:         +{macd_score}")

    # ── Bonus: RSI ──
    rsi = latest["rsi"]
    rsi_ok = rsi < 80
    print(f"\n  Bonus - RSI")
    print(f"    RSI:           {rsi:.1f}")
    print(f"    < 80:          {rsi_ok}")
    rsi_score = 5 if (rsi_ok and rsi < 70) else (3 if rsi_ok else 0)
    print(f"    Bonus:         +{rsi_score}")

    # ── Total Score ──
    big_score = 25 if (today_big and cluster_big) else (18 if today_big else 15)
    vol_score = 20 if shrink_limit else (18 if vol_ratio > 2.0 else 14)
    gain_score = 10 if abs(recent_gain) < 0.05 else (7 if abs(recent_gain) < 0.10 else 4)
    dd_score = 15 if max_dd < 0.05 else (12 if max_dd < 0.10 else 8)
    ma_score = 15 if (ma_strict and ma20_up) else (12 if (ma_bull and ma20_up) else 8)
    total = big_score + vol_score + gain_score + dd_score + ma_score + macd_score + rsi_score

    print(f"\n  ╔══════════════════════════════╗")
    print(f"  ║  SCORE BREAKDOWN            ║")
    print(f"  ║  Big signal:    +{big_score:2d}        ║")
    print(f"  ║  Volume:        +{vol_score:2d}        ║")
    print(f"  ║  Recent gain:   +{gain_score:2d}        ║")
    print(f"  ║  Drawdown:      +{dd_score:2d}        ║")
    print(f"  ║  MA alignment:  +{ma_score:2d}        ║")
    print(f"  ║  MACD:          +{macd_score:2d}        ║")
    print(f"  ║  RSI:           +{rsi_score:2d}        ║")
    print(f"  ║  ─────────────────────  ║")
    print(f"  ║  RAW TOTAL:     {total:3d}        ║")
    print(f"  ╚══════════════════════════════╝")
    print(f"  Limit up filter: {'EXCLUDED' if today_up >= 9.5 else 'OK'}")

    # Check sector
    # Quick inline sector calc
    tc_ind = {}
    for s in stocks:
        ind = s.get("industry_l1")
        if ind and ind != "其他":
            tc_ind[s["ts_code"]] = ind
    seg_gains = {}
    for ts, rows in daily.items():
        industry = tc_ind.get(ts)
        if not industry:
            continue
        dft = pd.DataFrame(rows)
        dft["trade_date"] = pd.to_datetime(dft["trade_date"], format="%Y%m%d")
        dft = dft[dft["trade_date"] <= pd.to_datetime(cutoff_date, format="%Y%m%d")].sort_values("trade_date")
        if len(dft) < 120:
            continue
        r = dft.iloc[-120:]
        g = (r.iloc[-1]["close"] / r.iloc[0]["close"] - 1) if r.iloc[0]["close"] > 0 else 0
        seg_gains.setdefault(industry, []).append(g)
    seg_avg = {}
    for ind, gains in seg_gains.items():
        if len(gains) >= 3:
            seg_avg[ind] = sum(gains) / len(gains)
    ranked = sorted(seg_avg.items(), key=lambda x: x[1], reverse=True)
    sector_bonus = 0
    stock_ind = tc_ind.get("688519.SH", "")
    for i, (ind, _) in enumerate(ranked):
        if ind == stock_ind:
            if i < 5: sector_bonus = 10
            elif i >= len(ranked) - 5: sector_bonus = -10
            break

    final = total + sector_bonus
    print(f"  Sector bonus:   {sector_bonus:+d} (industry: {stock_ind})")
    print(f"  FINAL SCORE:    {final} {'=> PASSED (top 5)' if final >= 40 else '=> FAILED (<40)'}")


# ================================================================
print("=" * 90)
print("DEEP DIVE: 南亚新材 (688519.SH) on 20260522 — made it to Gate 5")
print("=" * 90)

rows = daily["688519.SH"]
df = pd.DataFrame(rows)
df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
df = df.sort_values("trade_date")
gate_details(df, "20260522")

# Also check 20260506 (Gate 2 near-miss with vol_ratio=1.1x)
print("\n\n" + "=" * 90)
print("DEEP DIVE: 南亚新材 (688519.SH) on 20260506 — Gate 2 near-miss (vol_ratio=1.1x)")
print("=" * 90)
gate_details(df, "20260506")

# Also check 20260427 (Gate 2 near-miss with vol_ratio=0.9x)
print("\n\n" + "=" * 90)
print("DEEP DIVE: 南亚新材 (688519.SH) on 20260427 — Gate 2 near-miss (vol_ratio=0.9x)")
print("=" * 90)
gate_details(df, "20260427")

# Scan 长信科技: any dates with trigger?
print("\n\n" + "=" * 90)
print("SCAN: 长信科技 (300088.SZ) — which dates trigger strategy (ignoring market cap)?")
print("=" * 90)

rows2 = daily.get("300088.SZ", [])
if rows2:
    df2 = pd.DataFrame(rows2)
    df2["trade_date"] = pd.to_datetime(df2["trade_date"], format="%Y%m%d")
    df2 = df2.sort_values("trade_date")
    df2 = compute_all_indicators(df2)

    last_30_dates = df2["trade_date"].iloc[-30:]
    triggered = []
    for cutoff_dt in last_30_dates:
        cutoff_str = cutoff_dt.strftime("%Y%m%d")
        sub = df2[df2["trade_date"] <= cutoff_dt]
        if len(sub) < 30:
            continue
        result = strat.check_trend_upstart(sub)
        d = result["details"]
        if result["passed"]:
            triggered.append((cutoff_str, result["score"], d))
        elif d.get("today_big") or d.get("cluster_big"):
            # Got past Gate 1 at least
            if d.get("vol_expand") or d.get("shrink_limit"):
                triggered.append((cutoff_str, result["score"], d, "past_G2"))

    if triggered:
        print(f"  Found {len(triggered)} triggering/near-trigger dates:")
        for t in triggered:
            print(f"    {t[0]}: score={t[1]} {t[2].get('signal_text','')}")
    else:
        print("  No dates in last 30 with Gate 1 trigger")
        # Show closest
        max_up = 0
        max_date = ""
        for cutoff_dt in last_30_dates:
            sub = df2[df2["trade_date"] <= cutoff_dt]
            if len(sub) < 2:
                continue
            up = (sub.iloc[-1]["close"] / sub.iloc[-2]["close"] - 1) * 100
            if up > max_up:
                max_up = up
                max_date = cutoff_dt.strftime("%Y%m%d")
        print(f"  Max single-day gain in last 30d: {max_up:.1f}% on {max_date}")

print("\nDone.")
