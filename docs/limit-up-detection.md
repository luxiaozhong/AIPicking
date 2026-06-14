# 一字板/涨停板检测方案

## 问题描述

`grow_with_money_v1` 等每日调仓策略的回测逻辑是：
1. **T 日收盘后**：运行策略，选出 top N 只股票
2. **T+1 日开盘**：以开盘价买入新选中的股票，同时卖出不再持有的股票

这里存在一个真实性问题：**如果 T+1 日股票一字板（开盘即涨停，全天封死），散户实际无法买入，但回测引擎会以开盘价（涨停价）"买入"，导致回测收益虚高。**

---

## 当前状态

### 数据可用性

| 数据 | 表/字段 | 加载到引擎 | 备注 |
|------|---------|------------|------|
| `open` | `daily.open` | ✅ | 开盘价 |
| `high` | `daily.high` | ✅ | 最高价 |
| `low` | `daily.low` | ✅ | 最低价 |
| `close` | `daily.close` | ✅ | 收盘价 |
| `vol` | `daily.vol` | ✅ | 成交量 |
| `amount` | `daily.amount` | ✅ | 成交额 |
| `adj_close` | `daily.adj_close` | ✅ | 复权收盘价 |
| `pre_close` | `daily.pre_close` | ❌ **未加载** | 前收盘价（用于计算涨跌停价） |

`pre_close` 在 `Daily` 表中已存在（`backend/app/models/stock_tables.py:43`），由 `update_daily.py` 写入。但 `BacktestEngine._load_data()` 和 `_load_data_range()` 的 SQL 查询都没有加载此字段。

### 涉及的引擎

| 引擎 | 文件 | 买入方式 | 涨停检测 |
|------|------|----------|----------|
| `BacktestEngine` | `backtest_engine.py` | 不执行买卖，仅推荐选股 | N/A |
| `RebalanceEngine` | `rebalance_engine.py:180` | `buy_price = day_info.get("open")` | ❌ 无 |
| `TradeSimEngine` | `trade_sim_engine.py:274` | `buy_price = buy_day.get("open")` | ❌ 无 |

### 涨跌停幅度规则

根据 A 股交易规则，不同板块涨跌停幅度不同：

| 板块 | ts_code 前缀 | 涨跌幅限制 | 说明 |
|------|-------------|------------|------|
| 上海主板 | `60` | ±10% | 600xxx, 601xxx, 603xxx, 605xxx |
| 深圳主板 | `00` | ±10% | 000xxx, 001xxx, 002xxx, 003xxx |
| 创业板 | `30` | ±20% | 300xxx, 301xxx |
| 科创板 | `688`, `689` | ±20% | 688xxx, 689xxx |
| 北交所 | `83`, `87`, `43` | ±30% | 83xxxx, 87xxxx, 43xxxx |
| ST 股票 | 任意（名称含 ST） | ±5% | *ST, ST 前缀 |

注意：ST 股票判断需要看股票名称（`name` 字段），而非 `ts_code`。ST 股票的涨跌幅限制覆盖板块限制（例如主板 ST 从 ±10% 变为 ±5%）。

---

## 检测方案设计

### 方案 A：严格一字板检测（推荐）

**判断条件**：同时满足以下两个条件，认定为无法买入：

1. **涨停价开盘**：`open >= limit_up_price`（开盘价达到或超过涨停价）
2. **全天无波动**：`high == low`（最高价 == 最低价，即价格全天未变化）

**原理**：一字板的特征是开盘即涨停、全天封死，K 线图呈现"一字"形态：`open == high == low == close`。

**优点**：
- 精准识别一字板（涨停封死无法买入）
- T 字板（涨停开盘但盘中打开）不会被误判——`high > low`，散户有买入机会
- 不依赖成交量阈值（不同市值股票的"低量"标准不同，难以设定统一阈值）

**缺点**：
- 如果涨停开盘但盘中短暂打开后快速封回（接近一字板），仍会判定为可买入（实际买入难度极大）
- 需要 `pre_close` 数据来计算 `limit_up_price`

### 方案 B：保守涨停开盘检测

**判断条件**：仅判断 `open >= limit_up_price`。

**原理**：只要开盘即涨停，无论盘中是否打开，散户在开盘时都无法以开盘价买入。

**优点**：
- 简单、保守，不会虚增收益
- 对回测偏保守，实际策略上线后表现不会差于回测

**缺点**：
- 过于保守：T 字板（涨停开盘、盘中打开）也被排除，但散户在盘中打开后可以买入
- 会低估策略在强势股上的收益

