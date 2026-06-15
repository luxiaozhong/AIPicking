#!/usr/bin/env python3
"""
每日个股资金流向同步 — 腾讯自选股 via westock-data-clawhub npm 包

Fetches and stores into PostgreSQL:
  - 全市场 A 股日级资金流（主力/超大单/大单/中单/小单净流入 + 多日累计 + 大宗 + 两融 + 龙虎榜）

数据源：proxy.finance.qq.com（通过 westock-data-clawhub@1.0.4 npm CLI 代理）
覆盖字段：主力净额/超大单/大单/中单/小单 + 5/10/20日累计 + 大宗交易 + 融资融券 + 龙虎榜

Idempotent: INSERT ... ON CONFLICT DO UPDATE — safe to re-run.
批量策略：每批 50 只股票（npx 启动开销 ~1s），批间延迟 2s，全量约 7 分钟。

Writes to table:
  - daily_stock_fund_flow (ORM: DailyStockFundFlow)

表由 SQLAlchemy ORM 管理（Base.metadata.create_all），本脚本启动时也会
执行 CREATE TABLE IF NOT EXISTS 作为兜底。

Usage:
    cd backend
    venv/bin/python scripts/sync_stock_fund_flow.py --date 2026-06-12
    venv/bin/python scripts/sync_stock_fund_flow.py --date 2026-06-12 --batch-size 10 --log-level DEBUG
    venv/bin/python scripts/sync_stock_fund_flow.py --date 2026-06-12 --dry-run
    venv/bin/python scripts/sync_stock_fund_flow.py --pg-url postgresql://...

Cron:
    # 上午收盘后预同步（11:30）— 盘后 sync_all.py 会覆盖为最终数据
    30 11 * * 1-5 cd /opt/AIpicking/backend && \\
        venv/bin/python scripts/sync_stock_fund_flow.py --date $(date +\%Y-\%m-\%d) >> /var/log/aipicking/ingest.log 2>&1
    # 午后预同步（14:15）— 盘后 sync_all.py 会覆盖为最终数据
    15 14 * * 1-5 cd /opt/AIpicking/backend && \\
        venv/bin/python scripts/sync_stock_fund_flow.py --date $(date +\%Y-\%m-\%d) >> /var/log/aipicking/ingest.log 2>&1
    # 盘后最终同步（17:30，通过 sync_all.py 统一调度，自动覆盖上述数据）
"""

from __future__ import annotations

import argparse
import json
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
BATCH_DELAY_BASE = 2.0       # base delay between batches (seconds)
BATCH_DELAY_JITTER = 1.5     # random jitter on top of base delay
BATCH_TIMEOUT = 120           # subprocess timeout per batch (seconds)
MAX_RETRIES = 2               # retry attempts for transient failures
RETRY_BACKOFF = (5, 15)       # (min, max) retry backoff seconds

