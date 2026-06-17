#!/usr/bin/env python3
"""
指数成分股资金流向同步 — 腾讯自选股 via westock-data-clawhub npm 包

与 sync_stock_fund_flow.py 的区别：
  - 不拉全市场 5000+ 只股票，只拉指定指数的成分股（默认 100 只）
  - 股票列表来自 index_constituents 表（最新生效日），JOIN stocks 表获取带交易所后缀的 ts_code
  - 适合盘中高频刷新（秒级完成）

数据源：proxy.finance.qq.com（通过 westock-data-clawhub@1.0.4 npm CLI 代理）
表：daily_stock_fund_flow（与全市场 sync 共用，ON CONFLICT DO UPDATE 幂等）

Usage:
    cd backend
    venv/bin/python scripts/sync_index_fund_flow.py --index 980080 --date 2026-06-16
    venv/bin/python scripts/sync_index_fund_flow.py --index 980080 --date 2026-06-16 --dry-run --log-level DEBUG
    venv/bin/python scripts/sync_index_fund_flow.py --index 980080 --date 2026-06-16 --batch-size 100

Cron:
    # 盘中每 5 分钟刷新国证成长100 资金流（9:30-15:00）
    */5 9-14 * * 1-5 cd /opt/AIpicking/backend && \
        venv/bin/python scripts/sync_index_fund_flow.py --index 980080 --date $(date +\%Y-\%m-\%d) >> /var/log/aipicking/index_fund_flow.log 2>&1
    # 收盘后最终同步
    30 15 * * 1-5 cd /opt/AIpicking/backend && \
        venv/bin/python scripts/sync_index_fund_flow.py --index 980080 --date $(date +\%Y-\%m-\%d) >> /var/log/aipicking/index_fund_flow.log 2>&1
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import random
import re
import subprocess
import sys
import time
from datetime import date as date_type, datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
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

NPM_PACKAGE = "westock-data-clawhub@1.0.4"
BATCH_SIZE = 50
BATCH_DELAY_BASE = 1.0        # base delay between batches (seconds) — shorter for small sets
BATCH_DELAY_JITTER = 0.5      # random jitter on top of base delay
BATCH_TIMEOUT = 120            # subprocess timeout per batch (seconds)
MAX_RETRIES = 2                # retry attempts for transient failures
RETRY_BACKOFF = (3, 10)        # (min, max) retry backoff seconds


# ═════════════════════════════════════════════════════════════════════════
# Stock code conversion
# ═════════════════════════════════════════════════════════════════════════

_MARKET_TO_PREFIX = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
_PREFIX_TO_MARKET = {"sh": "SH", "sz": "SZ", "bj": "BJ"}

# 股票代码前缀 → 交易所推断（用于 stocks 表匹配失败的 fallback）
_CODE_PREFIX_MARKET = {}
# 6xxxxx → SH（沪市主板）
_CODE_PREFIX_MARKET.update({str(i): "SH" for i in range(600000, 700000, 100000)})
# 9xxxxx → SH（沪市科创板试验）
_CODE_PREFIX_MARKET.update({str(i): "SH" for i in range(900000, 1000000, 100000)})
# 0xxxxx → SZ（深市主板）
_CODE_PREFIX_MARKET.update({str(i): "SZ" for i in range(0, 100000, 100000)})
# 3xxxxx → SZ（创业板）
_CODE_PREFIX_MARKET.update({str(i): "SZ" for i in range(300000, 400000, 100000)})
# 2xxxxx → SZ（深市中小板遗留）
_CODE_PREFIX_MARKET.update({str(i): "SZ" for i in range(200000, 300000, 100000)})
# 8xxxxx → BJ（北交所）
_CODE_PREFIX_MARKET.update({str(i): "BJ" for i in range(800000, 900000, 100000)})
# 4xxxxx → BJ（北交所）
_CODE_PREFIX_MARKET.update({str(i): "BJ" for i in range(400000, 500000, 100000)})


def _infer_exchange(code: str) -> str:
    """根据股票代码前缀推断交易所后缀。

    600xxx/601xxx/603xxx/605xxx/9xxxxx → SH
    000xxx/001xxx/002xxx/003xxx/300xxx → SZ
    8xxxxx/4xxxxx → BJ
    """
    if len(code) != 6 or not code.isdigit():
        return "SZ"  # fallback
    prefix = int(code)
    if 600000 <= prefix < 700000 or 900000 <= prefix < 1000000:
        return "SH"
    elif 0 <= prefix < 400000 or 200000 <= prefix < 300000:
        return "SZ"
    elif 800000 <= prefix < 900000 or 400000 <= prefix < 500000:
        return "BJ"
    return "SZ"


def ts_code_to_npm(ts_code: str) -> str:
    """Convert DB ts_code (600519.SH) to npm CLI format (sh600519)."""
    code, market = ts_code.rsplit(".", 1)
    prefix = _MARKET_TO_PREFIX.get(market.upper(), "sz")
    return f"{prefix}{code}"


def npm_to_ts_code(npm_code: str) -> str:
    """Reverse: npm CLI format → DB ts_code."""
    prefix = npm_code[:2].lower()
    code = npm_code[2:]
    market = _PREFIX_TO_MARKET.get(prefix, "SZ")
    return f"{code}.{market}"


# ═════════════════════════════════════════════════════════════════════════
# Index constituent stock loader
# ═════════════════════════════════════════════════════════════════════════

def load_index_stocks(index_code: str):
    """Load constituent stocks for a given index from index_constituents.

    JOINs the stocks table to get ts_code with exchange suffix (.SH/.SZ/.BJ).
    Falls back to inferring exchange from code prefix if stock is missing from
    the stocks table.

    Returns:
        list of dict: [{"ts_code": "600519.SH", "stock_name": "贵州茅台"}, ...]
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 取最新生效日的成分股，JOIN stocks 获取带后缀的 ts_code
            cur.execute(
                """
                SELECT ic.ts_code AS raw_code, ic.stock_name,
                       s.ts_code AS full_ts_code
                FROM index_constituents ic
                LEFT JOIN stocks s ON (s.ts_code LIKE ic.ts_code || '.%%' OR s.ts_code = ic.ts_code)
                WHERE ic.index_code = %s
                  AND ic.eff_date = (
                      SELECT MAX(eff_date) FROM index_constituents
                      WHERE index_code = %s
                  )
                ORDER BY ic.weight DESC NULLS LAST
                """,
                (index_code, index_code),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    stocks = []
    missing = 0
    for raw_code, name, full_ts_code in rows:
        if full_ts_code:
            stocks.append({"ts_code": full_ts_code, "stock_name": name})
        else:
            # Fallback: 根据代码前缀推断交易所
            exchange = _infer_exchange(raw_code)
            inferred = f"{raw_code}.{exchange}"
            logging.debug(
                "Stock %s (%s) not in stocks table, inferred ts_code %s",
                raw_code, name, inferred,
            )
            stocks.append({"ts_code": inferred, "stock_name": name})
            missing += 1

    if missing:
        logging.warning(
            "%d/%d constituents not found in stocks table — exchange inferred",
            missing, len(stocks),
        )

    return stocks


# ═════════════════════════════════════════════════════════════════════════
# Markdown table parser
# ═════════════════════════════════════════════════════════════════════════

# npm CLI output column → DB column mapping
_COLUMN_MAP = {
    "BlockNetFlow":           ("block_net_flow",           float),
    "BlockTradingInfos":      ("block_trading_infos",       str),
    "ClosePrice":             ("close_price",               float),
    "EndDate":                ("end_date",                  str),
    "FwdClosePrice":          ("fwd_close_price",           float),
    "JumboNetFlow":           ("jumbo_net_flow",            float),
    "LastestTradedPrice":     ("lastest_traded_price",      float),
    "LhbTradingDetails":      ("lhb_trading_details",       str),
    "LhbInfos":               ("lhb_infos",                 str),
    "MainInFlow":             ("main_in_flow",              float),
    "MainInflowCircRate":     ("main_inflow_circ_rate",     float),
    "MainInflowIndustryRank": ("main_inflow_industry_rank", int),
    "MainInflowRank":         ("main_inflow_rank",          int),
    "MainNetFlow":            ("main_net_flow",             float),
    "MainNetFlow10D":         ("main_net_flow_10d",         float),
    "MainNetFlow20D":         ("main_net_flow_20d",         float),
    "MainNetFlow5D":          ("main_net_flow_5d",          float),
    "MainOutFlow":            ("main_out_flow",             float),
    "MarginTradeInfos":       ("margin_trade_infos",        str),
    "MidNetFlow":             ("mid_net_flow",              float),
    "RetailInFlow":           ("retail_in_flow",            float),
    "RetailOutFlow":          ("retail_out_flow",           float),
    "SecuCode":               ("secu_code",                 str),
    "SmallNetFlow":           ("small_net_flow",            float),
    "code":                   ("secu_code",                 str),
    "symbol":                 ("secu_code",                 str),
}


def _parse_value(raw: str, converter):
    """Parse a single cell value. Empty / whitespace-only → None."""
    val = raw.strip()
    if not val or val == "-":
        return None
    if converter is str:
        return val
    try:
        return converter(val)
    except (ValueError, TypeError):
        return None


def parse_markdown_table(output: str) -> list[dict]:
    """Parse the npm CLI markdown table output into a list of dicts."""
    lines = output.strip().split("\n")
    if not lines:
        return []

    # Find header row
    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and not stripped.startswith("|---"):
            if any(known in stripped for known in ("MainNetFlow", "SecuCode", "code")):
                header_idx = i
                break

    if header_idx is None:
        logging.warning("No markdown table header found in npm CLI output")
        return []

    # Parse header columns
    header_cells = [c.strip() for c in lines[header_idx].strip().strip("|").split("|")]
    col_map = {}
    for idx, name in enumerate(header_cells):
        if name in _COLUMN_MAP:
            col_map[idx] = _COLUMN_MAP[name]
        else:
            logging.debug(f"Unknown column in markdown table: '{name}'")

    if not col_map:
        logging.warning("No known columns matched in markdown header: %s", header_cells)
        return []

    # Parse data rows
    rows = []
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cleaned = stripped.replace("|", "").replace("-", "").replace(" ", "")
        if not cleaned:
            continue

        cells = [c.strip() for c in stripped.strip().strip("|").split("|")]
        row = {}
        for idx, (db_col, converter) in col_map.items():
            if idx < len(cells):
                row[db_col] = _parse_value(cells[idx], converter)

        if any(v is not None for v in row.values()):
            rows.append(row)

    return rows


# ═════════════════════════════════════════════════════════════════════════
# npm CLI runner
# ═════════════════════════════════════════════════════════════════════════

def run_npm_batch(npm_codes: list[str], date_str: str) -> list[dict]:
    """Run npx westock-data-clawhub for a batch of stocks.

    Returns parsed rows (with DB column names), or empty list on failure.
    """
    codes_arg = ",".join(npm_codes)
    cmd = ["npx", NPM_PACKAGE, "asfund", codes_arg, "--date", date_str]

    logging.debug(f"Running: {' '.join(cmd[:5])}... ({len(npm_codes)} stocks)")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=BATCH_TIMEOUT,
            env={**os.environ, "NODE_NO_WARNINGS": "1"},
        )
    except subprocess.TimeoutExpired:
        logging.error(f"npm CLI timed out after {BATCH_TIMEOUT}s "
                      f"for batch of {len(npm_codes)} stocks")
        return []
    except FileNotFoundError:
        logging.error("npx not found — is Node.js installed?")
        return []
    except Exception as e:
        logging.error(f"npm CLI subprocess error: {e}")
        return []

    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-300:]
        logging.error(f"npm CLI exited with code {result.returncode}: {stderr_tail}")
        return []

    stdout = result.stdout or ""
    if not stdout.strip():
        logging.warning("npm CLI returned empty output")
        return []

    rows = parse_markdown_table(stdout)
    if not rows:
        snippet = stdout.strip()[:500]
        logging.warning(f"Parsed 0 rows from npm output. Snippet: {snippet}")

    return rows