### 推荐方案

**推荐方案 A（严格一字板检测）**。理由：
1. 能准确识别真正的"无法买入"场景（一字板）
2. 不会误伤 T 字板（盘中有换手，理论上可以买入）
3. 与 A 股交易实际体验一致——一字板封死买不到，但有打开的就有机会

---

## 实现设计

### 1. 数据层：加载 `pre_close`

**文件**：`backend/app/services/backtest_engine.py`

**`_load_data()` (line 453)** 和 **`_load_data_range()` (line 607)** 的 SQL 查询需要加入 `Daily.pre_close`：

```python
# 当前
daily_stmt = select(
    Daily.ts_code, Daily.trade_date, Daily.open, Daily.high,
    Daily.low, Daily.close, Daily.vol, Daily.amount,
    Daily.adj_close,
)

# 修改后
daily_stmt = select(
    Daily.ts_code, Daily.trade_date, Daily.open, Daily.high,
    Daily.low, Daily.close, Daily.pre_close,  # 新增
    Daily.vol, Daily.amount, Daily.adj_close,
)
```

同时在 `_load_data_range()` 的字典构建中（line 719-726）加入 `pre_close`：

```python
daily_data[ts_code].append({
    ...
    "pre_close": row.get("pre_close"),  # 新增
    ...
})
```

### 2. 工具函数：计算涨停价

新增函数 `_get_limit_up_price(ts_code: str, pre_close: float, name: str = "") -> float`：

```python
def _get_limit_up_price(ts_code: str, pre_close: float, name: str = "") -> Optional[float]:
    """根据股票代码和前收盘价计算涨停价"""
    if pre_close is None or pre_close <= 0:
        return None
    
    # ST 股票：±5%
    if name and "ST" in name.upper():
        limit_pct = 0.05
    # 科创板：±20%
    elif ts_code.startswith(("688", "689")):
        limit_pct = 0.20
    # 创业板：±20%
    elif ts_code.startswith(("300", "301")):
        limit_pct = 0.20
    # 北交所：±30%
    elif ts_code.startswith(("83", "87", "43")):
        limit_pct = 0.30
    # 主板：±10%
    else:
        limit_pct = 0.10
    
    return round(pre_close * (1 + limit_pct), 2)
```

**Caveat**：ST 判断依赖 `name` 字段（如 "*ST 康得"、"ST 华英"）。`name` 通过 `ts_code_to_name` 映射获取。北交所部分股票名称可能不含 ST 但有特殊规则，但数量极少暂可忽略。

### 3. 判断函数：一字板检测

```python
def _is_limit_up_locked(day_info: dict, limit_up_price: float) -> bool:
    """判断是否为涨停一字板（无法买入）
    
    Args:
        day_info: 当日日线数据 {open, high, low, close, pre_close, ...}
        limit_up_price: 预先计算的涨停价
    
    Returns:
        True 如果是涨停一字板（无法买入）
    """
    open_price = day_info.get("open")
    high_price = day_info.get("high")
    low_price = day_info.get("low")
    
    if open_price is None or high_price is None or low_price is None:
        return False  # 数据缺失，不做判断
    
    if limit_up_price is None:
        return False  # 无法计算涨停价，不做判断
    
    # 条件1: 开盘价达到涨停价
    opened_at_limit = open_price >= limit_up_price
    
    # 条件2: 全天价格无波动（一字板特征）
    no_price_range = (high_price == low_price)
    
    return opened_at_limit and no_price_range
```

### 4. RebalanceEngine 买入拦截

**文件**：`backend/app/services/rebalance_engine.py`

在买入循环中（约 line 177-209），增加涨停一字板检测：

```python
# 当前逻辑（line 177-209）
for buy_info in pending_buys:
    ts_code = buy_info["ts_code"]
    day_info = today_prices.get(ts_code, {})
    buy_price = day_info.get("open")
    if buy_price is None or buy_price <= 0:
        continue  # 停牌跳过
    # ... 计算买入

# 修改后
for buy_info in pending_buys:
    ts_code = buy_info["ts_code"]
    day_info = today_prices.get(ts_code, {})
    buy_price = day_info.get("open")
    if buy_price is None or buy_price <= 0:
        continue  # 停牌跳过
    
    # 涨停一字板检测：无法买入，保留现金
    limit_up_price = _get_limit_up_price(
        ts_code,
        day_info.get("pre_close"),
        ts_code_to_name.get(ts_code, ""),
    )
    if _is_limit_up_locked(day_info, limit_up_price):
        # 记录一次跳过的买入尝试
        all_trades.append({
            "date": today,
            "ts_code": ts_code,
            "name": ts_code_to_name.get(ts_code, ts_code),
            "action": "skip",
            "price": round(buy_price, 2),
            "shares": 0,
            "amount": 0,
            "commission": 0,
            "total_cost": 0,
            "reason": "一字板涨停，无法买入",
        })
        continue  # 跳过，保留现金
    
    # ... 原买入逻辑
```

