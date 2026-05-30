"""
Daily A-share market data sync — standalone script, zero dependency on the app.

Fetches and stores into stock_db.sqlite:
  1. 同花顺热点 — hot stocks + theme attribution (zero auth)
  2. 北向资金 — northbound capital flow EOD cumulative (zero auth)
  3. 东财行业板块 — industry ranking + fund flow (rate-limited via em_get)

Idempotent: INSERT OR REPLACE on UNIQUE(trade_date, key) — safe to re-run.

Usage:
    cd backend
    venv/bin/python scripts/sync_market_data.py
    venv/bin/python scripts/sync_market_data.py --date 2026-05-29
    venv/bin/python scripts/sync_market_data.py --date 2026-05-29 --db /other/stock_db.sqlite
    venv/bin/python scripts/sync_market_data.py --init

Backfill a date range:
    for d in 2026-05-{20..29}; do
        venv/bin/python scripts/sync_market_data.py --date "$d" && sleep 2
    done

Cron (weekdays 18:30 Beijing time):
    30 18 * * 1-5 cd /opt/AIpicking/backend && \\
        venv/bin/python scripts/sync_market_data.py >> /var/log/aipicking/ingest.log 2>&1
"""

import argparse
import logging
import os
import random
import psycopg2
import psycopg2.extras
from urllib.parse import urlparse
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# ── Load .env (dev) then .env.production (server override) ──────────────
_ENV_DIR = Path(__file__).resolve().parent.parent  # backend/
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)

DEFAULT_PG_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://aipicking:aipicking_dev_pwd@localhost:5432/aipicking"
).replace("+asyncpg", "").replace("+psycopg2", "")

# ═════════════════════════════════════════════════════════════════════════
# Constants
# ═════════════════════════════════════════════════════════════════════════

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
)

# Eastmoney rate limiting (module-level, serial across all calls)
_em_session: Optional[requests.Session] = None
EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]

# ═════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════

def get_db_connection() -> psycopg2.extensions.connection:
    db_url = DEFAULT_PG_URL.replace("postgresql://", "").replace("postgresql+psycopg2://", "")
    r = urlparse(f"http://{db_url}")
    conn = psycopg2.connect(
        host=r.hostname or "localhost",
        port=r.port or 5432,
        user=r.username or "aipicking",
        password=r.password or "",
        dbname=r.path.lstrip("/") or "aipicking",
    )
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


def _get_em_session() -> requests.Session:
    global _em_session
    if _em_session is None:
        _em_session = requests.Session()
        _em_session.headers.update({"User-Agent": UA})
    return _em_session


def _em_get(url, params=None, headers=None, timeout=15, **kwargs):
    """Eastmoney unified request: auto-throttle + session reuse."""
    session = _get_em_session()
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        merged = {"Referer": "https://data.eastmoney.com/"}
        if headers:
            merged.update(headers)
        return session.get(url, params=params, headers=merged,
                           timeout=timeout, **kwargs)
    finally:
        _em_last_call[0] = time.time()


def _yi(val) -> Optional[float]:
    """Convert yuan → 亿元, None-safe."""
    if val is None:
        return None
    return round(float(val) / 1e8, 2)


# ═════════════════════════════════════════════════════════════════════════
# DDL
# ═════════════════════════════════════════════════════════════════════════

_TABLES = {}  # Tables are now managed by SQLAlchemy ORM (app.models.stock_tables)

def ensure_tables(conn: psycopg2.extensions.connection):
    """Tables are managed by SQLAlchemy ORM — no-op here."""
    pass


# ═════════════════════════════════════════════════════════════════════════
# Fetch: 同花顺热点
# ═════════════════════════════════════════════════════════════════════════

HOT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36",
}


