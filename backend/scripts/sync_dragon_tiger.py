#!/usr/bin/env python3
"""
每日龙虎榜数据采集 — 全市场汇总 + 买卖席位明细

数据源: 东财 datacenter-web API（已内置 em_get 节流防封）
存储:   PostgreSQL（psycopg2 直连）

用法:
    cd backend
    venv/bin/python scripts/sync_dragon_tiger.py                        # 今天
    venv/bin/python scripts/sync_dragon_tiger.py --date 2026-05-30      # 指定日期
    venv/bin/python scripts/sync_dragon_tiger.py --date 2026-05-30 --dry-run  # 只拉不存

Cron (weekdays 17:00 Beijing time):
    0 17 * * 1-5 cd /opt/AIpicking/backend && \
        venv/bin/python scripts/sync_dragon_tiger.py >> /var/log/aipicking/ingest.log 2>&1
"""
import argparse
import logging
import os
import random
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

# 加载 .env（dev）→ .env.production（prod 覆盖）
_ENV_DIR = Path(__file__).resolve().parent.parent  # backend/
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

# ═════════════════════════════════════════════════════════════════════════
# PostgreSQL 连接（复用 update_daily.py 的 _parse_pg_url 模式）
# ═════════════════════════════════════════════════════════════════════════

def _parse_pg_url(url: str) -> dict:
    """从 DATABASE_URL 解析 psycopg2 连接参数"""
    url = url.replace("+asyncpg", "").replace("+psycopg2", "")
    if "://" not in url:
        url = f"postgresql://{url}"
    r = urlparse(url if "://" in url else f"postgresql://{url}")
    return {
        "host": r.hostname or "localhost",
        "port": r.port or 5432,
        "user": r.username or "aipicking",
        "password": r.password or "",
        "dbname": r.path.lstrip("/") or "aipicking",
    }

_PG_PARAMS = _parse_pg_url(os.getenv(
    "DATABASE_URL",
    "postgresql://aipicking:aipicking_dev_pwd@localhost:5432/aipicking"
))

def get_conn():
    """获取 PostgreSQL 连接"""
    return psycopg2.connect(**_PG_PARAMS)


# ═════════════════════════════════════════════════════════════════════════
# 东财防封：节流 + 会话复用
# ═════════════════════════════════════════════════════════════════════════

_em_session: Optional[requests.Session] = None
EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]

def _get_em_session() -> requests.Session:
    global _em_session
    if _em_session is None:
        _em_session = requests.Session()
        _em_session.headers.update({"User-Agent": UA})
    return _em_session

def em_get(url: str, params=None, headers=None, timeout: int = 15, **kwargs):
    """东财统一请求入口：自动节流 + 复用 session + 默认 UA。"""
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

