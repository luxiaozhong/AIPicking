"""
Daily A-share market data sync — standalone script, zero dependency on the app.

Fetches and stores into stock_db.sqlite:
  1. 同花顺热点 — hot stocks + theme attribution (zero auth)
  2. 北向资金 — northbound capital flow EOD cumulative (zero auth)
  3. 东财板块 — industry + concept sector ranking & fund flow (rate-limited via em_get)

Idempotent: INSERT OR REPLACE on UNIQUE(trade_date, key) — safe to re-run.

Replaces the old ``sector_flow`` table with ``daily_sector_flow``:
  - Adds ``sector_type`` column ('industry' / 'concept')
  - Adds ``net_inflow`` = main + large + mid + small (亿元)
  - Covers both industry (m:90+t:2) and concept (m:90+t:3) sectors

Usage:
    cd backend
    venv/bin/python scripts/sync_market_data.py
    venv/bin/python scripts/sync_market_data.py --date 2026-05-29
    venv/bin/python scripts/sync_market_data.py --db /other/stock_db.sqlite
    venv/bin/python scripts/sync_market_data.py --init

Cron (weekdays 18:30 Beijing time):
    30 18 * * 1-5 cd /opt/AIpicking/backend && \\
        venv/bin/python scripts/sync_market_data.py >> /var/log/aipicking/ingest.log 2>&1
"""

import argparse
import itertools
import logging
import os
import random
import sqlite3
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

DEFAULT_STOCK_DB = os.getenv(
    "STOCK_DB_PATH", "/opt/stock_data/stock_db.sqlite"
)

# ═════════════════════════════════════════════════════════════════════════
# Constants
# ═════════════════════════════════════════════════════════════════════════

# Rotating User-Agent pool — randomize per request to evade fingerprinting
_UA_POOL = [
    # macOS Chrome
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Windows Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Windows Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    # Linux Chrome
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]
_UA_CYCLE = itertools.cycle(_UA_POOL)

# Accept-Language variants (rotated to look like different users)
_ACCEPT_LANG_POOL = [
    "zh-CN,zh;q=0.9,en;q=0.8",
    "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "zh-CN,zh;q=0.9",
]

_em_session: Optional[requests.Session] = None
EM_MIN_INTERVAL = 3.0        # base interval between Eastmoney requests (was 1.0)
EM_MAX_RETRIES = 3           # retry on block/429
EM_BLOCK_BACKOFF = (30, 120) # seconds to wait when blocked (min, max)

_em_last_call = [0.0]
_sector_pre_delayed = False  # ensure pre-delay only runs once per sync

# Sector types for Eastmoney push2 API
SECTOR_TYPES = {
    "industry": "m:90+t:2",   # 行业板块
    "concept":  "m:90+t:3",   # 概念板块
}

# ═════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════

def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_STOCK_DB
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _get_em_session() -> requests.Session:
    """Lazy-init shared session for connection reuse (headers set per-request)."""
    global _em_session
    if _em_session is None:
        _em_session = requests.Session()
    return _em_session


def _build_browser_headers(extra: Optional[dict] = None) -> dict:
    """Build realistic browser headers with random fingerprinting."""
    h = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": random.choice(_ACCEPT_LANG_POOL),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://data.eastmoney.com/",
        "Sec-Fetch-Dest": "script",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": next(_UA_CYCLE),
    }
    if extra:
        h.update(extra)
    return h


