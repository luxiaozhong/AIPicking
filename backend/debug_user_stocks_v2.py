"""
Comprehensive scoring analysis for 南亚新材, 长信科技, 苏州固锝
- Uses 20260526 (last day with clean data) as cutoff
- Also scans recent dates where each stock might have triggered
"""
import sys, os, sqlite3, pandas as pd, importlib.util

strat_path = os.path.join(os.path.dirname(__file__), "app/strategies/examples/22_Trend_Upstart.py")
spec = importlib.util.spec_from_file_location("trend_upstart", strat_path)
strat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strat)

DB_PATH = "/Users/aklu/workbuddy/2026-05-22-21-48-44/data/stock_db.sqlite"
CUTOFF = "20260526"  # 20260527 has corrupted volume data for ALL stocks
LATEST_DATE = "20260527"  # for data loading only (so scanning covers all dates)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

stock_rows = conn.execute("SELECT * FROM stocks").fetchall()
stocks = [dict(r) for r in stock_rows]

# Load ALL data (up to latest date) so scanning works; analysis filters by cutoff
daily_rows = conn.execute(
    "SELECT * FROM daily WHERE trade_date <= ? ORDER BY ts_code, trade_date", (LATEST_DATE,)
).fetchall()
conn.close()

daily = {}
for r in daily_rows:
    d = dict(r)
    daily.setdefault(d["ts_code"], []).append(d)

stock_lookup = {s["ts_code"]: s for s in stocks}
sector_heatmap = strat.calc_sector_heatmap(daily, stocks, CUTOFF)

def full_analysis(ts_code, name, cutoff):
    """Run the COMPLETE strategy pipeline (identical to run() function) for a single stock."""
    if ts_code not in daily:
        return None

    rows = daily[ts_code]
    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    df = df.sort_values("trade_date")
    df = df[df["trade_date"] <= pd.to_datetime(cutoff, format="%Y%m%d")]

    if len(df) == 0 or df.iloc[-1]["trade_date"] != pd.to_datetime(cutoff, format="%Y%m%d"):
        return None
    if len(df) < strat.MIN_HISTORY:
        return {"stage": "min_history", "reason": f"only {len(df)} days"}

    stock = stock_lookup.get(ts_code, {})
    industry = stock.get("industry_l1", "??")
    total_shares = stock.get("total_shares", 0) or 0
    close_price = df.iloc[-1]["close"]
    market_cap = total_shares * close_price / 1e8 if total_shares > 0 else 0

    if market_cap < strat.CAP_MIN or market_cap > strat.CAP_MAX:
        return {"stage": "market_cap", "reason": f"market_cap={market_cap:.0f}亿 not in [{strat.CAP_MIN}, {strat.CAP_MAX}]", "market_cap": market_cap}

    result = strat.check_trend_upstart(df)
    details = result["details"]
    breakdown = result["breakdown"]
    raw_score = result["score"]

    # Determine which gate failed
    if not (details.get("today_big") or details.get("cluster_big")):
        return {"stage": "gate1_big_signal", "reason": f"today_up={details.get('today_up',0):.1f}%, recent_bigs={details.get('recent_bigs',0)}/3", "details": details, "breakdown": breakdown, "score": raw_score}
    if not (details.get("vol_expand") or details.get("shrink_limit")):
        return {"stage": "gate2_volume", "reason": f"vol_ratio={details.get('vol_ratio',0):.2f}x", "details": details, "breakdown": breakdown, "score": raw_score}
    if not details.get("gain_ok"):
        return {"stage": "gate3_gain_range", "reason": f"recent_gain={details.get('recent_gain','?')}", "details": details, "breakdown": breakdown, "score": raw_score}
    if not details.get("dd_ok"):
        return {"stage": "gate4_drawdown", "reason": f"max_dd={details.get('max_dd','?')}", "details": details, "breakdown": breakdown, "score": raw_score}
    if not details.get("ma_bull"):
        return {"stage": "gate5_ma_bull", "reason": f"MA5={details.get('ma5',0):.2f} MA10={details.get('ma10',0):.2f} price={close_price:.2f}", "details": details, "breakdown": breakdown, "score": raw_score}

    # All gates passed
    today_up_pct = details.get("today_up", 0)
    if today_up_pct >= 9.5:
        return {"stage": "limit_up_excluded", "reason": f"today_up={today_up_pct:.1f}% >= 9.5%", "details": details, "breakdown": breakdown, "score": raw_score}

    sector_bonus = sector_heatmap.get(industry, 0) if industry else 0
    final_score = raw_score + sector_bonus
    if final_score < 40:
        return {"stage": "sector_fail", "reason": f"raw={raw_score}+sector={sector_bonus:+d}={final_score}<40", "details": details, "breakdown": breakdown, "score": raw_score, "industry": industry, "sector_bonus": sector_bonus, "final_score": final_score}

    return {"stage": "PASSED", "details": details, "breakdown": breakdown, "score": raw_score, "industry": industry, "sector_bonus": sector_bonus, "final_score": final_score, "market_cap": market_cap}


