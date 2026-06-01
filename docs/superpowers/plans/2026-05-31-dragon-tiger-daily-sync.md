# 龙虎榜每日采集脚本 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 新建 `sync_dragon_tiger.py` 每日抓取全市场龙虎榜汇总 + 买卖席位明细，存入 PostgreSQL。

**架构：** 独立脚本直连 PostgreSQL（psycopg2），复用 a-stock-data skill 的东财 `em_get()` 节流机制。SQLAlchemy 模型供应用层使用，脚本自身走裸 psycopg2 以保持零依赖应用代码。

**技术栈：** Python 3, psycopg2, requests, argparse, logging（与现有 `update_daily.py` / `sync_market_data.py` 统一风格）

---

### Task 1: 新增 SQLAlchemy 模型

**文件：**
- 修改: `backend/app/models/stock_tables.py`
- 修改: `backend/app/models/__init__.py`

- [ ] **Step 1: 在 stock_tables.py 中更新 import 并添加两个新模型**

先更新 `backend/app/models/stock_tables.py` 第 2-5 行的 import，添加 `Boolean`：

```python
from sqlalchemy import (
    Column, String, Integer, Float, Text, BigInteger, Boolean,
    Index, UniqueConstraint
)
```

然后在文件末尾（`DailyNorthboundFlow` 之后）添加两个新模型：

```python
class DailyDragonTiger(BaseModel):
    """每日龙虎榜上榜汇总"""
    __tablename__ = "daily_dragon_tiger"
    __table_args__ = (
        UniqueConstraint("trade_date", "stock_code", name="uq_dragon_tiger"),
        Index("idx_dt_date", "trade_date"),
        Index("idx_dt_code", "stock_code"),
    )

    trade_date = Column(String(10), nullable=False)
    stock_code = Column(String(20), nullable=False)
    stock_name = Column(String(100))
    reason = Column(String(200))
    close = Column(Float)
    change_pct = Column(Float)
    turnover_pct = Column(Float)
    net_buy_wan = Column(Float)
    buy_wan = Column(Float)
    sell_wan = Column(Float)


class DailyDragonTigerSeat(BaseModel):
    """每日龙虎榜买卖席位明细"""
    __tablename__ = "daily_dragon_tiger_seats"
    __table_args__ = (
        UniqueConstraint("trade_date", "stock_code", "seat_type", "rank",
                         name="uq_dt_seats"),
        Index("idx_dts_date", "trade_date"),
        Index("idx_dts_code", "stock_code"),
    )

    trade_date = Column(String(10), nullable=False)
    stock_code = Column(String(20), nullable=False)
    seat_type = Column(String(4), nullable=False)  # buy / sell
    rank = Column(Integer, nullable=False)          # 1-5
    seat_name = Column(String(100))
    seat_code = Column(String(20))
    buy_amt_wan = Column(Float)
    sell_amt_wan = Column(Float)
    net_amt_wan = Column(Float)
    is_institution = Column(Boolean, default=False)
```

- [ ] **Step 2: 在 __init__.py 导出新模型**

修改 `backend/app/models/__init__.py` 第 10-13 行：

```python
from .stock_tables import (
    Stock, Daily, DailySectorFlow, StockTheme,
    DailyHotStock, DailyHotTheme, DailyNorthboundFlow,
    DailyDragonTiger, DailyDragonTigerSeat,
)
```

- [ ] **Step 3: 验证模型可导入**

```bash
cd backend && source venv/bin/activate && python -c "from app.models import DailyDragonTiger, DailyDragonTigerSeat; print('OK')"
```

