"""
迁移脚本：创建 financial_reports 和 daily_valuation 表

用法：
    cd backend
    venv/bin/python migrate_add_financials.py
    venv/bin/python migrate_add_financials.py --pg-url postgresql://...
"""
import argparse
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

_ENV_DIR = Path(__file__).resolve().parent
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)

from app.config import settings


def get_conn(sync_url: str = None):
    """获取 PostgreSQL 连接"""
    url = sync_url or settings.SYNC_DATABASE_URL
    url = url.replace("+asyncpg", "").replace("+psycopg2", "")
    from urllib.parse import urlparse
    r = urlparse(url)
    return psycopg2.connect(
        host=r.hostname or "localhost",
        port=r.port or 5432,
        user=r.username or "aipicking",
        password=r.password or "",
        dbname=r.path.lstrip("/") or "aipicking",
    )


SQL_CREATE_FINANCIAL_REPORTS = """
CREATE TABLE IF NOT EXISTS financial_reports (
    id              SERIAL PRIMARY KEY,
    ts_code         VARCHAR(20) NOT NULL,
    report_date     VARCHAR(10) NOT NULL,
    report_type     VARCHAR(10) NOT NULL,
    pub_date        VARCHAR(10),
    eps             DOUBLE PRECISION,
    bvps            DOUBLE PRECISION,
    roe             DOUBLE PRECISION,
    roa             DOUBLE PRECISION,
    gross_margin    DOUBLE PRECISION,
    net_margin      DOUBLE PRECISION,
    net_profit      DOUBLE PRECISION,
    net_profit_yoy  DOUBLE PRECISION,
    revenue         DOUBLE PRECISION,
    revenue_yoy     DOUBLE PRECISION,
    debt_to_assets  DOUBLE PRECISION,
    current_ratio   DOUBLE PRECISION,
    quick_ratio     DOUBLE PRECISION,
    cf_operating    DOUBLE PRECISION,
    cf_ratio        DOUBLE PRECISION,
    total_shares    BIGINT,
    float_shares    BIGINT,
    total_assets         DOUBLE PRECISION,
    total_liabilities    DOUBLE PRECISION,
    shareholders_equity  DOUBLE PRECISION,
    source          VARCHAR(20) DEFAULT 'mootdx',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ts_code, report_date)
);

CREATE INDEX IF NOT EXISTS idx_fin_code ON financial_reports(ts_code);
CREATE INDEX IF NOT EXISTS idx_fin_date ON financial_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_fin_type ON financial_reports(report_type);
"""

SQL_CREATE_DAILY_VALUATION = """
CREATE TABLE IF NOT EXISTS daily_valuation (
    id              SERIAL PRIMARY KEY,
    ts_code         VARCHAR(20) NOT NULL,
    trade_date      VARCHAR(8) NOT NULL,
    pe_ttm          DOUBLE PRECISION,
    pe_static       DOUBLE PRECISION,
    pb              DOUBLE PRECISION,
    market_cap      DOUBLE PRECISION,
    circ_market_cap DOUBLE PRECISION,
    dividend_yield  DOUBLE PRECISION,
    source          VARCHAR(20) DEFAULT 'tencent',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ts_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_dv_code ON daily_valuation(ts_code);
CREATE INDEX IF NOT EXISTS idx_dv_date ON daily_valuation(trade_date);
"""


def migrate(sync_url: str = None):
    conn = get_conn(sync_url)
    try:
        cur = conn.cursor()
        cur.execute(SQL_CREATE_FINANCIAL_REPORTS)
        cur.execute(SQL_CREATE_DAILY_VALUATION)
        conn.commit()
        print("✅ financial_reports 和 daily_valuation 表已创建")
    except Exception as e:
        conn.rollback()
        print(f"❌ 迁移失败: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="创建基本面数据表")
    parser.add_argument("--pg-url", type=str, default=None,
                        help="PostgreSQL 连接字符串")
    args = parser.parse_args()
    migrate(args.pg_url)
