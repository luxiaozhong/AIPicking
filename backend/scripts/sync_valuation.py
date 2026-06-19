#!/usr/bin/env python3
"""
每日估值数据同步 — 通过腾讯财经 API 拉取 PE/PB/市值

腾讯财经字段索引（实测校准）:
  39=PE(TTM), 52=PE(静), 46=PB, 44=总市值(亿), 45=流通市值(亿)
  腾讯不封 IP，可批量拉取（每次最多约50只）

用法：
    venv/bin/python scripts/sync_valuation.py          # 增量（昨天）
    venv/bin/python scripts/sync_valuation.py --init   # 全量最近365天
    venv/bin/python scripts/sync_valuation.py --date 2026-05-30

cron（每个交易日 17:30）:
    30 17 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_valuation.py
"""
import argparse
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ENV_DIR = Path(__file__).resolve().parent.parent
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)


def _parse_pg_url(url: str) -> dict:
    url = url.replace("+asyncpg", "").replace("+psycopg2", "")
    from urllib.parse import urlparse
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

TENCENT_QUOTE_URL = "http://qt.gtimg.cn/q="
BATCH_SIZE = 50


def get_conn():
    return psycopg2.connect(**_PG_PARAMS)


def load_stocks():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT ts_code, symbol FROM stocks "
        "WHERE ts_code IS NOT NULL AND ts_code != '' "
        "AND (type IS NULL OR type = 'stock')"
    )
    rows = cur.fetchall()
    conn.close()
    return [{"ts_code": r[0], "symbol": r[1]} for r in rows]


def tencent_stock_code(ts_code: str) -> str:
    """将 ts_code（如 600519.SH / 000001.SZ）转为腾讯行情接口代码"""
    # 去掉交易所后缀
    code = ts_code.split(".")[0]
    if code.startswith(("6", "9")):
        return f"sh{code}"
    elif code.startswith("8"):
        return f"bj{code}"
    else:
        return f"sz{code}"


def fetch_valuations_batch(symbols: list[str]) -> list[dict]:
    """批量拉取腾讯估值数据"""
    url = TENCENT_QUOTE_URL + ",".join(symbols)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = resp.read().decode("gbk")
    except Exception as e:
        print(f"  ⚠️ 请求失败: {e}")
        return []

    results = []
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        try:
            key = line.split("=")[0].split("_")[-1]
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue
            code = key[2:]  # 去掉 sh/sz/bj 前缀，得到纯数字代码
            pe_ttm = float(vals[39]) if vals[39] else None
            pe_static = float(vals[52]) if vals[52] else None
            pb = float(vals[46]) if vals[46] else None
            mcap = float(vals[44]) if vals[44] else None
            circ_mcap = float(vals[45]) if vals[45] else None
            if pe_ttm or pb or mcap:
                results.append({
                    "raw_code": code,
                    "pe_ttm": pe_ttm,
                    "pe_static": pe_static,
                    "pb": pb,
                    "market_cap": mcap,
                    "circ_market_cap": circ_mcap,
                    "dividend_yield": None,
                })
        except (ValueError, IndexError):
            continue
    return results


def _fmt_date(d: str) -> str:
    """YYYYMMDD → YYYY-MM-DD；已是 YYYY-MM-DD 则原样返回"""
    d = d.replace("-", "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def bulk_upsert(records: list[tuple], trade_date: str):
    conn = get_conn()
    cur = conn.cursor()
    psycopg2.extras.execute_batch(cur, """
        INSERT INTO daily_valuation
            (ts_code, trade_date, pe_ttm, pe_static, pb,
             market_cap, circ_market_cap, dividend_yield, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'tencent')
        ON CONFLICT (ts_code, trade_date) DO UPDATE SET
            pe_ttm = EXCLUDED.pe_ttm, pe_static = EXCLUDED.pe_static,
            pb = EXCLUDED.pb, market_cap = EXCLUDED.market_cap,
            circ_market_cap = EXCLUDED.circ_market_cap,
            dividend_yield = EXCLUDED.dividend_yield
    """, records)
    conn.commit()
    conn.close()


def sync_date(trade_date: str):
    trade_date = _fmt_date(trade_date)  # 转为 YYYY-MM-DD 写入 DB
    stocks = load_stocks()
    print(f"📊 拉取 {trade_date} 估值数据，共 {len(stocks)} 只股票...")

    # 构建 raw_code -> ts_code 映射（如 600519 -> 600519.SH）
    code_map = {}
    for s in stocks:
        raw = s["ts_code"].split(".")[0]
        code_map[raw] = s["ts_code"]

    updated = 0
    records_batch = []
    prefix_symbols = []

    for i, s in enumerate(stocks):
        prefix_symbols.append(tencent_stock_code(s["ts_code"]))

        if len(prefix_symbols) >= BATCH_SIZE or i == len(stocks) - 1:
            results = fetch_valuations_batch(prefix_symbols)
            for r in results:
                ts_code = code_map.get(r["raw_code"])
                if not ts_code:
                    continue
                records_batch.append((
                    ts_code, trade_date,
                    r["pe_ttm"], r["pe_static"], r["pb"],
                    r["market_cap"], r["circ_market_cap"],
                    r["dividend_yield"],
                ))
                updated += 1

            if len(records_batch) >= 500:
                bulk_upsert(records_batch, trade_date)
                records_batch = []

            prefix_symbols = []
            time.sleep(0.1)

        if (i + 1) % 500 == 0:
            print(f"  进度: {i+1}/{len(stocks)}, 已获取 {updated} 条")

    if records_batch:
        bulk_upsert(records_batch, trade_date)

    print(f"✅ 完成！{trade_date} 写入 {updated} 条估值数据")
    return updated


def is_trade_day(date_str: str) -> bool:
    d = datetime.strptime(date_str.replace("-", ""), "%Y%m%d")
    return d.weekday() < 5


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="每日估值数据同步")
    parser.add_argument(
        "--init", action="store_true",
        help="初始化最近365天估值数据"
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="指定日期 YYYY-MM-DD（默认昨天）"
    )
    parser.add_argument(
        "--pg-url", type=str, default=None,
        help="PG 连接字符串"
    )
    args = parser.parse_args()

    if args.pg_url:
        _PG_PARAMS = _parse_pg_url(args.pg_url)

    if args.init:
        end = datetime.now()
        start = end - timedelta(days=365)
        d = start
        while d <= end:
            ds = d.strftime("%Y%m%d")
            if is_trade_day(ds):
                try:
                    sync_date(ds)
                except Exception as e:
                    print(f"  ⚠️ {ds} 失败: {e}")
            d += timedelta(days=1)
        print("🎉 初始化完成！")
    elif args.date:
        trade_date = args.date.replace("-", "")
        if not is_trade_day(trade_date):
            print(f"⚠️ {args.date} 不是交易日（周末），跳过")
            sys.exit(0)
        sync_date(trade_date)
    else:
        target = datetime.now().strftime("%Y%m%d")
        if not is_trade_day(target):
            print(f"⚠️ {target} 不是交易日，跳过")
            sys.exit(0)
        sync_date(target)