预期: 输出 `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/stock_tables.py backend/app/models/__init__.py
git commit -m "feat: add DailyDragonTiger and DailyDragonTigerSeat models

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 创建 sync_dragon_tiger.py 脚本 — DDL + 配置 + 节流 helper

**文件：**
- 创建: `backend/scripts/sync_dragon_tiger.py`

- [ ] **Step 1: 创建脚本骨架（shebang, imports, docstring, env 加载, argparse 壳）**

创建 `backend/scripts/sync_dragon_tiger.py`：

```python
#!/usr/bin/env python3
"""
每日龙虎榜数据采集 — 全市场汇总 + 买卖席位明细

数据源: 东财 datacenter-web API（已内置 em_get 节流防封）
存储:   PostgreSQL（psycopg2 直连）

用法:
    cd backend
    venv/bin/python scripts/sync_dragon_tiger.py                        # 今天
    venv/bin/python scripts/sync_dragon_tiger.py --date 2026-05-30      # 指定日期
    venv/bin/python scripts/sync_dragon_tiger.py --date 2026-05-30 --dry-run  # 只拉不存

Cron (weekdays 17:00 Beijing time):
    0 17 * * 1-5 cd /opt/AIpicking/backend && \\
        venv/bin/python scripts/sync_dragon_tiger.py >> /var/log/aipicking/ingest.log 2>&1
"""
import argparse
import logging
import os
import random
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

# 加载 .env（dev）→ .env.production（prod 覆盖）
_ENV_DIR = Path(__file__).resolve().parent.parent  # backend/
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
```

- [ ] **Step 2: 添加 PostgreSQL 连接管理**

在 docstring/常量之后追加：

```python
# ═════════════════════════════════════════════════════════════════════════
# PostgreSQL 连接（复用 update_daily.py 的 _parse_pg_url 模式）
# ═════════════════════════════════════════════════════════════════════════

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

_PG_PARAMS = _parse_pg_url(os.getenv("DATABASE_URL"))

def get_conn():
    """获取 PostgreSQL 连接"""
    return psycopg2.connect(**_PG_PARAMS)
```

- [ ] **Step 3: 添加东财节流 helper（从 a-stock-data skill 移植）**

```python
# ═════════════════════════════════════════════════════════════════════════
# 东财防封：节流 + 会话复用
# ═════════════════════════════════════════════════════════════════════════

_em_session: Optional[requests.Session] = None
EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]

def _get_em_session() -> requests.Session:
    global _em_session
    if _em_session is None:
        _em_session = requests.Session()
        _em_session.headers.update({"User-Agent": UA})
    return _em_session

def em_get(url: str, params=None, headers=None, timeout: int = 15, **kwargs):
    session = _get_em_session()
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        merged = {"Referer": "https://data.eastmoney.com/"}
        if headers:
            merged.update(headers)
        return session.get(url, params=params, headers=merged,
                           timeout=timeout, **kwargs)
    finally:
        _em_last_call[0] = time.time()