def eastmoney_datacenter(report_name: str, columns: str = "ALL",
                          filter_str: str = "", page_size: int = 500,
                          sort_columns: str = "", sort_types: str = "-1") -> list[dict]:
    """东财数据中心统一查询（已内置限流）"""
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = em_get(DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


# ═════════════════════════════════════════════════════════════════════════
# DDL
# ═════════════════════════════════════════════════════════════════════════

_DDL_DRAGON_TIGER = """
CREATE TABLE IF NOT EXISTS daily_dragon_tiger (
    id              SERIAL PRIMARY KEY,
    trade_date      TEXT NOT NULL,
    stock_code      TEXT NOT NULL,
    stock_name      TEXT,
    reason          TEXT,
    close           DOUBLE PRECISION,
    change_pct      DOUBLE PRECISION,
    turnover_pct    DOUBLE PRECISION,
    net_buy_wan     DOUBLE PRECISION,
    buy_wan         DOUBLE PRECISION,
    sell_wan        DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(trade_date, stock_code)
)
"""

_DDL_DRAGON_TIGER_SEATS = """
CREATE TABLE IF NOT EXISTS daily_dragon_tiger_seats (
    id              SERIAL PRIMARY KEY,
    trade_date      TEXT NOT NULL,
    stock_code      TEXT NOT NULL,
    seat_type       TEXT NOT NULL,
    rank            INTEGER NOT NULL,
    seat_name       TEXT,
    seat_code       TEXT,
    buy_amt_wan     DOUBLE PRECISION,
    sell_amt_wan    DOUBLE PRECISION,
    net_amt_wan     DOUBLE PRECISION,
    is_institution  BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(trade_date, stock_code, seat_type, rank)
)
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_dt_date ON daily_dragon_tiger(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_dt_code ON daily_dragon_tiger(stock_code)",
    "CREATE INDEX IF NOT EXISTS idx_dts_date ON daily_dragon_tiger_seats(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_dts_code ON daily_dragon_tiger_seats(stock_code)",
]

def ensure_tables():
    """创建龙虎榜表（幂等）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(_DDL_DRAGON_TIGER)
    cur.execute(_DDL_DRAGON_TIGER_SEATS)
    for idx in _INDEXES:
        cur.execute(idx)
    conn.commit()
    conn.close()


# ═════════════════════════════════════════════════════════════════════════
# 抓取：全市场龙虎榜汇总
# ═════════════════════════════════════════════════════════════════════════

def fetch_daily_list(date_str: str) -> list[dict]:
    """
    拉取指定交易日全市场龙虎榜上榜汇总。
    date_str: YYYY-MM-DD
    返回: [{stock_code, stock_name, reason, close, change_pct, turnover_pct,
            net_buy_wan, buy_wan, sell_wan}, ...]
    """
    filter_str = f"(TRADE_DATE>='{date_str}')(TRADE_DATE<='{date_str}')"
    data = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=filter_str,
        page_size=500,
        sort_columns="BILLBOARD_NET_AMT",
        sort_types="-1",
    )
    if not data:
        logging.info(f"No dragon tiger data for {date_str} (non-trading day or data not released)")
        return []

    stocks = []
    for row in data:
        stocks.append({
            "stock_code": row.get("SECURITY_CODE", ""),
            "stock_name": row.get("SECURITY_NAME_ABBR", ""),
            "reason": row.get("EXPLANATION", ""),
            "close": row.get("CLOSE_PRICE"),
            "change_pct": round(float(row.get("CHANGE_RATE") or 0), 2),
            "turnover_pct": round(float(row.get("TURNOVERRATE") or 0), 2),
            "net_buy_wan": round((row.get("BILLBOARD_NET_AMT") or 0) / 10000, 1),
            "buy_wan": round((row.get("BILLBOARD_BUY_AMT") or 0) / 10000, 1),
            "sell_wan": round((row.get("BILLBOARD_SELL_AMT") or 0) / 10000, 1),
        })
    logging.info(f"Fetched {len(stocks)} dragon tiger stocks for {date_str}")
    return stocks


# ═════════════════════════════════════════════════════════════════════════
# 存储
# ═════════════════════════════════════════════════════════════════════════

_LIST_UPSERT = """
INSERT INTO daily_dragon_tiger
    (trade_date, stock_code, stock_name, reason, close, change_pct,
     turnover_pct, net_buy_wan, buy_wan, sell_wan)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (trade_date, stock_code) DO UPDATE SET
    stock_name   = EXCLUDED.stock_name,
    reason       = EXCLUDED.reason,
    close        = EXCLUDED.close,
    change_pct   = EXCLUDED.change_pct,
    turnover_pct = EXCLUDED.turnover_pct,
    net_buy_wan  = EXCLUDED.net_buy_wan,
    buy_wan      = EXCLUDED.buy_wan,
    sell_wan     = EXCLUDED.sell_wan
"""

def save_daily_list(date_str: str, stocks: list[dict]) -> int:
    """存储龙虎榜汇总，返回写入行数"""
    if not stocks:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    rows = [(date_str, s["stock_code"], s["stock_name"], s["reason"],
             s["close"], s["change_pct"], s["turnover_pct"],
             s["net_buy_wan"], s["buy_wan"], s["sell_wan"])
            for s in stocks]
    psycopg2.extras.execute_batch(cur, _LIST_UPSERT, rows)
    conn.commit()
    conn.close()
    logging.info(f"Saved {len(rows)} dragon tiger stocks for {date_str}")
    return len(rows)