def fetch_hot_stocks(date_str: str) -> list[dict]:
    url = (
        f"http://zx.10jqka.com.cn/event/api/getharden/"
        f"date/{date_str}/orderby/date/orderway/desc/charset/GBK/"
    )
    try:
        r = requests.get(url, headers=HOT_HEADERS, timeout=10)
        r.encoding = "gbk"
        data = r.json()
    except Exception as e:
        logging.warning(f"Hot stocks fetch failed for {date_str}: {e}")
        return []

    if data.get("errocode", 0) != 0:
        logging.warning(f"Hot stocks API error: {data.get('errormsg', '')}")
        return []

    rows = data.get("data") or []
    if not rows:
        logging.info(f"No hot stock data for {date_str} (non-trading day)")
        return []

    stocks = []
    for i, row in enumerate(rows):
        stocks.append({
            "stock_code": row.get("code", ""),
            "stock_name": row.get("name", ""),
            "close": float(row["close"]) if row.get("close") else None,
            "change_amt": float(row["zhangdie"]) if row.get("zhangdie") else None,
            "change_pct": float(row["zhangfu"]) if row.get("zhangfu") else None,
            "turnover_pct": float(row["huanshou"]) if row.get("huanshou") else None,
            "volume": float(row["chengjiaoliang"]) if row.get("chengjiaoliang") else None,
            "amount": float(row["chengjiaoe"]) if row.get("chengjiaoe") else None,
            "reason": row.get("reason", ""),
            "market": row.get("market", ""),
            "dde_net": float(row["ddejingliang"]) if row.get("ddejingliang") else None,
            "sort_order": i + 1,
        })
    return stocks


def extract_themes(stocks: list[dict]) -> list[dict]:
    counter = Counter()
    for s in stocks:
        reason = s.get("reason", "")
        if reason:
            counter.update(t.strip() for t in str(reason).split("+") if t.strip())
    return [{"theme_name": t, "stock_count": n}
            for t, n in counter.most_common()]


# ═════════════════════════════════════════════════════════════════════════
# Fetch: 北向资金
# ═════════════════════════════════════════════════════════════════════════

HSGT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36",
    "Host": "data.hexin.cn",
    "Referer": "https://data.hexin.cn/",
}


def fetch_northbound_flow(date_str: str) -> Optional[dict]:
    url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
    try:
        r = requests.get(url, headers=HSGT_HEADERS, timeout=10)
        d = r.json()
    except Exception as e:
        logging.warning(f"Northbound fetch failed: {e}")
        return None

    times = d.get("time", [])
    hgt = d.get("hgt", [])
    sgt = d.get("sgt", [])

    if not times or not hgt or not sgt:
        logging.info("No northbound data (non-trading day)")
        return None

    hgt_last = sgt_last = None
    for v in reversed(hgt):
        if v is not None:
            hgt_last = float(v)
            break
    for v in reversed(sgt):
        if v is not None:
            sgt_last = float(v)
            break

    if hgt_last is None and sgt_last is None:
        logging.info("No valid northbound values")
        return None

    hgt_val = hgt_last or 0.0
    sgt_val = sgt_last or 0.0
    return {
        "trade_date": date_str,
        "hgt_net_yi": round(hgt_val, 2),
        "sgt_net_yi": round(sgt_val, 2),
        "total_net_yi": round(hgt_val + sgt_val, 2),
        "data_points": len(times),
    }


# ═════════════════════════════════════════════════════════════════════════
# Fetch: 东财行业板块
# ═════════════════════════════════════════════════════════════════════════

def fetch_industry_ranking() -> list[dict]:
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "200", "po": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fs": "m:90+t:2",
        "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
    }
    try:
        r = _em_get(url, params=params, timeout=15)
        d = r.json()
    except Exception as e:
        logging.warning(f"Industry ranking fetch failed: {e}")
        return []

    items = d.get("data", {}).get("diff")
    if not items:
        return []

    rows = []
    for i, item in enumerate(items):
        rows.append({
            "industry_code": item.get("f12", ""),
            "industry_name": item.get("f14", ""),
            "change_pct": item.get("f3"),
            "up_count": item.get("f104"),
            "down_count": item.get("f105"),
            "leader_stock": item.get("f140", ""),
            "leader_change": item.get("f136"),
            "rank": i + 1,
        })
    return rows


def fetch_industry_fund_flow() -> dict:
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "200", "po": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fs": "m:90+t:2",
        "fields": "f12,f14,f62,f184,f66,f72,f78",
    }
    try:
        r = _em_get(url, params=params, timeout=15)
        d = r.json()
    except Exception as e:
        logging.warning(f"Industry fund flow fetch failed: {e}")
        return {}

    items = d.get("data", {}).get("diff")
    if not items:
        return {}

    result = {}
    for item in items:
        code = item.get("f12", "")
        if not code:
            continue
        result[code] = {
            "main_net_yi": _yi(item.get("f62")),
            "super_large_net_yi": _yi(item.get("f184")),
            "large_net_yi": _yi(item.get("f66")),
            "mid_net_yi": _yi(item.get("f72")),
            "small_net_yi": _yi(item.get("f78")),
        }
    return result


