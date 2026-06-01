"""
Daily A-share market data sync — standalone script, zero dependency on the app.

Fetches and stores into PostgreSQL:
  1. 同花顺热点 — hot stocks + theme attribution (zero auth)
  2. 北向资金 — northbound capital flow EOD cumulative (zero auth)
  3. 东财板块 — industry + concept sector ranking & fund flow (rate-limited via em_get)

Idempotent: INSERT ... ON CONFLICT DO UPDATE — safe to re-run.

Writes to tables:
  - daily_hot_stocks, daily_hot_themes (同花顺)
  - daily_northbound_flow (北向资金)
  - daily_sector_flow (东财板块 — industry + concept)

Tables are managed by SQLAlchemy ORM (app/models/stock_tables.py);
this script does NOT create tables — they must already exist.

Usage:
    cd backend
    venv/bin/python scripts/sync_market_data.py
    venv/bin/python scripts/sync_market_data.py --date 2026-05-29
    venv/bin/python scripts/sync_market_data.py --pg-url postgresql://...

Cron (weekdays 18:30 Beijing time):
    30 18 * * 1-5 cd /opt/AIpicking/backend && \
        venv/bin/python scripts/sync_market_data.py >> /var/log/aipicking/ingest.log 2>&1
"""

import argparse
import itertools
import logging
import os
import random
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

# ── Load .env (dev) then .env.production (server override) ──────────────
_ENV_DIR = Path(__file__).resolve().parent.parent  # backend/
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)


# ═════════════════════════════════════════════════════════════════════════
# PostgreSQL connection
# ═════════════════════════════════════════════════════════════════════════

def _parse_pg_url(url: str) -> dict:
    """Parse DATABASE_URL into psycopg2 connection parameters."""
    url = url.replace("+asyncpg", "").replace("+psycopg2", "")
    if "://" not in url:
        url = f"postgresql://{url}"
    r = urlparse(url)
    return {
        "host": r.hostname or "localhost",
        "port": r.port or 5432,
        "user": r.username or "aipicking",
        "password": r.password or "",
        "dbname": r.path.lstrip("/") or "aipicking",
    }


_default_db = os.getenv("DATABASE_URL", "")
if not _default_db:
    _user = os.getenv("DB_USER", "aipicking")
    _pass = os.getenv("DB_PASSWORD", "")
    _host = os.getenv("DB_HOST", "localhost")
    _port = os.getenv("DB_PORT", "5432")
    _name = os.getenv("DB_NAME", "aipicking")
    _default_db = f"postgresql://{_user}:{_pass}@{_host}:{_port}/{_name}"
_PG_PARAMS = _parse_pg_url(_default_db)


def get_conn():
    """Get a new PostgreSQL connection."""
    return psycopg2.connect(**_PG_PARAMS)


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
EM_MIN_INTERVAL = 1.5        # base interval for dataapi requests (less strict than push2)
EM_MAX_RETRIES = 3           # retry on block/429
EM_BLOCK_BACKOFF = (30, 120) # seconds to wait when blocked (min, max)

_em_last_call = [0.0]
_sector_pre_delayed = False  # ensure pre-delay only runs once per sync

# Sector filter codes for dataapi (same format as push2, but dataapi works)
SECTOR_TYPES = {
    "industry": "m:90+s:4",   # 行业板块
    "concept":  "m:90+s:3",   # 概念板块
}

# ═════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════

def _get_em_session() -> requests.Session:
    """Lazy-init shared session (headers set per-request for anti-fingerprinting)."""
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
# Fetch: 东财板块（行业 + 概念）—  via dataapi (push2 is TLS-fingerprint-gated)
# ═════════════════════════════════════════════════════════════════════════
#
# push2.eastmoney.com now blocks non-browser TLS fingerprints even from within
# China, so we use data.eastmoney.com/dataapi/bkzj/getbkzj instead.
#
# The dataapi endpoint returns only {f12, f13, f14, <key>} per call, where
# <key> selects which extra field to return and sort by.  We make one call
# with key=f62 (主力净流入 → ranking) plus additional calls for change_pct,
# fund-flow breakdown, leader stock, up/down count — then merge by sector code.

