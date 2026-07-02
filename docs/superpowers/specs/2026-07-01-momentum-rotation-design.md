# 量价动量轮动策略 设计文档

**日期**: 2026-07-01
**分支**: feat/momentum-rotation-strategy

## 概述

基于多指数成分股池的横截面排名策略。每只股票按价格动量 + 成交量两个维度打分，Z-score 标准化后加权合成最终得分，取 top N。

## 策略文件

- **路径**: `backend/app/strategies/examples/momentum_rotation.py`
- **模式**: 独立策略文件，`run(data)` 接口（仿 `grow_with_money.py`）
- **数据依赖**: `REQUIRED_DATA = ["index_constituents"]`，仅使用日线 K 线数据

## 参数设计

所有参数通过 `params_schema` 暴露给前端，可在回测时调整：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `index_codes` | list[string] | `[]` | 指数代码列表，空数组时走引擎板块过滤 |
| `N` | int | 10 | 推荐数量（top N） |
| `mom_fast` | int | 20 | 短周期动量窗口（交易日） |
| `mom_slow` | int | 60 | 长周期动量窗口（交易日） |
| `mom_fast_weight` | float | 0.6 | 短周期权重（长周期权重 = 1 − 此值） |
| `vol_short` | int | 5 | 短期均量窗口（交易日） |
| `vol_long` | int | 20 | 长期均量窗口（交易日） |
| `volume_weight` | float | 0.4 | 成交量在总分中的权重 |

## 核心算法

### 股票池构建

1. 若 `index_codes` 非空 → 从 `data["index_constituents"]` 筛选匹配指数的成分股
2. 多指数取并集，`ts_code` 去重
3. 若 `index_codes` 为空 → 不干预，由引擎 `_apply_board_filter` 决定股票池

### 单股计算

对池内每只股票，从 `data["daily"][ts_code]` 获取日线数据：

```
# 动量原始分
ret_fast = (close[-1] / close[-mom_fast] - 1) × 100   # 20日收益率
ret_slow = (close[-1] / close[-mom_slow] - 1) × 100   # 60日收益率
momentum_raw = mom_fast_weight × ret_fast + (1 − mom_fast_weight) × ret_slow

# 量比
avg_vol_short = mean(vol[-vol_short:])
avg_vol_long  = mean(vol[-vol_long:])
volume_ratio  = avg_vol_short / avg_vol_long
```

### 横截面标准化

在股票池内对所有有效股票计算：

```
momentum_z = (momentum_raw − mean(momentum_raw)) / std(momentum_raw)
volume_z   = (volume_ratio − mean(volume_ratio)) / std(volume_ratio)
```

### 最终得分

```
score = (1 − volume_weight) × momentum_z + volume_weight × volume_z
```

按 `score` 降序排列，返回前 `N` 只。

## 数据流

```
BacktestEngine._load_data(cutoff_date)
  ├── stocks:     全量股票基础信息
  ├── daily:      过去 180 天日线（含 open/high/low/close/vol）
  ├── index_constituents: 各指数最新成分股 (REQUIRED_DATA)
  └── config:     策略参数（index_codes, N, mom_fast, ...）

         ↓

momentum_rotation.run(data)
  ├── 1. 解析 config 参数
  ├── 2. 构建股票池（指数成分股去重 或 全量）
  ├── 3. 遍历计算 momentum_raw + volume_ratio
  ├── 4. Z-score 标准化
  ├── 5. 加权合成最终得分
  └── 6. 返回 top N
```

## 边界情况

- **数据不足**: 某只股票日线数据少于 `max(mom_slow, vol_long)` 条 → 跳过
- **股票池为空**: 返回空数组 `[]`
- **标准差为 0**: 所有股票动量/量比相同 → Z-score 为 0（不做标准化）
- **停牌/新上市**: 日线窗口内数据不连续 → 用最近 N 个交易日而非日历日（由 pandas rolling 保证）

## seed 注册

在 `backend/app/seed_strategies.py` 的 `BUILTIN_STRATEGIES` 列表中添加条目：

```python
{
    "name": "动量轮动",
    "description": "量价动量轮动：多指数成分股池，按价格动量+成交量加权排名，选取top N",
    "file_path": "app/strategies/examples/momentum_rotation.py",
    "tags": "动量,量能,轮动,排名,指数成分股",
    "params_schema": json.dumps({...}, ensure_ascii=False),
},
```

## 不做什么

- **不涉及调仓逻辑** — 调仓由回测引擎（或未来 rebalance 引擎）处理
- **不修改 code_generator** — 排名类策略不适合 factor_config 信号体系
- **不增加新数据源** — 仅依赖日线 K 线，不需要资金流/龙虎榜
- **不涉及前端 UI 改动** — `params_schema` 自动渲染为表单
