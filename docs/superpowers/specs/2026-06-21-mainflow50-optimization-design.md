# 主力资金 50 指数优化 — 设计文档

日期: 2026-06-21 | 分支: feat/mainflow50-optimize | 基于: [2026-06-16 原版设计](2026-06-16-mainflow50-index-design.md)

## 一、概述

在原「每日盘后更新 Top 50」的基础上，引入四项优化：周频调仓、缓冲垫机制、趋势过滤、保留历史。改动集中于 `backend/scripts/update_mainflow_index.py` 单文件，不涉及 DDL 变更。

## 二、优化详情

### 2.1 调仓频率：日更 → 周更（周五）

**规则**：仅在周五执行调仓。若周五是节假日，顺延到下一个交易日。

**实现**：
- 新增 `get_next_rebalance_day()` — 从最近交易日往前找，返回最近的周五（含顺延逻辑）
- 新增 `is_rebalance_day(trade_date)` — 判断目标日期是否为调仓日
- `run()` 开头检查：非调仓日 → log info 并跳过
- CLI 新增 `--force` 参数：绕过调仓日检查

**非调仓日行为**：脚本被 cron 每日调用时，周一至周四直接跳过，不写任何数据。

### 2.2 缓冲垫机制（45/55 + 补满）

**规则**：
| 操作 | 条件 | 说明 |
|------|------|------|
| 强制踢出 | 持仓股排名 > 55 | 资金面已明显恶化 |
| 优先纳入 | 未持仓股排名 ≤ 45 | 被动触发买入信号 |
| 补满 | 调整后持仓 < 50 | 从排名最高未持仓股中补齐 |

**流程**：
```
1. 计算全市场排名（取 top 60）
2. 读取当前持仓（index_constituents 中最新 eff_date 的记录）
3. 分类持仓股：
   - 排名 ≤ 55 → 保留
   - 排名 > 55 或无排名（可能退市/停牌）→ 踢出
4. 选入候选：
   - 未持仓股中排名 ≤ 45 的 → 纳入
   - 如果保留+纳入 < 50 → 从排名最高未持仓股中补满到 50
5. 等权重（2%），写入
```

**首次运行**（无历史持仓）：跳过缓冲垫，直接取 top 50。

### 2.3 趋势过滤（AND）

**规则**：纳入候选（含优先纳入和补满）时，两道检查必须同时通过：

| 过滤 | SQL 实现 |
|------|---------|
| 均线过滤：close > 20日均线 | `close > AVG(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS 19 PRECEDING)` |
| 追高过滤：5日涨幅 < 15% | `(close - LAG(close, 4) OVER ...) / LAG(close, 4) OVER ... < 0.15` |

- 未通过过滤的股票**跳过**，由下一排名替补
- **踢出逻辑不受趋势过滤影响**（已在持仓的只看排名）

### 2.4 保留历史

**改动**：删除 `upsert_constituents()` 中的 `DELETE FROM index_constituents WHERE index_code = %s`。

每次调仓写入新的 `eff_date`（调仓日日期），ON CONFLICT 幂等。历史调仓记录自然保留。

## 三、关键边界情况

| 场景 | 处理 |
|------|------|
| 非调仓日被 cron 调用 | 跳过，log info "非调仓日，跳过" |
| `--force` 在非周五运行 | 正常执行全部逻辑（用于回测补跑） |
| `--date` 指定非周五 | 等效于 `--force`（指定日期即强制） |
| 首次运行（无历史持仓） | 算排名 → 趋势过滤 → 直接取 top 50 |
| 调仓日通过趋势过滤的不足 50 只 | 有多少写多少，log warning |
| 调仓日全市场净流入>0 的不足 50 只 | 选满实际数量 |
| 周五是节假日 | 顺延到下一交易日 |
| 连续多周不调仓（如春节） | 每个调仓日独立计算，不累积 |

## 四、函数变更清单

| 函数 | 变更 |
|------|------|
| `get_latest_trade_day()` | 不变 |
| `get_lookback_trade_dates()` | 不变 |
| `compute_top_stocks()` | 改为 `compute_rankings()` — 仍聚合 15 日主力净流入，但返回完整排名（top 60） |
| `upsert_index_info()` | 不变 |
| `upsert_constituents()` | **移除 DELETE**，只做 upsert |
| `verify()` | 更新：验证最新 eff_date 的成分股 |
| `run()` | 重构：加入调仓日检查、缓冲垫逻辑、趋势过滤 |
| `main()` | 新增 `--force` 参数 |

### 新增函数

| 函数 | 说明 |
|------|------|
| `is_rebalance_day(date_str)` | 判断是否为调仓日（周五，含顺延） |
| `get_current_holdings(conn)` | 读取最新 eff_date 的持仓 |
| `apply_trend_filter(conn, ts_codes, trade_dates)` | 批量趋势过滤，返回通过过滤的 code 集合 |
| `apply_buffer(rankings, holdings)` | 执行缓冲垫规则，返回最终成分股列表 |

## 五、不改动的部分

- 数据库表结构（index_info, index_constituents）
- sync_all.py 调度顺序
- index_code 900001 及相关元数据
- 排除规则（ST/北交所/次新股）
- 15 日滚动窗口和等权方式
- CLI 现有参数（--date, --top, --dry-run, --pg-url, --log-level）