def print_full_detail(r, name, cutoff):
    """Print detailed breakdown of a check_trend_upstart result."""
    if r is None:
        print(f"  No data on {cutoff}")
        return
    stage = r["stage"]
    print(f"\n  ── {name} on {cutoff} ──")
    print(f"  Stage: {stage}")

    if stage == "market_cap":
        print(f"  Market Cap: {r['market_cap']:.0f} 亿 (min: {strat.CAP_MIN} 亿)")
        return

    details = r.get("details", {})
    breakdown = r.get("breakdown", {})
    score = r.get("score", 0)

    if details:
        print(f"  today_up:       {details.get('today_up', '?'):.1f}%" if isinstance(details.get('today_up'), (int, float)) else f"  today_up:       {details.get('today_up', '?')}")
        print(f"  today_big:      {details.get('today_big', False)}")
        print(f"  recent_bigs:    {details.get('recent_bigs', 0)}/3")
        print(f"  cluster_big:    {details.get('cluster_big', False)}")
        print(f"  vol_ratio:      {details.get('vol_ratio', 0):.2f}x")
        print(f"  vol_expand:     {details.get('vol_expand', False)}")
        print(f"  shrink_limit:   {details.get('shrink_limit', False)}")
        print(f"  recent_gain:    {details.get('recent_gain', '?')}")
        print(f"  max_dd:         {details.get('max_dd', '?')}")
        print(f"  MA5/MA10/MA20:  {details.get('ma5', 0):.2f} / {details.get('ma10', 0):.2f} / {details.get('ma20', 0):.2f}")
        print(f"  ma_bull:        {details.get('ma_bull', False)}")
        print(f"  ma_strict:      {details.get('ma_strict', False)}")
        print(f"  ma20_up:        {details.get('ma20_up', False)}")
        print(f"  MACD golden:    {details.get('macd_golden', False)}")
        print(f"  MACD zero_above:{details.get('macd_zero', False)}")
        print(f"  RSI:            {details.get('rsi', 0):.1f}")

    if breakdown:
        print(f"  Score breakdown: {breakdown}")
        print(f"  Raw score:       {score}")

    if "industry" in r:
        print(f"  Industry:        {r['industry']}")
        print(f"  Sector bonus:    {r.get('sector_bonus', 0):+d}")
        print(f"  Final score:     {r.get('final_score', 0)}")
    if "market_cap" in r:
        print(f"  Market cap:      {r['market_cap']:.0f} 亿")


# ================================================================
print("=" * 90)
print("COMPREHENSIVE TREND UPSTART SCORING ANALYSIS")
print(f"Primary cutoff: {CUTOFF} (20260527 has corrupted volume data)")
print("=" * 90)

