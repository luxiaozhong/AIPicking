"""
数据库迁移：给 stocks 表添加 pinyin_initials 列并回填拼音首字母

用法：
    cd backend && venv/bin/python scripts/migrate_add_pinyin.py
    venv/bin/python scripts/migrate_add_pinyin.py --pg-url postgresql://...
    venv/bin/python scripts/migrate_add_pinyin.py --dry-run

说明：
    1. 添加 pinyin_initials 列（VARCHAR(50)，如不存在）
    2. 使用 pypinyin 库提取 name 的拼音首字母，回填所有存量股票
    3. sqlalchemy 模型已同步修改（models/stock_tables.py）
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

# 确保 backend/app 在路径中，以便导入 pinyin_utils
sys.path.insert(0, str(_ENV_DIR))
from app.utils.pinyin_utils import get_pinyin_initials


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
    p = argparse.ArgumentParser(description="Migrate: add pinyin_initials column + backfill")
    p.add_argument("--pg-url", default=None, help="PostgreSQL connection URL")
    p.add_argument("--dry-run", action="store_true", help="Show SQL without executing")
    p.add_argument("--verify", action="store_true", help="Verify pinyin data only, skip migration")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

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
        # ── 0. Verify-only mode ────────────────────
        if args.verify:
            logging.info("Verification mode: checking pinyin_initials...")
            cur.execute("""
                SELECT COUNT(*) FROM stocks
                WHERE pinyin_initials IS NULL OR pinyin_initials = '';
            """)
            empty_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM stocks")
            total = cur.fetchone()[0]
            logging.info(f"  Total stocks: {total}")
            logging.info(f"  Empty pinyin_initials: {empty_count}")

            cur.execute("""
                SELECT ts_code, name, pinyin_initials
                FROM stocks ORDER BY ts_code LIMIT 20;
            """)
            for row in cur.fetchall():
                logging.info(f"  {row[0]} | {row[1]} → {row[2]}")
            return

        # ── 1. Add column ──────────────────────────
        logging.info("Step 1/3: Adding pinyin_initials column...")
        if args.dry_run:
            logging.info("  [DRY RUN] ALTER TABLE stocks ADD COLUMN IF NOT EXISTS pinyin_initials VARCHAR(50) DEFAULT '';")
        else:
            cur.execute("""
                ALTER TABLE stocks ADD COLUMN IF NOT EXISTS pinyin_initials VARCHAR(50) DEFAULT '';
            """)
            conn.commit()
            logging.info("  ✓ pinyin_initials column ready")

        # ── 2. Backfill ─────────────────────────────
        logging.info("Step 2/3: Computing and backfilling pinyin initials...")
        cur.execute("SELECT ts_code, name FROM stocks ORDER BY ts_code")
        rows = cur.fetchall()

        updates = []
        for ts_code, name in rows:
            initials = get_pinyin_initials(name or "")
            updates.append((initials, ts_code))

        logging.info(f"  Computed pinyin_initials for {len(updates)} stocks")

        if args.dry_run:
            logging.info("  [DRY RUN] Would update %d rows", len(updates))
            for ts_code, name in rows[:10]:
                initials = get_pinyin_initials(name or "")
                logging.info(f"  {ts_code} | {name} → {initials}")
        else:
            psycopg2.extras.execute_batch(
                cur,
                "UPDATE stocks SET pinyin_initials = %s WHERE ts_code = %s",
                updates,
                page_size=500,
            )
            conn.commit()
            logging.info(f"  ✓ Backfilled {len(updates)} rows")

        # ── 3. Verify ──────────────────────────────
        if args.dry_run:
            logging.info("Step 3/3: Verification skipped (dry-run)")
        else:
            logging.info("Step 3/3: Verifying...")
            cur.execute("""
                SELECT COUNT(*) FROM stocks
                WHERE (pinyin_initials IS NULL OR pinyin_initials = '')
                  AND name IS NOT NULL AND name != '';
            """)
            empty_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM stocks")
            total = cur.fetchone()[0]
            logging.info(f"  Total stocks: {total}")
            logging.info(f"  Missing pinyin_initials: {empty_count}")

            # 抽查
            cur.execute("""
                SELECT ts_code, name, pinyin_initials
                FROM stocks ORDER BY ts_code LIMIT 20;
            """)
            for row in cur.fetchall():
                logging.info(f"  {row[0]} | {row[1]} → {row[2]}")

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