# Index ts_codes to exclude (no fund flow data)
INDEX_CODES = (
    "000001.SH", "000002.SH", "000003.SH", "000004.SH", "000005.SH",
    "000006.SH", "000007.SH", "000008.SH", "000009.SH", "000010.SH",
    "000011.SH", "000012.SH", "000013.SH", "000015.SH", "000016.SH",
    "000017.SH", "000300.SH", "000688.SH", "000698.SH", "000852.SH",
    "000853.SH", "000854.SH", "000855.SH", "000856.SH", "000857.SH",
    "000858.SH", "000859.SH", "000860.SH", "000861.SH", "000862.SH",
    "000863.SH", "000864.SH", "000865.SH", "000866.SH", "000867.SH",
    "000868.SH", "000869.SH", "000870.SH", "000871.SH", "000872.SH",
    "000873.SH", "000874.SH", "000875.SH", "000876.SH", "000877.SH",
    "000878.SH", "000879.SH", "000880.SH", "000881.SH", "000882.SH",
    "000883.SH", "000884.SH", "000885.SH", "000886.SH", "000887.SH",
    "000888.SH", "000889.SH", "000890.SH", "000891.SH", "000892.SH",
    "000893.SH", "000894.SH", "000895.SH", "000896.SH", "000897.SH",
    "000898.SH", "000899.SH", "000900.SH", "000901.SH", "000902.SH",
    "000903.SH", "000904.SH", "000905.SH", "000906.SH", "000907.SH",
    "000908.SH", "000909.SH", "000910.SH", "000911.SH", "000912.SH",
    "000913.SH", "000914.SH", "000915.SH", "000916.SH", "000917.SH",
    "000918.SH", "000919.SH", "000920.SH", "000921.SH", "000922.SH",
    "000923.SH", "000924.SH", "000925.SH", "000926.SH", "000927.SH",
    "000928.SH", "000929.SH", "000930.SH", "000931.SH", "000932.SH",
    "000933.SH", "000934.SH", "000935.SH", "000936.SH", "000937.SH",
    "000938.SH", "000939.SH", "000940.SH", "000941.SH", "000942.SH",
    "000943.SH", "000944.SH", "000945.SH", "000946.SH", "000947.SH",
    "000948.SH", "000949.SH", "000950.SH", "000951.SH", "000952.SH",
    "000953.SH", "000954.SH", "000955.SH", "000956.SH", "000957.SH",
    "000958.SH", "000959.SH", "000960.SH", "000961.SH", "000962.SH",
    "000963.SH", "000964.SH", "000965.SH", "000966.SH", "000967.SH",
    "000968.SH", "000969.SH", "000970.SH", "000971.SH", "000972.SH",
    "000973.SH", "000974.SH", "000975.SH", "000976.SH", "000977.SH",
    "000978.SH", "000979.SH", "000980.SH", "000981.SH", "000982.SH",
    "000983.SH", "000984.SH", "000985.SH", "000986.SH", "000987.SH",
    "000988.SH", "000989.SH", "000990.SH", "000991.SH", "000992.SH",
    "000993.SH", "000994.SH", "000995.SH", "000996.SH", "000997.SH",
    "000998.SH", "000999.SH",
    "399001.SZ", "399002.SZ", "399003.SZ", "399004.SZ", "399005.SZ",
    "399006.SZ", "399100.SZ", "399101.SZ", "399102.SZ", "399103.SZ",
    "399106.SZ", "399107.SZ", "399108.SZ", "399300.SZ", "399301.SZ",
    "399302.SZ", "399303.SZ", "399304.SZ", "399305.SZ", "399306.SZ",
    "399307.SZ", "399308.SZ", "399309.SZ", "399310.SZ", "399311.SZ",
    "399312.SZ", "399313.SZ", "399314.SZ", "399315.SZ", "399316.SZ",
    "399317.SZ", "399318.SZ", "399319.SZ", "399320.SZ", "399321.SZ",
    "399322.SZ", "399323.SZ", "399324.SZ", "399325.SZ", "399326.SZ",
    "399327.SZ", "399328.SZ", "399329.SZ", "399330.SZ", "399331.SZ",
    "399332.SZ", "399333.SZ", "399334.SZ", "399335.SZ", "399336.SZ",
    "399337.SZ", "399338.SZ", "399339.SZ", "399340.SZ", "399341.SZ",
    "399342.SZ", "399343.SZ", "399344.SZ", "399345.SZ", "399346.SZ",
    "399347.SZ", "399348.SZ", "399349.SZ", "399350.SZ", "399351.SZ",
    "399352.SZ", "399353.SZ", "399354.SZ", "399355.SZ", "399356.SZ",
    "399357.SZ", "399358.SZ", "399359.SZ", "399360.SZ", "399361.SZ",
    "399362.SZ", "399363.SZ", "399364.SZ", "399365.SZ", "399366.SZ",
    "399367.SZ", "399368.SZ", "399369.SZ", "399370.SZ", "399371.SZ",
    "399372.SZ", "399373.SZ", "399374.SZ", "399375.SZ", "399376.SZ",
    "399377.SZ", "399378.SZ", "399379.SZ", "399380.SZ", "399381.SZ",
    "399382.SZ", "399383.SZ", "399384.SZ", "399385.SZ", "399386.SZ",
    "399387.SZ", "399388.SZ", "399389.SZ", "399390.SZ", "399391.SZ",
    "399392.SZ", "399393.SZ", "399394.SZ", "399395.SZ", "399396.SZ",
    "399397.SZ", "399398.SZ", "399399.SZ", "399400.SZ",
    "899001.BJ", "899002.BJ", "899050.BJ",
)