# ── Check if 苏州固锝 exists ──
print("\n" + "=" * 90)
print("1. 苏州固锝 (002079.SZ)")
print("=" * 90)
r = conn.execute("SELECT * FROM stocks WHERE ts_code='002079.SZ'").fetchone() if False else None
print("  STATUS: NOT IN DATABASE")
print("  This stock (002079.SZ) is completely absent from the stock database.")
print("  Without data, the strategy cannot evaluate it at all.")
conn2 = sqlite3.connect(DB_PATH)
if not conn2.execute("SELECT 1 FROM stocks WHERE ts_code='002079.SZ'").fetchone():
    pass
conn2.close()

# ── 长信科技 on 20260526 ──
print("\n" + "=" * 90)
print("2. 长信科技 (300088.SZ)")
print("=" * 90)
stock = stock_lookup.get("300088.SZ", {})
total_sh = stock.get("total_shares", 0) or 0
industry = stock.get("industry_l1", "??")

# Check on 20260526
r = full_analysis("300088.SZ", "长信科技", "20260526")
print_full_detail(r, "长信科技", "20260526")

# Check on 20260527
r27 = full_analysis("300088.SZ", "长信科技", "20260527")
print_full_detail(r27, "长信科技", "20260527")

# Also show: what if we bypass the market cap filter?
print(f"\n  ── Detailed scoring if market cap filter were bypassed (20260526) ──")
if "300088.SZ" in daily:
    rows = daily["300088.SZ"]
    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    df = df.sort_values("trade_date")
    df = df[df["trade_date"] <= pd.to_datetime(CUTOFF, format="%Y%m%d")]
    if len(df) >= strat.MIN_HISTORY:
        result = strat.check_trend_upstart(df)
        d = result["details"]
        bd = result["breakdown"]
        print(f"  today_up:       {d.get('today_up', 0):.1f}%")
        print(f"  today_big:      {d.get('today_big', False)}")
        print(f"  recent_bigs:    {d.get('recent_bigs', 0)}/3 (cluster: {d.get('cluster_big', False)})")
        print(f"  vol_ratio:      {d.get('vol_ratio', 0):.2f}x (expand: {d.get('vol_expand', False)}, shrink_limit: {d.get('shrink_limit', False)})")
        print(f"  recent_gain:    {d.get('recent_gain', '?')} (ok: {d.get('gain_ok', False)})")
        print(f"  max_dd:         {d.get('max_dd', '?')} (ok: {d.get('dd_ok', False)})")
        print(f"  MA5/MA10/MA20:  {d.get('ma5',0):.2f} / {d.get('ma10',0):.2f} / {d.get('ma20',0):.2f}")
        print(f"  ma_bull:        {d.get('ma_bull', False)} (strict: {d.get('ma_strict', False)}, ma20_up: {d.get('ma20_up', False)})")
        print(f"  MACD golden:    {d.get('macd_golden', False)}, zero_above: {d.get('macd_zero', False)}")
        print(f"  RSI:            {d.get('rsi', 0):.1f} (ok: {d.get('rsi_ok', True)})")
        print(f"  Score breakdown:{bd}")
        print(f"  Raw score:      {result['score']}")
        print(f"  First gate failed: ", end="")
        if not (d.get("today_big") or d.get("cluster_big")):
            print("Gate 1 (no big up signal)")
        elif not (d.get("vol_expand") or d.get("shrink_limit")):
            print("Gate 2 (volume not confirmed)")
        elif not d.get("gain_ok"):
            print("Gate 3 (recent gain out of range)")
        elif not d.get("dd_ok"):
            print("Gate 4 (drawdown too high)")
        elif not d.get("ma_bull"):
            print("Gate 5 (MA not bull-aligned)")
        elif result["score"] < 40:
            print(f"Score {result['score']} < 40")
        else:
            print(f"ALL GATES PASSED! Score={result['score']}")

# ── 南亚新材 ──
print("\n" + "=" * 90)
print("3. 南亚新材 (688519.SH)")
print("=" * 90)

