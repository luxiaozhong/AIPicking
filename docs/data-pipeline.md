# Data Pipeline — 历史数据采集管线

回测功能依赖的**全部历史数据**由 `backend/scripts/` 下的定时任务采集，部署于服务器 `101.35.254.125` 的 crontab。

## 管线总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Crontab (服务器)                                  │
│                                                                     │
│  11:30 ── sync_stock_fund_flow.py  ──► daily_stock_fund_flow        │
│            (预同步，盘后覆盖)                                         │
│                                                                     │
│  14:15 ── sync_stock_fund_flow.py  ──► daily_stock_fund_flow        │
│            (预同步，盘后覆盖)                                         │
│                                                                     │
│  16:15 ── sync_all.py                                              │
│            │                                                        │
│            ├─ 1. update_daily.py        ──► daily (日线)             │
│            ├─ 2. update_index_daily.py  ──► daily (指数日线)         │
│            ├─ 3. sync_dragon_tiger.py   ──► daily_dragon_tiger       │
│            │                                daily_dragon_tiger_seats │
│            ├─ 4. sync_valuation.py      ──► daily_valuation          │
│            ├─ 5. sync_market_data.py    ──► daily_hot_stocks         │
│            │                                daily_hot_themes         │
│            │                                daily_northbound_flow    │
│            │                                daily_sector_flow        │
│            ├─ 6. sync_stock_fund_flow.py───► daily_stock_fund_flow   │
│            │                                (覆盖盘中预同步数据)       │
│            ├─ 7. sync_market_temperature.py──► daily_market_temperature │
│            └─ 8. sync_report.py         ──► 数据同步日报（通知）      │
│                                                                     │
│  (未配置 cron，仅手动)                                               │
│         sync_financials.py       ──► financial_reports（每季度一次）  │
└─────────────────────────────────────────────────────────────────────┘
```

## Crontab 配置（服务器上）

```cron
# === 盘后总调度（每个工作日 17:30）===
30 17 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_all.py >> /var/log/aipicking/sync_all.log 2>&1

# === 个股资金流盘中预同步（幂等，盘后 sync_all.py 会覆盖为最终数据）===
30 11 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_stock_fund_flow.py --date $(date +\%Y-\%m-\%d) >> /var/log/aipicking/ingest.log 2>&1
15 14 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_stock_fund_flow.py --date $(date +\%Y-\%m-\%d) >> /var/log/aipicking/ingest.log 2>&1

# === 盘中板块同步（每30分钟）===
35,5 9-11 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_market_data.py --intraday >> /var/log/aipicking/ingest.log 2>&1
5,35 13-14 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_market_data.py --intraday >> /var/log/aipicking/ingest.log 2>&1
55 14 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_market_data.py --intraday >> /var/log/aipicking/ingest.log 2>&1

# === 盘中个股日线更新（每30分钟，腾讯实时行情 qt.gtimg.cn，比板块同步晚2分钟）===
37,7 9-11 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/update_daily.py --intraday >> /var/log/aipicking/update_daily.log 2>&1
7,37 13-14 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/update_daily.py --intraday >> /var/log/aipicking/update_daily.log 2>&1
57 14 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/update_daily.py --intraday >> /var/log/aipicking/update_daily.log 2>&1

# === 盘中指数日线更新（每30分钟，比个股日线晚1分钟）===
38,8 9-11 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/update_index_daily.py --intraday >> /var/log/aipicking/update_daily.log 2>&1
8,38 13-14 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/update_index_daily.py --intraday >> /var/log/aipicking/update_daily.log 2>&1
58 14 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/update_index_daily.py --intraday >> /var/log/aipicking/update_daily.log 2>&1

# === 盘后回测（工作日 17:45）===
45 17 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python TmpScriptsBackTest/run_daily_backtests.py -q >> /var/log/aipicking/daily_backtest.log 2>&1