# Base URL for the working dataapi endpoint (replaces push2)
_DATAAPI_URL = "https://data.eastmoney.com/dataapi/bkzj/getbkzj"

# Keys we fetch from dataapi and their mapping to our output fields.
# (key, output_field, unit_converter) — converter=None means raw value.
_DATAAPI_KEYS = [
    ("f62", "main_net_yi",       _yi),                        # 主力净流入 元→亿
    ("f3",  "change_pct",        lambda v: round(float(v) / 100, 2) if v is not None else None),  # ×100 → %
    ("f66", "large_net_yi",      _yi),                        # 大单净流入
    ("f72", "mid_net_yi",        _yi),                        # 中单净流入
    ("f78", "small_net_yi",      _yi),                        # 小单净流入
    ("f184","super_large_net_yi",lambda v: round(float(v) / 100, 2) if v is not None else None),  # ×100 → 亿
    ("f104","up_count",          lambda v: int(float(v)) if v is not None else None),
    ("f105","down_count",        lambda v: int(float(v)) if v is not None else None),
    ("f204","leader_stock",      None),                       # 领涨股名称
]


def _dataapi_get(code: str, key: str) -> dict:
    """Fetch all sectors from dataapi, return dict keyed by sector code (f12).

    Args:
        code: filter code, e.g. 'm:90+s:4' (industry) or 'm:90+s:3' (concept)
        key:  field to sort by / include, e.g. 'f62' for main net flow
    """
    try:
        r = _em_get(_DATAAPI_URL, params={
            "key": key, "code": code, "pz": "200", "pn": "1"
        }, timeout=15)
        d = r.json()
    except Exception as e:
        logging.warning(f"dataapi failed (code={code}, key={key}): {e}")
        return {}

    items = d.get("data", {}).get("diff")
    if not items:
        return {}
    return {item["f12"]: item for item in items}


def fetch_sectors(sector_type: str) -> list[dict]:
    """Fetch sector data via dataapi — multiple key calls merged by sector code.

    Args:
        sector_type: 'industry' (m:90+s:4) or 'concept' (m:90+s:3).
    """
    code = SECTOR_TYPES.get(sector_type)
    if not code:
        logging.warning(f"Unknown sector_type: {sector_type}")
        return []

    _sector_pre_delay()

    # Primary call: sorted by main net flow (f62) — determines ranking order
    primary = _dataapi_get(code, "f62")
    if not primary:
        logging.warning(f"No sector data for {sector_type} (code={code})")
        return []

    # Fetch additional fields in parallel-minded sequence
    aux = {}
    for key, _out_field, _converter in _DATAAPI_KEYS:
        if key == "f62":
            continue  # already fetched as primary
        data = _dataapi_get(code, key)
        if data:
            aux[key] = data
        time.sleep(random.uniform(0.3, 1.0))  # gentle gap between calls

    # Merge: primary dict order = ranking (descending by f62)
    rows = []
    for rank_i, (sector_code, item) in enumerate(primary.items()):
        row = {
            "sector_code": sector_code,
            "sector_name": item.get("f14", ""),
            "sector_type": sector_type,
            "rank": rank_i + 1,
        }

        # Merge all auxiliary fields
        for key, out_field, converter in _DATAAPI_KEYS:
            # Get value from primary or auxiliary data
            val = None
            if key == "f62":
                src = item
            else:
                src = aux.get(key, {}).get(sector_code) or {}
            val = src.get(key) if src else None

            if val is not None and converter is not None:
                try:
                    val = converter(val)
                except (ValueError, TypeError):
                    val = None
            row[out_field] = val

        # Compute net_inflow = main + large + mid + small
        components = [
            row.get(k) or 0.0
            for k in ("main_net_yi", "large_net_yi", "mid_net_yi", "small_net_yi")
        ]
        row["net_inflow"] = round(sum(components), 2)

        # leader_change not directly available in dataapi
        row.setdefault("leader_change", None)

        rows.append(row)

    logging.info(
        f"Fetched {len(rows)} {sector_type} sectors "
        f"(top: {rows[0]['sector_name']} {rows[0]['net_inflow']:.1f}亿)"
        if rows else f"No {sector_type} sector data"
    )
    return rows


