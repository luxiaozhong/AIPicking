# SQLite → PostgreSQL 迁移 & 双库合并 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将两个 SQLite 数据库（应用 DB + 股票 DB）合并为一个 PostgreSQL 数据库，支持真正的多用户并发写入。

**Architecture:** FastAPI + SQLAlchemy async（asyncpg 驱动）+ 单一 PostgreSQL 数据库。股票数据表新建 SQLAlchemy ORM 模型，stock_service 和 backtest_engine 从原始 SQL 改为 ORM 查询。sync_market_data.py 脚本改为写入 PostgreSQL。

**Tech Stack:** PostgreSQL 16, asyncpg (async), psycopg2-binary (sync fallback), SQLAlchemy 2.0.25

**当前状态：**
- 应用 DB（aipicking.db）：7 张表（`users`, `strategies`, `backtest_reports`, `strategy_runs`, `batch_backtest_reports`, `ai_strategy_tasks`, `ai_factors`）~852KB
- 股票 DB（stock_db.sqlite）：8 张表（`stocks`, `daily`, `sector_flow`, `stock_themes`, `daily_hot_stocks`, `daily_hot_themes`, `daily_northbound_flow`, `daily_industry_flow`）~数百MB

**核心策略：先迁移数据并验证，再改代码。** 迁移期间 app 始终运行在 SQLite 上，零停机风险。数据验证通过后，一次性切代码到 PostgreSQL。

---

## 阶段一：环境准备

### Task 1: 安装 PostgreSQL 16 & 创建数据库

- [ ] **Step 1: 安装 PostgreSQL**

```bash
# macOS（本地开发）
brew install postgresql@16
brew services start postgresql@16

# Linux（服务器部署）
apt update && apt install -y postgresql-16
systemctl start postgresql
systemctl enable postgresql
```

- [ ] **Step 2: 创建数据库和用户**

```bash
sudo -u postgres psql <<SQL
CREATE USER aipicking WITH PASSWORD '<secure-password>';
CREATE DATABASE aipicking OWNER aipicking;
GRANT ALL PRIVILEGES ON DATABASE aipicking TO aipicking;
\c aipicking
GRANT ALL ON SCHEMA public TO aipicking;
SQL
```

- [ ] **Step 3: 验证连接**

```bash
psql -h localhost -U aipicking -d aipicking -c "SELECT version();"
```

- [ ] **Step 4: 安装 psycopg2（迁移脚本用）**

```bash
cd backend && pip install psycopg2-binary asyncpg
```

---

## 阶段二：迁移前置准备（最小代码改动，不影响现有 app）

此阶段只新增和修改迁移所需的最小代码，**app 仍然运行在 SQLite 上**。

### Task 2: 创建股票数据表 ORM 模型

**Files:**
- Create: `backend/app/models/stock_tables.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 创建 stock_tables.py**（仅用于建表，暂不接入业务代码）

```python
"""股票数据库表模型 — 从 SQLite 迁移到 PostgreSQL 用"""
from sqlalchemy import (
    Column, String, Integer, Float, Text,
    Index, UniqueConstraint
)
from .base import BaseModel


class Stock(BaseModel):
    """股票基础信息表"""
    __tablename__ = "stocks"

    ts_code = Column(String(20), unique=True, nullable=False, index=True)
    symbol = Column(String(10))
    name = Column(String(100))
    market = Column(String(10))
    list_date = Column(String(8))
    industry_l1 = Column(String(50))
    industry_l2 = Column(String(50))
    industry_l3 = Column(String(50))
    region = Column(String(50), default="")
    concepts = Column(Text)
    total_shares = Column(Integer, default=0)
    float_shares = Column(Integer, default=0)
    update_time = Column(String(20))


class Daily(BaseModel):
    """日线行情数据表"""
    __tablename__ = "daily"
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uq_daily_code_date"),
        Index("idx_daily_date", "trade_date"),
        Index("idx_daily_code", "ts_code"),
    )

    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(String(8), nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    vol = Column(Float)
    amount = Column(Float)
    adj_close = Column(Float)
    market_cap = Column(Float, nullable=True)
    circ_market_cap = Column(Float, nullable=True)


class SectorFlow(BaseModel):
    """板块资金流向表"""
    __tablename__ = "sector_flow"
    __table_args__ = (
        UniqueConstraint("trade_date", "sector_code", "sector_type", name="uq_sector_flow"),
        Index("idx_sector_flow_date", "trade_date"),
        Index("idx_sector_flow_code", "sector_code", "sector_type"),
        Index("idx_sector_flow_type", "sector_type"),
    )

    trade_date = Column(String(10), nullable=False)
    sector_code = Column(String(20), nullable=False)
    sector_name = Column(String(100), nullable=False)
    sector_type = Column(String(20), nullable=False)
    change_pct = Column(Float)
    total_amount = Column(Float)
    main_inflow = Column(Float)
    main_inflow_pct = Column(Float)
    retail_inflow = Column(Float)
    retail_inflow_pct = Column(Float)
    net_inflow = Column(Float)
    big_order_inflow = Column(Float)
    big_order_inflow_pct = Column(Float)
    mid_order_inflow = Column(Float)
    mid_order_inflow_pct = Column(Float)
    small_order_inflow = Column(Float)
    tiny_order_inflow = Column(Float)
    update_time = Column(String(20))


class StockTheme(BaseModel):
    """股票主题/概念表"""
    __tablename__ = "stock_themes"

    ts_code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100))
    industry_l1 = Column(String(50))
    industry_l2 = Column(String(50))
    industry_l3 = Column(String(50))
    region = Column(String(50))
    themes = Column(Text)
    update_time = Column(String(20))


