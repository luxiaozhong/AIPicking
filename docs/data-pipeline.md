# Data Pipeline — 历史数据采集管线

回测功能依赖的**全部历史数据**由 `backend/scripts/` 下的定时任务采集，部署于服务器 `101.35.254.125` 的 crontab。

## 管线总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Crontab (服务器)                              │
│                                                                     │
│  17:00 ── update_daily.py      ──► daily (日线 + 市值)               │
│  17:00 ── sync_dragon_tiger.py ──► daily_dragon_tiger                │
│                                    daily_dragon_tiger_seats          │
│  18:30 ── sync_market_data.py  ──► daily_hot_stocks                  │
│                                    daily_hot_themes                  │
│                                    daily_northbound_flow             │
│                                    daily_sector_flow                 │
│                                                                     │
│  (未配置 cron，仅手动)                                               │
│         sync_valuation.py      ──► daily_valuation（没有必要，可通过计算）  │
│         sync_financials.py     ──► financial_reports  （每季度一次， 手动做）     │
└─────────────────────────────────────────────────────────────────────┘
```

## Crontab 配置（服务器上）

```cron
# A 股日线 + 市值更新（每个工作日 17:00）
0 17 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/update_daily.py >> /var/log/aipicking/update_daily.log 2>&1

# 龙虎榜每日采集（每个工作日 17:00）
0 17 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_dragon_tiger.py >> /var/log/aipicking/ingest.log 2>&1

# A 股每日信号同步 — 同花顺热点 + 北向资金 + 东财板块（每个工作日 18:30）
30 18 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_market_data.py >> /var/log/aipicking/ingest.log 2>&1
```

## 三个核心 Job 详解

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

## 日志查看

```bash
# 登录服务器
ssh root@101.35.254.125

# 实时跟踪
tail -f /var/log/aipicking/update_daily.log     # 日线更新
tail -f /var/log/aipicking/ingest.log           # 龙虎榜 + 市场信号

# 查看最近 N 行
tail -100 /var/log/aipicking/ingest.log

# 查看 cron 执行记录
grep CRON /var/log/syslog | grep aipicking
```

## 手动执行

```bash
# 在服务器上
cd /opt/AIpicking/backend

# 日线更新（智能模式）
venv/bin/python scripts/update_daily.py

# 龙虎榜
venv/bin/python scripts/sync_dragon_tiger.py                  # 今天
venv/bin/python scripts/sync_dragon_tiger.py --date 2026-05-30

# 市场信号
venv/bin/python scripts/sync_market_data.py                   # 今天
venv/bin/python scripts/sync_market_data.py --date 2026-05-29

# 估值数据（未配置 cron，按需手动跑）
venv/bin/python scripts/sync_valuation.py                     # 增量
venv/bin/python scripts/sync_valuation.py --init              # 全量 365 天

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

- **`sync_valuation.py` 和 `sync_financials.py` 未配置 cron**：脚本已开发完成，但未加入 crontab。`sync_valuation.py` 在文档中标注 cron 为 `30 17 * * 1-5`，`sync_financials.py` 标注为 `0 3 2 5,9,11 * *`（每季度财报季后）。如需启用，手动加入 crontab 即可。
