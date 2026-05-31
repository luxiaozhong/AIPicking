"""
SQLite → PostgreSQL 数据迁移脚本

用法:
    cd backend
    source venv/bin/activate
    python scripts/migrate_sqlite_to_pg.py

环境变量:
    STOCK_DB_PATH    — 股票 SQLite 路径（默认 /opt/stock_data/stock_db.sqlite）
    PG_MIGRATE_URL   — 目标 PostgreSQL URL
"""
import sqlite3
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras
from sqlalchemy import create_engine

# ── 配置 ──────────────────────────────────────────────
APP_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "database", "aipicking.db"
)
STOCK_DB_PATH = os.getenv(
    "STOCK_DB_PATH",
    os.path.expanduser("~") + "/workbuddy/2026-05-22-21-48-44/data/stock_db.sqlite"
)

_pg_url = os.getenv("PG_MIGRATE_URL", "")
if not _pg_url:
    _pg_url = "postgresql+psycopg2://aipicking:aipicking_dev_pwd@localhost:5432/aipicking"


def parse_pg_url(url: str) -> dict:
    """解析 PostgreSQL URL 为 psycopg2 连接参数"""
    clean = url.replace("postgresql+psycopg2://", "postgresql://")
    r = urlparse(clean)
    return {
        "host": r.hostname or "localhost",
        "port": r.port or 5432,
        "user": r.username or "aipicking",
        "password": r.password or "",
        "dbname": r.path.lstrip("/") or "aipicking",
    }


def get_sqlite_conn(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_pg_conn() -> psycopg2.extensions.connection:
    params = parse_pg_url(_pg_url)
    return psycopg2.connect(**params)


# ── 表迁移顺序（先独立表，后 FK 依赖表） ──────────────
# (table_name, source_db)
TABLE_ORDER = [
    # 股票数据（无 FK 依赖）
    ("stocks", "stock"),
    ("daily", "stock"),
    # sector_flow / daily_industry_flow → 已合并到 daily_sector_flow（2026-05-31）
    ("stock_themes", "stock"),
    ("daily_hot_stocks", "stock"),
    ("daily_hot_themes", "stock"),
    ("daily_northbound_flow", "stock"),
    # 应用数据 — 独立表
    ("users", "app"),
    ("strategies", "app"),
    # 应用数据 — 依赖 users + strategies
    ("backtest_reports", "app"),
    ("strategy_runs", "app"),
    ("batch_backtest_reports", "app"),
    ("ai_strategy_tasks", "app"),
    ("ai_factors", "app"),
]

# PostgreSQL SERIAL 序列名列表
SEQUENCES = [
    "stocks_id_seq", "daily_id_seq",
    # sector_flow_id_seq / daily_industry_flow_id_seq → 已随表删除（2026-05-31）
    "stock_themes_id_seq", "daily_hot_stocks_id_seq",
    "daily_hot_themes_id_seq", "daily_northbound_flow_id_seq",
    "users_id_seq", "strategies_id_seq",
    "backtest_reports_id_seq", "strategy_runs_id_seq",
    "batch_backtest_reports_id_seq", "ai_strategy_tasks_id_seq",
    "ai_factors_id_seq",
]


def create_tables(pg_conn):
    """在 PostgreSQL 中创建所有表"""
    from app.database import init_db_sync
    pg_engine = create_engine(_pg_url)
    try:
        init_db_sync(pg_engine)
    finally:
        pg_engine.dispose()
    print("Tables created in PostgreSQL.\n")


def migrate_table(pg_conn, sqlite_conn, table_name: str, pg_cur) -> int:
    """迁移单张表，返回迁移行数。自动处理列名差异和 Boolean 类型转换。"""
    cur_src = sqlite_conn.cursor()
    try:
        cur_src.execute(f"SELECT * FROM {table_name}")
    except sqlite3.OperationalError as e:
        print(f"  [SKIP] {table_name}: {e}")
        return 0

    rows = cur_src.fetchall()
    if not rows:
        print(f"  {table_name}: 0 rows")
        return 0

    src_columns = [desc[0] for desc in cur_src.description]

    # 获取 PG 列信息（列名 + 数据类型）
    pg_cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
        (table_name,)
    )
    pg_col_rows = pg_cur.fetchall()
    pg_col_names = [r[0] for r in pg_col_rows]
    pg_col_types = {r[0]: r[1] for r in pg_col_rows}

    # 找出需要排除的列（SQLite 有但 PG 没有）
    excluded = [c for c in src_columns if c not in set(pg_col_names)]
    if excluded:
        print(f"  {table_name}: excluding {excluded} (not in PG schema)")

    # 构建目标列（只包含 PG 有的）
    target_cols = [c for c in pg_col_names if c in src_columns]
    col_names = ", ".join(target_cols)
    placeholders = ", ".join(["%s"] * len(target_cols))

    # 构建 SQLite 列名 → 列索引 的快速映射
    src_col_index = {col: i for i, col in enumerate(src_columns)}

    # 转换行数据：按 target_cols 顺序（即 PG 列顺序）取值
    filtered_rows = []
    for row in rows:
        row_tuple = tuple(row)
        values = []
        for tcol in target_cols:
            si = src_col_index[tcol]
            val = row_tuple[si]
            # Boolean 类型转换：SQLite INTEGER 0/1 → Python bool
            if pg_col_types.get(tcol) == "boolean" and isinstance(val, int):
                val = bool(val)
            # DateTime 类型：将空字符串或 0 转为 None
            if pg_col_types.get(tcol) in (
                "timestamp without time zone", "timestamp with time zone",
                "date", "time without time zone"
            ):
                if val is None or val == "" or val == 0:
                    val = None
            values.append(val)
        filtered_rows.append(tuple(values))

    sql = (
        f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders}) "
        f"ON CONFLICT DO NOTHING"
    )

    # Batch insert
    batch_size = 10000
    for i in range(0, len(filtered_rows), batch_size):
        batch = filtered_rows[i:i + batch_size]
        pg_cur.executemany(sql, batch)

    pg_conn.commit()
    print(f"  {table_name}: {len(rows)} rows migrated")
    return len(rows)