class DailyHotStock(BaseModel):
    """每日热门股票表"""
    __tablename__ = "daily_hot_stocks"
    __table_args__ = (
        UniqueConstraint("trade_date", "stock_code", name="uq_hot_stocks"),
        Index("idx_hot_stocks_date", "trade_date"),
        Index("idx_hot_stocks_code", "stock_code"),
        Index("idx_hot_stocks_reason", "reason"),
    )

    trade_date = Column(String(10), nullable=False)
    stock_code = Column(String(20), nullable=False)
    stock_name = Column(String(100), nullable=False)
    close = Column(Float)
    change_amt = Column(Float)
    change_pct = Column(Float)
    turnover_pct = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    reason = Column(String(200))
    market = Column(String(10))
    dde_net = Column(Float)
    sort_order = Column(Integer)


class DailyHotTheme(BaseModel):
    """每日热门主题表"""
    __tablename__ = "daily_hot_themes"
    __table_args__ = (
        UniqueConstraint("trade_date", "theme_name", name="uq_hot_themes"),
        Index("idx_hot_themes_date", "trade_date"),
        Index("idx_hot_themes_name", "theme_name"),
    )

    trade_date = Column(String(10), nullable=False)
    theme_name = Column(String(100), nullable=False)
    stock_count = Column(Integer, nullable=False)


class DailyNorthboundFlow(BaseModel):
    """每日北向资金流向表"""
    __tablename__ = "daily_northbound_flow"
    __table_args__ = (
        UniqueConstraint("trade_date", name="uq_northbound"),
        Index("idx_northbound_date", "trade_date"),
    )

    trade_date = Column(String(10), nullable=False)
    hgt_net_yi = Column(Float)
    sgt_net_yi = Column(Float)
    total_net_yi = Column(Float)
    data_points = Column(Integer)


class DailyIndustryFlow(BaseModel):
    """每日行业资金流向表"""
    __tablename__ = "daily_industry_flow"
    __table_args__ = (
        UniqueConstraint("trade_date", "industry_code", name="uq_industry_flow"),
        Index("idx_industry_flow_date", "trade_date"),
        Index("idx_industry_flow_code", "industry_code"),
        Index("idx_industry_flow_rank", "trade_date", "rank"),
    )

    trade_date = Column(String(10), nullable=False)
    industry_code = Column(String(20), nullable=False)
    industry_name = Column(String(100), nullable=False)
    change_pct = Column(Float)
    up_count = Column(Integer)
    down_count = Column(Integer)
    leader_stock = Column(String(20))
    leader_change = Column(Float)
    main_net_yi = Column(Float)
    super_large_net_yi = Column(Float)
    large_net_yi = Column(Float)
    mid_net_yi = Column(Float)
    small_net_yi = Column(Float)
    rank = Column(Integer)
```

- [ ] **Step 2: 更新 models/__init__.py**（追加导入，不删除现有代码）

```python
"""Models package"""
from sqlalchemy.orm import relationship
from .base import Base, BaseModel
from .user import User
from .strategy import Strategy
from .backtest import BacktestReport, StrategyRun, BatchBacktestReport
from .ai_task import AIStrategyTask
from .ai_factor import AIFactor
# 新增：股票数据表模型（迁移用）
from .stock_tables import (
    Stock, Daily, SectorFlow, StockTheme,
    DailyHotStock, DailyHotTheme, DailyNorthboundFlow, DailyIndustryFlow,
)

# 关系定义不变...
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/stock_tables.py backend/app/models/__init__.py
git commit -m "model: add stock data table ORM models for migration"
```

---

### Task 3: 新增 init_db_sync 函数（database.py）

**Files:**
- Modify: `backend/app/database.py`

**注意：** 只追加函数，不修改现有 `engine` 和 `get_db()` 等逻辑（app 仍在 SQLite 上运行）。

- [ ] **Step 1: 在 database.py 末尾追加 init_db_sync**

```python
# ====== 以下为 PostgreSQL 迁移用，不影响现有 SQLite 运行 ======

def _get_sync_pg_url() -> str:
    """获取同步 PostgreSQL 连接 URL（迁移脚本用）"""
    import os
    return os.getenv(
        "PG_MIGRATE_URL",
        "postgresql+psycopg2://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:5432/<DB_NAME>",
    )


def init_db_sync(pg_conn=None):
    """
    在 PostgreSQL 中创建所有表结构（同步）。
    
    用法1（传已有连接）：init_db_sync(pg_conn)
    用法2（自动创建连接）：init_db_sync()
    """
    from sqlalchemy import create_engine
    from .models.base import Base

    if pg_conn is not None:
        Base.metadata.create_all(pg_conn)
    else:
        engine = create_engine(_get_sync_pg_url())
        try:
            Base.metadata.create_all(engine)
        finally:
            engine.dispose()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/database.py
git commit -m "db: add init_db_sync() for PostgreSQL table creation during migration"
```

---

## 阶段三：数据迁移 & 比对验证

> **关键原则：** 此阶段 app 仍在 SQLite 上运行。先完成迁移和比对，确认数据 100% 一致后，再进入阶段四改代码。

### Task 4: 编写数据迁移脚本

**Files:**
- Create: `backend/scripts/migrate_sqlite_to_pg.py`

- [ ] **Step 1: 编写完整迁移脚本**

```python
"""
SQLite → PostgreSQL 数据迁移脚本

用法:
    cd backend
    python scripts/migrate_sqlite_to_pg.py

环境变量:
    STOCK_DB_PATH    — 股票 SQLite 路径（默认 /opt/stock_data/stock_db.sqlite）
    PG_MIGRATE_URL   — 目标 PostgreSQL URL（默认 postgresql+psycopg2://...）
    可选 DATABASE_URL — 用于提取 PG 连接（若有 +asyncpg 前缀会自动去除）
"""
import sqlite3
import os
import sys
from urllib.parse import urlparse

# 先确保能导入 app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras

# ── 配置 ──────────────────────────────────────────────
APP_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "database", "aipicking.db"
)
STOCK_DB_PATH = os.getenv("STOCK_DB_PATH", "/opt/stock_data/stock_db.sqlite")

# 迁移目标 PG URL
_pg_url = os.getenv("PG_MIGRATE_URL", "")
if not _pg_url:
    _pg_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:5432/<DB_NAME>"
    )
