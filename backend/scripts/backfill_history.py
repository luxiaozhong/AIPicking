#!/usr/bin/env python3
"""
历史数据回填脚本 — 2020-01-01 ~ 2023-09-21
内置防封措施：低并发、随机延迟、指数退避重试、分段冷却
"""
import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiohttp
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# ── 环境加载 ──────────────────────────────────────────────────────────
_ENV_DIR = Path(__file__).resolve().parent.parent  # backend/
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)

# ── 数据库配置 ────────────────────────────────────────────────────────
from urllib.parse import urlparse

_default_db = os.getenv("DATABASE_URL", "")
if not _default_db:
    _user = os.getenv("DB_USER", "aipicking")
    _pass = os.getenv("DB_PASSWORD", "")
    _host = os.getenv("DB_HOST", "localhost")
    _port = os.getenv("DB_PORT", "5432")
    _name = os.getenv("DB_NAME", "aipicking")
    _default_db = f"postgresql://{_user}:{_pass}@{_host}:{_port}/{_name}"

def _parse_pg_url(url: str) -> dict:
    url = url.replace("+asyncpg", "").replace("+psycopg2", "")
    if "://" not in url:
        url = f"postgresql://{url}"
    r = urlparse(url if "://" in url else f"postgresql://{url}")
    return {
        "host": r.hostname or "localhost",
        "port": r.port or 5432,
        "user": r.username or "aipicking",
        "password": r.password or "",
        "dbname": r.path.lstrip("/") or "aipicking",
    }

_PG_PARAMS = _parse_pg_url(_default_db)

# ── 防封参数 ──────────────────────────────────────────────────────────
TENCENT_API = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
CONCURRENCY = 8              # 低并发，避免触发反爬
TIMEOUT = aiohttp.ClientTimeout(total=30)
BASE_DELAY = 0.1             # 基础请求间隔（秒）
MAX_RETRIES = 3              # 最大重试次数
COOLDOWN_SECONDS = 8         # 每个月份段之间的冷却时间
JITTER = 0.5                 # 随机抖动范围（秒）

# ── 数据库工具 ────────────────────────────────────────────────────────
_INDEX_CODES = ("000001.SH", "399001.SZ", "399006.SZ", "000688.SH")

def get_conn():
    return psycopg2.connect(**_PG_PARAMS)

def load_stocks():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT ts_code, symbol FROM stocks WHERE ts_code NOT IN %s",
        (_INDEX_CODES,))
    rows = cur.fetchall()
    conn.close()
    return [{"ts_code": r[0], "symbol": r[1]} for r in rows]

