# Backtest Engine

## 概述

回测在**线程池**中运行（`loop.run_in_executor`），避免 CPU 密集的 pandas 操作阻塞事件循环。

策略代码通过 **AST 沙箱**校验，禁止 `os`、`sys`、`exec`、`eval` 等危险调用。

支持 `run(data)` 函数接口，适用于买入/卖出信号类和相似度匹配类策略。推荐结果必须包含 `signal` 字段。

## Factor Library (`app/factors/`)

| 目录 | 因子 |
|------|------|
| `momentum/` | KDJ, MACD, RSI |
| `trend/` | Breakout, MA cross, MA support |
| `volume/` | OBV, turnover, volume ratio |
| `pattern/` | Engulfing, hammer, morning star |
| `risk/` | Fixed stop, take profit, trailing stop |

## REQUIRED_DATA 机制

策略可通过声明 `REQUIRED_DATA` 来控制加载哪些额外数据源。不声明则加载全部（向后兼容）。

```python
REQUIRED_DATA = []                                    # 仅 stocks + daily
REQUIRED_DATA = ["dragon_tiger"]                      # + 龙虎榜
REQUIRED_DATA = ["sector_flow", "dragon_tiger"]       # + 两者
```

### 数据源映射

| Source | Tables | 触发条件 |
|--------|--------|---------|
| (core, always loaded) | `stocks`, `daily` | 所有策略 |
| `sector_flow` | `daily_sector_flow` | Tier 2 `sf_*` 条件 |
| `dragon_tiger` | `daily_dragon_tiger`, `daily_dragon_tiger_seats` | Tier 2 `dt_*` 条件 |
| `hot_stocks` | `daily_hot_stock` | (当前因子未使用) |
| `hot_themes` | `daily_hot_theme` | (当前因子未使用) |

## 关键模式：`select(Model.__table__)`

**非核心表的查询必须使用 `select(Model.__table__)`（Core 级别），而非 `select(Model)`（ORM 级别）。**

ORM 级别的 select 会导致 `dict(row._mapping)` 返回 `{'ModelName': <object>}` 而非 `{'column_name': value, ...}`，破坏策略代码中 `row["column_name"]` 的取值方式。

## code_generator.py 自动推断

`code_generator.py` 根据 `factor_config` 自动推断 `REQUIRED_DATA`：
- `selection_conditions` / `scoring_modifiers` 含 `dt_*` ID → `dragon_tiger`
- `selection_conditions` / `scoring_modifiers` 含 `sf_*` ID → `sector_flow`
- 纯 K 线因子 → `REQUIRED_DATA = []`