_pg_url = _pg_url.replace("+asyncpg", "").replace("+psycopg2", "")
_pg_url = f"postgresql+psycopg2://{urlparse(_pg_url).netloc}{urlparse(_pg_url).path}"


def parse_pg_url(url: str):
    """解析 PostgreSQL URL 为 psycopg2 连接参数"""
    # 去掉 +driver 前缀
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
TABLE_ORDER = [
    # 股票数据（无 FK 依赖）
    ("stocks",        "stock"),
    ("daily",         "stock"),
    ("sector_flow",   "stock"),
    ("stock_themes",  "stock"),
    ("daily_hot_stocks",   "stock"),
    ("daily_hot_themes",   "stock"),
    ("daily_northbound_flow", "stock"),
    ("daily_industry_flow",   "stock"),
    # 应用数据 — 独立表
    ("users",         "app"),
    ("strategies",    "app"),
    # 应用数据 — 依赖 users + strategies
    ("backtest_reports",       "app"),
    ("strategy_runs",          "app"),
    ("batch_backtest_reports", "app"),
    ("ai_strategy_tasks",      "app"),
    ("ai_factors",             "app"),
]

# PostgreSQL SERIAL 序列名（用于迁移后重置）
SEQUENCES = [
    "stocks_id_seq", "daily_id_seq", "sector_flow_id_seq",
    "stock_themes_id_seq", "daily_hot_stocks_id_seq",
    "daily_hot_themes_id_seq", "daily_northbound_flow_id_seq",
    "daily_industry_flow_id_seq", "users_id_seq", "strategies_id_seq",
    "backtest_reports_id_seq", "strategy_runs_id_seq",
    "batch_backtest_reports_id_seq", "ai_strategy_tasks_id_seq",
    "ai_factors_id_seq",
]


def create_tables(pg_conn):
    """在 PostgreSQL 中创建所有表"""
    from app.database import init_db_sync
    init_db_sync(pg_conn)
    pg_conn.commit()
    print("Tables created in PostgreSQL.")


def migrate_table(sqlite_conn, pg_conn, table_name: str) -> int:
    """迁移单张表，返回迁移行数"""
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

    columns = [desc[0] for desc in cur_src.description]
    col_names = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))

    cur_pg = pg_conn.cursor()
    sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    cur_pg.executemany(sql, rows)
    pg_conn.commit()
    print(f"  {table_name}: {len(rows)} rows migrated")
    return len(rows)


def reset_sequences(pg_conn):
    """重置所有 SERIAL 序列到实际最大值+1"""
    cur = pg_conn.cursor()
    for seq_name in SEQUENCES:
        # 提取表名：stocks_id_seq → stocks
        table_name = seq_name.replace("_id_seq", "")
        try:
            cur.execute(
                f"SELECT setval(%s, (SELECT COALESCE(MAX(id), 1) FROM {table_name}))",
                (seq_name,)
            )
        except Exception as e:
            print(f"  [WARN] reset sequence {seq_name}: {e}")
    pg_conn.commit()
    print("Sequences reset.")


def run_migration() -> dict:
    """
    执行迁移，返回每张表的迁移统计:
    {table_name: {"source": "app"|"stock", "count": int}}
    """
    print("=" * 60)
    print("  SQLite → PostgreSQL 数据迁移")
    print("=" * 60)
    print(f"  App DB:  {APP_DB_PATH}")
    print(f"  Stock DB: {STOCK_DB_PATH}")
    print(f"  Target:  {_pg_url.replace('postgresql+psycopg2://', 'postgresql://')}")
    print()

    # 1. 连接
    print("Connecting...")
    app_sqlite = get_sqlite_conn(APP_DB_PATH)
    stock_sqlite = get_sqlite_conn(STOCK_DB_PATH)
    pg_conn = get_pg_conn()

    # 2. 建表
    print("\nCreating tables...")
    create_tables(pg_conn)

    # 3. 逐表迁移
    stats = {}
    total = 0
    print("\nMigrating data...")
    for table_name, source in TABLE_ORDER:
        src_conn = stock_sqlite if source == "stock" else app_sqlite
        count = migrate_table(src_conn, pg_conn, table_name)
        stats[table_name] = {"source": source, "count": count}
        total += count

    # 4. 重置序列
    print("\nResetting sequences...")
    reset_sequences(pg_conn)

    # 5. 关闭
    app_sqlite.close()
    stock_sqlite.close()
    pg_conn.close()

    print(f"\nTotal: {total} rows across {len(TABLE_ORDER)} tables")
    print("Migration complete!")
    return stats


if __name__ == "__main__":
    run_migration()
```

- [ ] **Step 2: 本地执行迁移**

```bash
cd backend
python scripts/migrate_sqlite_to_pg.py
```

---

### Task 5: 数据比对验证

> **目标：** 逐表比对 SQLite 和 PostgreSQL 的行数和数据一致性，确保迁移 100% 正确。

- [ ] **Step 1: 创建比对脚本**

**Files:**
- Create: `backend/scripts/verify_migration.py`

```python
"""
数据迁移验证脚本 — 比对 SQLite 和 PostgreSQL 每张表的行数和抽样数据

用法:
    cd backend
    python scripts/verify_migration.py
    python scripts/verify_migration.py --full  # 全量比对（大表较慢）
"""
import sqlite3
import os
import sys
import hashlib
import json
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras

# ── 配置 ──────────────────────────────────────────────
APP_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "database", "aipicking.db"
)
STOCK_DB_PATH = os.getenv("STOCK_DB_PATH", "/opt/stock_data/stock_db.sqlite")

_pg_url = os.getenv("PG_MIGRATE_URL", "").replace("+asyncpg", "").replace("+psycopg2", "")
if not _pg_url:
    _pg_url = os.getenv("DATABASE_URL", "postgresql://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:5432/<DB_NAME>")
    _pg_url = _pg_url.replace("+asyncpg", "")

