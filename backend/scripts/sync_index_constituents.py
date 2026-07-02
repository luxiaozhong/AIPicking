#!/usr/bin/env python3
"""
指数成分股同步 — 从 akshare 拉取并写入 PostgreSQL

数据源：akshare.index_detail_cni（国证指数）/ 可扩展 index_stock_cons_csindex（中证）
写入表：
  - index_info        — 指数元数据（注册新指数）
  - index_constituents — 成分股明细（按 eff_date 区分调样周期）

Idempotent: INSERT ... ON CONFLICT DO NOTHING/UPDATE — 可重复运行。

Usage:
    cd backend
    venv/bin/python scripts/sync_index_constituents.py
    venv/bin/python scripts/sync_index_constituents.py --index 980080
    venv/bin/python scripts/sync_index_constituents.py --index 980080 --pg-url postgresql://...

数据表结构由 SQLAlchemy ORM 管理（Base.metadata.create_all），sync 内部也
执行 CREATE TABLE IF NOT EXISTS 作为兜底。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date as date_type
from pathlib import Path
from typing import Optional, Dict, Any

import psycopg2
import psycopg2.extras

# ── logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sync_index_constituents")

# ── 指数注册表 — 已知指数元数据 ─────────────────────────────────────
# data_source 取值:
#   akshare.index_detail_cni         — 国证指数（有权重/行业/市值）
#   akshare.index_stock_cons_weight_csindex — 中证指数（有权重，无行业/市值）
#   akshare.index_stock_cons         — 深证指数（无权重/行业/市值，仅名单）
def _infer_exchange(code: str) -> str:
    """根据股票代码前缀推断交易所后缀。

    600xxx/601xxx/603xxx/605xxx/9xxxxx → SH
    000xxx/001xxx/002xxx/003xxx/300xxx → SZ
    8xxxxx/4xxxxx → BJ
    """
    if len(code) != 6 or not code.isdigit():
        return "SZ"  # fallback
    prefix = int(code)
    if 600000 <= prefix < 700000 or 900000 <= prefix < 1000000:
        return "SH"
    elif 0 <= prefix < 400000 or 200000 <= prefix < 300000:
        return "SZ"
    elif 800000 <= prefix < 900000 or 400000 <= prefix < 500000:
        return "BJ"
    return "SZ"


def _normalize_ts_code(code: str) -> str:
    """确保 ts_code 带交易所后缀，如 002558 → 002558.SZ"""
    code = str(code).strip()
    if "." in code:
        return code
    return f"{code}.{_infer_exchange(code)}"


KNOWN_INDICES: Dict[str, Dict[str, Any]] = {
    # ── 国证 ──
    "980080": {
        "index_name": "成长100",
        "full_name": "国证成长100",
        "publisher": "国证",
        "constituent_count": 100,
        "data_source": "akshare.index_detail_cni",
    },
    "480080": {
        "index_name": "成长100R",
        "full_name": "国证成长100R",
        "publisher": "国证",
        "constituent_count": 100,
        "data_source": "akshare.index_detail_cni",
    },
    # ── 中证 ──
    "000905": {
        "index_name": "中证500",
        "full_name": "中证500指数",
        "publisher": "中证",
        "constituent_count": 500,
        "data_source": "akshare.index_stock_cons_weight_csindex",
    },
    "000852": {
        "index_name": "中证1000",
        "full_name": "中证1000指数",
        "publisher": "中证",
        "constituent_count": 1000,
        "data_source": "akshare.index_stock_cons_weight_csindex",
    },
    "931643": {
        "index_name": "科创创业50",
        "full_name": "中证科创创业50",
        "publisher": "中证",
        "constituent_count": 50,
        "data_source": "akshare.index_stock_cons_weight_csindex",
    },
    "950180": {
        "index_name": "科创AI",
        "full_name": "上证科创板人工智能",
        "publisher": "中证",
        "constituent_count": 30,
        "data_source": "akshare.index_stock_cons_weight_csindex",
    },
    # ── 中证（深市代码） ──
    "399966": {
        "index_name": "800证保",
        "full_name": "中证800证券保险指数",
        "publisher": "中证",
        "constituent_count": 50,
        "data_source": "akshare.index_stock_cons_weight_csindex",
    },
    # ── 深证 ──
    "399673": {
        "index_name": "创业板50",
        "full_name": "深证创业板50",
        "publisher": "深证",
        "constituent_count": 50,
        "data_source": "akshare.index_stock_cons",
    },
    "399667": {
        "index_name": "创业板成长",
        "full_name": "深证创业板成长",
        "publisher": "深证",
        "constituent_count": 50,
        "data_source": "akshare.index_stock_cons",
    },
    "399750": {
        "index_name": "深主板50",
        "full_name": "深证主板50",
        "publisher": "深证",
        "constituent_count": 50,
        "data_source": "akshare.index_stock_cons",
    },
}


# ── 建表 DDL（兜底，ORM create_all 优先） ──────────────────────────
DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS index_info (
        id              SERIAL PRIMARY KEY,
        index_code      VARCHAR(20)  NOT NULL,
        index_name      VARCHAR(50)  NOT NULL,
        full_name       VARCHAR(100),
        publisher       VARCHAR(20)  DEFAULT '国证',
        constituent_count INTEGER    DEFAULT 0,
        data_source     VARCHAR(50)  DEFAULT 'akshare.index_detail_cni',
        last_sync_date  VARCHAR(10),
        created_at      TIMESTAMP    DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai'),
        updated_at      TIMESTAMP    DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai'),
        CONSTRAINT uq_index_info_code UNIQUE (index_code)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_index_info_publisher ON index_info(publisher);
    """,
    """
    CREATE TABLE IF NOT EXISTS index_constituents (
        id              SERIAL PRIMARY KEY,
        index_code      VARCHAR(20)  NOT NULL,
        ts_code         VARCHAR(20)  NOT NULL,
        stock_name      VARCHAR(100) NOT NULL,
        industry        VARCHAR(50),
        market_cap      DOUBLE PRECISION,
        weight          DOUBLE PRECISION,
        eff_date        VARCHAR(10)  NOT NULL,
        created_at      TIMESTAMP    DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai'),
        updated_at      TIMESTAMP    DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai'),
        CONSTRAINT uq_index_constituent UNIQUE (index_code, ts_code, eff_date)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ic_index_code ON index_constituents(index_code);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ic_ts_code ON index_constituents(ts_code);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ic_eff_date ON index_constituents(eff_date);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ic_code_date ON index_constituents(index_code, eff_date);
    """,
]


