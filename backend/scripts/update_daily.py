#!/usr/bin/env python3
"""
每日增量更新 A 股日线数据（后复权）

模式选择逻辑（优先级从高到低）：
  1. --intraday          强制使用实时接口（拉今天盘中数据）
  2. --date YYYY-MM-DD   指定过去某天  → 历史日线接口
  3. --date today        指定今天
       盘中(9:25~15:00) → 实时接口
       盘后             → 历史日线接口
  4. 无参数（默认）
       判断今天是否为交易日：
         盘中 → 实时接口拉今天
         盘后 → 历史日线接口拉今天
       同时补齐昨天若缺数据

用法：
    cd backend && venv/bin/python scripts/update_daily.py              # 智能模式
    venv/bin/python scripts/update_daily.py --force                    # 强制补最近 5 天
    venv/bin/python scripts/update_daily.py --date 2026-05-22          # 指定某天
    venv/bin/python scripts/update_daily.py --date today               # 今天（自动盘中/盘后）
    venv/bin/python scripts/update_daily.py --intraday                 # 强制盘中实时模式
    venv/bin/python scripts/update_daily.py --pg-url postgresql://...  # 指定 PG 地址

环境变量：
    DATABASE_URL — PostgreSQL 连接（默认解析出 psycopg2 可用 URL）
"""
import argparse
import asyncio
import aiohttp
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# 加载 .env（dev）→ .env.production（prod 覆盖）
_ENV_DIR = Path(__file__).resolve().parent.parent  # backend/
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)

# ── 配置 ────────────────────────────────────────────────────────────────────

def _parse_pg_url(url: str) -> dict:
    """从 DATABASE_URL 解析 psycopg2 连接参数"""
    url = url.replace("+asyncpg", "").replace("+psycopg2", "")
    if "://" not in url:
        url = f"postgresql://{url}"
    # 处理 postgresql://user:pass@host:port/dbname 格式
    r = urlparse(url if "://" in url else f"postgresql://{url}")
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

TENCENT_API = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
QUOTE_API   = "http://qt.gtimg.cn/q="
CONCURRENCY = 30
TIMEOUT     = aiohttp.ClientTimeout(total=15)

# 节假日（排除这些日期）
HOLIDAYS_2024 = {"0101", "0210", "0211", "0212", "0213", "0214", "0215", "0216", "0217",
                   "0404", "0405", "0406", "0501", "0502", "0503", "0504", "0505",
                   "0608", "0609", "0610", "0929", "0930", "1001", "1002", "1003",
                   "1004", "1005", "1006", "1007"}
HOLIDAYS_2025 = {"0101", "0128", "0129", "0130", "0131", "0203", "0204",
                   "0404", "0405", "0406", "0501", "0502", "0503", "0504", "0505",
                   "0531", "0601", "0602", "1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008"}
HOLIDAYS_2026 = {"0101", "0217", "0218", "0219", "0220", "0221", "0222", "0223",
                   "0405", "0406", "0407", "0501", "0502", "0503", "0504", "0505",
                   "0625", "0626", "0627", "0929", "0930", "1001", "1002", "1003", "1004", "1005", "1006", "1007"}


def is_trade_day(date_str: str) -> bool:
    """判断是否为交易日，输入 YYYYMMDD 或 YYYY-MM-DD"""
    date_str = date_str.replace("-", "")
    d = datetime.strptime(date_str, "%Y%m%d")
    if d.weekday() >= 5:
        return False
    mmdd = d.strftime("%m%d")
    year = d.year
    holidays = {2024: HOLIDAYS_2024, 2025: HOLIDAYS_2025, 2026: HOLIDAYS_2026}
    if year in holidays and mmdd in holidays[year]:
        return False
    return True


def get_latest_trade_day_before(base_date: datetime) -> Optional[str]:
    """获取 base_date 之前（含当天）最近一个交易日，返回 YYYYMMDD"""
    d = base_date
    for _ in range(10):
        ds = d.strftime("%Y%m%d")
        if is_trade_day(ds):
            return ds
        d -= timedelta(days=1)
    return None