# === 龙虎榜早上回补（每天 8:30，含周六，覆盖周五漏掉的数据）===
30 8 * * * cd /opt/AIpicking/backend && venv/bin/python scripts/sync_dragon_tiger.py --date $(date -d "yesterday" +\%Y-\%m-\%d) >> /var/log/aipicking/ingest.log 2>&1
```

`sync_all.py` 内部按依赖顺序串行执行 8 个脚本，任意一步失败不会阻断后续任务，最终打印成功/失败汇总。

### 盘中更新说明

- **板块资金流** (`sync_market_data.py --intraday`)：每 30 分钟拉取东财板块排名+资金流，轻量模式
- **个股日线** (`update_daily.py --intraday`)：每 30 分钟拉取腾讯实时行情 (`qt.gtimg.cn`)，~5200 只 A 股，约 2-3 分钟完成
- **指数日线** (`update_index_daily.py --intraday`)：每 30 分钟拉取 5 大指数实时行情，秒级完成
- 三层任务错开 1-2 分钟执行，避免同时抢占网络/数据库资源

## 所有 Job 详解

### 1. `update_daily.py` — 日线数据

| 维度 | 详情 |
|------|------|
| **执行时间** | 每个工作日 17:00（收盘后 2 小时） |
| **数据库** | PostgreSQL |
| **写入表** | `daily`（日线 OHLCV + adj_close） |
| **数据源** | 腾讯财经 K 线 API（不封 IP） |
| **注意** | 市值数据已迁移至 `daily_valuation` 表（由 `sync_valuation.py` 同步） |
| **日志** | `/var/log/aipicking/update_daily.log` |
| **幂等性** | `ON CONFLICT (ts_code, trade_date) DO UPDATE` |

**运行模式：**
- **默认（智能）**：盘中自动用实时接口，盘后用历史日线接口；同时补齐昨天若有缺
- `--date YYYY-MM-DD`：指定某天
- `--date today`：今天，自动判断盘中/盘后
- `--intraday`：强制盘中实时模式
- `--force`：强制补最近 5 天

### 2. `sync_dragon_tiger.py` — 龙虎榜数据

| 维度 | 详情 |
|------|------|
| **执行时间** | 每个工作日 17:00 |
| **数据库** | PostgreSQL |
| **写入表** | `daily_dragon_tiger`（全市场汇总）、`daily_dragon_tiger_seats`（买卖席位明细） |
| **数据源** | 东财 datacenter-web API，内置 `em_get` 节流防封 |
| **日志** | `/var/log/aipicking/ingest.log`（与 sync_market_data 共用） |
| **幂等性** | `ON CONFLICT (trade_date, stock_code)` / `(trade_date, stock_code, seat_type, rank)` |

### 3. `sync_market_data.py` — 市场信号数据

| 维度 | 详情 |
|------|------|
| **执行时间** | 每个工作日 18:30（收盘后 3.5 小时，等数据发布） |
| **数据库** | PostgreSQL |
| **写入表** | `daily_hot_stocks`、`daily_hot_themes`、`daily_northbound_flow`、`daily_sector_flow` |
| **数据源** | 同花顺热点（零鉴权）、北向资金 EOD 累计、东财板块排名+资金流 |
| **日志** | `/var/log/aipicking/ingest.log` |
| **幂等性** | `ON CONFLICT (trade_date, stock_code)` / `(trade_date)` / `(trade_date, sector_type, sector_code)` |

### 4. `update_index_daily.py` — 指数日线

| 维度 | 详情 |
|------|------|
| **执行时间** | 每个工作日 17:05 |
| **数据库** | PostgreSQL |
| **写入表** | `daily`（指数日线数据，ts_code 以 `.IDX` 结尾） |
| **数据源** | 腾讯财经 K 线 API |
| **日志** | `/var/log/aipicking/update_daily.log` |
| **幂等性** | `ON CONFLICT (ts_code, trade_date) DO UPDATE` |

### 5. `sync_valuation.py` — 估值数据（PE/PB）

| 维度 | 详情 |
|------|------|
| **执行时间** | 每个工作日 17:12 |
| **数据库** | PostgreSQL |
| **写入表** | `daily_valuation`（pe_ttm、pe_static、pb、market_cap、circ_market_cap、dividend_yield） |
| **数据源** | 腾讯财经 API（字段 39=PE(TTM)、52=PE(静)、46=PB、44=总市值、45=流通市值） |
| **日志** | `/var/log/aipicking/ingest.log` |
| **幂等性** | `ON CONFLICT (ts_code, trade_date) DO UPDATE` |
| **前端使用** | K 线图弹窗 PB/PE 信息栏调用 `/api/v1/valuation/{ts_code}` |

**运行模式：**
- **默认**：增量拉取最新交易日
- `--init`：全量最近 365 天
- `--date YYYY-MM-DD`：指定某天

### 6. `sync_report.py` — 数据同步日报

| 维度 | 详情 |
|------|------|
| **执行时间** | 每个工作日 19:00 |
| **数据源** | 汇总各同步脚本的执行结果 |
| **日志** | `/var/log/aipicking/report.log` |
| **用途** | 生成每日数据同步状态报告，便于排查数据缺失 |

## 日志查看

```bash
# 登录服务器
ssh root@101.35.254.125

