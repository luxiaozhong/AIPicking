#!/usr/bin/env python3
"""
每日增量更新五大指数日线数据（上证指数、深证成指、创业板指、科创50、科创100）

与 update_daily.py 的区别：
  - 指数 K 线数据路径为 data.{symbol}.day（个股是 .qfqday）
  - 指数实时行情需要 s_ 前缀的 qt_symbol
  - 指数无市值、无复权概念
  - 仅 4 个指数，无需并发批量写入

用途：
    cd backend && venv/bin/python scripts/update_index_daily.py              # 智能模式
    venv/bin/python scripts/update_index_daily.py --force                    # 强制补最近 5 天
    venv/bin/python scripts/update_index_daily.py --date 2026-05-30          # 指定某天
    venv/bin/python scripts/update_index_daily.py --date today               # 今天（盘中/盘后自动判断）
    venv/bin/python scripts/update_index_daily.py --intraday                 # 强制盘中实时
    venv/bin/python scripts/update_index_daily.py --pg-url postgresql://...  # 指定 PG 地址

盘中 cron（通过 sync_intraday_daily.sh wrapper，每5分钟，仅交易时段 9:30-11:30 / 13:00-15:00）：
    # 详见 scripts/sync_intraday_daily.sh 头部注释

环境变量：
    DATABASE_URL — PostgreSQL 连接（默认解析出 psycopg2 可用 URL）
"""
import argparse
import asyncio
import aiohttp
import os
import sys
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

sys.path.insert(0, str(_ENV_DIR))

# ── 配置 ────────────────────────────────────────────────────────────────────

def _parse_pg_url(url: str) -> dict:
    """从 DATABASE_URL 解析 psycopg2 连接参数"""
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
EM_KLINE_API = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
TIMEOUT     = aiohttp.ClientTimeout(total=15)

# 指数 API 不含交易日字段，通过个股 API field[30] 获取真实交易日
_REF_STOCK = "sh600519"  # 贵州茅台，用于探测真实交易日


def _get_actual_trade_date(fallback_date: str) -> str:
    """通过个股实时行情 API 获取真实交易日（field[30]=YYYYMMDDHHMMSS）。

    非交易日 API 返回的是上一交易日的快照，field[30] 会显示正确日期。
    指数 API 不含时间戳，所以需要借助个股 API 来确定日期。
    """
    import requests as _requests
    try:
        r = _requests.get(f"{QUOTE_API}{_REF_STOCK}", timeout=5)
        text = r.content.decode("gbk", errors="replace")
        if "=" in text:
            content = text.split("=", 1)[1].strip().strip('"')
            fields = content.split("~")
            ts = fields[30].strip() if len(fields) > 30 and fields[30].strip() else ""
            if len(ts) >= 8:
                return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
    except Exception:
        pass
    return fallback_date

# ── 五大指数定义 ───────────────────────────────────────────────────────────
INDICES = [
    {
        "ts_code":    "000001.SH",
        "symbol":     "sh000001",       # 腾讯 K 线 API param
        "qt_symbol":  "s_sh000001",     # 腾讯实时行情 symbol
        "name":       "上证指数",
        "market":     "SH",
        "list_date":  "19901219",
    },
    {
        "ts_code":    "399001.SZ",
        "symbol":     "sz399001",
        "qt_symbol":  "s_sz399001",
        "name":       "深证成指",
        "market":     "SZ",
        "list_date":  "19910703",
    },
    {
        "ts_code":    "399006.SZ",
        "symbol":     "sz399006",
        "qt_symbol":  "s_sz399006",
        "name":       "创业板指",
        "market":     "SZ",
        "list_date":  "20100601",
    },
    {
        "ts_code":    "000688.SH",
        "symbol":     "sh000688",
        "qt_symbol":  "s_sh000688",
        "name":       "科创50",
        "market":     "SH",
        "list_date":  "20200723",
    },
    {
        "ts_code":    "000698.SH",
        "symbol":     "sh000698",
        "qt_symbol":  "s_sh000698",
        "name":       "科创100",
        "market":     "SH",
        "list_date":  "20230807",
    },
]

# 节假日（与 update_daily.py 保持一致）
HOLIDAYS_2024 = {"0101", "0210", "0211", "0212", "0213", "0214", "0215", "0216", "0217",
                   "0404", "0405", "0406", "0501", "0502", "0503", "0504", "0505",
                   "0608", "0609", "0610", "0929", "0930", "1001", "1002", "1003",
                   "1004", "1005", "1006", "1007"}
HOLIDAYS_2025 = {"0101", "0128", "0129", "0130", "0131", "0203", "0204",
                   "0404", "0405", "0406", "0501", "0502", "0503", "0504", "0505",
                   "0531", "0601", "0602", "1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008"}