def _em_get(url, params=None, headers=None, timeout=15, retry_on_block=True, **kwargs):
    """Eastmoney unified request with enhanced anti-detection.

    Features:
      - 3+ second base interval with random jitter (0.5–2.5s)
      - Rotating User-Agent + Accept-Language per request
      - Full browser-mimicking headers (Sec-Fetch-*, etc.)
      - Auto-detect blocks (403 / "频率" / "IP") and retry with exponential
        backoff (30–120s base, ×2 per attempt)
      - Session reuse for connection pooling (headers per-request to avoid
        fingerprinting)
    """
    session = _get_em_session()

    # Enforce base interval + jitter
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait)
    # Additional random jitter to break pattern detection
    time.sleep(random.uniform(0.5, 2.5))

    merged = _build_browser_headers(headers)

    last_exc = None
    for attempt in range(EM_MAX_RETRIES):
        try:
            resp = session.get(url, params=params, headers=merged,
                               timeout=timeout, **kwargs)
        except requests.RequestException as e:
            last_exc = e
            logging.warning(f"Eastmoney request failed (attempt {attempt+1}/{EM_MAX_RETRIES}): {e}")
            if attempt < EM_MAX_RETRIES - 1:
                backoff = EM_BLOCK_BACKOFF[0] * (2 ** attempt) + random.uniform(0, 10)
                logging.info(f"Retrying in {backoff:.0f}s...")
                time.sleep(backoff)
                merged = _build_browser_headers(headers)  # fresh fingerprint
            continue

        # Check for block signals
        if resp.status_code in (403, 429):
            logging.warning(
                f"Eastmoney returned {resp.status_code} "
                f"(attempt {attempt+1}/{EM_MAX_RETRIES})"
            )
            if attempt < EM_MAX_RETRIES - 1 and retry_on_block:
                backoff = EM_BLOCK_BACKOFF[0] * (2 ** attempt) + random.uniform(0, 10)
                logging.info(f"Blocked — waiting {backoff:.0f}s before retry...")
                time.sleep(backoff)
                merged = _build_browser_headers(headers)  # fresh fingerprint
                continue

        # Check response body for ban keywords (东财 sometimes returns 200 but
        # the body contains a ban page)
        text_sample = (resp.text or "")[:500]
        ban_keywords = ["访问频率", "IP", "被封", "验证码", "频繁", "您访问过于"]
        if any(kw in text_sample for kw in ban_keywords):
            logging.warning(
                f"Eastmoney response contains ban keyword "
                f"(attempt {attempt+1}/{EM_MAX_RETRIES})"
            )
            if attempt < EM_MAX_RETRIES - 1 and retry_on_block:
                backoff = EM_BLOCK_BACKOFF[0] * (2 ** attempt) + random.uniform(0, 10)
                logging.info(f"Blocked — waiting {backoff:.0f}s before retry...")
                time.sleep(backoff)
                merged = _build_browser_headers(headers)

        _em_last_call[0] = time.time()
        return resp

    # All retries exhausted
    if last_exc:
        raise last_exc
    # Return the last response even if it was a block (caller decides)
    _em_last_call[0] = time.time()
    return resp  # type: ignore[possibly-unbound]


def _sector_pre_delay():
    """One-time random delay before the first Eastmoney sector request.

    Breaks the predictable cron-triggered pattern — the actual request time
    varies by 10–60 seconds each run.
    """
    global _sector_pre_delayed
    if not _sector_pre_delayed:
        delay = random.uniform(10, 60)
        logging.info(f"Sector pre-delay: {delay:.0f}s (breaking cron pattern)...")
        time.sleep(delay)
        _sector_pre_delayed = True


def _yi(val) -> Optional[float]:
    """Convert yuan to yi (100M). None-safe."""
    if val is None:
        return None
    return round(float(val) / 1e8, 2)


# ═════════════════════════════════════════════════════════════════════════
# DDL
# ═════════════════════════════════════════════════════════════════════════