def eastmoney_datacenter(report_name: str, columns: str = "ALL",
                          filter_str: str = "", page_size: int = 500,
                          sort_columns: str = "", sort_types: str = "-1") -> list[dict]:
    """东财数据中心统一查询（已内置限流）"""
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = em_get(DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []
```

- [ ] **Step 4: 添加 DDL 和建表逻辑**

```python
# ═════════════════════════════════════════════════════════════════════════
# DDL
# ═════════════════════════════════════════════════════════════════════════

_DDL_DRAGON_TIGER = """
CREATE TABLE IF NOT EXISTS daily_dragon_tiger (
    id              SERIAL PRIMARY KEY,
    trade_date      TEXT NOT NULL,
    stock_code      TEXT NOT NULL,
    stock_name      TEXT,
    reason          TEXT,
    close           DOUBLE PRECISION,
    change_pct      DOUBLE PRECISION,
    turnover_pct    DOUBLE PRECISION,
    net_buy_wan     DOUBLE PRECISION,
    buy_wan         DOUBLE PRECISION,
    sell_wan        DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(trade_date, stock_code)
)
"""

_DDL_DRAGON_TIGER_SEATS = """
CREATE TABLE IF NOT EXISTS daily_dragon_tiger_seats (
    id              SERIAL PRIMARY KEY,
    trade_date      TEXT NOT NULL,
    stock_code      TEXT NOT NULL,
    seat_type       TEXT NOT NULL,
    rank            INTEGER NOT NULL,
    seat_name       TEXT,
    seat_code       TEXT,
    buy_amt_wan     DOUBLE PRECISION,
    sell_amt_wan    DOUBLE PRECISION,
    net_amt_wan     DOUBLE PRECISION,
    is_institution  BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(trade_date, stock_code, seat_type, rank)
)
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_dt_date ON daily_dragon_tiger(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_dt_code ON daily_dragon_tiger(stock_code)",
    "CREATE INDEX IF NOT EXISTS idx_dts_date ON daily_dragon_tiger_seats(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_dts_code ON daily_dragon_tiger_seats(stock_code)",
]

def ensure_tables():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(_DDL_DRAGON_TIGER)
    cur.execute(_DDL_DRAGON_TIGER_SEATS)
    for idx in _INDEXES:
        cur.execute(idx)
    conn.commit()
    conn.close()
```

- [ ] **Step 5: 验证脚本可以导入**

```bash
cd backend && source venv/bin/activate && python -c "import scripts.sync_dragon_tiger; print('OK')"
```

预期: 可能因路径问题失败 — 调整 `sys.path`。实际运行在脚本目录下，直接执行即可。

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/sync_dragon_tiger.py
git commit -m "feat: add sync_dragon_tiger.py skeleton with DDL and throttled HTTP helpers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 实现全市场龙虎榜汇总抓取 + 存储

**文件：**
- 修改: `backend/scripts/sync_dragon_tiger.py`

- [ ] **Step 1: 添加 fetch_daily_list() 函数**

在 DDL 部分之后追加：

```python
# ═════════════════════════════════════════════════════════════════════════
# 抓取：全市场龙虎榜汇总
# ═════════════════════════════════════════════════════════════════════════

def fetch_daily_list(date_str: str) -> list[dict]:
    """
    拉取指定交易日全市场龙虎榜上榜汇总。
    date_str: YYYY-MM-DD
    返回: [{code, name, reason, close, change_pct, turnover_pct,
            net_buy_wan, buy_wan, sell_wan}, ...]
    """
    filter_str = f"(TRADE_DATE>='{date_str}')(TRADE_DATE<='{date_str}')"
    data = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=filter_str,
        page_size=500,
        sort_columns="BILLBOARD_NET_AMT",
        sort_types="-1",
    )
    if not data:
        logging.info(f"No dragon tiger data for {date_str} (non-trading day or data not released)")
        return []

    stocks = []
    for row in data:
        stocks.append({
            "stock_code": row.get("SECURITY_CODE", ""),
            "stock_name": row.get("SECURITY_NAME_ABBR", ""),
            "reason": row.get("EXPLANATION", ""),
            "close": row.get("CLOSE_PRICE"),
            "change_pct": round(float(row.get("CHANGE_RATE") or 0), 2),
            "turnover_pct": round(float(row.get("TURNOVERRATE") or 0), 2),
            "net_buy_wan": round((row.get("BILLBOARD_NET_AMT") or 0) / 10000, 1),
            "buy_wan": round((row.get("BILLBOARD_BUY_AMT") or 0) / 10000, 1),
            "sell_wan": round((row.get("BILLBOARD_SELL_AMT") or 0) / 10000, 1),
        })
    logging.info(f"Fetched {len(stocks)} dragon tiger stocks for {date_str}")
    return stocks
```

- [ ] **Step 2: 添加 save_daily_list() 函数**

```python
# ═════════════════════════════════════════════════════════════════════════
# 存储
# ═════════════════════════════════════════════════════════════════════════

_LIST_UPSERT = """
INSERT INTO daily_dragon_tiger
    (trade_date, stock_code, stock_name, reason, close, change_pct,
     turnover_pct, net_buy_wan, buy_wan, sell_wan)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (trade_date, stock_code) DO UPDATE SET
    stock_name   = EXCLUDED.stock_name,
    reason       = EXCLUDED.reason,
    close        = EXCLUDED.close,
    change_pct   = EXCLUDED.change_pct,
    turnover_pct = EXCLUDED.turnover_pct,
    net_buy_wan  = EXCLUDED.net_buy_wan,
    buy_wan      = EXCLUDED.buy_wan,
    sell_wan     = EXCLUDED.sell_wan
"""

def save_daily_list(date_str: str, stocks: list[dict]) -> int:
    """存储龙虎榜汇总，返回写入行数"""
    if not stocks:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    rows = [(date_str, s["stock_code"], s["stock_name"], s["reason"],
             s["close"], s["change_pct"], s["turnover_pct"],
             s["net_buy_wan"], s["buy_wan"], s["sell_wan"])
            for s in stocks]
    psycopg2.extras.execute_batch(cur, _LIST_UPSERT, rows)
    conn.commit()
    conn.close()
    logging.info(f"Saved {len(rows)} dragon tiger stocks for {date_str}")
    return len(rows)
```

- [ ] **Step 3: 测试：只拉不存验证 fetch_daily_list()**

```bash
cd backend && source venv/bin/activate && python -c "
from scripts.sync_dragon_tiger import fetch_daily_list
stocks = fetch_daily_list('2026-05-30')
print(f'Fetched {len(stocks)} stocks')
if stocks:
    print(stocks[0])
"
```

预期: 输出最近交易日龙虎榜数据（非交易日可能为空）

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/sync_dragon_tiger.py
git commit -m "feat: add daily dragon tiger list fetch + upsert

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 实现个股席位明细抓取 + 存储

**文件：**
- 修改: `backend/scripts/sync_dragon_tiger.py`

- [ ] **Step 1: 添加 fetch_seats() 函数**

在 `fetch_daily_list()` 之后追加：

```python
def fetch_seats(stock_code: str, date_str: str, seat_type: str) -> list[dict]:
    """
    拉取单只股票龙虎榜买卖席位明细。
    seat_type: 'buy' → RPT_BILLBOARD_DAILYDETAILSBUY
               'sell' → RPT_BILLBOARD_DAILYDETAILSSELL
    返回 TOP5 席位列表
    """
    report_map = {
        "buy": "RPT_BILLBOARD_DAILYDETAILSBUY",
        "sell": "RPT_BILLBOARD_DAILYDETAILSSELL",
    }
    report_name = report_map.get(seat_type)
    if not report_name:
        return []

    sort_col = "BUY" if seat_type == "buy" else "SELL"
    filter_str = f"(TRADE_DATE='{date_str}')(SECURITY_CODE=\"{stock_code}\")"
    data = eastmoney_datacenter(
        report_name,
        filter_str=filter_str,
        page_size=10,
        sort_columns=sort_col,
        sort_types="-1",
    )

    seats = []
    for i, row in enumerate(data[:5]):
        seat_code = str(row.get("OPERATEDEPT_CODE", ""))
        seats.append({
            "stock_code": stock_code,
            "seat_type": seat_type,
            "rank": i + 1,
            "seat_name": row.get("OPERATEDEPT_NAME", ""),
            "seat_code": seat_code,
            "buy_amt_wan": round((row.get("BUY") or 0) / 10000, 1),
            "sell_amt_wan": round((row.get("SELL") or 0) / 10000, 1),
            "net_amt_wan": round((row.get("NET") or 0) / 10000, 1),
            "is_institution": seat_code == "0",
        })
    return seats
```

- [ ] **Step 2: 添加 save_seats() 函数**

在 `save_daily_list()` 之后追加：

```python
_SEATS_UPSERT = """
INSERT INTO daily_dragon_tiger_seats
    (trade_date, stock_code, seat_type, rank, seat_name, seat_code,
     buy_amt_wan, sell_amt_wan, net_amt_wan, is_institution)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (trade_date, stock_code, seat_type, rank) DO UPDATE SET
    seat_name     = EXCLUDED.seat_name,
    seat_code     = EXCLUDED.seat_code,
    buy_amt_wan   = EXCLUDED.buy_amt_wan,
    sell_amt_wan  = EXCLUDED.sell_amt_wan,
    net_amt_wan   = EXCLUDED.net_amt_wan,
    is_institution = EXCLUDED.is_institution
"""

def save_seats(date_str: str, seats: list[dict]) -> int:
    """存储席位明细，返回写入行数"""
    if not seats:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    rows = [(date_str, s["stock_code"], s["seat_type"], s["rank"],
             s["seat_name"], s["seat_code"],
             s["buy_amt_wan"], s["sell_amt_wan"], s["net_amt_wan"],
             s["is_institution"])
            for s in seats]
    psycopg2.extras.execute_batch(cur, _SEATS_UPSERT, rows)
    conn.commit()
    conn.close()
    return len(rows)
```

- [ ] **Step 3: 测试单只股票席位抓取**

```bash
cd backend && source venv/bin/activate && python -c "
from scripts.sync_dragon_tiger import fetch_seats
buy = fetch_seats('002475', '2026-05-30', 'buy')
sell = fetch_seats('002475', '2026-05-30', 'sell')
print(f'Buy seats: {len(buy)}, Sell seats: {len(sell)}')
if buy:
    print(buy[0])
"
```

预期: 输出买卖席位（如果该日期该股票确实上榜）

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/sync_dragon_tiger.py
git commit -m "feat: add dragon tiger seat details fetch + upsert

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: 实现 sync() 编排 + summary + CLI main()

**文件：**
- 修改: `backend/scripts/sync_dragon_tiger.py`

- [ ] **Step 1: 添加 sync() 编排函数 + 摘要输出**

在存储函数之后追加：

```python
# ═════════════════════════════════════════════════════════════════════════
# 编排
# ═════════════════════════════════════════════════════════════════════════

def sync(date_str: str, dry_run: bool = False) -> dict:
    """拉取 + 存储当日全市场龙虎榜数据。best-effort per stock。"""
    result = {
        "date": date_str,
        "list_count": 0,
        "seats_count": 0,
        "errors": [],
    }

    # 1. 全市场上榜汇总
    stocks = fetch_daily_list(date_str)
    if not stocks:
        logging.info(f"No dragon tiger data for {date_str}")
        return result

    if not dry_run:
        n = save_daily_list(date_str, stocks)
        result["list_count"] = n
    else:
        result["list_count"] = len(stocks)

    # 2. 逐只股票拉席位明细
    total_seats = 0
    for i, stock in enumerate(stocks):
        code = stock["stock_code"]
        name = stock["stock_name"]
        try:
            buy_seats = fetch_seats(code, date_str, "buy")
            sell_seats = fetch_seats(code, date_str, "sell")
            all_seats = buy_seats + sell_seats
            if not dry_run and all_seats:
                save_seats(date_str, all_seats)
            total_seats += len(all_seats)
            if (i + 1) % 20 == 0 or i == 0:
                logging.info(f"  [{i+1}/{len(stocks)}] {code} {name}: "
                           f"buy={len(buy_seats)} sell={len(sell_seats)}")
        except Exception as e:
            msg = f"{code} {name}: {e}"
            result["errors"].append(msg)
            logging.warning(f"  [{i+1}/{len(stocks)}] {msg}")

    result["seats_count"] = total_seats
    logging.info(f"Seats total: {total_seats} records, {len(result['errors'])} errors")

    # 3. 摘要
    _print_summary(date_str, stocks, result["errors"])

    return result


def _print_summary(date_str: str, stocks: list[dict], errors: list[str]):
    """打印龙虎榜摘要"""
    print()
    print("=" * 60)
    print(f"  龙虎榜 {date_str} — 共 {len(stocks)} 只上榜")
    print("=" * 60)

    # 净买入 TOP10
    print("\n📈 净买入 TOP10:")
    top_buy = sorted(stocks, key=lambda s: s["net_buy_wan"], reverse=True)[:10]
    for s in top_buy:
        print(f"  {s['stock_code']} {s['stock_name']:<8s} "
              f"净买{s['net_buy_wan']:>8.0f}万  涨跌{s['change_pct']:>+5.1f}%  "
              f"{s['reason']}")

    # 净卖出 TOP5
    print("\n📉 净卖出 TOP5:")
    top_sell = sorted(stocks, key=lambda s: s["net_buy_wan"])[:5]
    for s in top_sell:
        print(f"  {s['stock_code']} {s['stock_name']:<8s} "
              f"净买{s['net_buy_wan']:>8.0f}万  涨跌{s['change_pct']:>+5.1f}%  "
              f"{s['reason']}")

    # 上榜原因分布
    from collections import Counter
    reasons = Counter(s["reason"] for s in stocks)
    print("\n🏷️  上榜原因分布:")
    for reason, cnt in reasons.most_common():
        print(f"  {reason}: {cnt} 只")

    if errors:
        print(f"\n⚠️  席位明细采集失败 {len(errors)} 只")
    print("=" * 60)
```

- [ ] **Step 2: 添加 CLI main() 入口**

在文件末尾添加：

```python
# ═════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="龙虎榜每日数据采集")
    parser.add_argument("--date", default=None,
                        help="交易日期 YYYY-MM-DD（默认: 今天）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只拉取不写入数据库")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    date_str = args.date or date.today().strftime("%Y-%m-%d")

    # 建表（幂等）
    ensure_tables()

    if args.dry_run:
        logging.info(f"DRY RUN mode — fetching {date_str} without writing")

    result = sync(date_str, dry_run=args.dry_run)

    if result["list_count"] == 0 and not result["errors"]:
        logging.info(f"{date_str} 无龙虎榜数据（非交易日或数据未发布）")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 端到端 dry-run 测试**

```bash
cd backend && source venv/bin/activate && python scripts/sync_dragon_tiger.py --date 2026-05-30 --dry-run
```

预期: 输出龙虎榜摘要（如果 5/30 有数据），包括净买入 TOP10、上榜原因分布

- [ ] **Step 4: 端到端写入测试**

```bash
cd backend && source venv/bin/activate && python scripts/sync_dragon_tiger.py --date 2026-05-30
```

预期: 数据写入 PostgreSQL，然后验证：

```bash
cd backend && source venv/bin/activate && python -c "
from scripts.sync_dragon_tiger import get_conn
conn = get_conn()
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM daily_dragon_tiger WHERE trade_date='2026-05-30'\")
print(f'汇总: {cur.fetchone()[0]} 条')
cur.execute(\"SELECT COUNT(*) FROM daily_dragon_tiger_seats WHERE trade_date='2026-05-30'\")
print(f'席位: {cur.fetchone()[0]} 条')
conn.close()
"
```

- [ ] **Step 5: 幂等性验证 — 重复执行不报错不重复**

```bash
cd backend && source venv/bin/activate && python scripts/sync_dragon_tiger.py --date 2026-05-30
```

预期: 正常完成，无 UNIQUE 冲突报错

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/sync_dragon_tiger.py
git commit -m "feat: add sync() orchestrator, summary output and CLI main

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: 最终验证

- [ ] **Step 1: 全程测试 — dry-run + 写入 + 幂等**

```bash
cd backend && source venv/bin/activate && \
  python scripts/sync_dragon_tiger.py --date 2026-05-30 --dry-run && \
  python scripts/sync_dragon_tiger.py --date 2026-05-30
```

预期: 两次都正常完成，摘要正确

- [ ] **Step 2: 检查数据库数据正确性**

```bash
cd backend && source venv/bin/activate && python -c "
from scripts.sync_dragon_tiger import get_conn
conn = get_conn()
cur = conn.cursor()

# 上榜股票数
cur.execute(\"SELECT COUNT(DISTINCT stock_code) FROM daily_dragon_tiger WHERE trade_date='2026-05-30'\")
print(f'上榜股票: {cur.fetchone()[0]}')

# 净买入 TOP3
cur.execute('''
    SELECT stock_code, stock_name, net_buy_wan, reason
    FROM daily_dragon_tiger WHERE trade_date='2026-05-30'
    ORDER BY net_buy_wan DESC LIMIT 3
''')
for row in cur.fetchall():
    print(f'  {row[0]} {row[1]}: {row[2]}万 ({row[3]})')

# 席位明细覆盖率
cur.execute(\"SELECT COUNT(DISTINCT stock_code) FROM daily_dragon_tiger_seats WHERE trade_date='2026-05-30'\")
print(f'有席位明细的股票: {cur.fetchone()[0]}')

# 机构席位数量
cur.execute(\"SELECT COUNT(*) FROM daily_dragon_tiger_seats WHERE trade_date='2026-05-30' AND is_institution=TRUE\")
print(f'机构席位: {cur.fetchone()[0]}')

conn.close()
"
```

- [ ] **Step 3: 最终 commit（如有文档更新）**
