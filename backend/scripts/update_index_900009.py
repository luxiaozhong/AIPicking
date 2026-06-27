#!/usr/bin/env python3
"""
无耻之徒指数 (900009) — 聚合 980080 + 399667 + 900001 成分股

从 index_constituents 中取三个源指数最新的成分股，union 去重后写入 900009。

Idempotent: 可重复运行，每次运行会覆盖 900009 的全部成分股记录。

Usage:
    cd backend && source venv/bin/activate
    python scripts/update_index_900009.py
    python scripts/update_index_900009.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date as date_type
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# ── Load .env ──────────────────────────────────────────────────────────
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


_default_db = os.getenv("DATABASE_URL", "")
if not _default_db:
    _user = os.getenv("DB_USER", "aipicking")
    _pass = os.getenv("DB_PASSWORD", "")
    _host = os.getenv("DB_HOST", "localhost")
    _port = os.getenv("DB_PORT", "5432")
    _name = os.getenv("DB_NAME", "aipicking")
    _default_db = f"postgresql://{_user}:{_pass}@{_host}:{_port}/{_name}"
_PG_PARAMS = _parse_pg_url(_default_db)

INDEX_CODE = "900009"
INDEX_NAME = "无耻之徒"
FULL_NAME = "无耻之徒指数"
PUBLISHER = "自定义"
DATA_SOURCE = "custom.union_980080_399667_900001"

SOURCE_INDICES = ["980080", "399667", "900001"]


def get_conn():
    return psycopg2.connect(**_PG_PARAMS)


def fetch_source_constituents(conn, source_code: str) -> list[dict]:
    """取一个源指数最新的成分股列表。

    Returns:
        [{ts_code, stock_name, weight}, ...]
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ts_code, stock_name, weight
            FROM index_constituents
            WHERE index_code = %s
              AND eff_date = (
                  SELECT MAX(eff_date) FROM index_constituents
                  WHERE index_code = %s
              )
            ORDER BY weight DESC NULLS LAST
            """,
            (source_code, source_code),
        )
        rows = cur.fetchall()

    stocks = [
        {"ts_code": r[0], "stock_name": r[1], "weight": float(r[2]) if r[2] else None}
        for r in rows
    ]
    return stocks


def upsert_index_info(conn, count: int) -> None:
    """写入/更新 900009 的指数元数据"""
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
            (INDEX_CODE, INDEX_NAME, FULL_NAME, PUBLISHER, count, DATA_SOURCE, today),
        )
    conn.commit()
    logging.info("指数元数据已更新: %s (%s), %d 只成分股", FULL_NAME, INDEX_CODE, count)


def upsert_constituents(conn, stocks: list[dict], eff_date: str) -> int:
    """覆盖写入 900009 全部成分股。先删后插，确保干净。"""
    if not stocks:
        return 0

    with conn.cursor() as cur:
        # 清理旧记录
        cur.execute(
            "DELETE FROM index_constituents WHERE index_code = %s",
            (INDEX_CODE,),
        )
        deleted = cur.rowcount
        if deleted:
            logging.info("清理旧记录: %d 条", deleted)

        # 写入新记录
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO index_constituents (index_code, ts_code, stock_name,
                                            industry, market_cap, weight, eff_date)
            VALUES %s
            """,
            [
                (INDEX_CODE, s["ts_code"], s["stock_name"],
                 "", None, s.get("weight"), eff_date)
                for s in stocks
            ],
            template="(%s, %s, %s, %s, %s, %s, %s)",
        )
    conn.commit()
    logging.info("已写入 %d 条成分股记录（eff_date=%s）", len(stocks), eff_date)
    return len(stocks)


def run(dry_run: bool = False) -> dict:
    """主流程"""
    conn = get_conn()
    try:
        # 1. 从三个源指数拉取成分股
        all_stocks: dict[str, dict] = {}  # ts_code -> merged info

        for src in SOURCE_INDICES:
            stocks = fetch_source_constituents(conn, src)
            logging.info("源指数 %s: %d 只成分股", src, len(stocks))
            for s in stocks:
                code = s["ts_code"]
                if code in all_stocks:
                    # 已存在：保留来源信息
                    all_stocks[code]["source"] = (all_stocks[code].get("source", "") + f",{src}")
                else:
                    s["source"] = src
                    all_stocks[code] = s

        merged = list(all_stocks.values())
        # 按 ts_code 排序便于查看
        merged.sort(key=lambda s: s["ts_code"])

        # 统计各来源
        from_980080 = sum(1 for s in merged if "980080" in str(s.get("source", "")))
        from_399667 = sum(1 for s in merged if "399667" in str(s.get("source", "")))
        from_900001 = sum(1 for s in merged if "900001" in str(s.get("source", "")))

        logging.info(
            "合并结果: %d 只（980080: %d, 399667: %d, 900001: %d）",
            len(merged), from_980080, from_399667, from_900001,
        )

        if dry_run:
            logging.info("[DRY RUN] 不写入数据库")
            print(f"\n  指数 900009 成分股预览（共 {len(merged)} 只）:")
            print(f"  {'代码':<12} {'名称':<12} {'来源':<25} {'权重'}")
            print("  " + "-" * 60)
            for s in merged:
                src_str = str(s.get("source", ""))
                w_str = f"{s['weight']:.2f}%" if s.get("weight") else "-"
                print(f"  {s['ts_code']:<12} {s['stock_name']:<12} {src_str:<25} {w_str}")
            return {"success": True, "mode": "dry_run", "count": len(merged)}

        # 2. 写入 index_info
        upsert_index_info(conn, len(merged))

        # 3. 写入 index_constituents
        today = str(date_type.today())
        upsert_constituents(conn, merged, today)

        return {"success": True, "count": len(merged)}

    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(
        description="无耻之徒指数 (900009) — 聚合 980080+399667+900001 成分股")
    p.add_argument("--dry-run", action="store_true",
                   help="仅预览，不写入数据库")
    p.add_argument("--pg-url", default=None,
                   help="PostgreSQL 连接 URL")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    if args.pg_url:
        global _PG_PARAMS
        _PG_PARAMS = _parse_pg_url(args.pg_url)

    logging.info("无耻之徒指数更新 — 聚合 980080 + 399667 + 900001")

    result = run(dry_run=args.dry_run)

    if result["success"]:
        if result.get("mode") == "dry_run":
            print(f"\n✅ [DRY RUN] 预览完成：{result['count']} 只")
        else:
            print(f"\n✅ 无耻之徒 900009 更新完成：{result['count']} 只成分股")
    else:
        print(f"\n❌ 失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