def get_pg_url(pg_url: Optional[str] = None) -> str:
    """获取 PostgreSQL 连接 URL"""
    if pg_url:
        return pg_url

    # 尝试从环境变量读取
    for var in ("PG_MIGRATE_URL", "SYNC_DATABASE_URL", "DATABASE_URL"):
        url = os.getenv(var, "")
        if url:
            # asyncpg → psycopg2
            return url.replace("+asyncpg", "+psycopg2")

    # 回退：构建本地 URL
    db_user = os.getenv("DB_USER", "aipicking")
    db_pass = os.getenv("DB_PASSWORD", "")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "aipicking")
    return f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"


def ensure_tables(conn) -> None:
    """确保表结构存在（兜底）"""
    with conn.cursor() as cur:
        for ddl in DDL_STATEMENTS:
            cur.execute(ddl)
    conn.commit()
    log.info("表结构已就绪")


def fetch_constituents(index_code: str) -> list[dict]:
    """从 akshare 拉取最新成分股列表"""
    import akshare as ak

    log.info(f"正在从 akshare 获取 {index_code} 成分股...")
    df = ak.index_detail_cni(index_code)

    records = []
    for _, row in df.iterrows():
        records.append({
            "eff_date": str(row["日期"]),
            "ts_code": _normalize_ts_code(str(row["样本代码"])),
            "stock_name": str(row["样本简称"]),
            "industry": str(row.get("所属行业", "")),
            "market_cap": float(row["总市值"]) if row["总市值"] else None,
            "weight": float(row["权重"]) if row["权重"] else None,
        })

    # 按权重降序排列方便查看
    records.sort(key=lambda r: r["weight"] or 0, reverse=True)
    log.info(f"获取到 {len(records)} 只成分股（eff_date={records[0]['eff_date'] if records else 'N/A'}）")
    return records