HOLIDAYS_2026 = {"0101", "0217", "0218", "0219", "0220", "0221", "0222", "0223",
                   "0405", "0406", "0407", "0501", "0502", "0503", "0504", "0505",
                   "0619", "0929", "0930", "1001", "1002", "1003", "1004", "1005", "1006", "1007"}


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


def count_daily(trade_date: str) -> int:
    """查询某日已有指数数据条数，trade_date 为 YYYYMMDD 或 YYYY-MM-DD"""
    trade_date = _fmt_date(trade_date)  # 统一为 YYYY-MM-DD
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM daily WHERE trade_date=%s AND ts_code IN %s",
        (trade_date, tuple(idx["ts_code"] for idx in INDICES)))
    cnt = cur.fetchone()[0]
    conn.close()
    return cnt


# ── index_info 表 —— 幂等写入指数记录 ──────────────────────────────────────────

def ensure_index_info_entries():
    """确保 INDICES 中的指数记录存在于 index_info 表（INSERT ON CONFLICT 幂等）"""
    conn = get_conn()
    cur = conn.cursor()
    for idx in INDICES:
        cur.execute("""
            INSERT INTO index_info (index_code, ts_code, index_name, full_name, publisher, data_source)
            VALUES (%s, %s, %s, %s, %s, 'update_index_daily.py')
            ON CONFLICT (index_code) DO UPDATE SET
                ts_code = EXCLUDED.ts_code,
                index_name = EXCLUDED.index_name,
                full_name = EXCLUDED.full_name,
                publisher = EXCLUDED.publisher,
                last_sync_date = CURRENT_DATE
        """, (
            idx["ts_code"].replace(".SH", "").replace(".SZ", ""),  # index_code（无后缀）
            idx["ts_code"],       # ts_code（带后缀）
            idx["name"],          # index_name
            idx["name"],          # full_name（与 index_name 相同，如"上证指数"）
            _publisher(idx["market"]),
        ))
    conn.commit()
    conn.close()
    print(f"✅ index_info 表指数记录已就绪（{len(INDICES)} 条）")


def _publisher(market: str) -> str:
    """根据 market 推断编制机构"""
    return {"SH": "上证", "SZ": "深证"}.get(market, "中证")


# ── 历史 K 线接口（指数专用：读取 .day 而非 .qfqday）──────────────────────

async def download_one_index(session, idx: dict, start_date: str, end_date: str, fetch_extra_days: int = 2):
    """
    拉取单只指数指定范围的历史日线。
    指数数据位于 data.{symbol}.day（个股是 .qfqday）。
    返回 records 列表或 None。

    fetch_extra_days: 起始日向前扩展天数。腾讯 fqkline 接口在
    start_date == end_date（单日请求）时会返回 0 行，故默认向前扩 2 天，
    用多日区间请求后再按 [start_date, end_date] 过滤，避免漏拉当天数据。
    """
    # 扩展起始日，规避单日区间（start==end）请求返回空的问题
    start_dt = datetime.strptime(_fmt_date(start_date), "%Y-%m-%d")
    expanded_start = (start_dt - timedelta(days=fetch_extra_days)).strftime("%Y-%m-%d")

    url = (f"{TENCENT_API}?param={idx['symbol']},day,"
           f"{expanded_start},{_fmt_date(end_date)},20,day")
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            text = await resp.text()
    except Exception:
        return None

    try:
        data = json.loads(text)
        index_data = data.get("data", {}).get(idx["symbol"], {})
    except (json.JSONDecodeError, AttributeError):
        # 腾讯被 WAF 拦截或返回异常 → 东方财富兜底
        return await download_one_index_em(session, idx, start_date, end_date)

    # 指数无复权，数据在 .day 下（不是 .qfqday）
    day_list = index_data.get("day", [])
    if not day_list:
        # 腾讯无数据（含单日区间返回空）→ 东方财富兜底
        return await download_one_index_em(session, idx, start_date, end_date)

    range_start = _fmt_date(start_date)
    range_end = _fmt_date(end_date)

    records = []
    for row in day_list:
        if len(row) < 6:
            continue
        try:
            trade_date = row[0]  # 腾讯接口已返回 YYYY-MM-DD
            # 按目标区间过滤，扩展日前几天的数据不写入
            if trade_date < range_start or trade_date > range_end:
                continue
            # 腾讯 K 线字段顺序: [日期, 开盘, 收盘, 最高, 最低, 成交量]
            open_p  = float(row[1])
            close_p = float(row[2])
            high_p  = float(row[3])
            low_p   = float(row[4])
            vol     = float(row[5])
            # 指数成交额估算（K 线不含成交额字段）
            amount  = vol * ((open_p + close_p + high_p + low_p) / 4.0)
            records.append((idx["ts_code"], trade_date, open_p, high_p, low_p,
                            close_p, vol, amount, close_p))
        except (ValueError, IndexError):
            continue
    return records if records else None