def fetch_industry_sectors() -> list[dict]:
    ranking = fetch_industry_ranking()
    if not ranking:
        return []
    time.sleep(0.3)
    fund_flow = fetch_industry_fund_flow()
    for ind in ranking:
        ff = fund_flow.get(ind["industry_code"], {})
        ind.update({k: v for k, v in ff.items() if v is not None})
    return ranking


# ═════════════════════════════════════════════════════════════════════════
# Storage (INSERT OR REPLACE → idempotent)
# ═════════════════════════════════════════════════════════════════════════

_STOCK_INSERT = """
    INSERT INTO daily_hot_stocks
        (trade_date, stock_code, stock_name, close, change_amt, change_pct,
         turnover_pct, volume, amount, reason, market, dde_net, sort_order)
    VALUES (%(trade_date)s, %(stock_code)s, %(stock_name)s, %(close)s, %(change_amt)s,
            %(change_pct)s, %(turnover_pct)s, %(volume)s, %(amount)s, %(reason)s, %(market)s,
            %(dde_net)s, %(sort_order)s)
    ON CONFLICT (trade_date, stock_code) DO UPDATE SET
        close = EXCLUDED.close,
        change_amt = EXCLUDED.change_amt,
        change_pct = EXCLUDED.change_pct,
        turnover_pct = EXCLUDED.turnover_pct,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        reason = EXCLUDED.reason,
        market = EXCLUDED.market,
        dde_net = EXCLUDED.dde_net,
        sort_order = EXCLUDED.sort_order
"""

_THEME_INSERT = """
    INSERT INTO daily_hot_themes
        (trade_date, theme_name, stock_count)
    VALUES (%(trade_date)s, %(theme_name)s, %(stock_count)s)
    ON CONFLICT (trade_date, theme_name) DO UPDATE SET
        stock_count = EXCLUDED.stock_count
"""

_NORTHBOUND_INSERT = """
    INSERT INTO daily_northbound_flow
        (trade_date, hgt_net_yi, sgt_net_yi, total_net_yi, data_points)
    VALUES (%(trade_date)s, %(hgt_net_yi)s, %(sgt_net_yi)s, %(total_net_yi)s, %(data_points)s)
    ON CONFLICT (trade_date) DO UPDATE SET
        hgt_net_yi = EXCLUDED.hgt_net_yi,
        sgt_net_yi = EXCLUDED.sgt_net_yi,
        total_net_yi = EXCLUDED.total_net_yi,
        data_points = EXCLUDED.data_points
"""

_INDUSTRY_INSERT = """
    INSERT INTO daily_industry_flow
        (trade_date, industry_code, industry_name, change_pct, up_count,
         down_count, leader_stock, leader_change, main_net_yi,
         super_large_net_yi, large_net_yi, mid_net_yi, small_net_yi, rank)
    VALUES (%(trade_date)s, %(industry_code)s, %(industry_name)s, %(change_pct)s, %(up_count)s,
            %(down_count)s, %(leader_stock)s, %(leader_change)s, %(main_net_yi)s,
            %(super_large_net_yi)s, %(large_net_yi)s, %(mid_net_yi)s, %(small_net_yi)s, %(rank)s)
    ON CONFLICT (trade_date, industry_code) DO UPDATE SET
        industry_name = EXCLUDED.industry_name,
        change_pct = EXCLUDED.change_pct,
        up_count = EXCLUDED.up_count,
        down_count = EXCLUDED.down_count,
        leader_stock = EXCLUDED.leader_stock,
        leader_change = EXCLUDED.leader_change,
        main_net_yi = EXCLUDED.main_net_yi,
        super_large_net_yi = EXCLUDED.super_large_net_yi,
        large_net_yi = EXCLUDED.large_net_yi,
        mid_net_yi = EXCLUDED.mid_net_yi,
        small_net_yi = EXCLUDED.small_net_yi,
        rank = EXCLUDED.rank
"""


def _save_hot_stocks(conn, date_str, stocks):
    rows = [dict(s, trade_date=date_str) for s in stocks]
    conn.executemany(_STOCK_INSERT, rows)
    conn.commit()
    logging.info(f"Saved {len(rows)} hot stocks for {date_str}")
    return len(rows)


