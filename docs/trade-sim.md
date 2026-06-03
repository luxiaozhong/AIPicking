# 交易模拟 (Trade Sim)

## 概述

交易模拟在策略回测基础上增加真实资金管理维度：用户输入投资总额 → 资金均分到策略评分前 N 只股票 → 逐日追踪 → 执行止损止盈 → 记录逐笔交易明细和汇总。

与简单回测的区别：回测只看"推荐股票在 N 天后的平均收益"；交易模拟模拟真实的买入、持仓、卖出全过程，考虑买卖时机和持仓纪律。

## 核心流程

```
用户提交 → 策略选股（score 降序取 top N）
        → 资金均分（total_amount / top_n = 每只 allocated）
        → 逐股模拟：
           买入日 = cutoff_date 后第一个交易日（以开盘价成交）
           逐日循环：
             a. 更新最高价/最低价
             b. 计算 MA10（用于止损参考线）
             c. 检查止损止盈因子 → 触发则次日开盘价卖出
             d. 检查强制平仓（持有超过 max_hold_days 天）
           统计：收益、胜率、盈亏比、最大连续盈亏、收益分布
```

## 数据模型

### trade_sim_reports（单日）

| 字段 | 说明 |
|------|------|
| `strategy_id` | 策略 FK |
| `user_id` | 用户 FK |
| `cutoff_date` | 选股截止日 |
| `config` | JSON: `{total_amount, top_n, max_hold_days, stop_factors: [...]}` |
| `trades` | JSON 数组：逐笔交易明细（含 `daily_tracking`） |
| `summary` | JSON: 汇总统计 |
| `status` | pending / running / completed / failed |

### batch_trade_sim_reports（批量）

| 字段 | 说明 |
|------|------|
| `strategy_id` | 策略 FK |
| `user_id` | 用户 FK |
| `name` | 报告名称 |
| `start_date` / `end_date` | 日期范围 (YYYYMMDD) |
| `config` | 同单日 |
| `total_days` / `completed_days` | 总交易日数 / 已完成数 |
| `daily_results` | JSON 数组：每日的 `{cutoff_date, trades, summary, status}` |
| `status` | pending / running / completed / failed |

## API

Base: `/api/v1/trade-sims`

| Method | Path | 说明 |
|--------|------|------|
| POST | `/` | 提交单日交易模拟（异步） |
| GET | `/` | 列表（支持 `?status=&strategy_id=` 筛选） |
| GET | `/factors` | 获取可用止损止盈因子列表 |
| GET | `/:id` | 单日详情（含 trades + summary） |
| DELETE | `/:id` | 删除 |
| POST | `/batch` | 提交批量交易模拟 |
| GET | `/batch` | 批量列表（支持 `?strategy_id=` 筛选） |
| GET | `/batch/:id` | 批量详情（含 daily_results） |
| DELETE | `/batch/:id` | 删除批量 |

## 止损止盈因子

定义在 `backend/app/factors/trade_sim_stops.py`，通过 `StopFactorRegistry` 注册。

### 内置因子

| ID | 名称 | 参数 | 逻辑 |
|----|------|------|------|
| `stop_prev_low` | 破前低止损 | `ref_days` (默认20) | 当日收盘价 < ref_days 日前收盘价触发 |
| `stop_ma10_cross` | MA10跌破止损 | `coefficient` (默认0.93), `buffer_days` (默认2) | 连续 buffer_days 天收盘价 < MA10 × coefficient |
| `take_profit_pct` | 固定止盈 | `profit_pct` (默认5.0) | 涨幅 ≥ profit_pct% 触发 |

### 扩展方式

```python
# backend/app/factors/trade_sim_stops.py

def _check_my_factor(df: list, position: dict, params: dict) -> Optional[TriggerResult]:
    # df: 该股从买入日到当前日的日线数据
    # position: {buy_price, buy_date, buy_idx}
    # params: 因子参数
    ...
    if 触发条件:
        return TriggerResult(reason="触发描述")
    return None  # 未触发

StopFactorRegistry.register(
    id="my_factor",
    name="因子中文名",
    params=[ParamDef(name="param1", type="float", default=1.0, description="参数说明")],
    check_fn=_check_my_factor,
)
```

## 引擎架构

`TradeSimEngine` (`backend/app/services/trade_sim_engine.py`) 复用 `BacktestEngine` 的策略加载和数据加载能力：

- `run(cutoff_date)` — 单日模拟，返回 `{trades, summary}`
- `run_batch(start_date, end_date)` — 批量模拟，遍历每个交易日调用 `run()`

### 关键设计

1. **复用 BacktestEngine**：策略代码加载（AST 沙箱）、日线数据加载（`_load_data` / `_load_data_range`）均通过组合复用
2. **买入价 = 开盘价**：买入日为 cutoff_date 后第一个交易日，以开盘价成交
3. **卖出价 = 次日开盘价**：触发止损止盈的当天以收盘价判断，次日以开盘价卖出（模拟真实执行延迟）；若触发日为追踪最后一天，以收盘价卖出
4. **日内极值追踪**：`high_price` / `low_price` 使用日内最高/最低价（非收盘价），更真实反映持仓风险
5. **MA10 实时计算**：逐日基于前 10 个交易日收盘价计算，用于止损参考线展示

## 前端

- **TradeSimList** — 统一页面，Radio.Group 切换「单日交易模拟」/「批量交易模拟」
- **TradeSimDetail** — 单日详情：策略摘要 + 逐笔交易卡片（含 daily_tracking 走势图）
- **BatchTradeSimDetail** — 批量详情：进度条 + 每日结果折叠面板
- **BacktestForm** — 回测表单底部有「交易模拟」入口，可配置投资总额、选股数、持仓天数、止损因子

## 与回测的对比

| 维度 | 简单回测 | 交易模拟 |
|------|---------|---------|
| 选股方式 | 策略推荐 | 策略推荐（相同） |
| 跟踪方式 | N 天后直接看收益 | 逐日跟踪，可中途卖出 |
| 卖点 | 无（固定持有 N 天） | 止损止盈 + 强制平仓 |
| 资金 | 无概念 | 投资总额 → 均分 → 持股数 |
| 输出 | 平均收益 + 胜率 | 逐笔交易 + 日内追踪 + 收益分布 |
| 适用场景 | 策略信号质量快速验证 | 真实交易模拟，评估策略可执行性 |