def fetch_constituents_csi(index_code: str) -> list[dict]:
    """从 akshare / 中证官网拉取成分股（含权重）"""
    import akshare as ak

    log.info(f"正在从 中证 获取 {index_code} 成分股权重...")
    try:
        df = ak.index_stock_cons_weight_csindex(symbol=index_code)
    except ValueError:
        # 回退：直接请求 Excel（兼容 akshare 列数不匹配问题）
        import requests
        from io import BytesIO

        url = (
            f"https://oss-ch.csindex.com.cn/static/html/csindex/"
            f"public/uploads/file/autofile/closeweight/{index_code}closeweight.xls"
        )
        r = requests.get(url, timeout=30)
        df_raw = pd.read_excel(BytesIO(r.content))  # type: ignore[name-defined]
        # 只取前 10 列（标准股票指数列）
        df = df_raw.iloc[:, :10]
        df.columns = [
            "日期", "指数代码", "指数名称", "指数英文名称",
            "成分券代码", "成分券名称", "成分券英文名称",
            "交易所", "交易所英文名称", "权重",
        ]

    records = []
    for _, row in df.iterrows():
        records.append({
            "eff_date": _csi_fmt_date(row["日期"]),
            "ts_code": _normalize_ts_code(str(row["成分券代码"]).zfill(6)),
            "stock_name": str(row["成分券名称"]),
            "industry": str(row.get("所属行业", "")),
            "market_cap": None,  # 中证 API 无市值
            "weight": float(row["权重"]) if row["权重"] else None,
        })

    records.sort(key=lambda r: r["weight"] or 0, reverse=True)
    log.info(f"获取到 {len(records)} 只成分股（eff_date={records[0]['eff_date'] if records else 'N/A'}）")
    return records