# ── npm CLI output column → DB column mapping ─────────────────────────
# Parsed dynamically from markdown header row; this is the canonical set.
# npm_field: (db_column, python_type)
_COLUMN_MAP = {
    "BlockNetFlow":           ("block_net_flow",           float),
    "BlockTradingInfos":      ("block_trading_infos",       str),   # JSON text
    "ClosePrice":             ("close_price",               float),
    "EndDate":                ("end_date",                  str),
    "FwdClosePrice":          ("fwd_close_price",           float),
    "JumboNetFlow":           ("jumbo_net_flow",            float),
    "LastestTradedPrice":     ("lastest_traded_price",      float),
    "LhbTradingDetails":      ("lhb_trading_details",       str),   # JSON text
    "LhbInfos":               ("lhb_infos",                 str),   # JSON text (sometimes present)
    "MainInFlow":             ("main_in_flow",              float),
    "MainInflowCircRate":     ("main_inflow_circ_rate",     float),
    "MainInflowIndustryRank": ("main_inflow_industry_rank", int),
    "MainInflowRank":         ("main_inflow_rank",          int),
    "MainNetFlow":            ("main_net_flow",             float),
    "MainNetFlow10D":         ("main_net_flow_10d",         float),
    "MainNetFlow20D":         ("main_net_flow_20d",         float),
    "MainNetFlow5D":          ("main_net_flow_5d",          float),
    "MainOutFlow":            ("main_out_flow",             float),
    "MarginTradeInfos":       ("margin_trade_infos",        str),   # JSON text
    "MidNetFlow":             ("mid_net_flow",              float),
    "RetailInFlow":           ("retail_in_flow",            float),
    "RetailOutFlow":          ("retail_out_flow",           float),
    "SecuCode":               ("secu_code",                 str),
    "SmallNetFlow":           ("small_net_flow",            float),
    # npm CLI may use 'code' or 'symbol' instead of 'SecuCode' as primary identifier
    "code":                   ("secu_code",                 str),
    "symbol":                 ("secu_code",                 str),
}


# ═════════════════════════════════════════════════════════════════════════
# Stock code conversion
# ═════════════════════════════════════════════════════════════════════════

_MARKET_TO_PREFIX = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
_PREFIX_TO_MARKET = {"sh": "SH", "sz": "SZ", "bj": "BJ"}


def ts_code_to_npm(ts_code: str) -> str:
    """Convert DB ts_code to npm CLI format.

    "600519.SH" → "sh600519"
    "000858.SZ" → "sz000858"
    "832000.BJ" → "bj832000"
    """
    code, market = ts_code.rsplit(".", 1)
    prefix = _MARKET_TO_PREFIX.get(market.upper(), "sz")
    return f"{prefix}{code}"


def npm_to_ts_code(npm_code: str) -> str:
    """Reverse: npm CLI format → DB ts_code.

    "sh600519" → "600519.SH"
    "sz000858" → "000858.SZ"
    """
    prefix = npm_code[:2].lower()
    code = npm_code[2:]
    market = _PREFIX_TO_MARKET.get(prefix, "SZ")
    return f"{code}.{market}"


# ═════════════════════════════════════════════════════════════════════════
# Stock loader
# ═════════════════════════════════════════════════════════════════════════

