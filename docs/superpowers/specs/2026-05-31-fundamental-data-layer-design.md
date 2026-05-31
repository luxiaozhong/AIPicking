# 基本面数据层 — Phase 1 设计

> 状态：设计已确认，待进入实施规划
> 日期：2026-05-31
> 关联：[ideas](../../../docs/superpowers/ideas) #21 — 增加基于基本面的策略

## 概述

为 AIpicking 平台引入基本面数据支持，补齐目前仅有技术面数据的短板。采用三阶段递进策略，本文档覆盖 **Phase 1：数据层**（建表 + 拉取脚本 + 基础 API）。

### 三阶段路线图

```
Phase 1（本次）         Phase 2（后续）         Phase 3（后续）
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ 数据表 + 拉取 │  →   │ 因子库 + 回测 │  →   │ 前端 + AI集成│
│              │      │              │      │              │
│ • 建表       │      │ • 因子函数    │      │ • 可视化构建器│
│ • 全市场拉取  │      │ • 回测引擎    │      │ • AI 参考选股 │
│ • 基础 API   │      │ • 打分策略    │      │ • 策略模板    │
└──────────────┘      └──────────────┘      └──────────────┘
```

## 设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 数据源 | mootdx（通达信）+ 新浪三表 + 腾讯估值 | 首选 TCP 不封IP；腾讯 HTTP 不封IP |
| 存储方式 | PostgreSQL 落库 | 回测需要历史快照，不能实时拉取 |
| 更新策略 | cron 定时（财报季）+ 交易日盘后（估值） | 对齐现有 `update_daily.py` / `sync_market_data.py` 模式 |
| 使用方式 | 全模式（打分 + 筛选 + 多因子混合） | Phase 2 落地，Phase 1 先打好数据基础 |

## 数据库表设计

所有表位于同一 PostgreSQL 库（与 `stocks`、`daily` 等共存）。

### `financial_reports` — 财报季报快照

每只股票每报告期一条记录，覆盖最近 5 年（20 期），约 10.8 万条（5400 股 × 20 期）。

```sql
CREATE TABLE financial_reports (
    id              BIGSERIAL PRIMARY KEY,
    ts_code         VARCHAR(20) NOT NULL,      -- 股票代码
    report_date     VARCHAR(10) NOT NULL,      -- 报告期 YYYY-MM-DD（如 2026-03-31）
    report_type     VARCHAR(10) NOT NULL,      -- Q1 / Q2 / Q3 / FY
    pub_date        VARCHAR(10),               -- 实际发布日期

    -- 盈利质量（mootdx finance）
    eps             DOUBLE PRECISION,          -- 每股收益
    bvps            DOUBLE PRECISION,          -- 每股净资产
    roe             DOUBLE PRECISION,          -- ROE（%）
    roa             DOUBLE PRECISION,          -- ROA（%）
    gross_margin    DOUBLE PRECISION,          -- 毛利率（%）
    net_margin      DOUBLE PRECISION,          -- 净利率（%）

    -- 成长性
    net_profit      DOUBLE PRECISION,          -- 净利润（万元）
    net_profit_yoy  DOUBLE PRECISION,          -- 净利润同比（%）
    revenue         DOUBLE PRECISION,          -- 营业收入（万元）
    revenue_yoy     DOUBLE PRECISION,          -- 营收同比（%）

    -- 财务健康
    debt_to_assets  DOUBLE PRECISION,          -- 资产负债率（%）
    current_ratio   DOUBLE PRECISION,          -- 流动比率
    quick_ratio     DOUBLE PRECISION,          -- 速动比率

    -- 现金流
    cf_operating    DOUBLE PRECISION,          -- 经营现金流（万元）
    cf_ratio        DOUBLE PRECISION,          -- 经营现金流 / 净利润

    -- 股本
    total_shares    BIGINT,                    -- 总股本
    float_shares    BIGINT,                    -- 流通股本

    -- 新浪三表补充
    total_assets         DOUBLE PRECISION,     -- 总资产
    total_liabilities    DOUBLE PRECISION,     -- 总负债
    shareholders_equity  DOUBLE PRECISION,     -- 股东权益

    -- 元数据
    source          VARCHAR(20) DEFAULT 'mootdx',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(ts_code, report_date)
);

CREATE INDEX idx_fin_code ON financial_reports(ts_code);
CREATE INDEX idx_fin_date ON financial_reports(report_date);
CREATE INDEX idx_fin_type ON financial_reports(report_type);
```

### `daily_valuation` — 每日估值快照

每只股票每个交易日一条记录，约 135 万条/年（5400 股 × 250 交易日）。

```sql
CREATE TABLE daily_valuation (
    id              BIGSERIAL PRIMARY KEY,
    ts_code         VARCHAR(20) NOT NULL,
    trade_date      VARCHAR(8)  NOT NULL,       -- YYYYMMDD

    -- 腾讯财经实时估值
    pe_ttm          DOUBLE PRECISION,           -- PE(TTM)
    pe_static       DOUBLE PRECISION,           -- PE(静态)
    pb              DOUBLE PRECISION,           -- PB
    market_cap      DOUBLE PRECISION,           -- 总市值（亿元）
    circ_market_cap DOUBLE PRECISION,           -- 流通市值（亿元）
    dividend_yield  DOUBLE PRECISION,           -- 股息率（%）

    source          VARCHAR(20) DEFAULT 'tencent',
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(ts_code, trade_date)
);

CREATE INDEX idx_dv_code ON daily_valuation(ts_code);
CREATE INDEX idx_dv_date ON daily_valuation(trade_date);
```

### 表与现有模型的对比

