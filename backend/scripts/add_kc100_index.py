#!/usr/bin/env python3
"""
一次性脚本：添加 000698 科创100指数到 stocks 表并拉取过去一年日K线数据

用法：
    cd backend && venv/bin/python scripts/add_kc100_index.py
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
import os

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 加载 .env
_ENV_DIR = Path(__file__).resolve().parent.parent  # backend/
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)


def _parse_pg_url(url: str) -> dict:
    """从 DATABASE_URL 解析 psycopg2 连接参数"""
    url = url.replace("+asyncpg", "").replace("+psycopg2", "")
    r = urlparse(url)
    return {
        "host": r.hostname or "localhost",
        "port": r.port or 5432,
        "user": r.username or "aipicking",
        "password": r.password or "",
        "dbname": r.path.lstrip("/") or "aipicking",
    }


_default_db = os.getenv("DATABASE_URL", "")
_PG_PARAMS = _parse_pg_url(_default_db)

TENCENT_API = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

# ── 科创100指数定义 ──
KC100 = {
    "ts_code":    "000698.SH",
    "symbol":     "sh000698",
    "name":       "科创100",
    "market":     "SH",
    "list_date":  "20230807",  # 上证科创板100指数正式发布日
}


def get_conn():
    return psycopg2.connect(**_PG_PARAMS)


def _fmt_date(d: str) -> str:
    d = d.replace("-", "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


# ── Step 1: 插入 stocks 记录 ──

def insert_index_info_entry():
    """幂等插入科创100指数到 index_info 表"""
    conn = get_conn()
    cur = conn.cursor()
    index_code = KC100["ts_code"].replace(".SH", "").replace(".SZ", "")
    cur.execute("""
        INSERT INTO index_info (index_code, ts_code, index_name, full_name, publisher, data_source)
        VALUES (%s, %s, %s, %s, '上证', 'add_kc100_index.py')
        ON CONFLICT (index_code) DO UPDATE SET
            ts_code = EXCLUDED.ts_code,
            index_name = EXCLUDED.index_name,
            full_name = EXCLUDED.full_name,
            publisher = EXCLUDED.publisher,
            last_sync_date = CURRENT_DATE
    """, (index_code, KC100["ts_code"], KC100["name"], KC100["name"]))
    conn.commit()
    conn.close()
    print(f"✅ index_info 表已插入 {KC100['ts_code']} {KC100['name']}")


# ── Step 2: 从腾讯API拉取历史日K线 ──

def fetch_kline_history(start_date: str, end_date: str) -> list:
    """
    从腾讯 K 线 API 拉取指数历史日线。
    指数数据位于 data.{symbol}.day（不是 .qfqday）。
    返回 records 列表。
    """
    url = (f"{TENCENT_API}?param={KC100['symbol']},day,"
           f"{start_date},{end_date},400,day")
    print(f"📡 请求 URL: {url[:100]}...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://gu.qq.com/",
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.encoding = "utf-8"

    try:
        data = r.json()
        index_data = data.get("data", {}).get(KC100["symbol"], {})
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"❌ JSON 解析失败: {e}")
        print(f"   响应前200字符: {r.text[:200]}")
        return []

    day_list = index_data.get("day", [])
    if not day_list:
        # 尝试其他 key
        for k, v in data.get("data", {}).items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    if isinstance(sv, list) and len(sv) > 0:
                        print(f"   发现数据: {k}.{sk} ({len(sv)} 条)")
        print(f"❌ 未找到 .day 数据")
        return []

    records = []
    prev_close = None
    for row in day_list:
        if len(row) < 6:
            continue
        try:
            trade_date = row[0]  # YYYY-MM-DD
            open_p  = float(row[1])
            close_p = float(row[2])
            high_p  = float(row[3])
            low_p   = float(row[4])
            vol     = float(row[5])
            # 指数无成交额字段，用均价估算
            avg_price = (open_p + close_p + high_p + low_p) / 4.0
            amount = vol * avg_price
            records.append({
                "ts_code": KC100["ts_code"],
                "trade_date": trade_date,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "pre_close": prev_close,
                "vol": vol,
                "amount": amount,
                "adj_close": close_p,   # 指数不复权
            })
            prev_close = close_p
        except (ValueError, IndexError) as e:
            continue
    return records


# ── Step 3: 写入 daily 表 ──

def bulk_upsert_daily(records: list):
    """批量写入 daily 表（ON CONFLICT 覆盖更新）"""
    if not records:
        return 0

    conn = get_conn()
    cur = conn.cursor()

    tuples = []
    for r in records:
        tuples.append((
            r["ts_code"], r["trade_date"],
            r["open"], r["high"], r["low"], r["close"],
            r["pre_close"], r["vol"], r["amount"],
            r["adj_close"],
        ))

    psycopg2.extras.execute_batch(cur, """
        INSERT INTO daily (ts_code, trade_date, open, high, low, close,
                           pre_close, vol, amount, adj_close)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ts_code, trade_date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            pre_close = EXCLUDED.pre_close,
            vol = EXCLUDED.vol,
            amount = EXCLUDED.amount,
            adj_close = EXCLUDED.adj_close
    """, tuples)
    conn.commit()
    conn.close()
    return len(tuples)


# ── Step 4: 验证结果 ──

def verify():
    """验证写入结果"""
    conn = get_conn()
    cur = conn.cursor()

    # stocks 表
    cur.execute("SELECT * FROM stocks WHERE ts_code = %s", (KC100["ts_code"],))
    stock_row = cur.fetchone()
    if stock_row:
        print(f"\n📋 stocks 表记录: ts_code={stock_row[1]} name={stock_row[3]} "
              f"market={stock_row[4]} list_date={stock_row[5]}")

    # daily 表
    cur.execute(
        "SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM daily WHERE ts_code = %s",
        (KC100["ts_code"],))
    cnt, min_date, max_date = cur.fetchone()
    print(f"📊 daily 表记录: {cnt} 条, {min_date} ~ {max_date}")

    # 最近5条
    cur.execute(
        "SELECT trade_date, open, high, low, close, vol FROM daily WHERE ts_code = %s ORDER BY trade_date DESC LIMIT 5",
        (KC100["ts_code"],))
    print("📈 最近5条日线:")
    for row in cur.fetchall():
        print(f"  {row[0]} | O:{row[1]:.2f} H:{row[2]:.2f} L:{row[3]:.2f} C:{row[4]:.2f} V:{row[5]:.0f}")

    conn.close()


# ── 主流程 ──

def main():
    print(f"{'='*60}")
    print(f"添加 {KC100['name']}（{KC100['ts_code']}）到 stocks 并拉取日K线")
    print(f"{'='*60}\n")

    # 1. 插入 stocks
    print("Step 1/4: 插入 stocks 表记录...")
    insert_index_info_entry()

    # 2. 拉取历史日K线（过去一年：2025-06-13 ~ 2026-06-13）
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    print(f"\nStep 2/4: 拉取日K线 {start_date} ~ {end_date}...")
    records = fetch_kline_history(start_date, end_date)
    print(f"   获取 {len(records)} 条日线数据")

    # 3. 写入 daily 表
    print(f"\nStep 3/4: 写入 daily 表...")
    written = bulk_upsert_daily(records)
    print(f"   写入/更新 {written} 条记录")

    # 4. 验证
    print(f"\nStep 4/4: 验证结果...")
    verify()

    print(f"\n{'='*60}")
    print(f"✅ 完成！{KC100['name']}（{KC100['ts_code']}）数据已就绪")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