def _save_hot_themes(conn, date_str, themes):
    rows = [{"trade_date": date_str, "theme_name": t["theme_name"],
             "stock_count": t["stock_count"]} for t in themes]
    conn.executemany(_THEME_INSERT, rows)
    conn.commit()
    logging.info(f"Saved {len(rows)} hot themes for {date_str}")
    return len(rows)


def _save_northbound(conn, date_str, data):
    conn.execute(_NORTHBOUND_INSERT, {**data, "trade_date": date_str})
    conn.commit()
    direction = "流入" if data["total_net_yi"] >= 0 else "流出"
    logging.info(f"Saved northbound: 沪{data['hgt_net_yi']:+.2f} "
                 f"深{data['sgt_net_yi']:+.2f} 合计{direction}{abs(data['total_net_yi']):.2f}亿")
    return True


def _save_industry(conn, date_str, sectors):
    rows = []
    for ind in sectors:
        rows.append({
            "trade_date": date_str,
            "industry_code": ind.get("industry_code", ""),
            "industry_name": ind.get("industry_name", ""),
            "change_pct": ind.get("change_pct"),
            "up_count": ind.get("up_count"),
            "down_count": ind.get("down_count"),
            "leader_stock": ind.get("leader_stock", ""),
            "leader_change": ind.get("leader_change"),
            "main_net_yi": ind.get("main_net_yi"),
            "super_large_net_yi": ind.get("super_large_net_yi"),
            "large_net_yi": ind.get("large_net_yi"),
            "mid_net_yi": ind.get("mid_net_yi"),
            "small_net_yi": ind.get("small_net_yi"),
            "rank": ind.get("rank"),
        })
    conn.executemany(_INDUSTRY_INSERT, rows)
    conn.commit()
    logging.info(f"Saved {len(rows)} industry sectors for {date_str}")
    return len(rows)


# ═════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═════════════════════════════════════════════════════════════════════════

def sync(date_str: Optional[str] = None) -> dict:
    """Fetch + store all 3 data sources. Best-effort per source."""
    if date_str is None:
        date_str = date.today().strftime("%Y-%m-%d")

    result = {
        "date": date_str,
        "hot_stocks_count": 0,
        "themes_count": 0,
        "northbound": False,
        "industry_count": 0,
        "errors": [],
    }

    conn = get_db_connection()
    try:
        ensure_tables(conn)

        # 1. Hot stocks + themes
        try:
            stocks = fetch_hot_stocks(date_str)
            if stocks:
                _save_hot_stocks(conn, date_str, stocks)
                result["hot_stocks_count"] = len(stocks)
                themes = extract_themes(stocks)
                if themes:
                    _save_hot_themes(conn, date_str, themes)
                    result["themes_count"] = len(themes)
        except Exception as e:
            result["errors"].append(f"hot_stocks: {e}")
            logging.error(f"hot_stocks failed: {e}")

        # 2. Northbound
        try:
            nb = fetch_northbound_flow(date_str)
            if nb:
                _save_northbound(conn, date_str, nb)
                result["northbound"] = True
        except Exception as e:
            result["errors"].append(f"northbound: {e}")
            logging.error(f"northbound failed: {e}")

        # 3. Industry sectors
        try:
            sectors = fetch_industry_sectors()
            if sectors:
                _save_industry(conn, date_str, sectors)
                result["industry_count"] = len(sectors)
        except Exception as e:
            result["errors"].append(f"industry: {e}")
            logging.error(f"industry failed: {e}")

    finally:
        conn.close()

    logging.info(
        f"Sync {date_str} complete: "
        f"stocks={result['hot_stocks_count']} themes={result['themes_count']} "
        f"northbound={'✓' if result['northbound'] else '✗'} "
        f"industries={result['industry_count']}"
    )
    return result


# ═════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="Daily A-share market data sync")
    p.add_argument("--date", default=None, help="Trade date YYYY-MM-DD (default: today)")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    result = sync(date_str=args.date)

    print()
    print("=" * 50)
    print(f"  Sync Report — {result['date']}")
    print("=" * 50)
    print(f"  Hot stocks:       {result['hot_stocks_count']:>5d}")
    print(f"  Themes:           {result['themes_count']:>5d}")
    print(f"  Northbound flow:  {'✓' if result['northbound'] else '✗':>5s}")
    print(f"  Industry sectors: {result['industry_count']:>5d}")
    if result["errors"]:
        print(f"  Errors:           {len(result['errors']):>5d}")
        for e in result["errors"]:
            print(f"    - {e}")
    print("=" * 50)


if __name__ == "__main__":
    main()
