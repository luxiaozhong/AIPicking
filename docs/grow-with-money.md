# grow_with_money — 成长100 + 资金流选股策略

## 策略逻辑

1. 以**国证成长100（980080）**指数成分股为股票池
2. 计算每只成分股过去 **M** 个交易日的**主力净流入总额**
3. 按资金流总额降序排列，取前 **N** 只推荐

## 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `index_code` | string | `"980080"` | 指数代码（国证成长100） |
| `N` | int | 5 | 推荐股票数量 |
| `M` | int | 20 | 资金流回顾天数（交易日） |

## 用法

### 1. 框架回测（BacktestEngine）

策略文件：`backend/app/strategies/examples/grow_with_money.py`

策略已在数据库中注册（id=85），可直接通过 API 使用：

```bash
# 单日回测
curl -X POST http://localhost:8000/api/v1/backtests \
  -H "Authorization: Bearer ..." \
  -d '{
    "strategy_id": 85,
    "cutoff_date": "20260119",
    "track_days": [3, 7, 15],
    "config": {"N": 5, "M": 10}
  }'

# 执行策略（实时推荐，不追踪表现）
curl -X POST "http://localhost:8000/api/v1/backtests/execute/85?cutoff_date=20260612" \
  -H "Authorization: Bearer ..."
```

### 2. 直接调用引擎

```python
from app.services.backtest_engine import BacktestEngine

with open('app/strategies/examples/grow_with_money.py') as f:
    code = f.read()

engine = BacktestEngine(
    strategy_code=code,
    strategy_params={},
    config={"N": 5, "M": 20, "board_filter": ["60","00","688","689","300","301"]}
)
result = engine.run(cutoff_date="20260119", track_days=[3, 7, 15])
for rec in result["recommendations"]:
    print(f"{rec['ts_code']} {rec['name']} score={rec['score']}")
```

### 3. 交易模拟

策略支持回测框架的批量回测和交易模拟（trade-sim），参数通过 `config` 传入。

## 数据依赖

策略声明 `REQUIRED_DATA = ["fund_flow", "index_constituents"]`，回测引擎自动加载：

| 数据源 | 表 | 说明 |
|--------|-----|------|
| `fund_flow` | `daily_stock_fund_flow` | 个股每日主力净流入（120 自然日窗口） |
| `index_constituents` | `index_constituents` | 最新指数成分股列表 |

### 前置条件

- `daily_stock_fund_flow` 表需要有多天历史数据（策略需要 M 日回顾窗口）
- `index_constituents` 表已同步最新成分股（运行 `sync_index_constituents.py`）

## 2026-01-19 回测结果示例

```
M=10, N=5, cutoff=2026-01-19

  002222.SZ  福晶科技   score=21.9   3d=-2.80%   7d=-0.07%
  600150.SH  中国船舶   score=16.1   3d=+0.87%   7d=-2.96%
  002558.SZ  巨人网络   score=13.1   3d=-1.20%   7d=-10.27%
  301308.SZ  江波龙     score=8.8    3d=+7.60%   7d=+10.39%
  002851.SZ  麦格米特   score=7.0    3d=+7.10%   7d=+30.69%

  3d avg=+2.31%  win=60%
  7d avg=+5.55%  win=40%
```

## 架构设计

```
grow_with_money.py (strategy)
  │ REQUIRED_DATA = ["fund_flow", "index_constituents"]
  │
  ├─ BacktestEngine._load_data()
  │   ├─ _load_fund_flow()      → daily_stock_fund_flow（120天）
  │   └─ _load_index_constituents() → index_constituents（最新调样）
  │
  └─ run(data)
      ├─ 过滤成分股（index_code=980080）
      ├─ 映射 raw_code → ts_code（via stocks 表）
      ├─ 聚合 M 日主力净流入
      └─ 返回 top N 推荐
```

## 扩展

修改 `config.index_code` 即可切换到其他指数（需先同步对应成分股数据）。