# 表 → 源 SQLite 映射
TABLE_SOURCES = {
    "stocks": "stock", "daily": "stock", "sector_flow": "stock",
    "stock_themes": "stock", "daily_hot_stocks": "stock",
    "daily_hot_themes": "stock", "daily_northbound_flow": "stock",
    "daily_industry_flow": "stock",
    "users": "app", "strategies": "app", "backtest_reports": "app",
    "strategy_runs": "app", "batch_backtest_reports": "app",
    "ai_strategy_tasks": "app", "ai_factors": "app",
}


def parse_pg_url(url: str):
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
    return psycopg2.connect(**parse_pg_url(_pg_url))


def hash_row(row: tuple) -> str:
    """对一行数据计算 hash"""
    return hashlib.md5(
        json.dumps([str(v) for v in row], sort_keys=True).encode()
    ).hexdigest()


def verify_row_count(sqlite_conn, pg_conn, table_name: str) -> dict:
    """比对行数"""
    cur_s = sqlite_conn.cursor()
    cur_s.execute(f"SELECT COUNT(*) FROM {table_name}")
    sqlite_count = cur_s.fetchone()[0]

    cur_p = pg_conn.cursor()
    cur_p.execute(f"SELECT COUNT(*) FROM {table_name}")
    pg_count = cur_p.fetchone()[0]

    match = sqlite_count == pg_count
    return {
        "table": table_name,
        "sqlite_count": sqlite_count,
        "pg_count": pg_count,
        "match": match,
        "diff": pg_count - sqlite_count if not match else 0,
    }


