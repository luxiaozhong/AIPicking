# Data Pipeline — 历史数据采集管线

回测功能依赖的**全部历史数据**由 `backend/scripts/` 下的定时任务采集，部署于服务器 `101.35.254.125` 的 crontab。

## 管线总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Crontab（每工作日）                                 │
│                                                                     │
│   8:30 ──── sync_dragon_tiger.py   ──► 龙虎榜（次日补前一日）        │
│                                                                     │
│   9:00 ── sync_northbound.py     ──► daily_northbound_flow          │
│           （独立 cron，提前同步北向资金）                              │
│                                                                     │
│  9:30~11:30 ── sync_intraday_daily.sh   ──► daily（指数成分股日线）  │
│  13:00~15:00    每5分钟，交易时段内                                   │
│                │  1. update_index_daily.py --intraday                │
│                └─ 2. update_daily.py --intraday --index <idx>        │
│                                                                     │
│  9:30~11:30 ── sync_intraday_fund_flow.sh ──► daily_stock_fund_flow │
│  13:00~15:00    每3分钟，交易时段内                      +            │
│                │  1. sync_index_fund_flow.py --index <idx>           │
│                └─ 2. sync_index_fund_flow.py --self <indices>        │
│                                              intraday_fund_snapshot  │
│                                                                     │
│  17:00 ─── sync_all.py（盘后全量兜底）                                │
│            │                                                        │
│            ├─ 1. update_daily.py        ──► daily (日线，全市场)      │
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

## Crontab 配置

### 本地开发机（macOS）

```cron
# === 龙虎榜早上回补（每天 8:30，工作日）===
30 8 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && venv/bin/python scripts/sync_dragon_tiger.py --date $(date -v-1d +\%Y-\%m-\%d) >> /Users/aklu/CodeBuddy/AIpicking/logs/ingest.log 2>&1

# === 北向资金独立同步（每个交易日 9:00）===
0 9 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && venv/bin/python scripts/sync_northbound.py >> /Users/aklu/CodeBuddy/AIpicking/logs/northbound.log 2>&1

# === 盘中指数成分股日线同步（每5分钟，交易时段 9:30-11:30 / 13:00-15:00）===
# 内部依次：指数日线 → 980080 → 900001 → 900002 → 399667，sleep 30s/60s
# 上午（9:30-11:30）— 共 25 次
30-59/5 9 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && bash scripts/sync_intraday_daily.sh >> /Users/aklu/CodeBuddy/AIpicking/logs/update_daily_intraday.log 2>&1
*/5 10 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && bash scripts/sync_intraday_daily.sh >> /Users/aklu/CodeBuddy/AIpicking/logs/update_daily_intraday.log 2>&1
0-30/5 11 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && bash scripts/sync_intraday_daily.sh >> /Users/aklu/CodeBuddy/AIpicking/logs/update_daily_intraday.log 2>&1
# 下午（13:00-15:00）— 共 25 次
*/5 13 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && bash scripts/sync_intraday_daily.sh >> /Users/aklu/CodeBuddy/AIpicking/logs/update_daily_intraday.log 2>&1
*/5 14 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && bash scripts/sync_intraday_daily.sh >> /Users/aklu/CodeBuddy/AIpicking/logs/update_daily_intraday.log 2>&1
0 15 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && bash scripts/sync_intraday_daily.sh >> /Users/aklu/CodeBuddy/AIpicking/logs/update_daily_intraday.log 2>&1

# === 盘中指数成分股资金流同步（每3分钟，交易时段 9:30-11:30 / 13:00-15:00）===
# 内部依次：成分股批量 → 市场指数自身资金流，间隔 10s
# 上午（9:30-11:30）— 共 41 次
30-57/3 9 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && bash scripts/sync_intraday_fund_flow.sh >> /Users/aklu/CodeBuddy/AIpicking/logs/index_fund_flow.log 2>&1
*/3 10 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && bash scripts/sync_intraday_fund_flow.sh >> /Users/aklu/CodeBuddy/AIpicking/logs/index_fund_flow.log 2>&1
0-30/3 11 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && bash scripts/sync_intraday_fund_flow.sh >> /Users/aklu/CodeBuddy/AIpicking/logs/index_fund_flow.log 2>&1
# 下午（13:00-15:00）— 共 41 次
*/3 13 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && bash scripts/sync_intraday_fund_flow.sh >> /Users/aklu/CodeBuddy/AIpicking/logs/index_fund_flow.log 2>&1
*/3 14 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && bash scripts/sync_intraday_fund_flow.sh >> /Users/aklu/CodeBuddy/AIpicking/logs/index_fund_flow.log 2>&1
0 15 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && bash scripts/sync_intraday_fund_flow.sh >> /Users/aklu/CodeBuddy/AIpicking/logs/index_fund_flow.log 2>&1

# === 盘后总调度（每个工作日 16:13）===
13 16 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && venv/bin/python scripts/sync_all.py >> /Users/aklu/CodeBuddy/AIpicking/logs/sync_all.log 2>&1
```

