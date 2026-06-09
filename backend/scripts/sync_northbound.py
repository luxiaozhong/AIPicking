"""
北向资金独立同步脚本 — 每日 9:00 拉取前一个交易日深股通数据。

与 sync_market_data.py 互不依赖，可独立运行。当前仅深股通（MUTUAL_TYPE="002"）
数据可用，沪股通（MUTUAL_TYPE="001"）自 2024-08-16 起不再披露净买额。

数据源：东财 datacenter RPT_MUTUAL_DEAL_HISTORY
写入表：daily_northbound_flow（UPSERT，幂等）

用法：
    cd backend
    venv/bin/python scripts/sync_northbound.py                     # 同步昨天
    venv/bin/python scripts/sync_northbound.py --date 2026-06-06   # 指定日期
    venv/bin/python scripts/sync_northbound.py --dry-run           # 仅预览

Cron（每个交易日 9:00，同步昨天数据）：
    0 9 * * 1-5 cd /opt/AIpicking/backend && \
        venv/bin/python scripts/sync_northbound.py >> /var/log/aipicking/northbound.log 2>&1
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
        logging.warning(f"{date_str}: request failed — {e}")
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
    buy_yi = round(float(row.get("BUY_AMT") or 0) / 100, 2)
    sell_yi = round(float(row.get("SELL_AMT") or 0) / 100, 2)
    return {
        "trade_date": date_str,
        "hgt_net_yi": None,
        "sgt_net_yi": sgt_yi,
        "sgt_buy_yi": buy_yi,
        "sgt_sell_yi": sell_yi,
        "total_net_yi": sgt_yi,
        "data_points": 0,
    }


# ═════════════════════════════════════════════════════════════════════════
# Database
# ═════════════════════════════════════════════════════════════════════════

UPSERT_SQL = """
    INSERT INTO daily_northbound_flow
        (trade_date, hgt_net_yi, sgt_net_yi, sgt_buy_yi, sgt_sell_yi, total_net_yi, data_points)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (trade_date) DO UPDATE SET
        hgt_net_yi   = EXCLUDED.hgt_net_yi,
        sgt_net_yi   = EXCLUDED.sgt_net_yi,
        sgt_buy_yi   = EXCLUDED.sgt_buy_yi,
        sgt_sell_yi  = EXCLUDED.sgt_sell_yi,
        total_net_yi = EXCLUDED.total_net_yi,
        data_points  = EXCLUDED.data_points
"""


def get_conn():
    return psycopg2.connect(**_PG_PARAMS)


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
                    record["sgt_buy_yi"],
                    record["sgt_sell_yi"],
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


def main():
    p = argparse.ArgumentParser(
        description="同步北向资金数据（深股通），默认同步昨天"
    )
    p.add_argument(
        "--date",
        default=None,
        help="指定日期 YYYY-MM-DD（默认：昨天）",
    )
    p.add_argument("--dry-run", action="store_true", help="仅预览，不写入")
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

    # 默认同步昨天（9 点跑，当天数据尚未发布）
    if args.date:
        target_date = args.date
    else:
        target_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    logging.info(f"北向资金同步 — 目标日期: {target_date}")

    # ── Fetch ────────────────────────────────────────────────────────
    record = fetch_northbound_for_date(target_date)

    if record is None:
        logging.warning(f"{target_date}: 无北向数据（非交易日或数据未发布）")
        return

    direction = "流入" if record["sgt_net_yi"] >= 0 else "流出"
    logging.info(
        f"{target_date}: "
        f"深股通 买入{record['sgt_buy_yi']:.2f}亿 "
        f"卖出{record['sgt_sell_yi']:.2f}亿 "
        f"→ 净{direction}{abs(record['sgt_net_yi']):.2f}亿"
    )

    if args.dry_run:
        logging.info("DRY RUN — 未写入数据库")
        return

    # ── Save ─────────────────────────────────────────────────────────
    save_record(record)
    logging.info(f"{target_date}: 北向数据已保存 ✓")


if __name__ == "__main__":
    main()
