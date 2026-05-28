"""Quick validation: run the actual strategy run() with computed market cap."""
import sys
import os
import sqlite3
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

data = {"cutoff_date": CUTOFF, "stocks": stocks, "daily": daily}
result = strat.run(data)

print(f"Top picks: {len(result)}")
for i, r in enumerate(result):
    print(f"  {i+1}. {r['ts_code']} {r['name']}: score={r['score']} | {r['signal']}")
