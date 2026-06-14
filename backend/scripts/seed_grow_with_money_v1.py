#!/usr/bin/env python3
"""
注册 grow_with_money_v1 策略到数据库

Usage:
    cd backend
    venv/bin/python scripts/seed_grow_with_money_v1.py
    venv/bin/python scripts/seed_grow_with_money_v1.py --pg-url postgresql://...
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("seed_grow_with_money_v1")

PARAMS_SCHEMA = json.dumps(
    {
        "index_code": {
            "type": "string",
            "default": "980080",
            "label": "指数代码",
            "description": "国证成长100=980080",
        },
        "N": {
            "type": "int",
            "default": 3,
            "label": "推荐数量 N",
            "description": "选取资金流/市值比率前 N 名",
            "min": 1,
            "max": 20,
        },
        "M": {
            "type": "int",
            "default": 5,
            "label": "回顾天数 M",
            "description": "过去 M 个交易日的资金流累计",
            "min": 3,
            "max": 60,
        },
    },
    ensure_ascii=False,
)

STRATEGY_DATA = {
    "name": "grow_with_money_v1",
    "description": "成长100 + 资金流/市值选股：以国证成长100成分股为股票池，按过去M日主力资金净流入/总市值比率排序，推荐前N只",
    "file_path": "app/strategies/examples/grow_with_money_v1.py",
    "params_schema": PARAMS_SCHEMA,
    "tags": "指数成分股,资金流,成长100,资金效率,市值比率",
    "user_id": 1,  # admin
    "is_published": True,
}


def get_pg_url(pg_url: str | None = None) -> str:
    if pg_url:
        return pg_url
    for var in ("PG_MIGRATE_URL", "SYNC_DATABASE_URL", "DATABASE_URL"):
        url = os.getenv(var, "")
        if url:
            return url.replace("+asyncpg", "+psycopg2")
    db_user = os.getenv("DB_USER", "aipicking")
    db_pass = os.getenv("DB_PASSWORD", "")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "aipicking")
    return f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"


def main():
    parser = argparse.ArgumentParser(description="注册 grow_with_money_v1 策略")
    parser.add_argument("--pg-url", default=None, help="PostgreSQL 连接 URL")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    parser.add_argument("--update", action="store_true", help="更新已有记录（默认跳过）")
    args = parser.parse_args()

    if args.dry_run:
        log.info("[DRY RUN] 策略信息: %s", json.dumps(STRATEGY_DATA, ensure_ascii=False, indent=2))
        return

    pg_url = get_pg_url(args.pg_url)
    log.info("连接数据库: %s", pg_url.split("@")[1] if "@" in pg_url else pg_url)
    conn = psycopg2.connect(pg_url)

    try:
        with conn.cursor() as cur:
            # 检查是否已存在
            cur.execute("SELECT id, name, file_path FROM strategies WHERE name = %s", (STRATEGY_DATA["name"],))
            existing = cur.fetchone()

            if existing:
                if args.update:
                    cur.execute(
                        """
                        UPDATE strategies SET
                            description = %s,
                            file_path = %s,
                            params_schema = %s,
                            tags = %s,
                            is_published = %s,
                            version = COALESCE(version, 1),
                            created_at = COALESCE(created_at, NOW()),
                            updated_at = NOW()
                        WHERE name = %s
                        RETURNING id
                        """,
                        (
                            STRATEGY_DATA["description"],
                            STRATEGY_DATA["file_path"],
                            STRATEGY_DATA["params_schema"],
                            STRATEGY_DATA["tags"],
                            STRATEGY_DATA["is_published"],
                            STRATEGY_DATA["name"],
                        ),
                    )
                    updated_id = cur.fetchone()[0]
                    log.info("策略已更新: id=%d name=%s", updated_id, STRATEGY_DATA["name"])
                else:
                    log.info("策略已存在（跳过）: id=%d name=%s", existing[0], existing[1])
                    log.info("使用 --update 参数可以更新已有记录")
            else:
                cur.execute(
                    """
                    INSERT INTO strategies (name, description, file_path, params_schema,
                                            tags, user_id, is_published, status,
                                            version, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'active',
                            1, NOW(), NOW())
                    RETURNING id
                    """,
                    (
                        STRATEGY_DATA["name"],
                        STRATEGY_DATA["description"],
                        STRATEGY_DATA["file_path"],
                        STRATEGY_DATA["params_schema"],
                        STRATEGY_DATA["tags"],
                        STRATEGY_DATA["user_id"],
                        STRATEGY_DATA["is_published"],
                    ),
                )
                new_id = cur.fetchone()[0]
                log.info("策略已创建: id=%d name=%s", new_id, STRATEGY_DATA["name"])

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
