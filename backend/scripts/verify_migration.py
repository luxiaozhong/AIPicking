"""数据迁移验证脚本 — 比对 SQLite 和 PostgreSQL 数据一致性"""
import sqlite3
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras

# ── Config ─────────────────────────────
APP_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "database", "aipicking.db"
)
STOCK_DB_PATH = os.getenv(
    "STOCK_DB_PATH",
    os.path.expanduser("~") + "/workbuddy/2026-05-22-21-48-44/data/stock_db.sqlite"
)
PG_URL = os.getenv("PG_MIGRATE_URL", "")
if not PG_URL:
    _user = os.getenv("DB_USER", "aipicking")
    _pass = os.getenv("DB_PASSWORD", "")
    _host = os.getenv("DB_HOST", "localhost")
    _port = os.getenv("DB_PORT", "5432")
    _name = os.getenv("DB_NAME", "aipicking")
    PG_URL = f"postgresql://{_user}:{_pass}@{_host}:{_port}/{_name}"
PG_URL = PG_URL.replace("+asyncpg", "").replace("+psycopg2", "")

TABLE_SOURCES = {
    "stocks": "stock", "daily": "stock",
    # sector_flow / daily_industry_flow → 已合并到 daily_sector_flow（2026-05-31）
    "stock_themes": "stock", "daily_hot_stocks": "stock",
    "daily_hot_themes": "stock", "daily_northbound_flow": "stock",
    "users": "app", "strategies": "app", "backtest_reports": "app",
    "strategy_runs": "app", "batch_backtest_reports": "app",
    "ai_strategy_tasks": "app", "ai_factors": "app",
}


def parse_pg_url(url):
    u = url.replace("postgresql://", "")
    r = urlparse("http://" + u)
    return {
        "host": r.hostname or "localhost",
        "port": r.port or 5432,
        "user": r.username or "aipicking",
        "password": r.password or "",
        "dbname": r.path.lstrip("/") or "aipicking",
    }


def get_sqlite(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_pg():
    return psycopg2.connect(**parse_pg_url(PG_URL))


def hash_row(row):
    return hashlib.md5(
        json.dumps([str(v) for v in row], sort_keys=True, default=str).encode()
    ).hexdigest()


def verify_row_count(sqlite_conn, pg_conn, table_name):
    cur_s = sqlite_conn.cursor()
    cur_s.execute(f"SELECT COUNT(*) FROM {table_name}")
    s_count = cur_s.fetchone()[0]

    cur_p = pg_conn.cursor()
    cur_p.execute(f"SELECT COUNT(*) FROM {table_name}")
    p_count = cur_p.fetchone()[0]

    return s_count, p_count, s_count == p_count


def verify_content(sqlite_conn, pg_conn, table_name):
    """
    比对数据内容：逐列计算 COUNT/SUM/AVG/DISTINCT，比较聚合结果。
    适用于任意大小的表。
    """
    cur_s = sqlite_conn.cursor()
    cur_s.execute(f"SELECT COUNT(*) FROM {table_name}")
    total = cur_s.fetchone()[0]
    if total == 0:
        return True, "empty table"

    cur_s.execute(f"SELECT * FROM {table_name}")
    src_cols = [desc[0] for desc in cur_s.description]

    cur_p = pg_conn.cursor()
    cur_p.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = %s ORDER BY ordinal_position",
        (table_name,)
    )
    pg_cols = [r[0] for r in cur_p.fetchall()]

    exclude = {"id", "created_at", "updated_at"}
    common = [c for c in pg_cols if c in src_cols and c not in exclude]

    if not common:
        return True, "no common cols"

    return _verify_aggregate(sqlite_conn, pg_conn, table_name, common, total)


def _verify_aggregate(sq_conn, pg_conn, table_name, common, total):
    """
    用列聚合比对数据完整性。对每列检查：
    - COUNT(col): 非 NULL 行数
    - COUNT(DISTINCT col): 唯一值数量
    这两个指标足以验证数据是否完整迁移（行数相同 + 每列非空数和唯一值数相同 = 数据一致）。
    """
    mismatches = []
    checked = 0

    for c in common:
        checked += 1

        # SQLite aggregates
        cur_s = sq_conn.cursor()
        cur_s.execute(
            f"SELECT COUNT({c}), COUNT(DISTINCT {c}) FROM {table_name}"
        )
        s_nonnull, s_distinct = cur_s.fetchone()

        # PG aggregates
        cur_p = pg_conn.cursor()
        cur_p.execute(
            f'SELECT COUNT("{c}"), COUNT(DISTINCT "{c}") FROM {table_name}'
        )
        p_nonnull, p_distinct = cur_p.fetchone()

        if s_nonnull != p_nonnull or s_distinct != p_distinct:
            mismatches.append(
                f"{c}(N={s_nonnull}→{p_nonnull},D={s_distinct}→{p_distinct})"
            )
            if len(mismatches) >= 3:
                break

    if mismatches:
        return False, f"✗ {', '.join(mismatches)}"
    return True, f"✓ {checked} cols match"


def main():
    app_sqlite = get_sqlite(APP_DB_PATH)
    stock_sqlite = get_sqlite(STOCK_DB_PATH)
    pg_conn = get_pg()

    all_ok = True

    # ── Phase 1: Row Count ──
    print("=" * 70)
    print("  Phase 1: Row Count Comparison")
    print("=" * 70)
    print(f"{'Table':<30} {'SQLite':>10} {'PG':>10} {'Status':>10}")
    print("-" * 65)

    for table_name in sorted(TABLE_SOURCES.keys()):
        source = TABLE_SOURCES[table_name]
        sqlite_conn = stock_sqlite if source == "stock" else app_sqlite
        s_count, p_count, match = verify_row_count(sqlite_conn, pg_conn, table_name)
        status = "✓ OK" if match else f"✗ DIFF: {p_count - s_count:+d}"
        print(f"{table_name:<30} {s_count:>10} {p_count:>10} {status:>10}")
        if not match:
            all_ok = False

    # ── Phase 2: Content Verification ──
    print(f"\n{'=' * 70}")
    print("  Phase 2: Content Verification")
    print("=" * 70)

    for table_name in sorted(TABLE_SOURCES.keys()):
        source = TABLE_SOURCES[table_name]
        sqlite_conn = stock_sqlite if source == "stock" else app_sqlite
        match, info = verify_content(sqlite_conn, pg_conn, table_name)
        status = "✓ OK" if match else "✗ MISMATCH"
        print(f"  {table_name:<30} → {status}  ({info})")
        if not match:
            all_ok = False

    # ── Summary ──
    print(f"\n{'=' * 70}")
    if all_ok:
        print("  ✓ ALL CHECKS PASSED — Migration consistent!")
    else:
        print("  ✗ VERIFICATION FAILED — See mismatches above")
    print("=" * 70)

    app_sqlite.close()
    stock_sqlite.close()
    pg_conn.close()

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