def is_intraday_now() -> bool:
    """判断当前是否在盘中时间（9:25~11:30 或 13:00~15:00）且为交易日"""
    now = datetime.now()
    if not is_trade_day(now.strftime("%Y%m%d")):
        return False
    t = now.hour * 100 + now.minute
    return (925 <= t <= 1130) or (1300 <= t <= 1500)


def get_conn():
    """获取 PostgreSQL 连接"""
    return psycopg2.connect(**_PG_PARAMS)


def _fmt_date(d: str) -> str:
    """YYYYMMDD → YYYY-MM-DD；已是 YYYY-MM-DD 则原样返回"""
    d = d.replace("-", "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


# 指数 ts_code（由 update_index_daily.py 处理，此处排除）
_INDEX_CODES = ("000001.SH", "399001.SZ", "399006.SZ", "000688.SH", "000698.SH")

def load_stocks():
    """从 PostgreSQL stocks 表读取股票列表（排除指数）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT ts_code, symbol FROM stocks WHERE ts_code NOT IN %s",
        (_INDEX_CODES,))
    rows = cur.fetchall()
    conn.close()
    return [{"ts_code": r[0], "symbol": r[1]} for r in rows]


def count_daily(trade_date: str) -> int:
    """查询某日已有数据条数，trade_date 为 YYYYMMDD 或 YYYY-MM-DD"""
    trade_date = _fmt_date(trade_date)  # 统一为 YYYY-MM-DD
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM daily WHERE trade_date=%s", (trade_date,))
    cnt = cur.fetchone()[0]
    conn.close()
    return cnt


# ── 历史/盘后日线接口 ──────────────────────────────────────────────────────
async def download_one(session, ts_code, symbol, start_date, end_date, fetch_extra_days=7):
    """拉取单只股票指定范围日线（前复权），返回 records 列表或 None

    fetch_extra_days: 在 start_date 之前多拉取的天数，用于获取 pre_close。
    腾讯前复权数据在同一 API 响应中使用相同的复权因子，因此用前一天收盘价
    作为 pre_close 可以保证涨跌幅计算正确。
    """
    from datetime import datetime as dt, timedelta as td
    # 扩展起始日期以获取 pre_close（同一复权因子）
    expanded_start = dt.strptime(_fmt_date(start_date), "%Y-%m-%d") - td(days=fetch_extra_days)
    expanded_start_str = expanded_start.strftime("%Y-%m-%d")

    url = (f"{TENCENT_API}?param={symbol},day,"
           f"{expanded_start_str},{_fmt_date(end_date)},40,qfq")
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            text = await resp.text()
    except Exception:
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
        return None

    if not qfq_data:
        return None

    records = []
    prev_close = None
    for row in qfq_data:
        if len(row) < 6:
            continue
        try:
            trade_date = row[0]  # 腾讯接口已返回 YYYY-MM-DD
            # 腾讯K线接口 qfqday 字段顺序: [日期, 开盘, 收盘, 最高, 最低, 成交量]
            open_p  = float(row[1])
            close_p = float(row[2])
            high_p  = float(row[3])
            low_p   = float(row[4])
            vol     = float(row[5])
            amount  = vol * close_p * 100
            records.append((ts_code, trade_date, open_p, high_p, low_p,
                             close_p, prev_close, vol, amount, close_p, None, None))
            prev_close = close_p
        except (ValueError, IndexError):
            continue
    return records


# ── 实时报价接口（盘中 + 兜底） ───────────────────────────────────────────
async def fetch_realtime_quote(session, symbol, trade_date):
    """
    拉取实时报价，返回 record_tuple
    trade_date 为 YYYY-MM-DD
    """
    url = f"{QUOTE_API}{symbol}"
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            raw = await resp.read()
        text = raw.decode("gbk", errors="replace")
    except Exception:
        return None

    if "=" not in text:
        return None
    try:
        content = text.split("=", 1)[1].strip().strip('"')
        fields = content.split("~")
        if len(fields) < 46:
            return None

        price      = float(fields[3]) if fields[3].strip() else None
        prev_close = float(fields[4]) if fields[4].strip() else None
        open_p     = float(fields[5]) if fields[5].strip() else None
        high_p     = float(fields[33]) if fields[33].strip() else None
        low_p      = float(fields[34]) if fields[34].strip() else None
        vol        = float(fields[6])  if fields[6].strip()  else 0
        amount     = float(fields[37]) if fields[37].strip() else 0
        amount     = amount * 10000

        if price is None or price == 0:
            return None
        if vol == 0 and open_p == 0:
            return None

        record = (None, trade_date,
                  open_p or prev_close, high_p or price,
                  low_p or price, price, prev_close,
                  vol, amount, price)
        return record
    except (ValueError, IndexError):
        return None


# ── 数据库写入 ────────────────────────────────────────────────────────────
def upsert_daily(record):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO daily (ts_code, trade_date, open, high, low, close, pre_close, vol, amount, adj_close)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ts_code, trade_date) DO UPDATE SET
            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
            close = EXCLUDED.close, pre_close = EXCLUDED.pre_close,
            vol = EXCLUDED.vol, amount = EXCLUDED.amount,
            adj_close = EXCLUDED.adj_close
    """, record)
    conn.commit()
    conn.close()