def verify_data_sample(sqlite_conn, pg_conn, table_name: str, sample_size: int = 100) -> dict:
    """抽样比对：取前后各 50 行做 hash 比对"""
    cur_s = sqlite_conn.cursor()
    cur_s.execute(f"SELECT * FROM {table_name}")
    columns = [desc[0] for desc in cur_s.description]
    all_rows = cur_s.fetchall()
    total = len(all_rows)

    if total == 0:
        return {"table": table_name, "total": 0, "sample_checked": 0,
                "mismatches": 0, "match": True}

    # 取前 sample_size//2 + 后 sample_size//2
    sample = list(all_rows[:sample_size // 2])
    if total > sample_size:
        sample += list(all_rows[-(sample_size // 2):])

    cur_p = pg_conn.cursor()
    cur_p.execute(f"SELECT * FROM {table_name}")
    pg_rows = cur_p.fetchall()

    # 构建 PG hash 集合（按第一列 id 索引）
    pg_by_id = {}
    for row in pg_rows:
        pg_by_id[row[0]] = row

    mismatches = 0
    for sqlite_row in sample:
        row_id = sqlite_row[0]
        if row_id in pg_by_id:
            if hash_row(sqlite_row) != hash_row(pg_by_id[row_id]):
                mismatches += 1
        else:
            mismatches += 1

    return {
        "table": table_name,
        "total": total,
        "sample_checked": len(sample),
        "mismatches": mismatches,
        "match": mismatches == 0,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Full data verification (slower)")
    parser.add_argument("--table", help="Verify single table only")
    args = parser.parse_args()

    app_sqlite = get_sqlite_conn(APP_DB_PATH)
    stock_sqlite = get_sqlite_conn(STOCK_DB_PATH)
    pg_conn = get_pg_conn()

    tables = [args.table] if args.table else sorted(TABLE_SOURCES.keys())
    all_ok = True

    print("=" * 70)
    print("  Migration Verification Report")
    print("=" * 70)

    # ── Phase 1: 行数比对 ─────────────────────────────
    print("\n── Phase 1: Row Count Comparison ──")
    print(f"{'Table':<30} {'SQLite':>8} {'PG':>8} {'Status':>10}")
    print("-" * 60)

    for table_name in tables:
        source = TABLE_SOURCES.get(table_name, "app")
        sqlite_conn = stock_sqlite if source == "stock" else app_sqlite
        result = verify_row_count(sqlite_conn, pg_conn, table_name)
        status = "✓ OK" if result["match"] else f"✗ DIFF: {result['diff']:+d}"
        print(f"{table_name:<30} {result['sqlite_count']:>8} {result['pg_count']:>8} {status:>10}")
        if not result["match"]:
            all_ok = False

    # ── Phase 2: 抽样数据比对 ──────────────────────────
    sample_size = 0 if args.full else 200  # full 模式下全量比对
    print(f"\n── Phase 2: Data Integrity Check (sample_size={'ALL' if args.full else sample_size}) ──")

    mismatched_tables = []
    for table_name in tables:
        source = TABLE_SOURCES.get(table_name, "app")
        sqlite_conn = stock_sqlite if source == "stock" else app_sqlite
        result = verify_data_sample(sqlite_conn, pg_conn, table_name, sample_size=sample_size)
        if result["total"] == 0:
            continue
        status = "✓ OK" if result["match"] else f"✗ {result['mismatches']} mismatches"
        print(f"  {table_name:<30} checked {result['sample_checked']}/{result['total']} rows → {status}")
        if not result["match"]:
            mismatched_tables.append(table_name)
            all_ok = False

    # ── Summary ────────────────────────────────────────
    print("\n" + "=" * 70)
    if all_ok:
        print("  ✓ ALL CHECKS PASSED — Migration is consistent!")
    else:
        print(f"  ✗ VERIFICATION FAILED — {len(mismatched_tables)} table(s) have mismatches:")
        for t in mismatched_tables:
            print(f"    - {t}")
    print("=" * 70)

    app_sqlite.close()
    stock_sqlite.close()
    pg_conn.close()

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 执行比对**

```bash
cd backend
python scripts/verify_migration.py
```

预期输出：
```
======================================================================
  Migration Verification Report
======================================================================

── Phase 1: Row Count Comparison ──
Table                           SQLite       PG     Status
------------------------------------------------------------
ai_factors                            2        2      ✓ OK
ai_strategy_tasks                     3        3      ✓ OK
backtest_reports                      5        5      ✓ OK
...
stocks                             5432     5432      ✓ OK
...
── Phase 2: Data Integrity Check ──
  stocks                          checked 200/5432 rows → ✓ OK
  ...
======================================================================
  ✓ ALL CHECKS PASSED — Migration is consistent!
======================================================================
```

- [ ] **Step 3: 如果比对失败，根据错误信息修复迁移脚本，重新执行 Task 4 → Task 5**

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/migrate_sqlite_to_pg.py backend/scripts/verify_migration.py
git commit -m "feat: add SQLite-to-PostgreSQL migration and verification scripts"
```

---

## 阶段四：App 代码改造（切换到 PostgreSQL）

> **此时数据已完整迁移到 PostgreSQL 且验证通过。开始改代码让 app 读写 PostgreSQL。**

### Task 6: 更新 requirements.txt

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 替换依赖**

```txt
# 数据库
sqlalchemy==2.0.25
# aiosqlite==0.19.0          # 移除
asyncpg==0.29.0               # 新增：PostgreSQL async 驱动
psycopg2-binary==2.9.9        # 新增：PostgreSQL sync 驱动（backtest 线程用）
```

- [ ] **Step 2: 安装**

```bash
cd backend && pip install asyncpg psycopg2-binary
```

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "deps: replace aiosqlite with asyncpg + psycopg2-binary"
```

---

### Task 7: 更新 config.py

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: 修改 DATABASE_URL 默认值，新增 SYNC_DATABASE_URL，移除 STOCK_DB_PATH**

```python
class Settings:
    def __init__(self):
        # ... 其他配置不变 ...

        # 数据库配置
        _default_db_url = (
            "postgresql+asyncpg://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:5432/<DB_NAME>"
        )
        self.DATABASE_URL = os.getenv("DATABASE_URL", _default_db_url)
        self.SYNC_DATABASE_URL = os.getenv(
            "SYNC_DATABASE_URL",
            self.DATABASE_URL.replace("+asyncpg", "+psycopg2"),
        )

        # 移除：
        # self.STOCK_DB_PATH = os.getenv("STOCK_DB_PATH", "/opt/stock_data/stock_db.sqlite")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/config.py
git commit -m "config: switch to PostgreSQL DATABASE_URL, add SYNC_DATABASE_URL, remove STOCK_DB_PATH"
```

---

### Task 8: 更新 database.py（连接池配置）

**Files:**
- Modify: `backend/app/database.py`

- [ ] **Step 1: 更新引擎配置**

```python
"""数据库连接和会话管理"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from .config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """依赖注入：获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def async_session():
    """创建新的异步会话（用于后台任务）"""
    return AsyncSessionLocal()


async def init_db():
    """初始化数据库（创建表）"""
    from .models.base import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ====== 迁移/同步工具函数 ======

def init_db_sync(pg_conn=None):
    """在 PostgreSQL 中创建所有表结构（同步）"""
    from sqlalchemy import create_engine
    from .models.base import Base
    if pg_conn is not None:
        Base.metadata.create_all(pg_conn)
    else:
        sync_engine = create_engine(settings.SYNC_DATABASE_URL)
        try:
            Base.metadata.create_all(sync_engine)
        finally:
            sync_engine.dispose()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/database.py
git commit -m "db: configure asyncpg connection pool, keep init_db_sync for migration"
```

---

### Task 9: 改造 stock_service.py（aiosqlite → SQLAlchemy ORM）

**Files:**
- Modify: `backend/app/services/stock_service.py`

- [ ] **Step 1: 用 ORM 完全重写**

```python
"""股票搜索服务 — 通过 SQLAlchemy ORM 查询 PostgreSQL"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.stock_tables import Stock, Daily


class StockService:
    """股票搜索和 K 线数据查询"""

    @staticmethod
    async def search(db: AsyncSession, q: str, limit: int = 10) -> dict:
        like_q = f"%{q}%"
        stmt = (
            select(Stock.ts_code, Stock.symbol, Stock.name, Stock.market)
            .where(
                (Stock.ts_code.ilike(like_q)) | (Stock.name.ilike(like_q))
            )
            .order_by(Stock.ts_code)
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.all()
        items = [
            {"ts_code": r.ts_code, "symbol": r.symbol, "name": r.name, "market": r.market}
            for r in rows
        ]
        return {"items": items, "total": len(items)}

    @staticmethod
    async def get_kline(db: AsyncSession, ts_code: str, days: int = 365) -> dict:
        stock_stmt = select(Stock.name).where(Stock.ts_code == ts_code)
        stock_result = await db.execute(stock_stmt)
        stock_name = stock_result.scalar()

        stmt = (
            select(
                Daily.trade_date, Daily.open, Daily.high, Daily.low,
                Daily.close, Daily.vol, Daily.amount
            )
            .where(Daily.ts_code == ts_code)
            .order_by(Daily.trade_date.desc())
            .limit(days)
        )
        result = await db.execute(stmt)
        rows = result.all()
        items = [
            {
                "trade_date": r.trade_date, "open": r.open, "high": r.high,
                "low": r.low, "close": r.close, "vol": r.vol, "amount": r.amount,
            }
            for r in reversed(rows)
        ]
        return {"ts_code": ts_code, "name": stock_name or "", "items": items}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/stock_service.py
git commit -m "refactor: rewrite stock_service from raw aiosqlite to SQLAlchemy ORM"
```

---

### Task 10: 改造 backtest_engine.py（sqlite3 → SQLAlchemy 同步 ORM）

**Files:**
- Modify: `backend/app/services/backtest_engine.py`

**注意：** backtest_engine 在 thread pool 中运行（同步），需要用 SQLAlchemy 同步 session + psycopg2。

- [ ] **Step 1: 替换文件顶部导入和连接方式**

```python
"""回测引擎核心"""
import ast
import io
import os
import sys
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from ..config import settings
from ..models.stock_tables import Stock, Daily, SectorFlow

# 同步引擎（thread pool 中使用）
_sync_engine = create_engine(settings.SYNC_DATABASE_URL)
SyncSession = sessionmaker(bind=_sync_engine)


def _get_db():
    """获取同步数据库会话（回测线程中使用）"""
    return SyncSession()
```

- [ ] **Step 2: 删除 `STOCK_DB_PATH = settings.STOCK_DB_PATH`**

- [ ] **Step 3: 重写 `_load_data` 方法**

```python
def _load_data(self, cutoff_date: str):
    session = _get_db()
    try:
        # 1. 股票基础信息
        stmt = select(
            Stock.ts_code, Stock.symbol, Stock.name, Stock.market,
            Stock.industry_l1, Stock.industry_l2, Stock.industry_l3,
            Stock.concepts, Stock.total_shares, Stock.float_shares
        ).where(Stock.ts_code.isnot(None), Stock.ts_code != "")
        stocks_result = session.execute(stmt)
        stocks_data = [dict(row._mapping) for row in stocks_result]

        # 2. 日期范围
        cutoff_dt = datetime.strptime(cutoff_date, "%Y%m%d")
        start_dt = cutoff_dt - timedelta(days=180)
        start_date = start_dt.strftime("%Y%m%d")
        flow_start_date = (cutoff_dt - timedelta(days=30)).strftime("%Y%m%d")

        # 3. 日线数据
        daily_stmt = select(
            Daily.ts_code, Daily.trade_date, Daily.open, Daily.high,
            Daily.low, Daily.close, Daily.vol, Daily.amount,
            Daily.adj_close, Daily.market_cap, Daily.circ_market_cap
        ).where(
            Daily.trade_date.between(start_date, cutoff_date)
        ).order_by(Daily.ts_code, Daily.trade_date)
        daily_result = session.execute(daily_stmt)
        daily_rows = [dict(row._mapping) for row in daily_result]

        # 4. 板块资金流向
        sector_stmt = select(SectorFlow).where(
            SectorFlow.trade_date.between(flow_start_date, cutoff_date)
        ).order_by(SectorFlow.trade_date, SectorFlow.sector_type, SectorFlow.sector_name)
        sector_result = session.execute(sector_stmt)
        sector_flow_data = [dict(row._mapping) for row in sector_result]
    finally:
        session.close()

    # 5. 按 ts_code 分组
    daily_data = {}
    for row in daily_rows:
        ts_code = row["ts_code"]
        if ts_code not in daily_data:
            daily_data[ts_code] = []
        daily_data[ts_code].append({
            "trade_date": row["trade_date"], "open": row["open"],
            "high": row["high"], "low": row["low"], "close": row["close"],
            "vol": row["vol"], "amount": row["amount"],
            "adj_close": row["adj_close"], "market_cap": row["market_cap"],
            "circ_market_cap": row["circ_market_cap"],
        })

    return stocks_data, daily_data, sector_flow_data
```

- [ ] **Step 4: 重写 `_load_data_range` 方法**（同理，使用 `between(earliest_date, end_date)`）

- [ ] **Step 5: 重写 `_track_performance` 方法**

```python
def _track_performance(self, recommendations, cutoff_date, track_days):
    session = _get_db()
    try:
        ts_codes = [r['ts_code'] for r in recommendations]
        if not ts_codes:
            return recommendations

        # 截止日价格
        stmt = select(
            Daily.ts_code, Daily.adj_close, Daily.close
        ).where(
            Daily.ts_code.in_(ts_codes),
            Daily.trade_date == cutoff_date
        )
        result = session.execute(stmt)
        cutoff_prices = {}
        for row in result:
            price = row.adj_close if row.adj_close else row.close
            cutoff_prices[row.ts_code] = price

        # 前一日价格（计算当日涨跌）
        for rec in recommendations:
            ts_code = rec['ts_code']
            prev_stmt = select(
                Daily.adj_close, Daily.close
            ).where(
                Daily.ts_code == ts_code,
                Daily.trade_date < cutoff_date
            ).order_by(Daily.trade_date.desc()).limit(1)
            prev_result = session.execute(prev_stmt).first()
            if prev_result and ts_code in cutoff_prices:
                prev_price = prev_result.adj_close if prev_result.adj_close else prev_result.close
                rec['return_0d'] = round(
                    (cutoff_prices[ts_code] - prev_price) / prev_price, 6
                )
            else:
                rec['return_0d'] = None

        # 后续表现追踪
        for rec in recommendations:
            ts_code = rec['ts_code']
            cutoff_price = cutoff_prices.get(ts_code)
            if not cutoff_price:
                for d in track_days:
                    rec[f'return_{d}d'] = None
                continue

            future_stmt = select(
                Daily.trade_date, Daily.adj_close, Daily.close
            ).where(
                Daily.ts_code == ts_code,
                Daily.trade_date > cutoff_date
            ).order_by(Daily.trade_date).limit(30)
            future_rows = session.execute(future_stmt).all()

            future_prices = {}
            for row in future_rows:
                price = row.adj_close if row.adj_close else row.close
                future_prices[row.trade_date] = price

            future_dates = sorted(future_prices.keys())
            for d in track_days:
                if len(future_dates) >= d:
                    target_price = future_prices[future_dates[d - 1]]
                    rec[f'return_{d}d'] = round(
                        (target_price - cutoff_price) / cutoff_price, 6
                    )
                else:
                    rec[f'return_{d}d'] = None
    finally:
        session.close()

    return recommendations
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/backtest_engine.py
git commit -m "refactor: rewrite backtest_engine from raw sqlite3 to SQLAlchemy sync ORM"
```

---

### Task 11: 修复 backtest_service.py（sync engine 创建方式）

**Files:**
- Modify: `backend/app/services/backtest_service.py`

- [ ] **Step 1: 修改 `_run_backtest` 中的 engine 创建**

```python
@staticmethod
def _run_backtest(backtest_id: int, cutoff_date: str, track_days: List[int]):
    """执行回测（线程池中运行，使用同步 Session）"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from ..config import settings

    engine = create_engine(settings.SYNC_DATABASE_URL)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        # ... 其余逻辑不变 ...
```

- [ ] **Step 2: 同步修改 `_run_batch_backtest` 方法**

- [ ] **Step 3: 移除 `from .backtest_engine import BacktestEngine, STOCK_DB_PATH` 中的 `STOCK_DB_PATH`**

```python
from .backtest_engine import BacktestEngine
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/backtest_service.py
git commit -m "fix: use SYNC_DATABASE_URL from config instead of URL string munging"
```

---

### Task 12: 更新 stock API 路由（注入 db session）

**Files:**
- Modify: `backend/app/api/stocks.py`

- [ ] **Step 1: 给路由函数注入 db session**

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..services.stock_service import StockService

router = APIRouter()


@router.get("/search")
async def search_stocks(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    result = await StockService.search(db, q=q, limit=limit)
    return {"code": 0, "message": "success", "data": result}


@router.get("/{ts_code}/kline")
async def get_stock_kline(
    ts_code: str,
    days: int = Query(365, ge=1, le=730),
    db: AsyncSession = Depends(get_db),
):
    result = await StockService.get_kline(db, ts_code=ts_code, days=days)
    return {"code": 0, "message": "success", "data": result}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/stocks.py
git commit -m "fix: inject db session into stock API routes"
```

---

### Task 13: 更新 sync_market_data.py（sqlite3 → psycopg2）

**Files:**
- Modify: `backend/scripts/sync_market_data.py`

- [ ] **Step 1: 替换 DB 连接层** — `sqlite3` → `psycopg2`，`INSERT OR REPLACE` → `ON CONFLICT DO UPDATE`

```python
import psycopg2
import psycopg2.extras
from urllib.parse import urlparse


def get_db_connection() -> psycopg2.extensions.connection:
    db_url = os.getenv("DATABASE_URL", "postgresql://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:5432/<DB_NAME>")
    db_url = db_url.replace("+asyncpg", "").replace("+psycopg2", "")
    r = urlparse(db_url)
    conn = psycopg2.connect(
        host=r.hostname or "localhost",
        port=r.port or 5432,
        user=r.username or "aipicking",
        password=r.password or "",
        dbname=r.path.lstrip("/") or "aipicking",
    )
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn
```

- [ ] **Step 2: 更新 DDL** — `AUTOINCREMENT` → `SERIAL`，`datetime('now')` → `NOW()`

- [ ] **Step 3: 更新所有 INSERT 语句** — `INSERT OR REPLACE` → `INSERT ... ON CONFLICT ... DO UPDATE`

```python
_STOCK_INSERT = """
    INSERT INTO daily_hot_stocks
        (trade_date, stock_code, stock_name, close, change_amt, change_pct,
         turnover_pct, volume, amount, reason, market, dde_net, sort_order)
    VALUES (%(trade_date)s, %(stock_code)s, %(stock_name)s, %(close)s, %(change_amt)s,
            %(change_pct)s, %(turnover_pct)s, %(volume)s, %(amount)s, %(reason)s,
            %(market)s, %(dde_net)s, %(sort_order)s)
    ON CONFLICT (trade_date, stock_code) DO UPDATE SET
        close = EXCLUDED.close,
        change_amt = EXCLUDED.change_amt,
        change_pct = EXCLUDED.change_pct,
        turnover_pct = EXCLUDED.turnover_pct,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        reason = EXCLUDED.reason,
        market = EXCLUDED.market,
        dde_net = EXCLUDED.dde_net,
        sort_order = EXCLUDED.sort_order
"""
# 其他 INSERT 语句同理...
```

- [ ] **Step 4: 移除 `--db` CLI 参数和 `DEFAULT_STOCK_DB`**

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/sync_market_data.py
git commit -m "refactor: migrate sync_market_data from sqlite3 to psycopg2/PostgreSQL"
```

---

### Task 14: 更新 main.py & 测试 & .env

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_strategies.py`
- Modify: `backend/tests/test_backtests.py`
- Modify: `backend/.env`

- [ ] **Step 1: 清理 main.py 中 SQLite 相关的手动迁移**

```python
@app.on_event("startup")
async def startup_event():
    await init_db()

    # 移除手动 ALTER TABLE 代码（已有 ORM 模型覆盖）

    from .database import async_session
    from .services.auth_service import seed_default_admin
    session = await async_session()
    try:
        admin = await seed_default_admin(session)
        await session.commit()
        print(f"默认管理员账号已就绪: {admin.username}")
    finally:
        await session.close()

    # seed_strategies & education 不变...
```

- [ ] **Step 2: 更新测试文件 — 测试保持 SQLite 内存库**

```python
# tests/test_strategies.py
import os
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "sqlite+aiosqlite:///:memory:"
)
```

- [ ] **Step 3: 更新 .env**

```bash
DATABASE_URL=postgresql+asyncpg://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:5432/<DB_NAME>
SYNC_DATABASE_URL=postgresql+psycopg2://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:5432/<DB_NAME>
# STOCK_DB_PATH 移除
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/tests/ backend/.env
git commit -m "chore: clean up startup code, update .env for PostgreSQL"
```

---

## 阶段五：验证 & 部署

### Task 15: 本地全功能验证

- [ ] **Step 1: 启动后端**

```bash
cd backend && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: 验证所有 API 端点**

```bash
# 健康检查
curl http://localhost:8000/health

# 股票搜索（原股票 DB 数据）
curl "http://localhost:8000/api/v1/stocks/search?q=平安"

# K 线数据
curl "http://localhost:8000/api/v1/stocks/000001.SZ/kline?days=30"

# 登录
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<admin-password>"}'

# 策略列表
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<admin-password>"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/strategies
```

- [ ] **Step 3: 验证回测功能**

```bash
# 提交回测
curl -X POST http://localhost:8000/api/v1/backtests \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"strategy_id": 1, "cutoff_date": "20260501", "track_days": [3, 7, 15]}'
```

- [ ] **Step 4: 验证 sync_market_data**

```bash
python backend/scripts/sync_market_data.py --date 2026-05-29
```

- [ ] **Step 5: 运行测试**

```bash
pytest backend/tests/ -v
```

- [ ] **Step 6: 修复验证中发现的问题，commit**

```bash
git add -A && git commit -m "fix: issues found during local verification"
```

---

### Task 16: 服务器部署

**服务器:** `<YOUR_SERVER_IP>`

- [ ] **Step 1: SSH 到服务器，安装 PostgreSQL 16**

```bash
ssh root@<YOUR_SERVER_IP>
apt update && apt install -y postgresql-16
systemctl start postgresql
systemctl enable postgresql
```

- [ ] **Step 2: 创建数据库和用户**

```bash
sudo -u postgres psql <<SQL
CREATE USER aipicking WITH PASSWORD '<secure-password>';
CREATE DATABASE aipicking OWNER aipicking;
GRANT ALL PRIVILEGES ON DATABASE aipicking TO aipicking;
\c aipicking
GRANT ALL ON SCHEMA public TO aipicking;
SQL
```

- [ ] **Step 3: 拉取代码 & 安装依赖**

```bash
cd /opt/AIpicking
git pull
cd backend && pip install asyncpg psycopg2-binary
```

- [ ] **Step 4: 执行数据迁移**

```bash
cd /opt/AIpicking/backend
PG_MIGRATE_URL="postgresql://aipicking:<secure-password>@localhost:5432/aipicking" \
  python scripts/migrate_sqlite_to_pg.py
```

- [ ] **Step 5: 执行数据比对**

```bash
PG_MIGRATE_URL="postgresql://aipicking:<secure-password>@localhost:5432/aipicking" \
  python scripts/verify_migration.py
```

如果比对不通过，**停止部署**，排查原因。

- [ ] **Step 6: 更新 .env.production**

```bash
cat > /opt/AIpicking/backend/.env.production <<EOF
DATABASE_URL=postgresql+asyncpg://aipicking:<secure-password>@localhost:5432/aipicking
SYNC_DATABASE_URL=postgresql+psycopg2://aipicking:<secure-password>@localhost:5432/aipicking
DEEPSEEK_API_KEY=<existing-key>
JWT_SECRET_KEY=<existing-key>
# ... 其他配置保持不变 ...
EOF
```

- [ ] **Step 7: 重启服务**

```bash
cd /opt/AIpicking/frontend && npm install --silent && npm run build
systemctl restart aipicking
```

- [ ] **Step 8: 验证部署**

```bash
curl http://localhost:8000/health
curl "http://localhost:8000/api/v1/stocks/search?q=平安"
# 验证前端页面
curl -s http://localhost:5173 | head -20
```

- [ ] **Step 9: 更新 cron（sync_market_data）**

```bash
# cron 不再需要 --db 参数
crontab -l | sed 's|--db /opt/stock_data/stock_db.sqlite||' | crontab -
```

---

## 执行顺序总览

```
阶段一: Task 1                         ← 安装 PG
阶段二: Task 2 → Task 3                ← ORM 模型 + init_db_sync（不动现有代码）
阶段三: Task 4 → Task 5                ← 迁移数据 + 比对验证（app 仍在 SQLite）
         ⚠️ 比对不通过则修复重来
阶段四: Task 6 → ... → Task 14        ← 改代码切换到 PG
阶段五: Task 15 → Task 16              ← 验证 + 服务器部署
```

## 文件变更汇总

| 文件 | 变更 | 阶段 |
|------|------|------|
| `backend/app/models/stock_tables.py` | **新建** | 二 |
| `backend/app/models/__init__.py` | 修改（追加导入） | 二 |
| `backend/app/database.py` | 修改（追加 init_db_sync，后改连接池） | 二 + 四 |
| `backend/scripts/migrate_sqlite_to_pg.py` | **新建** | 三 |
| `backend/scripts/verify_migration.py` | **新建** | 三 |
| `backend/requirements.txt` | 修改 | 四 |
| `backend/app/config.py` | 修改 | 四 |
| `backend/app/services/stock_service.py` | 重写 | 四 |
| `backend/app/services/backtest_engine.py` | 重写 | 四 |
| `backend/app/services/backtest_service.py` | 修改 | 四 |
| `backend/app/api/stocks.py` | 修改 | 四 |
| `backend/scripts/sync_market_data.py` | 重写 | 四 |
| `backend/app/main.py` | 修改 | 四 |
| `backend/tests/test_*.py` | 修改 | 四 |
| `backend/.env` / `.env.production` | 修改 | 四 + 五 |
| `deploy.sh` | 修改 | 五 |

## 风险点 & 注意事项

1. **迁移期间 app 零影响** — 阶段二~三 app 一直运行在 SQLite 上，PostgreSQL 只是接收数据。只有阶段四改完代码重启的那一刻才切换。

2. **比对是关键质量门** — Task 5 必须全部 ✓ OK 才能进入阶段四。如果某表不匹配，排查迁移脚本，清空 PG 重来。

3. **daily 表数据量大** — 可能有几十万行，迁移和比对需要数分钟。考虑在迁移脚本中加批量插入（`executemany` 已足够）。

4. **Boolean 类型** — SQLite 存 0/1，SQLAlchemy `Boolean` 类型在 PostgreSQL 自动转为 `BOOLEAN`。如果迁移脚本用原始 `executemany`，SQLite 的 0/1 值能正确写入 PG 的 BOOLEAN 列。

5. **SQL 方言差异：**
   - `INSERT OR REPLACE` → `INSERT ... ON CONFLICT ... DO UPDATE`
   - `AUTOINCREMENT` → `SERIAL`
   - `datetime('now', 'localtime')` → `NOW()` 或应用层生成

6. **测试保持 SQLite** — CI 环境不需要装 PostgreSQL，通过 `TEST_DATABASE_URL` 覆盖即可。

7. **连接池耗尽** — 多用户场景下注意连接池大小（pool_size=20, max_overflow=10），必要时监控 `pg_stat_activity`。

8. **迁移后 SQLite 文件不删除** — 保留 `aipicking.db` 和 `stock_db.sqlite` 作为备份。确认 PG 稳定运行一段时间后再清理。