# ── 东方财富兜底（腾讯 K 线被 WAF 封时启用）────────────────────────────────

async def download_one_index_em(session, idx: dict, start_date: str, end_date: str):
    """
    东方财富历史日线兜底，返回 records 列表或 None。
    指数 secid：沪市 1.xxxxxx，深市 0.xxxxxx；无复权（fqt=0）。
    """
    start_s = _fmt_date(start_date).replace("-", "")
    end_s = _fmt_date(end_date).replace("-", "")
    code = idx["symbol"][2:]  # 去掉 sh/sz 前缀
    market = "1" if idx["symbol"].startswith("sh") else "0"
    secid = f"{market}.{code}"
    url = (f"{EM_KLINE_API}?secid={secid}&fields1=f1"
           f"&fields2=f51,f52,f53,f54,f55,f56,f57"
           f"&klt=101&fqt=0&beg={start_s}&end={end_s}")
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            data = json.loads(await resp.text())
    except Exception:
        return None

    k = data.get("data")
    if not k:
        return None
    klines = k.get("klines", [])
    if not klines:
        return None

    range_start = _fmt_date(start_date)
    range_end = _fmt_date(end_date)
    records = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 7:
            continue
        trade_date = parts[0]
        if trade_date < range_start or trade_date > range_end:
            continue
        try:
            open_p  = float(parts[1])
            close_p = float(parts[2])
            high_p  = float(parts[3])
            low_p   = float(parts[4])
            vol     = float(parts[5])
            amount  = float(parts[6])
            records.append((idx["ts_code"], trade_date, open_p, high_p, low_p,
                            close_p, vol, amount, close_p))
        except (ValueError, IndexError):
            continue
    return records if records else None


# ── 实时行情接口（指数专用：s_ 前缀 + 不同字段位置）───────────────────────

async def fetch_realtime_quote_index(session, idx: dict, trade_date: str):
    """
    拉取指数实时行情。trade_date 为 YYYY-MM-DD。
    指数 qt 接口需要 s_ 前缀，且字段位置与个股不同。
    返回 record tuple 或 None。
    """
    url = f"{QUOTE_API}{idx['qt_symbol']}"
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

        # 指数 qt 格式: ~ZS~ 标记结尾，字段相比个股少很多
        if len(fields) < 10:
            return None

        # 关键字段（已验证）:
        # fields[3] = 当前价
        # fields[4] = 涨跌额  (price - prev_close)
        # fields[5] = 涨跌幅%
        # fields[6] = 成交量
        # fields[7] = 成交额（万元）
        price      = float(fields[3]) if fields[3].strip() else None
        change     = float(fields[4]) if fields[4].strip() else 0.0
        vol        = float(fields[6]) if fields[6].strip() else 0
        amount_wan = float(fields[7]) if len(fields) > 7 and fields[7].strip() else 0

        if price is None or price == 0:
            return None

        prev_close = price - change
        # 实时接口不提供完整的 OHLC，用当前价/前收价填充
        open_p  = prev_close
        high_p  = max(price, prev_close)
        low_p   = min(price, prev_close)
        amount  = amount_wan * 10000  # 万元 → 元

        record = (idx["ts_code"], trade_date,
                  open_p, high_p, low_p, price,
                  vol, amount, price)
        return record
    except (ValueError, IndexError):
        return None


# ── 数据库写入 ────────────────────────────────────────────────────────────

def upsert_daily(record):
    """单条写入 daily 表（ON CONFLICT 覆盖更新）"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO daily (ts_code, trade_date, open, high, low, close, vol, amount, adj_close)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ts_code, trade_date) DO UPDATE SET
            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
            close = EXCLUDED.close, vol = EXCLUDED.vol, amount = EXCLUDED.amount,
            adj_close = EXCLUDED.adj_close
    """, record)
    conn.commit()
    conn.close()


def bulk_upsert(records):
    """批量写入 daily 表"""
    conn = get_conn()
    cur = conn.cursor()
    psycopg2.extras.execute_batch(cur, """
        INSERT INTO daily (ts_code, trade_date, open, high, low, close, vol, amount, adj_close)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ts_code, trade_date) DO UPDATE SET
            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
            close = EXCLUDED.close, vol = EXCLUDED.vol, amount = EXCLUDED.amount,
            adj_close = EXCLUDED.adj_close
    """, records)
    conn.commit()
    conn.close()


# ── 实时拉取任务（盘中模式）────────────────────────────────────────────────

