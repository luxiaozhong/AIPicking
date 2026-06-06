"""
数据库迁移：给 daily 表添加 pre_close 列并回填历史数据

用法：
    cd backend && venv/bin/python scripts/migrate_add_pre_close.py
    venv/bin/python scripts/migrate_add_pre_close.py --pg-url postgresql://...

说明：
    1. 添加 pre_close 列（如果不存在）
    2. 回填 pre_close = 前一交易日的 close（同一 ts_code）
    3. 更新 sqlalchemy 模型已完成（models/stock_tables.py）

背景：
    腾讯前复权(qfq)接口返回的价格复权因子随除权事件变化。不同日期同步的数据
    使用不同复权因子，导致跨日涨跌幅计算失真（如金房能源 2026-06-05 显示
    -28.89%，实际应在 ±10% 以内）。

    修复方案：同步时存储 pre_close（同一 API 响应内获取，复权因子一致），
    查询时直接使用 pre_close。本脚本为历史数据补填 pre_close。
"""

import argparse
import os
import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ENV_DIR = Path(__file__).resolve().parent.parent  # backend/
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)


def _parse_pg_url(url: str) -> dict:
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


def main():
    p = argparse.ArgumentParser(description="Migrate: add pre_close column + backfill")
    p.add_argument("--pg-url", default=None, help="PostgreSQL connection URL")
    p.add_argument("--dry-run", action="store_true", help="Show SQL without executing")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    # ── Parse connection ───────────────────────────
    _default_db = os.getenv("DATABASE_URL", "")
    if not _default_db:
        _user = os.getenv("DB_USER", "aipicking")
        _pass = os.getenv("DB_PASSWORD", "")
        _host = os.getenv("DB_HOST", "localhost")
        _port = os.getenv("DB_PORT", "5432")
        _name = os.getenv("DB_NAME", "aipicking")
        _default_db = f"postgresql://{_user}:{_pass}@{_host}:{_port}/{_name}"

    if args.pg_url:
        params = _parse_pg_url(args.pg_url)
    else:
        params = _parse_pg_url(_default_db)

    conn = psycopg2.connect(**params)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # ── 1. Add column ──────────────────────────
        logging.info("Step 1/3: Adding pre_close column...")
        cur.execute("""
            ALTER TABLE daily ADD COLUMN IF NOT EXISTS pre_close FLOAT;
        """)
        conn.commit()
        logging.info("  ✓ pre_close column ready")

        # ── 2. Backfill (recent 30 days only, using window function for speed) ──
        # Full table backfill (7M+ rows) would take hours with correlated subquery.
        # We backfill only the most recent 30 trading days (~150K rows) which users
        # actively browse. Older data falls back to the self-join at query time.
        logging.info("Step 2/3: Backfilling pre_close for recent 30 trading days...")

        backfill_sql = """
            WITH recent_dates AS (
                SELECT DISTINCT trade_date FROM daily ORDER BY trade_date DESC LIMIT 30
            ),
            date_range AS (
                SELECT MIN(trade_date) AS min_recent, MAX(trade_date) AS max_recent FROM recent_dates
            ),
            extra_date AS (
                SELECT MAX(trade_date) AS extra FROM daily
                WHERE trade_date < (SELECT min_recent FROM date_range)
            ),
            all_dates AS (
                SELECT trade_date FROM recent_dates
                UNION
                SELECT extra FROM extra_date WHERE extra IS NOT NULL
            ),
            pre_close_cte AS (
                SELECT
                    d.ts_code,
                    d.trade_date,
                    LAG(d.close) OVER (PARTITION BY d.ts_code ORDER BY d.trade_date) AS computed_pre_close
                FROM daily d
                WHERE d.trade_date IN (SELECT trade_date FROM all_dates)
            )
            UPDATE daily d
            SET pre_close = p.computed_pre_close
            FROM pre_close_cte p
            WHERE d.ts_code = p.ts_code
              AND d.trade_date = p.trade_date
              AND d.pre_close IS NULL
              AND p.computed_pre_close IS NOT NULL
              AND d.trade_date IN (SELECT trade_date FROM recent_dates);
        """

        if args.dry_run:
            logging.info(f"  [DRY RUN] Would execute backfill for recent 30 days")
        else:
            cur.execute(backfill_sql)
            updated = cur.rowcount
            conn.commit()
            logging.info(f"  ✓ Backfilled {updated} rows (recent 30 trading days)")

        # ── 3. Verify ──────────────────────────────
        logging.info("Step 3/3: Verifying...")
        cur.execute("SELECT COUNT(*) FROM daily WHERE pre_close IS NULL")
        null_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM daily")
        total = cur.fetchone()[0]
        fill_rate = (1 - null_count / total * 1.0) * 100 if total > 0 else 0
        logging.info(f"  Total rows: {total}")
        logging.info(f"  NULL pre_close: {null_count} ({100 - fill_rate:.1f}%)")
        logging.info(f"  Fill rate: {fill_rate:.1f}%")

        if null_count > 0:
            logging.info(
                "  Note: Older rows have NULL pre_close — query falls back to self-join."
            )

        logging.info("Migration complete!")

    except Exception as e:
        conn.rollback()
        logging.error(f"Migration failed: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
