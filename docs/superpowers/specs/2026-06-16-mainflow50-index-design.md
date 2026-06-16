# 主力资金 50 指数 — 设计文档

日期: 2026-06-16 | 分支: feat/mainflow50-index

## 一、概述

每日收盘后，从全市场 A 股中筛选「滚动 15 日主力资金流总和 Top 50」的个股，等权构成自定义指数。成分股每日更新，存入现有 `index_constituents` 表。

## 二、指数定义

| 元数据 | 值 |
|--------|-----|
| index_code | `900001` |
| index_name | `主力资金50` |
| full_name | `主力资金50指数` |
| publisher | `自定义` |
| constituent_count | 50 |
| data_source | `custom.main_flow_15d` |
| 权重方式 | 等权（每只 2%） |
| 更新频率 | 每日盘后 |
| 选股范围 | 全市场 A 股（沪深两市，排除 ST/*ST/次新股/北交所） |

## 三、筛选规则

### 3.1 入选条件

按每只股票最近 **15 个交易日**的 `main_net_flow`（主力净流入）总和降序排列，取前 50 只。

### 3.2 排除规则

| 条件 | 实现方式 |
|------|---------|
| ST / *ST | `stocks.name LIKE '%ST%'` |
| 北交所 | `ts_code LIKE '%.BJ'`（现阶段资金流数据覆盖不稳定） |
| 上市 < 60 自然日 | `stocks.list_date > (today - 60d)` |
| 近 15 日无资金流数据 | `COUNT(daily_stock_fund_flow.ts_code) < 1`（JOIN 自然排除） |

> 注：若符合条件的股票不足 50 只（如极端行情全市场主力净流出），则选满实际数量。

## 四、数据流

```
现有 sync_all.py 盘后调度（17:30）
  ...
  sync_stock_fund_flow.py     ← 全市场资金流入 daily_stock_fund_flow
  ...
  update_mainflow_index.py    ★ 新增：最后一步
```

### update_mainflow_index.py 核心逻辑

1. **获取最近 15 个交易日列表** — 从 `daily` 表中取 DISTINCT trade_date，降序取 15 个，确保是真实交易日
2. **聚合资金流** — 查询 `daily_stock_fund_flow` JOIN `stocks`，15 日 `SUM(main_net_flow)`
3. **过滤** — 排除 ST/*ST / 次新股 / 北交所
4. **排序取 Top 50** — `ORDER BY flow_15d DESC LIMIT 50`
5. **写入 index_constituents** — `eff_date = 今日`，`weight = 2.0`（等权）
6. **更新 index_info.last_sync_date**

### 幂等性

`index_constituents` 唯一约束 `(index_code, ts_code, eff_date)`，每天重复跑自动覆盖（ON CONFLICT DO UPDATE），不产生重复数据。

## 五、数据库变更

无 DDL 变更。复用现有表：
- `index_info` — 插入 900001 元数据（首次）
- `index_constituents` — 每日写入 50 条成分股

## 六、新增/修改文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/scripts/update_mainflow_index.py` | **新增** | 核心脚本 |
| `backend/scripts/sync_index_constituents.py` | 修改 | KNOWN_INDICES 注册 900001 |
| `backend/scripts/sync_all.py` | 修改 | JOBS 列表追加新任务 |

## 七、CLI 接口

```bash
cd backend && source venv/bin/activate

# 默认：计算今天（盘后自动取最近交易日）
python scripts/update_mainflow_index.py

# 指定日期
python scripts/update_mainflow_index.py --date 2026-06-16

# Dry-run：预览 Top 50 不写入
python scripts/update_mainflow_index.py --dry-run

# 自定义 top_n（默认 50）
python scripts/update_mainflow_index.py --top 30

# 指定数据库
python scripts/update_mainflow_index.py --pg-url postgresql://...
```

## 八、Cron 集成

在 `sync_all.py` 中作为最后一步执行。无需单独 cron。

```
30 17 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_all.py
```

## 九、前端展示（后续可选）

- 已有 `index_constituents` 查询 API/Hooks，前端可直接用
- 后续可在仪表盘增加「主力资金50」指数卡片和成分股列表

## 十、边界情况

| 场景 | 处理 |
|------|------|
| 非交易日 | 自动取最近交易日（`--date` 默认逻辑） |
| 符合条件的股票 < 50 只 | 选满实际数量，日志 warn |
| 新脚本在某天失败 | `sync_all.py` 标记失败但前面的任务不受影响；次日重跑自动覆盖 |
| 资金流数据缺失（某只股票缺少某些交易日） | `SUM(main_net_flow)` 自然处理，有几天算几天 |
| 服务器已部署旧版 sync_all.py | 需要 `git pull` + 重启 cron/服务 |

## 十一、与现有指数的关系

900001 是一个**独立自定义指数**，数据存储在 `index_info` + `index_constituents` 表中，和国证成长100（980080）等官方指数**平级共存**。可被现有前端的指数选择器发现和展示。