_TABLES = {
    "daily_hot_stocks": """
        CREATE TABLE IF NOT EXISTS daily_hot_stocks (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date    TEXT    NOT NULL,
            stock_code    TEXT    NOT NULL,
            stock_name    TEXT    NOT NULL,
            close         REAL,
            change_amt    REAL,
            change_pct    REAL,
            turnover_pct  REAL,
            volume        REAL,
            amount        REAL,
            reason        TEXT,
            market        TEXT,
            dde_net       REAL,
            sort_order    INTEGER,
            created_at    TEXT    DEFAULT (datetime('now', 'localtime')),
            UNIQUE(trade_date, stock_code)
        )
    """,
    "daily_hot_themes": """
        CREATE TABLE IF NOT EXISTS daily_hot_themes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date    TEXT    NOT NULL,
            theme_name    TEXT    NOT NULL,
            stock_count   INTEGER NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now', 'localtime')),
            UNIQUE(trade_date, theme_name)
        )
    """,
    "daily_northbound_flow": """
        CREATE TABLE IF NOT EXISTS daily_northbound_flow (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date    TEXT    NOT NULL,
            hgt_net_yi    REAL,
            sgt_net_yi    REAL,
            total_net_yi  REAL,
            data_points   INTEGER,
            created_at    TEXT    DEFAULT (datetime('now', 'localtime')),
            UNIQUE(trade_date)
        )
    """,
    "daily_sector_flow": """
        CREATE TABLE IF NOT EXISTS daily_sector_flow (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date        TEXT    NOT NULL,
            sector_type       TEXT    NOT NULL,
            sector_code       TEXT    NOT NULL,
            sector_name       TEXT    NOT NULL,
            change_pct        REAL,
            up_count          INTEGER,
            down_count        INTEGER,
            leader_stock      TEXT,
            leader_change     REAL,
            main_net_yi       REAL,
            super_large_net_yi REAL,
            large_net_yi      REAL,
            mid_net_yi        REAL,
            small_net_yi      REAL,
            net_inflow        REAL,
            rank              INTEGER,
            created_at        TEXT    DEFAULT (datetime('now', 'localtime')),
            UNIQUE(trade_date, sector_type, sector_code)
        )
    """,
}

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_hot_stocks_date ON daily_hot_stocks(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_hot_stocks_code ON daily_hot_stocks(stock_code)",
    "CREATE INDEX IF NOT EXISTS idx_hot_stocks_reason ON daily_hot_stocks(reason)",
    "CREATE INDEX IF NOT EXISTS idx_hot_themes_date ON daily_hot_themes(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_hot_themes_name ON daily_hot_themes(theme_name)",
    "CREATE INDEX IF NOT EXISTS idx_northbound_date ON daily_northbound_flow(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_dsf_date ON daily_sector_flow(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_dsf_type ON daily_sector_flow(sector_type)",
    "CREATE INDEX IF NOT EXISTS idx_dsf_code ON daily_sector_flow(sector_type, sector_code)",
    "CREATE INDEX IF NOT EXISTS idx_dsf_name ON daily_sector_flow(sector_type, sector_name)",
]


def ensure_tables(conn: sqlite3.Connection):
    for ddl in _TABLES.values():
        conn.execute(ddl)
    for idx in _INDEXES:
        conn.execute(idx)


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
# Fetch: 东财板块（行业 + 概念）
# ═════════════════════════════════════════════════════════════════════════

# Common fields for both ranking + fund flow
_SECTOR_RANK_FIELDS = (
    "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207"
)
_SECTOR_FLOW_FIELDS = "f12,f14,f62,f184,f66,f72,f78"


def _fetch_sector_ranking(fs_filter: str) -> list[dict]:
    """Fetch sector ranking for a given Eastmoney filter string."""
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "200", "po": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fs": fs_filter,
        "fields": _SECTOR_RANK_FIELDS,
    }
    try:
        r = _em_get(url, params=params, timeout=15)
        d = r.json()
    except Exception as e:
        logging.warning(f"Sector ranking fetch failed ({fs_filter}): {e}")
        return []

    items = d.get("data", {}).get("diff")
    if not items:
        return []

    rows = []
    for i, item in enumerate(items):
        rows.append({
            "sector_code": item.get("f12", ""),
            "sector_name": item.get("f14", ""),
            "change_pct": item.get("f3"),
            "up_count": item.get("f104"),
            "down_count": item.get("f105"),
            "leader_stock": item.get("f140", ""),
            "leader_change": item.get("f136"),
            "rank": i + 1,
        })
    return rows


def _fetch_sector_fund_flow(fs_filter: str) -> dict:
    """Fetch sector fund flow for a given Eastmoney filter string."""
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "200", "po": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fs": fs_filter,
        "fields": _SECTOR_FLOW_FIELDS,
    }
    try:
        r = _em_get(url, params=params, timeout=15)
        d = r.json()
    except Exception as e:
        logging.warning(f"Sector fund flow fetch failed ({fs_filter}): {e}")
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