# ═════════════════════════════════════════════════════════════════════════
# Table DDL (idempotent safety net)
# ═════════════════════════════════════════════════════════════════════════

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS daily_stock_fund_flow (
    id              SERIAL PRIMARY KEY,
    created_at      TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai'),
    updated_at      TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai'),

    trade_date              VARCHAR(10)  NOT NULL,
    ts_code                 VARCHAR(20)  NOT NULL,

    main_net_flow           DOUBLE PRECISION,
    jumbo_net_flow          DOUBLE PRECISION,
    block_net_flow          DOUBLE PRECISION,
    mid_net_flow            DOUBLE PRECISION,
    small_net_flow          DOUBLE PRECISION,
    main_in_flow            DOUBLE PRECISION,
    main_out_flow           DOUBLE PRECISION,
    retail_in_flow          DOUBLE PRECISION,
    retail_out_flow         DOUBLE PRECISION,

    main_net_flow_5d        DOUBLE PRECISION,
    main_net_flow_10d       DOUBLE PRECISION,
    main_net_flow_20d       DOUBLE PRECISION,

    main_inflow_circ_rate   DOUBLE PRECISION,
    main_inflow_rank        INTEGER,
    main_inflow_industry_rank INTEGER,

    close_price             DOUBLE PRECISION,
    fwd_close_price         DOUBLE PRECISION,
    lastest_traded_price    DOUBLE PRECISION,
    end_date                VARCHAR(10),
    secu_code               VARCHAR(20),

    block_trading_infos     TEXT,
    margin_trade_infos      TEXT,
    lhb_trading_details     TEXT,
    lhb_infos               TEXT,

    CONSTRAINT uq_stock_fund_flow UNIQUE (trade_date, ts_code)
);

