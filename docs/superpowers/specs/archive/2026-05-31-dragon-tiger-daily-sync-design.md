# 龙虎榜每日采集脚本设计

> 日期: 2026-05-31 | 状态: draft

## 概述

新建 `sync_dragon_tiger.py` 脚本，每个交易日盘后自动抓取全市场龙虎榜数据（上榜汇总 + 买卖席位明细），
存入 PostgreSQL。

## 数据源

东财 datacenter API，复用项目已有的 `em_get()` 节流机制：

| 报表名 | 用途 | 调用频率 |
|--------|------|---------|
| `RPT_DAILYBILLBOARD_DETAILSNEW` | 全市场每日上榜汇总 | 1 次/天 |
| `RPT_BILLBOARD_DAILYDETAILSBUY` | 单只股票买入席位 TOP5 | N 次/天 |
| `RPT_BILLBOARD_DAILYDETAILSSELL` | 单只股票卖出席位 TOP5 | N 次/天 |

## 数据库表

全部建在 PostgreSQL（项目已从 SQLite 迁移到 PG，不再使用 stock_db.sqlite）。

### daily_dragon_tiger

| 列 | 类型 | 说明 |
|----|------|------|
| id | SERIAL PK | |
| trade_date | TEXT(10) NOT NULL | YYYY-MM-DD |
| stock_code | TEXT(20) NOT NULL | 6 位代码 |
| stock_name | TEXT(100) | 股票简称 |
| reason | TEXT(200) | 上榜原因 |
| close | REAL | 收盘价 |
| change_pct | REAL | 涨跌幅 % |
| turnover_pct | REAL | 换手率 % |
| net_buy_wan | REAL | 净买入（万元） |
| buy_wan | REAL | 买入总额（万元） |
| sell_wan | REAL | 卖出总额（万元） |
| created_at | TIMESTAMPTZ | DEFAULT now() |

UNIQUE: `(trade_date, stock_code)`

### daily_dragon_tiger_seats

| 列 | 类型 | 说明 |
|----|------|------|
| id | SERIAL PK | |
| trade_date | TEXT(10) NOT NULL | YYYY-MM-DD |
| stock_code | TEXT(20) NOT NULL | 6 位代码 |
| seat_type | TEXT(4) NOT NULL | buy / sell |
| rank | INTEGER NOT NULL | 排名 1-5 |
| seat_name | TEXT(100) | 营业部名称 |
| seat_code | TEXT(20) | "0" = 机构专用 |
| buy_amt_wan | REAL | 买入（万元） |
| sell_amt_wan | REAL | 卖出（万元） |
| net_amt_wan | REAL | 净买入（万元） |
| is_institution | BOOLEAN | seat_code == "0" |

UNIQUE: `(trade_date, stock_code, seat_type, rank)`

## 脚本结构

### 文件位置

`backend/scripts/sync_dragon_tiger.py`

### CLI

```bash
venv/bin/python scripts/sync_dragon_tiger.py                    # 今天
venv/bin/python scripts/sync_dragon_tiger.py --date 2026-05-30  # 指定日期
venv/bin/python scripts/sync_dragon_tiger.py --date 2026-05-30 --dry-run  # 只拉不存
```

### 核心流程

```
sync(date)
  │
  ├─ 1. fetch_daily_list(date)       → 全市场上榜汇总
  │      eastmoney_datacenter("RPT_DAILYBILLBOARD_DETAILSNEW", ...)
  │
  ├─ 2. save_daily_list(rows)        → INSERT ... ON CONFLICT UPDATE
  │
  ├─ 3. for each stock:
  │      fetch_seats(code, date, 'buy')   → 买入 TOP5
  │      fetch_seats(code, date, 'sell')  → 卖出 TOP5
  │      save_seats(buy_seats + sell_seats)
  │      em_get 自动节流 ≥1s
  │
  └─ 4. print summary
```

### 错误处理

Best-effort per stock：单只股票席位拉取失败记为 warning，继续下一只。
无数据（非交易日/数据未发布）正常退出。

### 幂等性

所有写入使用 `INSERT ... ON CONFLICT DO UPDATE`，可安全重复执行。

### 调度

Cron: `0 17 * * 1-5`（每个交易日收盘后 17:00 北京时）

## 模型层

在 `backend/app/models/stock_tables.py` 新增两个 SQLAlchemy 模型：

- `DailyDragonTiger` → `daily_dragon_tiger`
- `DailyDragonTigerSeat` → `daily_dragon_tiger_seats`

## 不做什么

- 不提供前端展示页面（本期只做数据采集）
- 不集成到 `sync_market_data.py`（职责独立）
- 不修改 `sync_market_data.py` 的 SQLite → PG（另案处理）