# ═════════════════════════════════════════════════════════════════════════
# Storage (INSERT ... ON CONFLICT DO UPDATE → idempotent)
# ═════════════════════════════════════════════════════════════════════════

_STOCK_UPSERT = """
    INSERT INTO daily_hot_stocks
        (trade_date, stock_code, stock_name, close, change_amt, change_pct,
         turnover_pct, volume, amount, reason, market, dde_net, sort_order)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (trade_date, stock_code) DO UPDATE SET
        stock_name   = EXCLUDED.stock_name,
        close        = EXCLUDED.close,
        change_amt   = EXCLUDED.change_amt,
        change_pct   = EXCLUDED.change_pct,
        turnover_pct = EXCLUDED.turnover_pct,
        volume       = EXCLUDED.volume,
        amount       = EXCLUDED.amount,
        reason       = EXCLUDED.reason,
        market       = EXCLUDED.market,
        dde_net      = EXCLUDED.dde_net,
        sort_order   = EXCLUDED.sort_order
"""

_THEME_UPSERT = """
    INSERT INTO daily_hot_themes (trade_date, theme_name, stock_count)
    VALUES (%s, %s, %s)
    ON CONFLICT (trade_date, theme_name) DO UPDATE SET
        stock_count = EXCLUDED.stock_count
"""

_NORTHBOUND_UPSERT = """
    INSERT INTO daily_northbound_flow
        (trade_date, hgt_net_yi, sgt_net_yi, total_net_yi, data_points)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (trade_date) DO UPDATE SET
        hgt_net_yi   = EXCLUDED.hgt_net_yi,
        sgt_net_yi   = EXCLUDED.sgt_net_yi,
        total_net_yi = EXCLUDED.total_net_yi,
        data_points  = EXCLUDED.data_points
"""

_SECTOR_UPSERT = """
    INSERT INTO daily_sector_flow
        (trade_date, sector_type, sector_code, sector_name, change_pct,
         up_count, down_count, leader_stock, leader_change, main_net_yi,
         super_large_net_yi, large_net_yi, mid_net_yi, small_net_yi,
         net_inflow, rank)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (trade_date, sector_type, sector_code) DO UPDATE SET
        sector_name        = EXCLUDED.sector_name,
        change_pct         = EXCLUDED.change_pct,
        up_count           = EXCLUDED.up_count,
        down_count         = EXCLUDED.down_count,
        leader_stock       = EXCLUDED.leader_stock,
        leader_change      = EXCLUDED.leader_change,
        main_net_yi        = EXCLUDED.main_net_yi,
        super_large_net_yi = EXCLUDED.super_large_net_yi,
        large_net_yi       = EXCLUDED.large_net_yi,
        mid_net_yi         = EXCLUDED.mid_net_yi,
        small_net_yi       = EXCLUDED.small_net_yi,
        net_inflow         = EXCLUDED.net_inflow,
        rank               = EXCLUDED.rank
"""

_STOCK_COLS = (
    "trade_date", "stock_code", "stock_name", "close", "change_amt",
    "change_pct", "turnover_pct", "volume", "amount", "reason", "market",
    "dde_net", "sort_order",
)

_SECTOR_COLS = (
    "trade_date", "sector_type", "sector_code", "sector_name", "change_pct",
    "up_count", "down_count", "leader_stock", "leader_change", "main_net_yi",
    "super_large_net_yi", "large_net_yi", "mid_net_yi", "small_net_yi",
    "net_inflow", "rank",
)


