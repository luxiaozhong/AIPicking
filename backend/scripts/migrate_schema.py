#!/usr/bin/env python3
"""
DB migration: add stocks.type + index_info.ts_code + migrate index data.

用法：
    cd /opt/AIpicking/backend && venv/bin/python scripts/migrate_schema.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 加载 .env，与 config.py 保持一致
from dotenv import load_dotenv

_env_dir = Path(__file__).resolve().parent.parent
for _env_file in (".env", ".env.production"):
    _path = _env_dir / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)

import psycopg2
import re

DB_URL = os.getenv("SYNC_DATABASE_URL", "")
if not DB_URL:
    print("错误: 未设置 SYNC_DATABASE_URL，请在 .env 或 .env.production 中配置")
    sys.exit(1)

# 移除 SQLAlchemy 驱动前缀（+psycopg2 / +asyncpg），psycopg2 只接受纯 postgresql://
DB_URL = re.sub(r"^postgresql\+[^:]+://", "postgresql://", DB_URL)
conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

# === Step 1: Add columns ===
print("1. 添加 stocks.type 列...")
cur.execute("ALTER TABLE stocks ADD COLUMN IF NOT EXISTS type VARCHAR(10) DEFAULT 'stock'")
cur.execute("CREATE INDEX IF NOT EXISTS idx_stocks_type ON stocks(type)")
conn.commit()
print("   ✓ stocks.type 列 + 索引已添加")

print("1b. 添加 users.last_login 列（登录时写入，缺失会导致 /auth/login 500）...")
cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP")
conn.commit()
print("   ✓ users.last_login 列已添加")

print("2. 添加 index_info.ts_code 列...")
cur.execute("ALTER TABLE index_info ADD COLUMN IF NOT EXISTS ts_code VARCHAR(20)")
conn.commit()
print("   ✓ index_info.ts_code 列已添加")

# === Step 2: Verify current state ===
cur.execute("SELECT type, COUNT(*) FROM stocks GROUP BY type")
dist = cur.fetchall()
print(f"\n   当前 stocks type 分布: {dist}")

cur.execute("SELECT COUNT(*) FROM index_info")
print(f"   当前 index_info 记录数: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM stocks WHERE type = 'index'")
idx_stocks = cur.fetchone()[0]
print(f"   stocks 中 type=index 的记录数: {idx_stocks}")

# === Step 3: Migrate 15 market indices from stocks to index_info ===
indices = [
    ("000001", "000001.SH", "上证指数", "上证综指"),
    ("399001", "399001.SZ", "深证成指", "深证成份指数"),
    ("399006", "399006.SZ", "创业板指", "创业板指数"),
    ("000688", "000688.SH", "科创50", "科创50指数"),
    ("000016", "000016.SH", "上证50", "上证50指数"),
    ("000300", "000300.SH", "沪深300", "沪深300指数"),
    ("000905", "000905.SH", "中证500", "中证500指数"),
    ("000852", "000852.SH", "中证1000", "中证1000指数"),
    ("399005", "399005.SZ", "中小100", "中小100指数"),
    ("399673", "399673.SZ", "创业板50", "创业板50指数"),
    ("399625", "399625.SZ", "深证主板50", "深证主板50指数"),
    ("931643", "931643.SH", "科创创业50", "科创创业50指数"),
    ("950180", "950180.SH", "科创AI", "科创AI指数"),
    ("980080", "980080.SH", "国证成长100", "国证成长100指数"),
    ("900002", "900002.SH", "自定义指数", "自定义指数"),
]

if idx_stocks > 0:
    print("\n3. 从 stocks 迁移 type=index 记录到 index_info...")
    for code, ts_code, index_name, full_name in indices:
        cur.execute("SELECT id FROM index_info WHERE index_code = %s", (code,))
        if cur.fetchone():
            cur.execute(
                "UPDATE index_info SET ts_code=%s, index_name=%s, full_name=%s WHERE index_code=%s",
                (ts_code, index_name, full_name, code),
            )
        else:
            cur.execute(
                "INSERT INTO index_info (index_code, ts_code, index_name, full_name) VALUES (%s,%s,%s,%s)",
                (code, ts_code, index_name, full_name),
            )
        print(f"   ✓ {code} ({index_name})")

    cur.execute("DELETE FROM stocks WHERE type = 'index'")
    print(f"   已从 stocks 删除 {cur.rowcount} 条 type=index 记录")
    conn.commit()
else:
    print("\n3. stocks 无 type=index 记录，补充 index_info 缺失数据...")
    for code, ts_code, index_name, full_name in indices:
        cur.execute("SELECT id, ts_code FROM index_info WHERE index_code = %s", (code,))
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO index_info (index_code, ts_code, index_name, full_name) VALUES (%s,%s,%s,%s)",
                (code, ts_code, index_name, full_name),
            )
            print(f"   + {code} ({index_name})")
        elif row[1] is None:
            cur.execute("UPDATE index_info SET ts_code=%s WHERE index_code=%s", (ts_code, code))
            print(f"   ~ {code} → {ts_code}")
    conn.commit()

# === Step 4: Unique index on ts_code ===
print("\n4. 创建 index_info.ts_code 唯一索引...")
cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_index_info_ts_code ON index_info(ts_code)")
conn.commit()
print("   ✓ 索引已创建")

# === Step 5: Verify ===
print("\n5. 最终验证:")
cur.execute("SELECT type, COUNT(*) FROM stocks GROUP BY type")
print(f"   stocks type 分布: {cur.fetchall()}")
cur.execute("SELECT COUNT(*) FROM index_info WHERE ts_code IS NOT NULL")
print(f"   index_info 有 ts_code 的记录: {cur.fetchone()[0]}")
cur.execute("SELECT index_code, ts_code, index_name FROM index_info ORDER BY index_code")
for row in cur.fetchall():
    print(f"     {row[0]} | {(row[1] or '(null)'):12s} | {row[2]}")

cur.execute("CREATE INDEX IF NOT EXISTS idx_stocks_type ON stocks(type)")

conn.close()
print("\n✓ 迁移完成!")