def reset_sequences(pg_conn):
    """重置所有 SERIAL 序列到实际最大值+1"""
    cur = pg_conn.cursor()
    for seq_name in SEQUENCES:
        table_name = seq_name.replace("_id_seq", "")
        try:
            cur.execute(
                "SELECT setval(%s, (SELECT COALESCE(MAX(id), 1) FROM %s))",
                (seq_name, table_name)
            )
        except Exception as e:
            # Table might not exist or column might not be "id"
            pass
    pg_conn.commit()
    print("Sequences reset.\n")


def run_migration() -> dict:
    """执行迁移，返回每张表的迁移统计"""
    print("=" * 60)
    print("  SQLite → PostgreSQL 数据迁移")
    print("=" * 60)
    print(f"  App DB:    {APP_DB_PATH}")
    print(f"  Stock DB:  {STOCK_DB_PATH}")
    print(f"  Target PG: {_pg_url.replace('postgresql+psycopg2://', 'postgresql://')}")
    print()

    # 1. 检查源文件是否存在
    if not os.path.exists(APP_DB_PATH):
        print(f"ERROR: App DB not found: {APP_DB_PATH}")
        sys.exit(1)
    if not os.path.exists(STOCK_DB_PATH):
        print(f"ERROR: Stock DB not found: {STOCK_DB_PATH}")
        sys.exit(1)

    # 2. 连接
    print("Connecting...")
    app_sqlite = get_sqlite_conn(APP_DB_PATH)
    stock_sqlite = get_sqlite_conn(STOCK_DB_PATH)
    pg_conn = get_pg_conn()
    pg_cur = pg_conn.cursor()

    # 3. 建表
    print("Creating tables...")
    create_tables(pg_conn)

    # 4. 逐表迁移
    stats = {}
    total = 0
    print("Migrating data...")
    for table_name, source in TABLE_ORDER:
        src_conn = stock_sqlite if source == "stock" else app_sqlite
        count = migrate_table(pg_conn, src_conn, table_name, pg_cur)
        stats[table_name] = {"source": source, "count": count}
        total += count

    # 5. 重置序列
    print("\nResetting sequences...")
    reset_sequences(pg_conn)

    # 6. 关闭
    pg_cur.close()
    app_sqlite.close()
    stock_sqlite.close()
    pg_conn.close()

    print(f"Total: {total} rows across {len(TABLE_ORDER)} tables")
    print("Migration complete!")
    return stats


if __name__ == "__main__":
    run_migration()