CREATE INDEX IF NOT EXISTS idx_sff_date ON daily_stock_fund_flow (trade_date);
CREATE INDEX IF NOT EXISTS idx_sff_code ON daily_stock_fund_flow (ts_code);
"""


def ensure_table():
    """Create the daily_stock_fund_flow table if it doesn't exist."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(_CREATE_TABLE_SQL)
        conn.commit()
        logging.info("Table daily_stock_fund_flow ensured")
    finally:
        conn.close()


# ═════════════════════════════════════════════════════════════════════════
# Intraday snapshot table — for bar chart race replay
# ═════════════════════════════════════════════════════════════════════════

_CREATE_SNAPSHOT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS intraday_fund_snapshot (
    id              BIGSERIAL PRIMARY KEY,
    trade_date      VARCHAR(10) NOT NULL,
    snapshot_time   TIMESTAMPTZ NOT NULL DEFAULT (now() AT TIME ZONE 'Asia/Shanghai'),
    ts_code         VARCHAR(20) NOT NULL,
    main_net_flow   DOUBLE PRECISION,
    jumbo_net_flow  DOUBLE PRECISION,
    block_net_flow  DOUBLE PRECISION,
    main_net_flow_5d DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_ifs_date_time
    ON intraday_fund_snapshot (trade_date, snapshot_time);
CREATE INDEX IF NOT EXISTS idx_ifs_code
    ON intraday_fund_snapshot (ts_code);
"""

_SNAPSHOT_INSERT = """
INSERT INTO intraday_fund_snapshot
    (trade_date, snapshot_time, ts_code, index_code,
     main_net_flow, jumbo_net_flow, block_net_flow, main_net_flow_5d)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def ensure_snapshot_table():
    """Create the intraday_fund_snapshot table if it doesn't exist, or migrate."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(_CREATE_SNAPSHOT_TABLE_SQL)
            # Migration: add main_net_flow_5d column if missing (pre-existing table)
            cur.execute(
                "ALTER TABLE intraday_fund_snapshot "
                "ADD COLUMN IF NOT EXISTS main_net_flow_5d DOUBLE PRECISION"
            )
            # Migration: add index_code column to distinguish snapshots from different indices
            cur.execute(
                "ALTER TABLE intraday_fund_snapshot "
                "ADD COLUMN IF NOT EXISTS index_code VARCHAR(20)"
            )
        conn.commit()
        logging.info("Table intraday_fund_snapshot ensured")
    finally:
        conn.close()


def _compute_real_5d_flows(date_str: str, ts_codes: list[str]) -> dict[str, float]:
    """Compute the real 5-day rolling sum of main_net_flow for each stock.

    Queries daily_stock_fund_flow for the last 5 trading days (including date_str)
    and sums main_net_flow per stock.  Falls back to the API field for stocks with
    insufficient history.
    """
    if not ts_codes:
        return {}

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Find the 5 most recent trading days up to and including date_str
            cur.execute(
                """
                SELECT DISTINCT trade_date
                FROM daily_stock_fund_flow
                WHERE trade_date <= %s
                ORDER BY trade_date DESC
                LIMIT 5
                """,
                (date_str,),
            )
            trading_dates = [r[0] for r in cur.fetchall()]
            if not trading_dates:
                return {}

            # Sum main_net_flow for each ts_code over these 5 trading days
            cur.execute(
                """
                SELECT ts_code, COALESCE(SUM(main_net_flow), 0) AS flow_5d
                FROM daily_stock_fund_flow
                WHERE ts_code = ANY(%s) AND trade_date = ANY(%s)
                GROUP BY ts_code
                """,
                (ts_codes, trading_dates),
            )
            result = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
            logging.debug(
                "Computed real 5d flows for %d/%d stocks over %s..%s",
                len(result), len(ts_codes),
                trading_dates[-1], trading_dates[0],
            )
            return result
    finally:
        conn.close()


def save_snapshots(date_str: str, index_code: str, snapshot_rows: list[dict]) -> int:
    """Save intraday snapshots for bar chart race replay.

    Each row should have: ts_code, main_net_flow, jumbo_net_flow, block_net_flow.
    The main_net_flow_5d is computed from the DB (real 5-day rolling sum),
    not from the potentially inaccurate API field.

    All rows share the same snapshot_time (now).
    The index_code is stored to distinguish snapshots from different indices.

    Auto-cleans snapshots older than 3 days, preserving recent data for replay.
    """
    if not snapshot_rows:
        return 0

    # Compute real 5-day rolling sums from actual daily data
    ts_codes = [r["ts_code"] for r in snapshot_rows if r.get("ts_code")]
    real_5d = _compute_real_5d_flows(date_str, ts_codes)

    snapshot_time = datetime.now()
    tuples = [
        (
            date_str,
            snapshot_time,
            r["ts_code"],
            index_code,
            r.get("main_net_flow"),
            r.get("jumbo_net_flow"),
            r.get("block_net_flow"),
            real_5d.get(r["ts_code"]) if r.get("ts_code") in real_5d
                else r.get("main_net_flow_5d"),  # fallback to API field
        )
        for r in snapshot_rows
    ]

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 保留最近 3 天数据，清理更早的快照
            cutoff = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=3)).strftime("%Y-%m-%d")
            cur.execute(
                "SELECT 1 FROM intraday_fund_snapshot WHERE trade_date < %s LIMIT 1",
                (cutoff,),
            )
            if cur.fetchone():
                cur.execute(
                    "DELETE FROM intraday_fund_snapshot WHERE trade_date < %s",
                    (cutoff,),
                )
            psycopg2.extras.execute_batch(cur, _SNAPSHOT_INSERT, tuples)
        conn.commit()
        logging.info(
            "Snapshots saved: %d rows at %s",
            len(tuples),
            snapshot_time.strftime("%H:%M:%S"),
        )
    finally:
        conn.close()

    return len(tuples)


# ═════════════════════════════════════════════════════════════════════════
# Storage
# ═════════════════════════════════════════════════════════════════════════

_FUND_FLOW_UPSERT = """
INSERT INTO daily_stock_fund_flow
    (trade_date, ts_code,
     main_net_flow, jumbo_net_flow, block_net_flow, mid_net_flow,
     small_net_flow, main_in_flow, main_out_flow, retail_in_flow,
     retail_out_flow, main_net_flow_5d, main_net_flow_10d,
     main_net_flow_20d, main_inflow_circ_rate, main_inflow_rank,
     main_inflow_industry_rank, close_price, fwd_close_price,
     lastest_traded_price, end_date, secu_code,
     block_trading_infos, margin_trade_infos, lhb_trading_details,
     lhb_infos)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (trade_date, ts_code) DO UPDATE SET
    main_net_flow           = EXCLUDED.main_net_flow,
    jumbo_net_flow          = EXCLUDED.jumbo_net_flow,
    block_net_flow          = EXCLUDED.block_net_flow,
    mid_net_flow            = EXCLUDED.mid_net_flow,
    small_net_flow          = EXCLUDED.small_net_flow,
    main_in_flow            = EXCLUDED.main_in_flow,
    main_out_flow           = EXCLUDED.main_out_flow,
    retail_in_flow          = EXCLUDED.retail_in_flow,
    retail_out_flow         = EXCLUDED.retail_out_flow,
    main_net_flow_5d        = EXCLUDED.main_net_flow_5d,
    main_net_flow_10d       = EXCLUDED.main_net_flow_10d,
    main_net_flow_20d       = EXCLUDED.main_net_flow_20d,
    main_inflow_circ_rate   = EXCLUDED.main_inflow_circ_rate,
    main_inflow_rank        = EXCLUDED.main_inflow_rank,
    main_inflow_industry_rank = EXCLUDED.main_inflow_industry_rank,
    close_price             = EXCLUDED.close_price,
    fwd_close_price         = EXCLUDED.fwd_close_price,
    lastest_traded_price    = EXCLUDED.lastest_traded_price,
    end_date                = EXCLUDED.end_date,
    secu_code               = EXCLUDED.secu_code,
    block_trading_infos     = EXCLUDED.block_trading_infos,
    margin_trade_infos      = EXCLUDED.margin_trade_infos,
    lhb_trading_details     = EXCLUDED.lhb_trading_details,
    lhb_infos               = EXCLUDED.lhb_infos
"""

_UPSERT_COLS = (
    "trade_date", "ts_code",
    "main_net_flow", "jumbo_net_flow", "block_net_flow", "mid_net_flow",
    "small_net_flow", "main_in_flow", "main_out_flow", "retail_in_flow",
    "retail_out_flow", "main_net_flow_5d", "main_net_flow_10d",
    "main_net_flow_20d", "main_inflow_circ_rate", "main_inflow_rank",
    "main_inflow_industry_rank", "close_price", "fwd_close_price",
    "lastest_traded_price", "end_date", "secu_code",
    "block_trading_infos", "margin_trade_infos", "lhb_trading_details",
    "lhb_infos",
)


def save_batch(date_str: str, rows: list[dict]) -> int:
    """Save a batch of fund flow rows to PostgreSQL.

    Each row dict must have DB column names as keys.
    The trade_date and ts_code are injected before saving.
    Returns number of rows saved.
    """
    if not rows:
        return 0

    tuples = []
    for row in rows:
        if "ts_code" not in row:
            secu = row.get("secu_code", "")
            if secu:
                row["ts_code"] = npm_to_ts_code(secu)
            else:
                logging.warning(f"Row without secu_code, skipping: {row}")
                continue
        row["trade_date"] = date_str
        tup = tuple(row.get(c) for c in _UPSERT_COLS)
        tuples.append(tup)

    if not tuples:
        return 0

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, _FUND_FLOW_UPSERT, tuples)
        conn.commit()
    finally:
        conn.close()

    return len(tuples)


# ═════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═════════════════════════════════════════════════════════════════════════

def sync(date_str: str, index_code: str, batch_size: int = BATCH_SIZE,
         dry_run: bool = False) -> dict:
    """Main sync: load index constituents, batch-call npm CLI, save to DB.

    Args:
        date_str:   Trade date YYYY-MM-DD
        index_code: Index code (e.g. '980080' for 国证成长100)
        batch_size: Stocks per npm CLI call (default 50)
        dry_run:    If True, print plan but don't execute

    Returns:
        {"date": str, "index_code": str, "index_name": str,
         "total_stocks": int, "batches": int,
         "success_batches": int, "fail_batches": int,
         "total_saved": int, "elapsed_s": float, "errors": list[str]}
    """
    # 1. Load index constituents
    logging.info(f"Loading constituents for index {index_code}...")
    stocks_info = load_index_stocks(index_code)

    total_stocks = len(stocks_info)
    if total_stocks == 0:
        logging.error(f"No constituents found for index {index_code}")
        return {"date": date_str, "index_code": index_code,
                "total_stocks": 0, "errors": ["Empty constituents"]}

    # Get index name for reporting
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT full_name FROM index_info WHERE index_code = %s",
                (index_code,),
            )
            row = cur.fetchone()
            index_name = row[0] if row else index_code
    finally:
        conn.close()

    stocks = [s["ts_code"] for s in stocks_info]
    npm_codes = [ts_code_to_npm(ts) for ts in stocks]
    total_batches = math.ceil(len(npm_codes) / batch_size)

    logging.info(
        f"指数: {index_name} ({index_code}) | "
        f"成分股: {total_stocks} | 批次: {total_batches} (batch_size={batch_size})"
    )

    if dry_run:
        logging.info(f"[DRY RUN] Would run {total_batches} batches "
                     f"(~{total_batches * (BATCH_DELAY_BASE + 1):.0f}s)")
        for i in range(0, min(3, len(npm_codes)), 1):
            batch = npm_codes[i:i + batch_size]
            codes_preview = ",".join(batch[:3])
            if len(batch) > 3:
                codes_preview += f",... ({len(batch)} total)"
            logging.info(f"[DRY RUN] Batch {i+1}: npx {NPM_PACKAGE} asfund "
                         f"{codes_preview} --date {date_str}")
        # Print constituent list
        logging.info(f"[DRY RUN] Constituents (top 10 by weight):")
        for s in stocks_info[:10]:
            logging.info(f"  {s['ts_code']}  {s['stock_name']}")
        if len(stocks_info) > 10:
            logging.info(f"  ... and {len(stocks_info) - 10} more")
        return {"date": date_str, "index_code": index_code,
                "index_name": index_name, "total_stocks": total_stocks,
                "batches": total_batches, "total_saved": 0,
                "mode": "dry_run"}

    # 2. Run batches
    success_batches = 0
    fail_batches = 0
    total_saved = 0
    errors = []
    snapshot_rows: list[dict] = []  # accumulate for intraday snapshot

    start_time = time.time()

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(npm_codes))
        batch = npm_codes[start:end]
        batch_num = batch_idx + 1

        # Try with retries
        rows = []
        for attempt in range(MAX_RETRIES + 1):
            try:
                rows = run_npm_batch(batch, date_str)
                if rows:
                    break
            except Exception as e:
                logging.warning(f"Batch {batch_num}/{total_batches} "
                                f"attempt {attempt+1} failed: {e}")
            if attempt < MAX_RETRIES:
                backoff = random.uniform(*RETRY_BACKOFF)
                logging.info(f"Retrying batch {batch_num} in {backoff:.0f}s...")
                time.sleep(backoff)

        if not rows:
            fail_batches += 1
            first_stock = stocks_info[start] if start < len(stocks_info) else {"ts_code": "?"}
            last_stock = stocks_info[end - 1] if end - 1 < len(stocks_info) else {"ts_code": "?"}
            err_msg = (f"Batch {batch_num}/{total_batches} "
                       f"({first_stock['ts_code']}…{last_stock['ts_code']}) "
                       f"failed after {MAX_RETRIES + 1} attempts")
            errors.append(err_msg)
            logging.error(err_msg)
            continue

        # Convert npm_code → ts_code for each row
        for row in rows:
            if "ts_code" not in row and "secu_code" in row:
                row["ts_code"] = npm_to_ts_code(row["secu_code"])

        # Validate: API may return previous trading day's data for non-trading days
        sample_end_date = rows[0].get("end_date", "") if rows else ""
        if sample_end_date and sample_end_date != date_str:
            logging.warning(
                f"Batch {batch_num}/{total_batches}: EndDate mismatch — "
                f"requested {date_str}, API returned {sample_end_date}. "
                f"Non-trading day, skipping."
            )
            continue

        # Save this batch immediately
        try:
            saved = save_batch(date_str, rows)
            total_saved += saved
            success_batches += 1
            # Accumulate snapshot rows for intraday replay
            for row in rows:
                ts = row.get("ts_code", "")
                if ts:
                    snapshot_rows.append({
                        "ts_code": ts,
                        "main_net_flow": row.get("main_net_flow"),
                        "jumbo_net_flow": row.get("jumbo_net_flow"),
                        "block_net_flow": row.get("block_net_flow"),
                        "main_net_flow_5d": row.get("main_net_flow_5d"),
                    })
            first_stock = stocks_info[start] if start < len(stocks_info) else {"ts_code": "?"}
            last_stock = stocks_info[end - 1] if end - 1 < len(stocks_info) else {"ts_code": "?"}
            logging.info(
                f"Batch {batch_num}/{total_batches}: "
                f"{len(rows)} parsed, {saved} saved "
                f"({first_stock['ts_code']} … {last_stock['ts_code']})"
            )
        except Exception as e:
            fail_batches += 1
            err_msg = f"Batch {batch_num} save failed: {e}"
            errors.append(err_msg)
            logging.error(err_msg)

        # Inter-batch delay (except after last batch)
        if batch_num < total_batches:
            delay = BATCH_DELAY_BASE + random.uniform(0, BATCH_DELAY_JITTER)
            time.sleep(delay)

    elapsed = time.time() - start_time

    # 3. Save intraday snapshots for bar chart race replay
    snapshot_count = 0
    try:
        snapshot_count = save_snapshots(date_str, index_code, snapshot_rows)
    except Exception as e:
        logging.error(f"Failed to save intraday snapshots: {e}")

    logging.info(
        f"Sync complete: {total_saved} rows saved in {elapsed:.0f}s "
        f"({success_batches}/{total_batches} batches OK, "
        f"{fail_batches} failed)"
    )

    return {
        "date": date_str,
        "index_code": index_code,
        "index_name": index_name,
        "total_stocks": total_stocks,
        "batches": total_batches,
        "success_batches": success_batches,
        "fail_batches": fail_batches,
        "total_saved": total_saved,
        "snapshots_saved": snapshot_count,
        "elapsed_s": round(elapsed, 1),
        "errors": errors,
    }


# ═════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════

def sync_self(date_str: str, index_codes_str: str, batch_size: int = 50,
              dry_run: bool = False) -> dict:
    """Sync fund flow for market indices treated as single entities.

    Unlike the normal constituent-based sync, this fetches each index itself
    (e.g. sh000001 上证指数, sz399006 创业板指) as if it were a stock.
    No constituent expansion, no intraday snapshots.

    Args:
        index_codes_str: Comma-separated index codes (e.g. "000001,399006,000688")
    """
    codes = [c.strip() for c in index_codes_str.split(",") if c.strip()]
    if not codes:
        return {"date": date_str, "total_saved": 0, "errors": ["No index codes"]}

    # Convert to npm format — if already has sh/sz prefix, use directly
    npm_codes = []
    for c in codes:
        if c.lower().startswith(("sh", "sz", "bj")):
            npm_codes.append(c.lower())
        else:
            npm_codes.append(ts_code_to_npm(f"{c}.{_infer_exchange(c)}"))
    logging.info("指数自身资金流同步: %d 个指数", len(codes))

    if dry_run:
        for nc in npm_codes:
            logging.info("[DRY RUN] npx %s asfund %s --date %s", NPM_PACKAGE, nc, date_str)
        return {"date": date_str, "total": len(codes), "total_saved": 0, "mode": "dry_run"}

    # Batch into groups
    total_batches = math.ceil(len(npm_codes) / batch_size)
    all_rows = []
    success_batches = 0
    errors = []

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(npm_codes))
        batch = npm_codes[start:end]

        rows = []
        for attempt in range(MAX_RETRIES + 1):
            try:
                rows = run_npm_batch(batch, date_str)
                if rows:
                    break
            except Exception as e:
                logging.warning("Batch %d attempt %d failed: %s", batch_idx + 1, attempt + 1, e)
            if attempt < MAX_RETRIES:
                time.sleep(random.uniform(*RETRY_BACKOFF))

        if not rows:
            errors.append(f"Batch {batch_idx+1} failed after {MAX_RETRIES+1} attempts")
            continue

        # Validate end_date
        sample_end_date = rows[0].get("end_date", "")
        if sample_end_date and sample_end_date != date_str:
            logging.warning("Batch %d EndDate mismatch — requested %s, got %s. Skipping.",
                           batch_idx + 1, date_str, sample_end_date)
            continue

        # Convert npm_code → ts_code
        for row in rows:
            if "ts_code" not in row and "secu_code" in row:
                row["ts_code"] = npm_to_ts_code(row["secu_code"])

        all_rows.extend(rows)
        success_batches += 1

    # Save all at once
    saved = save_batch(date_str, all_rows) if all_rows else 0
    logging.info("Market indices fund flow: %d rows saved (%d/%d batches OK)",
                saved, success_batches, total_batches)

    return {
        "date": date_str,
        "total": len(codes),
        "batches": total_batches,
        "success_batches": success_batches,
        "total_saved": saved,
        "errors": errors,
    }


def main():
    p = argparse.ArgumentParser(
        description="指数成分股资金流向同步 — 腾讯自选股 via westock-data-clawhub")
    p.add_argument("--index", required=True,
                   help="指数代码，如 980080（国证成长100）")
    p.add_argument("--date", default=None,
                   help="交易日期 YYYY-MM-DD（默认: 今天，盘后自动取最近交易日）")
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                   help=f"每批股票数量（默认 {BATCH_SIZE}，指数成分股少可设 100）")
    p.add_argument("--dry-run", action="store_true",
                   help="仅打印计划，不实际执行")
    p.add_argument("--self", action="store_true", dest="self_mode",
                   help="指数自身模式：把指数代码当个股直接拉，不展开成分股")
    p.add_argument("--pg-url", default=None,
                   help="PostgreSQL 连接 URL（默认: $DATABASE_URL）")
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

    date_str = args.date
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    # Validate date format
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        logging.error(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")
        sys.exit(1)

    # Reject weekends — A-share market closed, no fund flow data generated
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    if target_date.isoweekday() >= 6:
        if args.date is None:
            days_back = target_date.isoweekday() - 5
            target_date = target_date - timedelta(days=days_back)
            date_str = target_date.strftime("%Y-%m-%d")
            logging.info(
                "Default date fell on weekend, using previous trading day: %s",
                date_str,
            )
        else:
            logging.error(
                f"{date_str} is a weekend (%s), A-share market closed — "
                "no fund flow data available. Refusing to sync.",
                target_date.strftime("%A"),
            )
            sys.exit(1)

    # 1. Ensure tables exist
    try:
        ensure_table()
        ensure_snapshot_table()
    except Exception as e:
        logging.error(f"Failed to ensure table: {e}")
        sys.exit(1)

    # 2. Run sync
    if args.self_mode:
        result = sync_self(date_str=date_str, index_codes_str=args.index,
                           batch_size=args.batch_size, dry_run=args.dry_run)
    else:
        result = sync(date_str=date_str, index_code=args.index,
                      batch_size=args.batch_size, dry_run=args.dry_run)

    # 3. Report
    print()
    print("=" * 60)
    if args.self_mode:
        print(f"  市场指数自身资金流同步报告")
    else:
        print(f"  指数成分股资金流向同步报告")
    print("=" * 60)
    if args.self_mode:
        print(f"  指数数量:      {result.get('total', 0):>6d}")
    else:
        print(f"  指数:          {result.get('index_name', args.index)} ({args.index})")
    print(f"  日期:          {result['date']}")
    if result.get("mode") == "dry_run":
        print(f"  [DRY RUN] 计划导入: {result.get('total', result.get('total_stocks', 0))} 条")
        print(f"  [DRY RUN] 批次数:   {result.get('batches', 1)}")
    else:
        if args.self_mode:
            print(f"  批次数:        {result.get('batches', 0):>6d}")
        else:
            print(f"  成分股数:      {result.get('total_stocks', 0):>6d}")
            print(f"  批次数:        {result.get('batches', 0):>6d}")
        print(f"  成功批次:      {result.get('success_batches', 0):>6d}")
        print(f"  失败批次:      {result.get('fail_batches', result.get('errors', []) and len(result.get('errors', [])) or 0):>6d}")
        print(f"  成功写入:      {result.get('total_saved', 0):>6d}")
        if "elapsed_s" in result:
            print(f"  耗时:          {result['elapsed_s']:>6.1f}s")
        if result.get("errors"):
            print(f"  错误:          {len(result['errors']):>6d}")
            for e in result["errors"][:5]:
                print(f"    - {e}")
            if len(result["errors"]) > 5:
                print(f"    ... 及其他 {len(result['errors']) - 5} 个错误")
    print("=" * 60)

    if not result.get("mode") == "dry_run" and result["total_saved"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