### 服务器（Linux，`101.35.254.125`）

> 注意：服务器 GitHub 网络不通，更新需通过本地 git push → 服务器手动 pull。
> 详见 [deployment.md](deployment.md)。

```cron
# === 龙虎榜早上回补 ===
30 8 * * * cd /opt/AIpicking/backend && venv/bin/python scripts/sync_dragon_tiger.py --date $(date -d "yesterday" +\%Y-\%m-\%d) >> /var/log/aipicking/ingest.log 2>&1

# === 盘后总调度（每个工作日 17:00）===
0 17 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_all.py >> /var/log/aipicking/sync_all.log 2>&1
```

### 盘中更新架构

盘中不再全量拉取 ~5200 只 A 股，改为**按指数过滤**：只更新关注指数的成分股（默认 980080 国证成长100 + 900001 主力资金50 + 900002 大盘低波50 + 399667 创业大盘，共约 200 只），秒级完成。

两个 wrapper 脚本负责盘中调度，cron 只在交易时段（9:30-11:30 / 13:00-15:00）触发：

| Wrapper | 频率 | 执行顺序 | 间隔 | 日志 |
|---------|------|---------|------|------|
| `sync_intraday_daily.sh` | 每 5 分钟 | 指数日线 → 980080 → 900001 → 900002 → 399667 | 30s / 60s | `update_daily_intraday.log` |
| `sync_intraday_fund_flow.sh` | 每 3 分钟 | 成分股批量（4 指数）→ 市场指数自身资金流（14 指数） | 10s | `index_fund_flow.log` |

设计要点：
- **交易时段对齐**：cron 精确匹配 9:30-11:30 和 13:00-15:00，不在开盘前和午休期间浪费 API 调用
- **避免并发**：同一 wrapper 内各步骤串行、间隔 10-60s，两个 wrapper 间 cron 同一分钟触发但访问不同表，不冲突
- **盘后兜底**：`sync_all.py` 在盘后以全量模式重跑，确保数据完整性
- **可扩展**：默认指数可通过命令行参数覆盖，如 `bash scripts/sync_intraday_daily.sh 980080 900001 931643`

## 所有 Job 详解

### 0. `sync_northbound.py` — 北向资金独立同步（独立 cron）

| 维度 | 详情 |
|------|------|
| **执行时间** | 每个交易日 9:00 |
| **数据库** | PostgreSQL |
| **写入表** | `daily_northbound_flow`（深股通净买入额、买入额、卖出额） |
| **数据源** | 东财 datacenter RPT_MUTUAL_DEAL_HISTORY（MUTUAL_TYPE="002"） |
| **日志** | `/var/log/aipicking/northbound.log` |
| **幂等性** | `ON CONFLICT (trade_date) DO UPDATE` |

**设计意图：** 盘中同步管线（sync_market_data.py）在 18:30 才跑，北向资金数据实际在次日早上即可获取。独立 cron 在每天 9 点开盘前拉取昨天的深股通数据，确保用户在开盘前就能在系统中看到最新北向资金流向。

> 沪股通（MUTUAL_TYPE="001"）自 2024-08-16 起不再披露净买额，当前仅深股通数据可用。

**运行模式：**
- **默认**：同步昨天的数据
- `--date YYYY-MM-DD`：指定日期
- `--dry-run`：仅预览不写入

### 1. `update_daily.py` — 日线数据 + 市值

| 维度 | 详情 |
|------|------|
| **执行时间** | 盘中每 5 分钟（按指数过滤，约 150 只）+ 盘后 sync_all 全量兜底（~5200 只） |
| **数据库** | PostgreSQL |
| **写入表** | `daily`（日线 OHLCV + adj_close） |
| **数据源** | 腾讯财经 K 线 API / 实时行情（`qt.gtimg.cn`，不封 IP） |
| **注意** | 市值数据已迁移至 `daily_valuation` 表（由 `sync_valuation.py` 同步） |
| **日志** | 盘后 `/var/log/aipicking/update_daily.log`；盘中 `update_daily_intraday.log` |
| **幂等性** | `ON CONFLICT (ts_code, trade_date) DO UPDATE` |