**现金处理**：跳过的股票资金保留为现金，不重新分配给其他股票（因为其他股票的买入量已按均分计算，重新分配会改变权重）。

### 5. TradeSimEngine 买入拦截（可选）

**文件**：`backend/app/services/trade_sim_engine.py`

在 `_simulate_trade()` 方法中（约 line 274）：

```python
buy_price = buy_day.get("open")
if buy_price is None or buy_price <= 0:
    trade["sell_reason"] = "数据缺失（无开盘价）"
    return trade

# 新增：一字板检测
limit_up_price = _get_limit_up_price(ts_code, buy_day.get("pre_close"), name)
if _is_limit_up_locked(buy_day, limit_up_price):
    trade["sell_reason"] = "一字板涨停，无法买入"
    return trade
```

`TradeSimEngine._load_tracking_data()` 也需要加入 `pre_close`：

```python
stmt = select(
    Daily.ts_code, Daily.trade_date, Daily.open, Daily.high,
    Daily.low, Daily.close, Daily.pre_close,  # 新增
    Daily.adj_close, Daily.vol, Daily.amount,
)
```

---

## 极端情况与边界条件

### 一字板变体

| 场景 | `open` vs limit | `high` vs `low` | 判定 | 合理性 |
|------|----------------|-----------------|------|--------|
| 纯一字板 | `open == limit` | `high == low` | **跳过买入** ✅ | 完全无法买入 |
| 一字板但尾盘漏单 | `open == limit` | `high == low` | 跳过买入 | 日线无打开记录，保守跳过 |
| T 字板（打开后封回） | `open == limit` | `high > low` | **允许买入** | 散户在打开时可以买入 |
| 开盘高开但未涨停 | `open < limit` | 任意 | 允许买入 | 不是一字板 |
| 天地板（涨停→跌停） | `open == limit` | `high > low` | 允许买入 | 打开了（虽然是暴跌），但确实有机会买入 |
| 新股上市首日 | `pre_close` 可能为空 | N/A | 不做判断 | 数据不完整 |

### 数据缺失处理

- `pre_close = None` 或 `pre_close <= 0`：无法计算涨停价 → **不做一字板判断，正常买入**
- `open` / `high` / `low` 为 `None`：停牌或数据缺失 → **已在现有逻辑中跳过**（`buy_price is None or buy_price <= 0`）

### 不同复权因子的处理

`update_daily.py` 从腾讯 API 获取数据使用**同一复权因子**，`pre_close` 和当日 `open/high/low/close` 处于同一复权体系下，涨跌幅计算正确。如果未来换用不同数据源，需要注意 `pre_close` 的一致性。

---

## 影响范围总结

| 文件 | 变更类型 | 内容 |
|------|----------|------|
| `backtest_engine.py` | 修改 SQL | `_load_data()` 和 `_load_data_range()` 查询加入 `Daily.pre_close` |
| `backtest_engine.py` | 修改字典 | `_load_data_range()` 的 daily 字典加入 `pre_close` |
| `rebalance_engine.py` | 新增函数 | `_get_limit_up_price()` 和 `_is_limit_up_locked()` |
| `rebalance_engine.py` | 修改买入逻辑 | 买入前检测一字板，命中则跳过 |
| `trade_sim_engine.py` | 修改 SQL | `_load_tracking_data()` 查询加入 `Daily.pre_close` |
| `trade_sim_engine.py` | 修改买入逻辑 | 买入前检测一字板，命中则标记无法买入 |

---

## 不做的范围

1. **不新增数据库字段**：`pre_close` 已存在于 `daily` 表，无需修改表结构
2. **不改策略代码**：一字板检测是引擎层通用能力，策略无需感知
3. **不修改 `BacktestEngine.run()` 的回测逻辑**：该引擎只做推荐 + 跟踪，不执行买卖交易
4. **不检测跌停卖出**：当前先聚焦买入端的一字板问题，卖出端的跌停一字板后续再评估（rebalance_engine 卖出时如遇跌停一字板同样无法卖出，但影响较小——最多多持有一天）