def bulk_upsert(records):
    conn = get_conn()
    cur = conn.cursor()
    psycopg2.extras.execute_batch(cur, """
        INSERT INTO daily (ts_code, trade_date, open, high, low, close, pre_close, vol, amount, adj_close)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ts_code, trade_date) DO UPDATE SET
            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
            close = EXCLUDED.close, pre_close = EXCLUDED.pre_close,
            vol = EXCLUDED.vol, amount = EXCLUDED.amount,
            adj_close = EXCLUDED.adj_close
    """, records)
    conn.commit()
    conn.close()


# ── 实时拉取任务（盘中模式） ──────────────────────────────────────────────
async def run_intraday(stocks, trade_date: str):
    """用实时接口拉取 trade_date（YYYYMMDD）的数据"""
    trade_date = _fmt_date(trade_date)  # 转为 YYYY-MM-DD 写入 DB
    print(f"🚀 实时接口模式：拉取 {trade_date} 报价，共 {len(stocks)} 只股票...\n")
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        semaphore = asyncio.Semaphore(CONCURRENCY)

        async def bounded_fetch(s):
            async with semaphore:
                record = await fetch_realtime_quote(
                    session, s["symbol"], trade_date)
                return s["ts_code"], record

        tasks = [bounded_fetch(s) for s in stocks]
        updated, skipped = 0, 0
        batch = []
        BATCH_SIZE = 200
        for coro in asyncio.as_completed(tasks):
            ts_code, record = await coro
            if record:
                full_record = (ts_code,) + record[1:]
                batch.append(full_record)
                updated += 1
                if updated <= 3 or updated % 500 == 0:
                    print(f"  ✅ {ts_code}：现价 {record[5]:.2f} 昨收 {record[6]:.2f}")
                # 批量写入
                if len(batch) >= BATCH_SIZE:
                    bulk_upsert(batch)
                    batch = []
            else:
                skipped += 1
            await asyncio.sleep(0.02)
        # 剩余批量写入
        if batch:
            bulk_upsert(batch)

    print(f"\n🎉 实时更新完成！成功 {updated} 只，跳过 {skipped} 只（停牌/未开盘）")
    return updated