def fetch_sectors(sector_type: str) -> list[dict]:
    """Fetch sector ranking + fund flow for a given sector type.

    Args:
        sector_type: 'industry' (m:90+t:2) or 'concept' (m:90+t:3).

    Returns merged list of dicts ready for insertion into daily_sector_flow.
    """
    fs_filter = SECTOR_TYPES.get(sector_type)
    if not fs_filter:
        logging.warning(f"Unknown sector_type: {sector_type}")
        return []

    # One-time random pre-delay before first Eastmoney sector request
    _sector_pre_delay()

    ranking = _fetch_sector_ranking(fs_filter)
    if not ranking:
        return []

    # Longer delay between ranking and fund flow (was 0.3s — too fast)
    gap = random.uniform(2.0, 5.0)
    logging.debug(f"Waiting {gap:.1f}s before fund flow request for {sector_type}...")
    time.sleep(gap)

    fund_flow = _fetch_sector_fund_flow(fs_filter)

    for item in ranking:
        ff = fund_flow.get(item["sector_code"], {})
        # Merge fund flow fields
        for k in ("main_net_yi", "super_large_net_yi", "large_net_yi",
                  "mid_net_yi", "small_net_yi"):
            if k not in item and k in ff:
                item[k] = ff[k]
        # Compute net_inflow = main + large + mid + small
        vals = [item.get(k) or 0.0 for k in
                ("main_net_yi", "large_net_yi", "mid_net_yi", "small_net_yi")]
        item["net_inflow"] = round(sum(v for v in vals if v), 2)
        item["sector_type"] = sector_type

    return ranking


# ═════════════════════════════════════════════════════════════════════════
# Storage (INSERT OR REPLACE → idempotent)
# ═════════════════════════════════════════════════════════════════════════

_STOCK_INSERT = """
    INSERT OR REPLACE INTO daily_hot_stocks
        (trade_date, stock_code, stock_name, close, change_amt, change_pct,
         turnover_pct, volume, amount, reason, market, dde_net, sort_order)
    VALUES (:trade_date, :stock_code, :stock_name, :close, :change_amt,
            :change_pct, :turnover_pct, :volume, :amount, :reason, :market,
            :dde_net, :sort_order)
"""

_THEME_INSERT = """
    INSERT OR REPLACE INTO daily_hot_themes
        (trade_date, theme_name, stock_count)
    VALUES (:trade_date, :theme_name, :stock_count)
"""

_NORTHBOUND_INSERT = """
    INSERT OR REPLACE INTO daily_northbound_flow
        (trade_date, hgt_net_yi, sgt_net_yi, total_net_yi, data_points)
    VALUES (:trade_date, :hgt_net_yi, :sgt_net_yi, :total_net_yi, :data_points)
"""