| 现有表 | 新增表 | 关系 |
|--------|--------|------|
| `stocks` (股票基础信息) | `financial_reports` | 一对多（1 股 → N 期财报） |
| `daily` (日线行情) | `daily_valuation` | 一对一（同日同股可 JOIN） |
| — | `financial_reports` | `daily` 通过 `trade_date` ≤ `pub_date` 判断回测时可见性 |

> **回测可见性关键约束**：回测时只能使用 `pub_date` ≤ `cutoff_date` 的财报。避免「未来函数」——不能在截止日用到了尚未发布的财报数据。

## 数据拉取脚本

遵循 `backend/scripts/` 目录现有模式（`update_daily.py` / `sync_market_data.py`）：
- argparse CLI（`--init`、`--date`、`--force`、`--pg-url`）
- `get_conn()` 获取 psycopg2 连接
- `ON CONFLICT ... DO UPDATE` 幂等写入
- 从 `.env` / `.env.production` 加载配置

### `scripts/sync_financials.py` — 财报数据同步

**数据源**：mootdx finance（37 字段季报快照，TCP 7709 端口）+ 新浪财报三表（补充完整字段）

**用法**：
```bash
# 全量初始化（拉取近 5 年所有财报，~5400 只股票 × 20 期）
venv/bin/python scripts/sync_financials.py --init

# 增量更新（只拉最新一期，盘后日常维护）
venv/bin/python scripts/sync_financials.py

# 指定日期范围
venv/bin/python scripts/sync_financials.py --start 2020-01-01 --end 2026-03-31

# 单票测试
venv/bin/python scripts/sync_financials.py --code 600519
```

**cron（每季度财报季结束后第一周）**：
```
# A股财报披露截止日：一季报/年报 4/30，中报 8/31，三季报 10/31
# 年报: 5/2 03:00 | 一季报: 5/2 03:00 | 中报: 9/2 03:00 | 三季报: 11/2 03:00
0 3 2 5,9,11 * * cd /opt/AIpicking/backend && venv/bin/python scripts/sync_financials.py >> /var/log/aipicking/financials.log 2>&1
```

**技术要点**：
- mootdx TCP 串行拉取（单连接，不并发），全量初始化预计 ~2 小时
- 新浪三表 HTTP 拉取，间隔 ≥ 0.5s
- 每只股票写入时计算 `net_profit_yoy`、`revenue_yoy` 同比字段

### `scripts/sync_valuation.py` — 估值数据同步

**数据源**：腾讯财经 HTTP API（PE/PB/市值/股息率）

**用法**：
```bash
# 历史初始化（拉取最近 365 天每日估值）
venv/bin/python scripts/sync_valuation.py --init

# 每日增量（拉昨天估值）
venv/bin/python scripts/sync_valuation.py

# 补指定日期
venv/bin/python scripts/sync_valuation.py --date 2026-05-30
```

**cron（每个交易日盘后）**：
```
# 周一至周五 17:30（盘后，数据已稳定）
30 17 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_valuation.py >> /var/log/aipicking/valuation.log 2>&1
```

**技术要点**：
- 腾讯财经单次可拉多只股票（逗号拼接），批量拉取效率高
- 参考 `update_daily.py` 的 `fetch_realtime_quote` 模式
- 腾讯不封 IP，可适度并发（~10 只/批次）

## API 端点

新增路由文件 `backend/app/api/financials.py`，挂载到 `/api/v1/financials`。

| 方法 | 路径 | 说明 | Phase |
|------|------|------|-------|
| GET | `/api/v1/financials/{ts_code}` | 单股财报历史（默认 20 期） | 1 |
| GET | `/api/v1/financials/{ts_code}/latest` | 最新一期财报 | 1 |
| GET | `/api/v1/valuation/{ts_code}` | 单股估值历史（默认 365 天） | 1 |
| GET | `/api/v1/valuation/snapshot` | 全市场最新估值快照 | 1 |
| GET | `/api/v1/financials/screen` | 简单筛选（roe_min, pe_max 等） | 1 |

所有端点返回统一格式 `{code: 0, message: "success", data: ...}`，和现有 API 一致。

## 对回测引擎的影响（Phase 2 预览）

`BacktestEngine._load_data()` 在加载数据时新增查询：
```python
# 加载截止日之前已发布的最新财报
fin_stmt = select(FinancialReport).where(
    FinancialReport.ts_code.in_(ts_codes),
    FinancialReport.pub_date <= cutoff_date_fmt
).order_by(FinancialReport.report_date.desc())
```

`strategy_input` 新增字段：
```python
{
    "financials": {ts_code: {report_date, roe, eps, ...}},  # 每个股票最新可用财报
    "valuations": {ts_code: {pe_ttm, pb, ...}},              # 截止日估值
}
```

> 回测引擎改动不在 Phase 1 范围，此处仅标注影响方向。

## 文件清单（Phase 1 新增）

```
backend/app/
├── api/financials.py              # 财务数据 API 路由（新增）
├── models/financial.py            # FinancialReport, DailyValuation 模型（新增）
├── schemas/financial.py           # Pydantic schema（新增）
└── services/financial_service.py  # 财务数据查询服务（新增）

backend/scripts/
├── sync_financials.py             # 财报数据同步脚本（新增）
└── sync_valuation.py              # 估值数据同步脚本（新增）

backend/
└── migrate_add_financials.py      # 建表迁移脚本（新增）
```

## 不在范围

- 因子库实现（Phase 2）
- 回测引擎改造（Phase 2）
- 前端页面（Phase 3）
- AI Builder 基本面因子提取（Phase 3）
- 行业分析数据（已有 `stocks.industry_l1/l2/l3` 字段，暂不扩展）