def load_stocks() -> list[str]:
    """Load all A-share stock ts_codes from the stocks table, excluding indexes.

    Returns ts_code strings sorted alphabetically (e.g. ["000001.SZ", ...]).
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ts_code FROM stocks WHERE ts_code NOT IN %s ORDER BY ts_code",
                (INDEX_CODES,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


# ═════════════════════════════════════════════════════════════════════════
# Markdown table parser
# ═════════════════════════════════════════════════════════════════════════

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
    """Parse the npm CLI markdown table output into a list of dicts.

    The npm CLI outputs a pipe table like:

        | code | MainNetFlow | ... |
        | --- | --- | ... |
        | sh600519 | 61654379.00 | ... |

    Returns list of dicts with DB column names as keys, ready for upsert.
    """
    lines = output.strip().split("\n")
    if not lines:
        return []

    # Find the header row — first line starting with "| " that contains column names
    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and not stripped.startswith("|---"):
            # Check if it looks like a header (has known column names)
            if any(known in stripped for known in ("MainNetFlow", "SecuCode", "code")):
                header_idx = i
                break

    if header_idx is None:
        logging.warning("No markdown table header found in npm CLI output")
        return []

    # Parse header columns
    header_cells = [c.strip() for c in lines[header_idx].strip().strip("|").split("|")]
    # Build column index map: header position → (db_col, converter)
    col_map = {}  # idx → (db_col, converter)
    for idx, name in enumerate(header_cells):
        # Try matching by canonical name first, then case-insensitive
        if name in _COLUMN_MAP:
            col_map[idx] = _COLUMN_MAP[name]
        else:
            # Some headers may vary (e.g. "symbol" vs "code"); skip unknown
            logging.debug(f"Unknown column in markdown table: '{name}'")

    if not col_map:
        logging.warning("No known columns matched in markdown header: %s", header_cells)
        return []

    # Parse data rows (skip header and separator)
    rows = []
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        # Skip separator lines (| --- | --- |)
        cleaned = stripped.replace("|", "").replace("-", "").replace(" ", "")
        if not cleaned:
            continue

        cells = [c.strip() for c in stripped.strip().strip("|").split("|")]
        row = {}
        for idx, (db_col, converter) in col_map.items():
            if idx < len(cells):
                row[db_col] = _parse_value(cells[idx], converter)

        # Only keep rows that have at least some data
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

    # Parse markdown table from stdout
    rows = parse_markdown_table(stdout)
    if not rows:
        # Log a snippet for debugging
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

# Column order for the upsert tuple (matches INSERT column list)
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
        # Derive ts_code from npm_code if not already set
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

def sync(date_str: str, batch_size: int = BATCH_SIZE,
         dry_run: bool = False) -> dict:
    """Main sync: load stocks, batch-call npm CLI, save to DB.

    Args:
        date_str:  Trade date YYYY-MM-DD
        batch_size: Stocks per npm CLI call (default 50)
        dry_run:    If True, print plan but don't execute

    Returns:
        {"date": str, "total_stocks": int, "batches": int,
         "success_batches": int, "fail_batches": int,
         "total_saved": int, "elapsed_s": float, "errors": list[str]}
    """
    # 1. Load stock codes
    logging.info(f"Loading stock codes from stocks table...")
    if dry_run:
        stocks = ["000001.SZ", "000002.SZ", "600519.SH"]  # sample for dry-run
    else:
        stocks = load_stocks()

    total_stocks = len(stocks)
    if total_stocks == 0:
        logging.error("No stocks found in stocks table")
        return {"date": date_str, "total_stocks": 0, "errors": ["Empty stocks table"]}

    npm_codes = [ts_code_to_npm(ts) for ts in stocks]
    total_batches = math.ceil(len(npm_codes) / batch_size)

    logging.info(f"Total stocks: {total_stocks}, batch size: {batch_size}, "
                 f"batches: {total_batches}")

    if dry_run:
        logging.info(f"[DRY RUN] Would run {total_batches} batches "
                     f"(~{total_batches * (BATCH_DELAY_BASE + 2):.0f}s)")
        for i in range(0, min(3, len(npm_codes)), 1):
            batch = npm_codes[i:i + batch_size]
            logging.info(f"[DRY RUN] Batch 1: npx {NPM_PACKAGE} asfund "
                         f"{','.join(batch[:3])}... --date {date_str}")
        return {"date": date_str, "total_stocks": total_stocks,
                "batches": total_batches, "total_saved": 0,
                "mode": "dry_run"}

    # 2. Run batches
    success_batches = 0
    fail_batches = 0
    total_saved = 0
    errors = []

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
            first_code = stocks[start] if isinstance(stocks[start], str) else stocks[start]
            last_code = stocks[end - 1] if isinstance(stocks[end - 1], str) else stocks[end - 1]
            err_msg = (f"Batch {batch_num}/{total_batches} "
                       f"({first_code}…{last_code}) "
                       f"failed after {MAX_RETRIES + 1} attempts")
            errors.append(err_msg)
            logging.error(err_msg)
            continue

        # Convert npm_code → ts_code for each row
        for row in rows:
            if "ts_code" not in row and "secu_code" in row:
                row["ts_code"] = npm_to_ts_code(row["secu_code"])

        # Validate: API may return previous trading day's data for non-trading days
        # (weekends, holidays). Check EndDate matches requested date.
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
            first_code = stocks[start] if isinstance(stocks[start], str) else stocks[start]
            last_code = stocks[end - 1] if isinstance(stocks[end - 1], str) else stocks[end - 1]
            logging.info(
                f"Batch {batch_num}/{total_batches}: "
                f"{len(rows)} parsed, {saved} saved "
                f"({first_code} … {last_code})"
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
    logging.info(
        f"Sync complete: {total_saved} rows saved in {elapsed:.0f}s "
        f"({success_batches}/{total_batches} batches OK, "
        f"{fail_batches} failed)"
    )

    return {
        "date": date_str,
        "total_stocks": total_stocks,
        "batches": total_batches,
        "success_batches": success_batches,
        "fail_batches": fail_batches,
        "total_saved": total_saved,
        "elapsed_s": round(elapsed, 1),
        "errors": errors,
    }


# ═════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="每日个股资金流向同步 — 腾讯自选股 via westock-data-clawhub")
    p.add_argument("--date", default=None,
                   help="交易日期 YYYY-MM-DD（默认: 昨天，即上个交易日）")
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                   help=f"每批股票数量（默认 {BATCH_SIZE}）")
    p.add_argument("--dry-run", action="store_true",
                   help="仅打印计划，不实际执行")
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
        now = datetime.now()
        if now.hour >= 16:
            target = now
        else:
            target = now - timedelta(days=1)
        date_str = target.strftime("%Y-%m-%d")

    # Validate date format
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        logging.error(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")
        sys.exit(1)

    # Reject weekends — A-share market closed, no fund flow data generated
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    if target_date.isoweekday() >= 6:  # Saturday=6, Sunday=7
        if args.date is None:
            # 默认日期（自动计算）落到周末 → 回退到最近周五
            days_back = target_date.isoweekday() - 5  # Sat→1, Sun→2
            target_date = target_date - timedelta(days=days_back)
            date_str = target_date.strftime("%Y-%m-%d")
            logging.info(
                "Default date fell on weekend, using previous trading day: %s",
                date_str,
            )
        else:
            # 用户显式传了 --date 但却是周末 → 报错
            logging.error(
                f"{date_str} is a weekend (%s), A-share market closed — "
                "no fund flow data available. Refusing to sync.",
                target_date.strftime("%A"),
            )
            sys.exit(1)

    # 1. Ensure table exists
    try:
        ensure_table()
    except Exception as e:
        logging.error(f"Failed to ensure table: {e}")
        sys.exit(1)

    # 2. Run sync
    result = sync(date_str=date_str, batch_size=args.batch_size,
                  dry_run=args.dry_run)

    # 3. Report
    print()
    print("=" * 60)
    print(f"  个股资金流向同步报告 — {result['date']}")
    print("=" * 60)
    if result.get("mode") == "dry_run":
        print(f"  [DRY RUN] 计划导入: {result['total_stocks']} 只")
        print(f"  [DRY RUN] 批次数:   {result['batches']}")
    else:
        print(f"  股票总数:      {result['total_stocks']:>6d}")
        print(f"  批次数:        {result['batches']:>6d}")
        print(f"  成功批次:      {result['success_batches']:>6d}")
        print(f"  失败批次:      {result['fail_batches']:>6d}")
        print(f"  成功写入:      {result['total_saved']:>6d}")
        print(f"  耗时:          {result['elapsed_s']:>6.1f}s")
        if result["errors"]:
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