# 总调度日志（sync_all.py 输出）
tail -f /var/log/aipicking/sync_all.log

# 查看 cron 执行记录
grep CRON /var/log/syslog | grep aipicking
```

## 手动执行

```bash
# 在服务器上
cd /opt/AIpicking/backend

# 一键执行全部同步（推荐）
venv/bin/python scripts/sync_all.py                           # 默认日期
venv/bin/python scripts/sync_all.py --date 2026-06-04         # 指定日期
venv/bin/python scripts/sync_all.py --dry-run                 # 仅预览
venv/bin/python scripts/sync_all.py --skip valuation report   # 跳过某些任务

# 单独执行某个脚本
venv/bin/python scripts/update_daily.py                       # 日线更新
venv/bin/python scripts/sync_dragon_tiger.py                  # 龙虎榜
venv/bin/python scripts/sync_valuation.py                     # 估值（增量）
venv/bin/python scripts/sync_valuation.py --init              # 估值（全量 365 天）

# 财报数据（未配置 cron，按需手动跑）
venv/bin/python scripts/sync_financials.py                    # 增量
venv/bin/python scripts/sync_financials.py --init             # 全量近 5 年
```

## 与回测引擎的关系

回测引擎通过 `REQUIRED_DATA` 机制按需加载这些数据（详见 [backtest-engine.md](backtest-engine.md)）：

| REQUIRED_DATA 值 | 加载的表 | 对应的采集脚本 |
|-------------------|---------|---------------|
| `[]`（默认） | `stocks` + `daily` | `update_daily.py` |
| `"sector_flow"` | `daily_sector_flow` | `sync_market_data.py` |
| `"dragon_tiger"` | `daily_dragon_tiger`、`daily_dragon_tiger_seats` | `sync_dragon_tiger.py` |
| `"hot_stocks"` | `daily_hot_stocks` | `sync_market_data.py` |
| `"hot_themes"` | `daily_hot_themes` | `sync_market_data.py` |

> `hot_stocks` 和 `hot_themes` 当前在因子库中没有使用，但数据已采集，可供未来扩展。

## 已知问题

- **`sync_financials.py` 未配置 cron**：财报数据仅支持手动执行。Quarterly 报表发布后可手动跑一次。如需自动化，cron 建议 `0 3 2 5,9,11 * *`（每季度财报季后）。

## 维护记录

| 日期 | 变更 |
|------|------|
| 2026-06-15 | 新增 11:30 / 14:15 两档个股资金流盘中预同步（幂等写入，盘后 sync_all 覆盖为最终数据） |
| 2026-06-05 | 所有同步任务整合为 `sync_all.py` 总调度，cron 简化为一条（17:00） |
| 2026-06-05 | `sync_valuation.py` 加入 cron，补充 `update_index_daily.py` 和 `sync_report.py` 文档 |