def bulk_upsert(records):
    if not records:
        return
    conn = None
    for attempt in range(MAX_RETRIES):
        try:
            conn = get_conn()
            cur = conn.cursor()
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO daily (ts_code, trade_date, open, high, low, close, vol, amount, adj_close, market_cap, circ_market_cap)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ts_code, trade_date) DO UPDATE SET
                    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                    close = EXCLUDED.close, vol = EXCLUDED.vol, amount = EXCLUDED.amount,
                    adj_close = EXCLUDED.adj_close,
                    market_cap = EXCLUDED.market_cap, circ_market_cap = EXCLUDED.circ_market_cap
            """, records)
            conn.commit()
            return
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = (2 ** attempt) * 2
                print(f"  ⚠️ 批量写入失败（{e}），{wait}s 后重试...")
                time.sleep(wait)
            else:
                print(f"  ❌ 批量写入最终失败：{e}")
                raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

# ── 下载函数 ──────────────────────────────────────────────────────────
async def download_one(session, ts_code, symbol, start_date, end_date, retry=0):
    """拉取单只股票日线，带重试和退避"""
    _fmt = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    url = (f"{TENCENT_API}?param={symbol},day,"
           f"{_fmt(start_date)},{_fmt(end_date)},500,qfq")

    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            text = await resp.text()
    except Exception as e:
        if retry < MAX_RETRIES:
            wait = (2 ** retry) * 2 + random.uniform(0, JITTER)
            await asyncio.sleep(wait)
            return await download_one(session, ts_code, symbol, start_date, end_date, retry + 1)
        return None

    try:
        data = json.loads(text)
        stock_data = data.get("data", {}).get(symbol, {})
        if not stock_data:
            for k, v in data.get("data", {}).items():
                if k.upper() == symbol.upper():
                    stock_data = v
                    break
        qfq_data = stock_data.get("qfqday", [])
    except (json.JSONDecodeError, AttributeError):
        if retry < MAX_RETRIES:
            wait = (2 ** retry) + random.uniform(0, JITTER)
            await asyncio.sleep(wait)
            return await download_one(session, ts_code, symbol, start_date, end_date, retry + 1)
        return None

    if not qfq_data:
        return []

    records = []
    for row in qfq_data:
        if len(row) < 6:
            continue
        try:
            trade_date = row[0].replace("-", "")
            open_p  = float(row[1])
            close_p = float(row[2])
            high_p  = float(row[3])
            low_p   = float(row[4])
            vol     = float(row[5])
            amount  = vol * close_p * 100
            records.append((ts_code, trade_date, open_p, high_p, low_p,
                           close_p, vol, amount, close_p, None, None))
        except (ValueError, IndexError):
            continue
    return records

# ── 主回填逻辑 ────────────────────────────────────────────────────────
async def backfill_month(stocks, month_start: str, month_end: str):
    """回填一个月份的数据"""
    print(f"\n{'─'*50}")
    print(f"📅 回填 {month_start[:6]} ({month_start} ~ {month_end})")
    print(f"{'─'*50}")

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        semaphore = asyncio.Semaphore(CONCURRENCY)

        async def fetch_one(s):
            async with semaphore:
                # 随机延迟防封
                await asyncio.sleep(BASE_DELAY + random.uniform(0, JITTER))
                records = await download_one(
                    session, s["ts_code"], s["symbol"], month_start, month_end)
                if records is None:
                    return s["ts_code"], None, "fail"
                elif len(records) == 0:
                    return s["ts_code"], [], "empty"
                else:
                    return s["ts_code"], records, "ok"

        tasks = [fetch_one(s) for s in stocks]
        ok_count, empty_count, fail_count = 0, 0, 0
        total_records = 0
        batch = []
        BATCH_SIZE = 100

        for coro in asyncio.as_completed(tasks):
            ts_code, records, status = await coro
            if status == "ok":
                batch.extend(records)
                total_records += len(records)
                ok_count += 1
            elif status == "empty":
                empty_count += 1
            else:
                fail_count += 1

            # 批量写入
            if len(batch) >= BATCH_SIZE:
                bulk_upsert(batch)
                batch = []

            # 进度打印
            done = ok_count + empty_count + fail_count
            if done % 500 == 0 or done <= 3:
                print(f"  [{done}/{len(stocks)}] ✅{ok_count} ⚪{empty_count} ❌{fail_count} | 已入库 {total_records} 条")

        # 剩余写入
        if batch:
            bulk_upsert(batch)

    print(f"  ✅ 完成：{ok_count} 只有数据，{empty_count} 只无数据，{fail_count} 只失败，共 {total_records} 条")
    return ok_count, total_records

def generate_month_ranges(start_ym: str, end_ym: str):
    """生成逐月日期范围，返回 [(YYYYMMDD_start, YYYYMMDD_end), ...]"""
    start = datetime.strptime(start_ym, "%Y%m")
    end = datetime.strptime(end_ym, "%Y%m")
    ranges = []
    cur = start
    while cur <= end:
        y, m = cur.year, cur.month
        # 月初
        ms = f"{y}{m:02d}01"
        # 月末
        if m == 12:
            me = f"{y}1231"
        else:
            me = f"{y}{m+1:02d}01"
        ranges.append((ms, me))
        # 下个月
        if m == 12:
            cur = datetime(y + 1, 1, 1)
        else:
            cur = datetime(y, m + 1, 1)
    return ranges

async def main():
    start_ts = time.time()

    # 验证 DB 连接
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM stocks")
    total = cur.fetchone()[0]
    conn.close()
    if total == 0:
        print("❌ stocks 表为空，请先初始化")
        return
    print(f"📊 stocks 表共 {total} 只股票")

    stocks = load_stocks()
    print(f"📊 排除 4 个指数后，共 {len(stocks)} 只股票待回填")

    # 生成月份列表：2020-01 ~ 2023-09
    month_ranges = generate_month_ranges("202001", "202309")
    print(f"📅 共 {len(month_ranges)} 个月份段：{month_ranges[0][0][:6]} ~ {month_ranges[-1][0][:6]}\n")
    print(f"⚙️  防封参数：并发={CONCURRENCY}，基础延迟={BASE_DELAY}s，抖动={JITTER}s，冷却={COOLDOWN_SECONDS}s")
    print(f"⏱️  预计耗时：~{len(month_ranges) * (COOLDOWN_SECONDS + len(stocks) / CONCURRENCY * 0.3) / 60:.0f} 分钟\n")

    grand_ok = 0
    grand_records = 0

    for i, (ms, me) in enumerate(month_ranges):
        # 月份间冷却（第一个月不冷却）
        if i > 0:
            print(f"\n😴 冷却 {COOLDOWN_SECONDS}s 防止被封...")
            await asyncio.sleep(COOLDOWN_SECONDS)

        ok, records = await backfill_month(stocks, ms, me)
        grand_ok += ok
        grand_records += records

    elapsed = time.time() - start_ts
    print(f"\n{'='*60}")
    print(f"🎉 全部回填完成！")
    print(f"   时间范围: {month_ranges[0][0]} ~ {month_ranges[-1][1]}")
    print(f"   覆盖股票: {grand_ok} 只有数据")
    print(f"   总记录数: {grand_records} 条")
    print(f"   总耗时: {elapsed/60:.1f} 分钟")
    print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())
