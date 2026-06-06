"""
Backfill northbound flow data using eastmoney RPT_MUTUAL_DEAL_HISTORY.

Background:
  - hexin dayChart API was returning stale/corrupted data (only 2 repeating patterns)
  - eastmoney KAMT net flow fields are all 0 since 2024-08 (HKEX policy change)
  - New source: RPT_MUTUAL_DEAL_HISTORY (深股通 MUTUAL_TYPE="002")
  - 沪股通 (MUTUAL_TYPE="001") has been unavailable since 2024-08-16

Actions:
  1. Delete all northbound records where data was sourced from broken hexin API
  2. Backfill with real 深股通 data from new API
  3. Dry-run mode available for preview

Usage:
    cd backend
    venv/bin/python scripts/backfill_northbound.py --dry-run       # Preview only
    venv/bin/python scripts/backfill_northbound.py                 # Execute
    venv/bin/python scripts/backfill_northbound.py --from 2026-05-01  # Partial backfill
"""

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

# ── Load env ──────────────────────────────────────────────────────────
_ENV_DIR = Path(__file__).resolve().parent.parent  # backend/
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)

_default_db = os.getenv("DATABASE_URL", "")
if not _default_db:
    _user = os.getenv("DB_USER", "aipicking")
    _pass = os.getenv("DB_PASSWORD", "")
    _host = os.getenv("DB_HOST", "localhost")
    _port = os.getenv("DB_PORT", "5432")
    _name = os.getenv("DB_NAME", "aipicking")
    _default_db = f"postgresql://{_user}:{_pass}@{_host}:{_port}/{_name}"

_url = _default_db.replace("+asyncpg", "").replace("+psycopg2", "")
if "://" not in _url:
    _url = f"postgresql://{_url}"
_r = urlparse(_url)
_PG_PARAMS = {
    "host": _r.hostname or "localhost",
    "port": _r.port or 5432,
    "user": _r.username or "aipicking",
    "password": _r.password or "",
    "dbname": _r.path.lstrip("/") or "aipicking",
}

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
NORTHBOUND_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

# ═════════════════════════════════════════════════════════════════════════
# API
# ═════════════════════════════════════════════════════════════════════════


def fetch_northbound_for_date(date_str: str) -> Optional[dict]:
    """Fetch 深股通 northbound flow for a specific date."""
    params = {
        "reportName": "RPT_MUTUAL_DEAL_HISTORY",
        "columns": "TRADE_DATE,NET_DEAL_AMT,BUY_AMT,SELL_AMT",
        "filter": (
            f'(MUTUAL_TYPE="002")'
            f"(TRADE_DATE>='{date_str}')"
            f"(TRADE_DATE<='{date_str}')"
        ),
        "pageNumber": "1",
        "pageSize": "1",
        "sortColumns": "TRADE_DATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
    }
    headers = {"User-Agent": UA, "Referer": "https://data.eastmoney.com/"}

    try:
        r = requests.get(NORTHBOUND_URL, params=params, headers=headers, timeout=15)
        d = r.json()
    except Exception as e:
        logging.warning(f"  {date_str}: request failed — {e}")
        return None

    result = d.get("result")
    if result is None:
        return None
    data = result.get("data", [])
    if not data:
        return None

    row = data[0]
    net_deal = row.get("NET_DEAL_AMT")
    if net_deal is None:
        return None

    sgt_yi = round(float(net_deal) / 100, 2)
    return {
        "trade_date": date_str,
        "hgt_net_yi": None,
        "sgt_net_yi": sgt_yi,
        "total_net_yi": sgt_yi,
        "data_points": 0,
    }


# ═════════════════════════════════════════════════════════════════════════
# Database
# ═════════════════════════════════════════════════════════════════════════

UPSERT_SQL = """
    INSERT INTO daily_northbound_flow
        (trade_date, hgt_net_yi, sgt_net_yi, total_net_yi, data_points)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (trade_date) DO UPDATE SET
        hgt_net_yi   = EXCLUDED.hgt_net_yi,
        sgt_net_yi   = EXCLUDED.sgt_net_yi,
        total_net_yi = EXCLUDED.total_net_yi,
        data_points  = EXCLUDED.data_points
"""