_SECTOR_INSERT = """
    INSERT OR REPLACE INTO daily_sector_flow
        (trade_date, sector_type, sector_code, sector_name, change_pct,
         up_count, down_count, leader_stock, leader_change, main_net_yi,
         super_large_net_yi, large_net_yi, mid_net_yi, small_net_yi,
         net_inflow, rank)
    VALUES (:trade_date, :sector_type, :sector_code, :sector_name, :change_pct,
            :up_count, :down_count, :leader_stock, :leader_change, :main_net_yi,
            :super_large_net_yi, :large_net_yi, :mid_net_yi, :small_net_yi,
            :net_inflow, :rank)
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


def _save_sectors(conn, date_str, sectors):
    """Save sector data to daily_sector_flow. Returns count inserted."""
    rows = []
    for item in sectors:
        rows.append({
            "trade_date": date_str,
            "sector_type": item.get("sector_type", ""),
            "sector_code": item.get("sector_code", ""),
            "sector_name": item.get("sector_name", ""),
            "change_pct": item.get("change_pct"),
            "up_count": item.get("up_count"),
            "down_count": item.get("down_count"),
            "leader_stock": item.get("leader_stock", ""),
            "leader_change": item.get("leader_change"),
            "main_net_yi": item.get("main_net_yi"),
            "super_large_net_yi": item.get("super_large_net_yi"),
            "large_net_yi": item.get("large_net_yi"),
            "mid_net_yi": item.get("mid_net_yi"),
            "small_net_yi": item.get("small_net_yi"),
            "net_inflow": item.get("net_inflow"),
            "rank": item.get("rank"),
        })
    conn.executemany(_SECTOR_INSERT, rows)
    conn.commit()
    logging.info(f"Saved {len(rows)} {sectors[0].get('sector_type', '?')} sectors "
                  f"for {date_str}" if sectors else f"Saved 0 sectors for {date_str}")
    return len(rows)


# ═════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═════════════════════════════════════════════════════════════════════════

def sync(date_str: Optional[str] = None, db_path: Optional[str] = None) -> dict:
    """Fetch + store all data sources. Best-effort per source."""
    if date_str is None:
        date_str = date.today().strftime("%Y-%m-%d")

    result = {
        "date": date_str,
        "hot_stocks_count": 0,
        "themes_count": 0,
        "northbound": False,
        "industry_count": 0,
        "concept_count": 0,
        "errors": [],
    }

    conn = get_db_connection(db_path)
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

        # 3. Industry sectors (东财, rate-limited)
        try:
            industries = fetch_sectors("industry")
            if industries:
                _save_sectors(conn, date_str, industries)
                result["industry_count"] = len(industries)
        except Exception as e:
            result["errors"].append(f"industry_sectors: {e}")
            logging.error(f"industry sectors failed: {e}")

        # Extra gap between industry and concept fetches
        # (different fs filter, but same push2 endpoint — looks like a burst)
        if industries:
            gap = random.uniform(3.0, 8.0)
            logging.info(f"Waiting {gap:.1f}s before concept sector fetch...")
            time.sleep(gap)

        # 4. Concept sectors (东财, rate-limited)
        try:
            concepts = fetch_sectors("concept")
            if concepts:
                _save_sectors(conn, date_str, concepts)
                result["concept_count"] = len(concepts)
        except Exception as e:
            result["errors"].append(f"concept_sectors: {e}")
            logging.error(f"concept sectors failed: {e}")

    finally:
        conn.close()

    logging.info(
        f"Sync {date_str} complete: "
        f"stocks={result['hot_stocks_count']} themes={result['themes_count']} "
        f"northbound={'ok' if result['northbound'] else 'no'} "
        f"industries={result['industry_count']} concepts={result['concept_count']}"
    )
    return result


# ═════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="Daily A-share market data sync")
    p.add_argument("--date", default=None,
                   help="Trade date YYYY-MM-DD (default: today)")
    p.add_argument("--db", default=None, help="Stock DB path override")
    p.add_argument("--init", action="store_true",
                   help="Create tables only, no fetch")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    date_str = args.date or date.today().strftime("%Y-%m-%d")

    conn = get_db_connection(args.db)
    try:
        ensure_tables(conn)
        conn.commit()
    finally:
        conn.close()

    if args.init:
        logging.info(
            f"Tables created in {args.db or DEFAULT_STOCK_DB}. Done."
        )
        return

    result = sync(date_str=date_str, db_path=args.db)

    print()
    print("=" * 50)
    print(f"  Sync Report — {result['date']}")
    print("=" * 50)
    print(f"  Hot stocks:       {result['hot_stocks_count']:>5d}")
    print(f"  Themes:           {result['themes_count']:>5d}")
    print(f"  Northbound flow:  {'ok' if result['northbound'] else 'no':>5s}")
    print(f"  Industry sectors: {result['industry_count']:>5d}")
    print(f"  Concept sectors:  {result['concept_count']:>5d}")
    if result["errors"]:
        print(f"  Errors:           {len(result['errors']):>5d}")
        for e in result["errors"]:
            print(f"    - {e}")
    print("=" * 50)


if __name__ == "__main__":
    main()
