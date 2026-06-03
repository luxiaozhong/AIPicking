# Board Filter — 回测板块筛选 & 入选率展示

## 概述

在回测提交时允许用户选择基础板块（上证/深圳/科创/创业），回测报告中展示入选股总数、基础板块总股数、入选率三个指标。批量回测中按天展示，且 0 入选日不展示。

---

## 一、板块定义

| 板块（UI 复选框） | ts_code 前缀匹配 |
|------------------|-----------------|
| 上证 | `60` |
| 深圳 | `00` |
| 科创 | `688`, `689` |
| 创业 | `300`, `301` |

匹配逻辑：`ts_code.startswith(prefix)`，科创/创业需要满足任意一个前缀。

---

## 二、数据结构变更

### 2.1 config 扩展

提交回测时 `config` 中新增字段：

```json
{
  "board_filter": ["60", "00", "688", "689", "300", "301"]
}
```

- 必选至少一个板块，默认全选（4 个复选框全勾 = 6 个前缀）
- 存储为字符串数组，每个元素为单个 ts_code 前缀
- 匹配方式：`any(ts_code.startswith(prefix) for prefix in board_filter)`

### 2.2 BacktestSummary 新增字段

```python
class BacktestSummary(BaseModel):
    # ... 现有字段保持不变 ...
    total_qualifying: int       # 满足策略条件的股票总数（topN 截断前）
    base_stock_count: int       # 选中板块在数据库中的总股数（池子大小）
    pick_rate: float            # 入选率 = total_qualifying / base_stock_count
```

适用场景：
- `BacktestResponse.summary`（单次回测）
- `DailyResultItem.summary`（批量回测每日结果）

---

## 三、后端改动

### 3.1 文件：`backend/app/services/backtest_engine.py`

#### `run()` 方法

1. 从 `config.board_filter` 读取板块过滤条件
2. 加载 stocks 后按 `ts_code` 前缀过滤，计数 → `base_stock_count`
3. 仅将过滤后的 stocks 传入策略 `run()`
4. 策略返回后，截断前：`total_qualifying = len(recommendations)`
5. 计算 `pick_rate = total_qualifying / base_stock_count`
6. 写入 `summary`

#### `run_batch()` 方法

1. 同上逻辑，每个交易日独立计算
2. **过滤**：`recommendations` 为空时跳过该日，不加入 `daily_results` 数组

### 3.2 文件：`backend/app/schemas/backtest.py`

- `BacktestSummary` 新增 `total_qualifying`, `base_stock_count`, `pick_rate`

---

## 四、前端改动

### 4.1 文件：`frontend/src/types/backtest.ts`

`BacktestSummary` 接口新增：
```typescript
total_qualifying: number;
base_stock_count: number;
pick_rate: number;
```

### 4.2 文件：`frontend/src/pages/BacktestForm.tsx`

- 新增 4 个 `Checkbox`，默认全部选中，至少选一个
- 选中值写入 `config.board_filter`
- 适用于单次回测和批量回测两种模式

### 4.3 文件：`frontend/src/pages/BacktestDetail.tsx`

汇总指标卡片新增 3 个 `StatCard`：

| StatCard | 数据字段 | 格式 |
|----------|---------|------|
| 入选总数 | `total_qualifying` | 整数 |
| 基础总股数 | `base_stock_count` | 整数 |
| 入选率 | `pick_rate` | 百分比 (xx.xx%) |

### 4.4 文件：`frontend/src/pages/BatchBacktestDetail.tsx`

**过滤：**
- `collapseItems` 构建时过滤 `recommendations.length === 0` 的日期（后端已过滤，前端兜底）

**每日面板 `DailyPanel`：**
- 新增一行 `Row`，展示当日「入选总数 / 基础总股数 / 入选率」三个 `StatCard`

**表格交互（每日推荐股票表格）：**

| 触发 | 行为 |
|------|------|
| 点击股票代码文字 | 弹出 `StockKLineModal`（复用），展示该股近一年 K 线 |
| 点击行首 `+` 展开 | 展开行显示每日追踪面板，调用 `/stocks/kline` API 获取该股 K 线数据，从截止日后一天开始展示，渲染 OHLCV 表 + 收盘价折线图（复用 `TradeSimDetail.expandedRowRender` 模式） |

**每日追踪实现细节：**
- 数据来源：复用现有 `/api/stocks/kline?ts_code=XXX&days=N` 接口
- 表格列：日期、开盘、收盘、最高、最低、成交量
- 图表：收盘价折线图（ECharts），X 轴为日期
- 追踪起点：截止日（买入日）的次日

---

## 五、影响范围汇总

| 层 | 文件 | 改动 |
|----|------|------|
| 后端 | `schemas/backtest.py` | `BacktestSummary` +3 字段 |
| 后端 | `services/backtest_engine.py` | 板块过滤 + 计数 + 空日过滤 |
| 前端 | `types/backtest.ts` | `BacktestSummary` +3 字段 |
| 前端 | `pages/BacktestForm.tsx` | +板块复选框 |
| 前端 | `pages/BacktestDetail.tsx` | +3 StatCard |
| 前端 | `pages/BatchBacktestDetail.tsx` | 过滤 + 每日统计 + 表格交互 |

---

## 六、复用清单

| 组件/模块 | 来源 | 用途 |
|-----------|------|------|
| `StockKLineModal` | `components/shared/StockKLineModal.tsx` | 点击股票代码弹出 K 线图 |
| `useKLineData` hook | `hooks/useKLineData.ts` | 获取 K 线数据（K 线弹窗 + 每日追踪表共用） |
| `/api/stocks/kline` | `backend/app/api/stocks.py` | K 线数据接口 |
| `expandedRowRender` 模式 | `pages/TradeSimDetail.tsx` | 展开行展示每日追踪（表 + 图） |
| `StatCard` | `components/shared/StatCard.tsx` | 指标卡片 |
| `ReturnLabel` | `components/shared/ReturnLabel.tsx` | 涨跌幅标签 |

---

## 七、边界情况

1. **base_stock_count = 0**：选中板块无股票时，pick_rate 设为 0，前端显示 "0.00%"
2. **total_qualifying > base_stock_count**：防御性处理 `pick_rate = min(1.0, total_qualifying / base_stock_count)`
3. **批量回测某天策略异常**：按现有逻辑 status=failed，仍展示但标记失败
4. **旧回测数据显示**：旧报告 `summary` 不含新字段，前端 fallback 显示 "—"
5. **`_empty_summary()`**：需同步更新，新字段默认值为 0
6. **板块过滤对策略的影响**：过滤后的 stocks 传入策略，策略只能从选中板块选股，这是预期行为