def _csi_fmt_date(val) -> str:
    """中证日期可能是 date / int 20260529 / str '2026-05-29'"""
    import datetime as _dt
    if isinstance(val, _dt.date):
        return val.strftime("%Y-%m-%d")
    s = str(val).replace("-", "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def fetch_constituents_sz(index_code: str) -> list[dict]:
    """从 akshare 拉取深证指数成分股（仅名单，无权重/行业/市值）

    注意：ak.index_stock_cons 返回的 "纳入日期" 是每只股票各自被纳入指数的日期，
    并非统一的调样生效日。如果直接原样使用，会导致后端按 MAX(eff_date) 查询时
    只能拿到最新一批被纳入的股票（例如 14/50），而非全部当前成分股。

    因此统一用今天作为 eff_date，确保每次同步后所有当前成分股属于同一批次。
    """
    import akshare as ak

    log.info(f"正在从 深证 获取 {index_code} 成分股...")
    df = ak.index_stock_cons(symbol=index_code)

    today = str(date_type.today())
    records = []
    for _, row in df.iterrows():
        records.append({
            "eff_date": today,
            "ts_code": _normalize_ts_code(str(row["品种代码"]).zfill(6)),
            "stock_name": str(row["品种名称"]),
            "industry": "",
            "market_cap": None,
            "weight": None,
        })

    log.info(f"获取到 {len(records)} 只成分股（eff_date={today}）")
    return records


def upsert_index_info(conn, index_code: str) -> str:
    """写入指数元数据，返回今天的日期字符串"""
    info = KNOWN_INDICES.get(index_code)
    if not info:
        log.warning(f"指数 {index_code} 不在已知注册表中，使用默认信息")
        info = {
            "index_name": index_code,
            "full_name": f"指数{index_code}",
            "publisher": "未知",
            "constituent_count": 0,
            "data_source": "akshare.index_detail_cni",
        }

    today = str(date_type.today())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO index_info (index_code, index_name, full_name, publisher,
                                    constituent_count, data_source, last_sync_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (index_code) DO UPDATE SET
                constituent_count = EXCLUDED.constituent_count,
                last_sync_date = EXCLUDED.last_sync_date,
                updated_at = NOW() AT TIME ZONE 'Asia/Shanghai'
            """,
            (
                index_code,
                info["index_name"],
                info["full_name"],
                info["publisher"],
                info["constituent_count"],
                info["data_source"],
                today,
            ),
        )
    conn.commit()
    log.info(f"指数元数据已更新: {info['full_name']} ({index_code})")
    return today


def upsert_constituents(conn, index_code: str, records: list[dict]) -> int:
    """批量写入成分股（ON CONFLICT DO NOTHING — 幂等）"""
    if not records:
        log.warning("没有成分股数据可写入")
        return 0

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO index_constituents (index_code, ts_code, stock_name,
                                            industry, market_cap, weight, eff_date)
            VALUES %s
            ON CONFLICT (index_code, ts_code, eff_date) DO UPDATE SET
                stock_name = EXCLUDED.stock_name,
                industry   = EXCLUDED.industry,
                market_cap = EXCLUDED.market_cap,
                weight     = EXCLUDED.weight,
                updated_at = NOW() AT TIME ZONE 'Asia/Shanghai'
            """,
            [
                (
                    index_code,
                    r["ts_code"],
                    r["stock_name"],
                    r["industry"],
                    r["market_cap"],
                    r["weight"],
                    r["eff_date"],
                )
                for r in records
            ],
            template="(%s, %s, %s, %s, %s, %s, %s)",
        )
    conn.commit()
    log.info(f"已写入 {len(records)} 条成分股记录")
    return len(records)


def verify(conn, index_code: str, expected: int = 100) -> None:
    """验证写入数据"""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT eff_date, COUNT(*) as cnt,
                   SUM(weight) as total_weight,
                   COUNT(*) FILTER (WHERE weight IS NULL) as null_weight
            FROM index_constituents
            WHERE index_code = %s
            GROUP BY eff_date
            ORDER BY eff_date DESC
            """,
            (index_code,),
        )
        rows = cur.fetchall()
        if not rows:
            log.warning("验证失败：表中无数据")
            return

        for eff_date, cnt, total_weight, null_weight in rows:
            tw_str = f"{total_weight:.2f}%" if total_weight is not None else "N/A（深证无权重）"
            log.info(
                f"验证: eff_date={eff_date} | "
                f"成分股={cnt}/{expected} | "
                f"权重合计={tw_str} | "
                f"缺失权重={null_weight}"
            )


def main():
    parser = argparse.ArgumentParser(
        description="同步指数成分股到 PostgreSQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                          # 默认同步 980080（国证成长100）
  %(prog)s --index 980080
  %(prog)s --index 980080 --dry-run # 只打印不写入
  %(prog)s --pg-url postgresql://user:pass@host/db
        """,
    )
    parser.add_argument("--index", default="980080",
                        help="指数代码 (默认: 980080 国证成长100)")
    parser.add_argument("--pg-url", default=None,
                        help="PostgreSQL 连接 URL")
    parser.add_argument("--dry-run", action="store_true",
                        help="只拉取数据，不写入数据库")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING"])
    args = parser.parse_args()

    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # 1. 根据数据源拉取数据
    info = KNOWN_INDICES.get(args.index, {})
    source = info.get("data_source", "akshare.index_detail_cni")

    if source == "akshare.index_stock_cons_weight_csindex":
        records = fetch_constituents_csi(args.index)
    elif source == "akshare.index_stock_cons":
        records = fetch_constituents_sz(args.index)
    else:
        records = fetch_constituents(args.index)

    if args.dry_run:
        log.info("[DRY RUN] 不写入数据库")
        for r in records[:10]:
            log.info(
                f"  {r['ts_code']:>8}  {r['stock_name']:<8}  "
                f"权重={r['weight']:.2f}%  行业={r['industry']}"
            )
        if len(records) > 10:
            log.info(f"  ... 共 {len(records)} 只")
        return

    # 2. 连接数据库
    pg_url = get_pg_url(args.pg_url)
    log.info(f"连接数据库: {pg_url.split('@')[1] if '@' in pg_url else pg_url}")
    conn = psycopg2.connect(pg_url)
    try:
        # 3. 建表兜底
        ensure_tables(conn)

        # 4. 写入元数据
        upsert_index_info(conn, args.index)

        # 5. 写入成分股
        upsert_constituents(conn, args.index, records)

        # 6. 验证
        expected = KNOWN_INDICES.get(args.index, {}).get("constituent_count", 100)
        verify(conn, args.index, expected)

        log.info("同步完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