async def run_intraday(trade_date: str):
    """用实时接口拉取 4 个指数的盘中报价"""
    trade_date = _get_actual_trade_date(_fmt_date(trade_date))
    print(f"🚀 实时接口模式：拉取 {trade_date} 指数报价...\n")

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        records = []
        for idx in INDICES:
            record = await fetch_realtime_quote_index(session, idx, trade_date)
            if record:
                records.append(record)
                print(f"  ✅ {idx['name']}（{idx['ts_code']}）：现价 {record[5]:.2f}")
            else:
                print(f"  ⚠️  {idx['name']}（{idx['ts_code']}）：获取失败")

        if records:
            bulk_upsert(records)

    print(f"\n🎉 实时更新完成！成功 {len(records)}/4 个指数")
    return len(records)


# ── 历史日线拉取任务 ──────────────────────────────────────────────────────

async def run_history(start_date: str, end_date: str):
    """用历史日线接口拉取 4 个指数指定范围的数据"""
    print(f"🚀 历史日线模式：{start_date} ~ {end_date}，共 4 个指数...\n")

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        total_records = 0
        for idx in INDICES:
            records = await download_one_index(session, idx, start_date, end_date)
            if records:
                bulk_upsert(records)
                total_records += len(records)
                print(f"  ✅ {idx['name']}（{idx['ts_code']}）：+{len(records)} 条  "
                      f"{records[0][1]} ~ {records[-1][1]}")
            else:
                print(f"  ⚠️  {idx['name']}（{idx['ts_code']}）：无数据")

    print(f"\n🎉 历史更新完成！新增/覆盖 {total_records} 条指数数据")
    return total_records


# ── 主流程 ────────────────────────────────────────────────────────────────

async def main(force=False, target_date=None, intraday=False, pg_url=None):
    global _PG_PARAMS
    if pg_url:
        _PG_PARAMS = _parse_pg_url(pg_url)

    # 0. 确保 stocks 表有指数记录
    ensure_index_info_entries()

    now = datetime.now()
    today_str = now.strftime("%Y%m%d")
    today_is_trade = is_trade_day(today_str)

    # ── 1. --force：历史接口补最近 5 个交易日 ──
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
        print(f"📅 盘后更新今天({today_str})")
        print(f"🔄 强制更新模式：{start_date} ~ {end_date}")
        await run_history(start_date, end_date)
        return

    # ── 2. --intraday：强制实时接口拉今天 ──
    if intraday:
        if not today_is_trade:
            print(f"⚠️  今天({today_str})不是交易日，无法拉取实时数据")
            return
        print(f"📅 盘后更新今天({today_str})")
        print(f"📡 强制盘中实时模式：{today_str}")
        await run_intraday(today_str)
        return

    # ── 3. --date 指定某一天 ──
    if target_date:
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
            if is_intraday_now():
                print(f"🕐 当前盘中，使用实时接口拉取今天({date_str})")
                await run_intraday(date_str)
            else:
                print(f"🕒 当前盘后，使用历史日线接口拉取今天({date_str})")
                records = await run_history(date_str, date_str)
                if records == 0:
                    print(f"⚠️  历史接口无数据，使用实时接口兜底...")
                    await run_intraday(date_str)
        else:
            print(f"📅 历史日期({date_str})，使用历史日线接口")
            await run_history(date_str, date_str)
        return

    # ── 4. 无参数默认模式 ──
    # 始终输出日期标记行，确保 sync_report.py 能识别本次运行
    print(f"📅 盘后更新今天({today_str})")

    if today_is_trade:
        if is_intraday_now():
            print(f"🕐 盘中模式（{today_str}），使用实时接口")
            await run_intraday(today_str)
        else:
            cnt = count_daily(today_str)
            if cnt > 0:
                print(f"✅ 今天({today_str})已有 {cnt} 条指数数据")
                print(f"📊 指数历史更新完成！跳过 — 已有 {cnt} 条数据（覆盖 0 条）")
            else:
                print(f"📅 盘后更新今天({today_str})，使用历史日线接口")
                await run_history(today_str, today_str)
    else:
        latest = get_latest_trade_day_before(now - timedelta(days=1))
        if not latest:
            print("⚠️  找不到最近交易日，退出")
            return
        cnt = count_daily(latest)
        if cnt > 0:
            print(f"✅ 最近交易日({latest})已有 {cnt} 条指数数据，无需更新")
            print(f"📊 指数历史更新完成！跳过 — 已有 {cnt} 条数据（覆盖 0 条）")
            return
        print(f"📅 补充最近交易日({latest})指数数据，使用历史日线接口")
        await run_history(latest, latest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="四大指数日线数据同步工具")
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
            target_date = d

    asyncio.run(main(force=args.force, target_date=target_date,
                     intraday=args.intraday, pg_url=args.pg_url))