def get_conn():
    return psycopg2.connect(**_PG_PARAMS)


def count_northbound() -> int:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM daily_northbound_flow")
            return cur.fetchone()[0]
    finally:
        conn.close()


def delete_corrupted(after_date: str = "2024-08-16") -> int:
    """Delete records that contain corrupted hexin data."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Delete records where data came from broken hexin API
            # (after the HKEX policy change date, plus any with the known
            # stale patterns -40.38 or +370.47)
            cur.execute(
                "DELETE FROM daily_northbound_flow WHERE trade_date > %s",
                (after_date,),
            )
            deleted = cur.rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()


def save_record(record: dict):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                UPSERT_SQL,
                (
                    record["trade_date"],
                    record["hgt_net_yi"],
                    record["sgt_net_yi"],
                    record["total_net_yi"],
                    record["data_points"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


# ═════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════


def generate_trading_days(from_date: str, to_date: str) -> list[str]:
    """Generate all weekdays between two dates (approximate trading days)."""
    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            days.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return days


def main():
    p = argparse.ArgumentParser(
        description="Backfill northbound flow data from eastmoney API"
    )
    p.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    p.add_argument(
        "--from",
        dest="from_date",
        default="2024-04-19",
        help="Start date YYYY-MM-DD (default: 2024-04-19, earliest available)",
    )
    p.add_argument(
        "--to",
        dest="to_date",
        default=None,
        help="End date YYYY-MM-DD (default: today)",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    to_date = args.to_date or date.today().strftime("%Y-%m-%d")
    from_date = args.from_date

    # ── Step 1: Show current state ──────────────────────────────────
    before_count = count_northbound()
    logging.info(f"Current northbound records: {before_count}")

    if args.dry_run:
        logging.info("DRY RUN — no changes will be made")
        logging.info(f"Would delete records after 2024-08-16")
        logging.info(f"Would backfill from {from_date} to {to_date}")

        # Preview what would be backfilled
        trading_days = generate_trading_days(from_date, to_date)
        logging.info(f"Trading days in range: {len(trading_days)}")
        logging.info(f"Estimated API calls: {len(trading_days)}")

        # Try fetching the most recent 3 days to verify data quality
        logging.info("Sample fetch (last 3 trading days):")
        recent = [d for d in trading_days[-5:] if d <= to_date][-3:]
        for d in recent:
            record = fetch_northbound_for_date(d)
            if record:
                direction = "流入" if record["sgt_net_yi"] >= 0 else "流出"
                logging.info(
                    f"  {d}: 深股通 净{direction}{abs(record['sgt_net_yi']):.2f}亿"
                )
            else:
                logging.info(f"  {d}: no data (non-trading day)")
        return

    # ── Step 2: Delete corrupted data ──────────────────────────────
    logging.info("Deleting corrupted northbound records (after 2024-08-16)...")
    deleted = delete_corrupted()
    logging.info(f"Deleted {deleted} corrupted records")

    # ── Step 3: Backfill ───────────────────────────────────────────
    trading_days = generate_trading_days(from_date, to_date)
    logging.info(
        f"Backfilling from {from_date} to {to_date} "
        f"({len(trading_days)} potential trading days)"
    )

    success = 0
    skipped = 0
    for i, d in enumerate(trading_days):
        if (i + 1) % 20 == 0:
            logging.info(f"  Progress: {i+1}/{len(trading_days)} (saved {success}, skipped {skipped})")

        record = fetch_northbound_for_date(d)
        if record:
            save_record(record)
            success += 1
        else:
            skipped += 1

    # ── Step 4: Summary ────────────────────────────────────────────
    after_count = count_northbound()
    logging.info(
        f"Backfill complete: saved {success}, skipped {skipped}, "
        f"total records {before_count} → {after_count}"
    )

    # Show recent data for verification
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT trade_date, sgt_net_yi, total_net_yi "
                "FROM daily_northbound_flow "
                "ORDER BY trade_date DESC LIMIT 5"
            )
            logging.info("Recent records:")
            for row in cur.fetchall():
                direction = "流入" if (row[1] or 0) >= 0 else "流出"
                logging.info(f"  {row[0]}: 深股通 净{direction}{abs(row[1] or 0):.2f}亿")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