# ── 历史/盘后日线拉取任务 ─────────────────────────────────────────────────
async def run_history(stocks, start_date: str, end_date: str, do_fallback=False):
    """
    用历史日线接口拉取 start_date ~ end_date 的数据
    do_fallback: 是否在盘后补齐 end_date 缺失的股票（用 qt 兜底）
    """
    print(f"🚀 历史日线模式：{start_date} ~ {end_date}，共 {len(stocks)} 只股票...\n")
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        semaphore = asyncio.Semaphore(CONCURRENCY)

        async def bounded_update(s):
            async with semaphore:
                records = await download_one(
                    session, s["ts_code"], s["symbol"], start_date, end_date)
                return s["ts_code"], s["symbol"], records

        tasks = [bounded_update(s) for s in stocks]
        new_count = 0
        for coro in asyncio.as_completed(tasks):
            ts_code, symbol, records = await coro
            if records:
                bulk_upsert(records)
                new_count += len(records)
                print(f"  ✅ {ts_code}：+{len(records)} 条")
            else:
                print(f"  ⚠️  {ts_code}：无新数据")
            await asyncio.sleep(0.02)

        # ── qt 兜底：补齐日线接口缺失的股票 ──
        if do_fallback:
            fallback_date = _fmt_date(end_date)
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT s.ts_code, s.symbol FROM stocks s
                WHERE s.ts_code NOT IN (
                    SELECT ts_code FROM daily WHERE trade_date=%s
                )
            """, (fallback_date,))
            missing = cur.fetchall()
            conn.close()

            if missing:
                print(f"\n⚠️  日线接口缺失 {len(missing)} 只，qt 实时接口兜底...")
                fb_updated, fb_skipped = 0, 0
                for ts_code, symbol in missing:
                    record = await fetch_realtime_quote(
                        session, symbol, fallback_date)
                    if record:
                        full_record = (ts_code,) + record[1:]
                        upsert_daily(full_record)
                        fb_updated += 1
                        if fb_updated <= 3 or fb_updated % 500 == 0:
                            print(f"  ✅ {ts_code}：收盘 {record[5]:.2f}")
                    else:
                        fb_skipped += 1
                    if fb_updated % 100 == 0:
                        await asyncio.sleep(0.02)
                new_count += fb_updated
                print(f"  📊 qt 兜底 {fb_updated} 只，跳过 {fb_skipped} 只（停牌/退市）")
            else:
                print(f"\n✅ 日线接口全覆盖，无需兜底")

    print(f"\n🎉 历史更新完成！新增/覆盖 {new_count} 条数据")
    return new_count


# ── 主流程 ────────────────────────────────────────────────────────────────
async def main(force=False, target_date=None, intraday=False, pg_url=None):
    global _PG_PARAMS
    if pg_url:
        _PG_PARAMS = _parse_pg_url(pg_url)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM stocks")
    total = cur.fetchone()[0]
    conn.close()
    if total == 0:
        print("❌ 股票列表为空，请先初始化 stocks 表")
        return
    print(f"📊 数据库已有 {total} 只股票")

    stocks = load_stocks()
    now = datetime.now()
    today_str = now.strftime("%Y%m%d")
    today_is_trade = is_trade_day(today_str)

    # ────────────────────────────────────────────────────────────────────
    # 1. --force：历史接口补最近 5 个交易日
    # ────────────────────────────────────────────────────────────────────
    if force:
        d = now
        dates = []
        while len(dates) < 5:
            d -= timedelta(days=1)
            ds = d.strftime("%Y%m%d")
            if is_trade_day(ds):
                dates.append(ds)
        start_date = min(dates)
        end_date   = max(dates)
        print(f"🔄 强制更新模式：{start_date} ~ {end_date}")
        await run_history(stocks, start_date, end_date, do_fallback=False)
        return

    # ────────────────────────────────────────────────────────────────────
    # 2. --intraday：强制实时接口拉今天
    # ────────────────────────────────────────────────────────────────────
    if intraday:
        if not today_is_trade:
            print(f"⚠️  今天({today_str})不是交易日，无法拉取实时数据")
            return
        print(f"📡 强制盘中实时模式：{today_str}")
        await run_intraday(stocks, today_str)
        return

    # ────────────────────────────────────────────────────────────────────
    # 3. --date 指定某一天
    # ────────────────────────────────────────────────────────────────────
    if target_date:
        # 解析日期
        if target_date.lower() == "today":
            date_str = today_str
            is_today = True
        else:
            date_str = target_date.replace("-", "")
            is_today = (date_str == today_str)

        if not is_trade_day(date_str):
            print(f"⚠️  {date_str} 不是交易日，退出")
            return

        if is_today:
            # 今天：盘中用实时，盘后用历史
            if is_intraday_now():
                print(f"🕐 当前盘中，使用实时接口拉取今天({date_str})")
                await run_intraday(stocks, date_str)
            else:
                print(f"🕒 当前盘后，使用历史日线接口拉取今天({date_str})")
                await run_history(stocks, date_str, date_str, do_fallback=True)
        else:
            # 过去某天：始终用历史接口
            print(f"📅 历史日期({date_str})，使用历史日线接口")
            await run_history(stocks, date_str, date_str, do_fallback=False)
        return

    # ────────────────────────────────────────────────────────────────────
    # 4. 无参数默认模式：智能判断
    #    - 今天是交易日且盘中 → 实时接口更新今天
    #    - 今天是交易日且盘后 → 历史接口更新今天（含兜底）
    #    - 今天非交易日 → 历史接口补昨天（或最近交易日）
    #    顺带检查昨天（最近交易日）是否有数据，没有则补
    # ────────────────────────────────────────────────────────────────────
    # 完整交易日至少应有 4500+ 只股票，盘中实时数据通常只有 ~3000 只
    MIN_DAILY_COUNT = 4500

    if today_is_trade:
        if is_intraday_now():
            print(f"🕐 盘中模式（{today_str}），使用实时接口")
            await run_intraday(stocks, today_str)
        else:
            # 盘后：检查今天数据是否完整
            cnt = count_daily(today_str)
            if cnt >= MIN_DAILY_COUNT:
                print(f"✅ 今天({today_str})已有 {cnt} 条数据，数据完整，跳过")
            else:
                if cnt > 0:
                    print(f"⚠️ 今天({today_str})仅有 {cnt} 条数据（不完整，可能是盘中写入），执行完整更新")
                else:
                    print(f"📅 今天({today_str})无数据，使用历史日线接口")
                await run_history(stocks, today_str, today_str, do_fallback=True)
    else:
        # 今天非交易日，补最近交易日
        latest = get_latest_trade_day_before(now - timedelta(days=1))
        if not latest:
            print("⚠️  找不到最近交易日，退出")
            return
        cnt = count_daily(latest)
        if cnt >= MIN_DAILY_COUNT:
            print(f"✅ 最近交易日({latest})已有 {cnt} 条数据，数据完整，无需更新")
            return
        if cnt > 0:
            print(f"⚠️ 最近交易日({latest})仅有 {cnt} 条数据（不完整），执行补充更新")
        else:
            print(f"📅 最近交易日({latest})无数据，使用历史日线接口")
        await run_history(stocks, latest, latest, do_fallback=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A股日线数据同步工具")
    parser.add_argument("--force", action="store_true",
                        help="强制历史接口补最近 5 个交易日")
    parser.add_argument("--date", type=str,
                        help="指定日期（YYYY-MM-DD / YYYYMMDD / today）")
    parser.add_argument("--intraday", action="store_true",
                        help="强制使用实时接口拉取今天数据")
    parser.add_argument("--pg-url", type=str, default=None,
                        help="PostgreSQL 连接 URL（默认: $DATABASE_URL）")
    args = parser.parse_args()

    target_date = None
    if args.date:
        d = args.date.replace("-", "")
        if d.lower() == "today":
            target_date = "today"
        else:
            target_date = d  # 统一传 YYYYMMDD

    asyncio.run(main(force=args.force, target_date=target_date, intraday=args.intraday, pg_url=args.pg_url))