# Scan recent trading days to find which days trigger the strategy
print("\n  Scanning last 20 trading days for strategy triggers...")
if "688519.SH" in daily:
    rows = daily["688519.SH"]
    df_all = pd.DataFrame(rows)
    df_all["trade_date"] = pd.to_datetime(df_all["trade_date"], format="%Y%m%d")
    df_all = df_all.sort_values("trade_date")
    stock = stock_lookup.get("688519.SH", {})
    total_sh = stock.get("total_shares", 0) or 0
    industry = stock.get("industry_l1", "??")

    last_20_dates = df_all["trade_date"].iloc[-20:]

    for _, cutoff_dt in last_20_dates.items():
        cutoff_str = cutoff_dt.strftime("%Y%m%d")
        df = df_all[df_all["trade_date"] <= cutoff_dt].copy()
        if len(df) < strat.MIN_HISTORY:
            continue

        close_price = df.iloc[-1]["close"]
        mcap = total_sh * close_price / 1e8 if total_sh > 0 else 0
        cap_ok = strat.CAP_MIN <= mcap <= strat.CAP_MAX

        result = strat.check_trend_upstart(df)
        d = result["details"]
        bd = result["breakdown"]

        today_up = d.get("today_up", 0)
        today_big = d.get("today_big", False)
        cluster = d.get("cluster_big", False)
        vol_exp = d.get("vol_expand", False)
        shrink = d.get("shrink_limit", False)
        gain_ok = d.get("gain_ok", False)
        dd_ok = d.get("dd_ok", False)
        ma_ok = d.get("ma_bull", False)
        vol_ratio = d.get("vol_ratio", 0)

        # Determine which gate failed
        if not cap_ok:
            stage = f"CAP({mcap:.0f}亿)"
        elif not today_big and not cluster:
            stage = f"G1(today={today_up:.1f}%)"
        elif not vol_exp and not shrink:
            stage = f"G2(vol={vol_ratio:.1f}x)"
        elif not gain_ok:
            stage = f"G3(gain={d.get('recent_gain','?')})"
        elif not dd_ok:
            stage = f"G4(dd={d.get('max_dd','?')})"
        elif not ma_ok:
            stage = "G5(no bull)"
        elif today_up >= 9.5:
            stage = f"LIMIT_UP({today_up:.1f}%)"
        else:
            sector_bonus = sector_heatmap.get(industry, 0) if industry else 0
            final_score = result["score"] + sector_bonus
            stage = f"PASSED! raw={result['score']} final={final_score}"

        marker = " <--" if "PASSED" in stage else ""
        print(f"  {cutoff_str}: {stage}{marker}")

# ── Full detail on 20260526 ──
print(f"\n  ── Detailed scoring on {CUTOFF} ──")
r = full_analysis("688519.SH", "南亚新材", CUTOFF)
print_full_detail(r, "南亚新材", CUTOFF)

# ── Summary ──
print("\n" + "=" * 90)
print("SUMMARY")
print("=" * 90)
print("""
  苏州固锝 (002079.SZ): 数据库中不存在此股票，策略完全无法评估。

  长信科技 (300088.SZ): 市值仅 196 亿，低于策略要求的 300 亿门槛。
    - 即使绕过市值过滤，在 20260526 仍然会因为 Gate 1 (涨幅不足) 或 Gate 2 (量能不足) 失败。
    - 该策略专门针对中大盘股（300-5000亿），小盘股无论信号多强都会排除。

  南亚新材 (688519.SH): 在最近交易日没有同时满足所有条件。
    - 20260522: 涨停(10.3%)可触发Gate1，但Gate2需要量能确认(缩量涨停需要vol<0.8x且涨幅>9.5%)
    - 20260527: 涨幅6.95%满足Gate1，但该日数据库成交量数据损坏(vol仅为正常的3%)
    - 其他日期: 涨幅不足以触发Gate1(需要>5%或3天2阳)

  关键原因:
  1. 数据覆盖: 苏州固锝完全不在库中
  2. 市值门槛: 长信科技196亿 < 300亿底限
  3. 信号时机: 南亚新材近期的强势日(5/22涨停, 5/27涨7%)各被不同Gate拦下
     - 5/22涨停被Gate2(量能)卡住
     - 5/27数据异常导致量比仅0.03x
""")
