# Data Pipeline — 历史数据采集管线

回测功能依赖的**全部历史数据**由 `backend/scripts/` 下的定时任务采集，部署于服务器 `101.35.254.125` 的 crontab。

## 管线总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Crontab (服务器) — 仅一条                          │
│                                                                     │
│  16:15 ── sync_all.py                                              │
│            │                                                        │
│            ├─ 1. update_daily.py        ──► daily (日线 + 市值)      │
│            ├─ 2. update_index_daily.py  ──► daily (指数日线)         │
│            ├─ 3. sync_dragon_tiger.py   ──► daily_dragon_tiger       │
│            │                                daily_dragon_tiger_seats │
│            ├─ 4. sync_valuation.py      ──► daily_valuation          │
│            ├─ 5. sync_market_data.py    ──► daily_hot_stocks         │
│            │                                daily_hot_themes         │
│            │                                daily_northbound_flow    │
│            │                                daily_sector_flow        │
│            └─ 6. sync_report.py         ──► 数据同步日报（通知）      │
│                                                                     │
│  (未配置 cron，仅手动)                                               │
│         sync_financials.py       ──► financial_reports（每季度一次）  │
└─────────────────────────────────────────────────────────────────────┘
```

## Crontab 配置（服务器上）

所有同步任务由 `sync_all.py` 统一调度，cron 只需一条：

```cron
# AIpicking 每日数据同步总调度（每个工作日 16:15）
15 16 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_all.py >> /var/log/aipicking/sync_all.log 2>&1
```

`sync_all.py` 内部按依赖顺序串行执行 6 个脚本，任意一步失败不会阻断后续任务，最终打印成功/失败汇总。

## 所有 Job 详解

### 1. `update_daily.py` — 日线数据 + 市值

| 维度 | 详情 |
|------|------|
| **执行时间** | 每个工作日 17:00（收盘后 2 小时） |
| **数据库** | PostgreSQL |
| **写入表** | `daily`（日线 OHLCV + adj_close + market_cap + circ_market_cap） |
| **数据源** | 腾讯财经 K 线 API（不封 IP） |
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
| 2026-06-05 | 所有同步任务整合为 `sync_all.py` 总调度，cron 简化为一条（17:00） |
| 2026-06-05 | `sync_valuation.py` 加入 cron，补充 `update_index_daily.py` 和 `sync_report.py` 文档 |