def _save_hot_stocks(date_str: str, stocks: list[dict]) -> int:
    rows = [tuple([dict(s, trade_date=date_str).get(c) for c in _STOCK_COLS]) for s in stocks]
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, _STOCK_UPSERT, rows)
        conn.commit()
    finally:
        conn.close()
    logging.info(f"Saved {len(rows)} hot stocks for {date_str}")
    return len(rows)


def _save_hot_themes(date_str: str, themes: list[dict]) -> int:
    rows = [(date_str, t["theme_name"], t["stock_count"]) for t in themes]
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, _THEME_UPSERT, rows)
        conn.commit()
    finally:
        conn.close()
    logging.info(f"Saved {len(rows)} hot themes for {date_str}")
    return len(rows)


def _save_northbound(date_str: str, data: dict) -> bool:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(_NORTHBOUND_UPSERT, (
                date_str,
                data["hgt_net_yi"],
                data["sgt_net_yi"],
                data["total_net_yi"],
                data["data_points"],
            ))
        conn.commit()
    finally:
        conn.close()
    direction = "流入" if data["total_net_yi"] >= 0 else "流出"
    logging.info(f"Saved northbound: 沪{data['hgt_net_yi']:+.2f} "
                 f"深{data['sgt_net_yi']:+.2f} 合计{direction}{abs(data['total_net_yi']):.2f}亿")
    return True


def _save_sectors(date_str: str, sectors: list[dict]) -> int:
    """Save sector data to daily_sector_flow. Returns count inserted."""
    rows = []
    for item in sectors:
        row = tuple(item.get(c) for c in _SECTOR_COLS)
        # trade_date is first column — patch from date_str
        rows.append((date_str,) + row[1:])

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, _SECTOR_UPSERT, rows)
        conn.commit()
    finally:
        conn.close()
    logging.info(f"Saved {len(rows)} {sectors[0].get('sector_type', '?')} sectors "
                  f"for {date_str}" if sectors else f"Saved 0 sectors for {date_str}")
    return len(rows)


# ═════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═════════════════════════════════════════════════════════════════════════

def sync(date_str: Optional[str] = None) -> dict:
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

    # 1. Hot stocks + themes
    try:
        stocks = fetch_hot_stocks(date_str)
        if stocks:
            _save_hot_stocks(date_str, stocks)
            result["hot_stocks_count"] = len(stocks)
            themes = extract_themes(stocks)
            if themes:
                _save_hot_themes(date_str, themes)
                result["themes_count"] = len(themes)
    except Exception as e:
        result["errors"].append(f"hot_stocks: {e}")
        logging.error(f"hot_stocks failed: {e}")

    # 2. Northbound
    try:
        nb = fetch_northbound_flow(date_str)
        if nb:
            _save_northbound(date_str, nb)
            result["northbound"] = True
    except Exception as e:
        result["errors"].append(f"northbound: {e}")
        logging.error(f"northbound failed: {e}")

    # 3. Industry sectors (东财, rate-limited)
    try:
        industries = fetch_sectors("industry")
        if industries:
            _save_sectors(date_str, industries)
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
            _save_sectors(date_str, concepts)
            result["concept_count"] = len(concepts)
    except Exception as e:
        result["errors"].append(f"concept_sectors: {e}")
        logging.error(f"concept sectors failed: {e}")

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
    p = argparse.ArgumentParser(description="Daily A-share market data sync (PostgreSQL)")
    p.add_argument("--date", default=None,
                   help="Trade date YYYY-MM-DD (default: today)")
    p.add_argument("--pg-url", default=None,
                   help="PostgreSQL connection URL (default: $DATABASE_URL)")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    # Allow runtime override of PG connection
    if args.pg_url:
        global _PG_PARAMS
        _PG_PARAMS = _parse_pg_url(args.pg_url)

    date_str = args.date or date.today().strftime("%Y-%m-%d")

    result = sync(date_str=date_str)

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