**运行模式：**
- **默认（智能）**：盘中自动用实时接口，盘后用历史日线接口；同时补齐昨天若有缺
- `--date YYYY-MM-DD`：指定某天
- `--date today`：今天，自动判断盘中/盘后
- `--intraday`：强制盘中实时模式
- `--intraday --index 980080`：盘中只更新指定指数成分股（从 `index_constituents` 表读取股票列表）
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
| **执行时间** | 盘中每 5 分钟（由 `sync_intraday_daily.sh` 调用）+ 盘后 sync_all 兜底 |
| **数据库** | PostgreSQL |
| **写入表** | `daily`（5 大指数：上证/深证/创业板/科创50/科创100，ts_code 以 .SH/.SZ 结尾） |
| **数据源** | 腾讯实时行情 + 历史 K 线 API |
| **日志** | `update_daily_intraday.log`（盘中）/ `update_daily.log`（盘后） |
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

### 7. `sync_index_fund_flow.py` — 指数成分股资金流向

| 维度 | 详情 |
|------|------|
| **执行时间** | 盘中每 5 分钟（由 `sync_intraday_fund_flow.sh` 调用） |
| **数据库** | PostgreSQL |
| **写入表** | `daily_stock_fund_flow`（资金流明细）、`intraday_fund_snapshot`（盘中快照） |
| **数据源** | 腾讯自选股 proxy.finance.qq.com（via westock-data-clawhub npm CLI） |
| **日志** | `index_fund_flow.log` |
| **幂等性** | `ON CONFLICT DO UPDATE` |

与全市场 `sync_stock_fund_flow.py` 的区别：只拉取指定指数的成分股（默认 ~150 只），适合盘中高频刷新，秒级完成。

### 8. `sync_intraday_daily.sh` — 盘中指数成分股日线 Wrapper

Shell 包装脚本，cron 每 5 分钟触发一次，内部依次执行：

```
指数日线 (秒级) ──[sleep 30s]──► 980080 成分股日线 (~100只, 2-3s) ──[sleep 60s]──► 900001 成分股日线 (~50只, 1-2s)
```

| 维度 | 详情 |
|------|------|
| **默认指数** | `980080 900001`，可通过命令行参数覆盖 |
| **总耗时** | ~95 秒（含 sleep） |
| **日志** | `update_daily_intraday.log` |

### 9. `sync_intraday_fund_flow.sh` — 盘中指数成分股资金流 Wrapper

Shell 包装脚本，cron 每 5 分钟触发一次，内部依次执行：

```
980080 资金流 (~100只, ~5s) ──[sleep 60s]──► 900001 资金流 (~50只, ~3s)
```

| 维度 | 详情 |
|------|------|
| **默认指数** | `980080 900001`，可通过命令行参数覆盖 |
| **总耗时** | ~68 秒（含 sleep） |
| **日志** | `index_fund_flow.log` |

## 日志查看

```bash
# 登录服务器
ssh root@101.35.254.125

# 北向资金同步日志
tail -f /var/log/aipicking/northbound.log

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
venv/bin/python scripts/sync_northbound.py                    # 北向资金（默认昨天）
venv/bin/python scripts/sync_northbound.py --date 2026-06-06  # 北向资金（指定日期）
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
| 2026-06-18 | 盘中 cron 精确对齐交易时段（9:30-11:30 / 13:00-15:00），消除开盘前/午休无效调用，新增 15:00 收盘快照；资金流改为每 3 分钟（原 5 分钟）；服务器移除盘中同步（暂不需要）；shell wrapper 默认指数扩展为 4 个；sync_all 调整为 16:13 |
| 2026-06-16 | 盘中日线/资金流改为按指数过滤（~150 只），新增 `sync_intraday_daily.sh` + `sync_intraday_fund_flow.sh` wrapper，`update_daily.py` 新增 `--index` 参数；移除全市场 30 分钟盘中日线 |
| 2026-06-15 | 新增 11:30 / 14:15 两档个股资金流盘中预同步（幂等写入，盘后 sync_all 覆盖为最终数据） |
| 2026-06-09 | 新增 `sync_northbound.py` 独立 cron（每天 9:00），提前同步北向资金数据 |
| 2026-06-05 | 所有同步任务整合为 `sync_all.py` 总调度，cron 简化为一条（17:00） |
| 2026-06-05 | `sync_valuation.py` 加入 cron，补充 `update_index_daily.py` 和 `sync_report.py` 文档 |
