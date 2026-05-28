# AIpicking v2 - 可视化策略构建器 Spec

> 状态：待确认
> 目标：用户无需编写代码，通过选择/组合因子，像搭积木一样创建量化策略

---

## 1. 核心概念

### 1.1 策略构建模型

```
[用户选择因子] → [配置因子参数] → [组合因子逻辑] → [生成完整策略代码] → [回测]
```

- **因子（Factor）**：最小的可复用策略单元，背后有对应的 Python 程序逻辑
- **因子组合（Factor Combination）**：多个因子通过 AND/OR 逻辑组合
- **策略（Strategy）**：最终生成的完整量化策略程序
- **策略模板**：预置的因子组合方案，用户可直接使用或二次编辑

### 1.2 用户操作流程

1. 新建策略 → 选择策略模板 或 从空白开始
2. 添加因子（买入信号因子、卖出信号因子、风控因子）
3. 配置每个因子的参数
4. 预览生成的策略代码（可选，只读）
5. 保存策略 → 运行回测

---

## 2. 因子库设计

### 2.1 因子分类

| 分类 | 说明 | 典型因子 |
|------|------|----------|
| **趋势类** | 判断价格趋势方向 | MA均线、EMA、布林带、抛物线SAR |
| **动量类** | 判断涨跌动能 | MACD、RSI、KDJ、CCI |
| **量能类** | 判断成交量变化 | 量比、换手率、OBV能量潮 |
| **形态类** | K线形态识别 | 红三兵、乌云盖顶、启明星、吞没形态 |
| **波动率类** | 判断价格波动幅度 | ATR、布林带宽度、历史波动率 |
| **资金流类** | 主力资金动向 | 大单净流入、北向资金、融资余额 |
| **基本面类** | 公司财务指标 | PE、PB、ROE、营收增长率 |
| **风控类** | 止损止盈规则 | 固定止损、追踪止损、时间止损 |

### 2.2 因子定义规范

每个因子在后端对应一个 Python 模块，遵循统一规范：

```python
# backend/app/factors/trend_ma_cross.py

FACTOR_META = {
    "id": "trend_ma_cross",
    "name": "均线金叉/死叉",
    "category": "趋势类",
    "description": "短期均线上穿长期均线形成金叉买入信号，下穿形成死叉卖出信号",
    "params": [
        {
            "name": "short_period",
            "label": "短期均线周期",
            "type": "int",
            "default": 5,
            "min": 1,
            "max": 60
        },
        {
            "name": "long_period",
            "label": "长期均线周期",
            "type": "int",
            "default": 20,
            "min": 5,
            "max": 250
        }
    ],
    "signal_type": "both",  # buy / sell / both
}

def compute(df, params):
    """
    计算因子信号
    df: pandas DataFrame，包含 OHLCV 数据
    params: 用户配置的参数字典
    return: pandas Series，信号列 (1=买入信号, -1=卖出信号, 0=无信号)
    """
    short_ma = df['close'].rolling(params['short_period']).mean()
    long_ma = df['close'].rolling(params['long_period']).mean()
    # 金叉：short_ma上穿long_ma → 1
    # 死叉：short_ma下穿long_ma → -1
    signal = ...
    return signal
```

### 2.3 因子参数类型

| 类型 | 前端组件 | 示例 |
|------|----------|------|
| `int` | InputNumber | 周期参数 |
| `float` | InputNumber | 比例阈值 |
| `enum` | Select | 均线类型（SMA/EMA） |
| `bool` | Switch | 是否启用 |
| `date` | DatePicker | 回测区间 |

---

## 3. 因子库清单（v1 优先实现）

### 3.1 趋势类因子

| ID | 名称 | 说明 | 核心参数 |
|----|------|------|----------|
| `trend_ma_cross` | 均线金叉死叉 | 短均线上穿/下穿长均线 | 短周期、长周期 |
| `trend_ma_support` | 均线支撑 | 股价在均线上方获得支撑 | 均线周期、容差比例 |
| `trend_breakout` | 突破新高 | 股价突破N日最高价 | 观察周期 |
| `trend_boll` | 布林带突破 | 价格突破布林带上轨/下轨 | 周期、标准差倍数 |
| `trend_ema_trend` | EMA趋势 | EMA多头/空头排列 | 短期EMA、长期EMA |

### 3.2 动量类因子

| ID | 名称 | 说明 | 核心参数 |
|----|------|------|----------|
| `momentum_macd` | MACD金叉死叉 | MACD线穿越信号线 | 快线、慢线、信号线周期 |
| `momentum_rsi` | RSI超买超卖 | RSI进入超买/超卖区间 | RSI周期、超买阈值、超卖阈值 |
| `momentum_kdj` | KDJ金叉死叉 | K线与D线的交叉信号 | K周期、D周期、J周期 |
| `momentum_cci` | CCI突破 | CCI突破±100区间 | CCI周期 |

### 3.3 量能类因子

| ID | 名称 | 说明 | 核心参数 |
|----|------|------|----------|
| `volume_ratio` | 量比放大 | 当日量比超过阈值 | 量比阈值 |
| `volume_obv` | OBV能量潮 | OBV创新高/新低 | 观察周期 |
| `volume_turnover` | 换手率筛选 | 换手率在区间内 | 最小换手率、最大换手率 |

### 3.4 形态类因子

| ID | 名称 | 说明 | 核心参数 |
|----|------|------|----------|
| `pattern_morning_star` | 启明星 | 底部反转形态 | 观察周期 |
| `pattern_engulfing` | 吞没形态 | 看涨/看跌吞没 | 观察周期 |
| `pattern_hammer` | 锤子线 | 底部反转K线 | 观察周期 |

### 3.5 风控类因子

| ID | 名称 | 说明 | 核心参数 |
|----|------|------|----------|
| `risk_fixed_stop` | 固定止损 | 跌破买入价N%止损 | 止损比例 |
| `risk_trailing_stop` | 追踪止损 | 从最高价回撤N%止损 | 回撤比例 |
| `risk_take_profit` | 固定止盈 | 盈利N%止盈 | 止盈比例 |
| `risk_max_hold` | 最大持仓时间 | 持仓超过N天强制卖出 | 最大持仓天数 |
| `risk_max_loss` | 最大亏损限额 | 当日亏损超N%停止交易 | 亏损比例 |

---

## 4. 策略生成逻辑

### 4.1 策略结构模板

生成的策略代码遵循统一结构：

```python
# 自动生成的策略代码 - [策略名称]
# 生成时间: [timestamp]

import pandas as pd
import numpy as np

# 自动导入因子
from factors.trend_ma_cross import compute as trend_ma_cross_compute
from factors.momentum_rsi import compute as momentum_rsi_compute
from factors.risk_fixed_stop import compute as risk_fixed_stop_compute

class Strategy:
    """用户策略：[策略名称]"""

    def __init__(self, params=None):
        self.params = params or {}

    def generate_signals(self, df):
        """生成买卖信号"""
        signals = pd.DataFrame(index=df.index)
        signals['buy'] = 0
        signals['sell'] = 0

        # 买入信号因子（AND逻辑：所有条件同时满足）
        buy_signals = []
        buy_signals.append(trend_ma_cross_compute(df, self.params.get('trend_ma_cross', {})) == 1)
        buy_signals.append(momentum_rsi_compute(df, self.params.get('momentum_rsi', {})) == 1)
        # ... 更多因子

        signals['buy'] = np.logical_and.reduce(buy_signals).astype(int)

        # 卖出信号因子
        sell_signals = []
        sell_signals.append(risk_fixed_stop_compute(df, self.params.get('risk_fixed_stop', {})) == -1)
        # ... 更多因子

        signals['sell'] = np.logical_or.reduce(sell_signals).astype(int)

        return signals

    def run(self, df, initial_capital=100000):
        """执行回测"""
        signals = self.generate_signals(df)
        # ... 回测逻辑
        return results
```

### 4.2 因子组合逻辑

- **买入信号**：多个因子支持 AND / OR 逻辑组合
  - AND：所有因子同时发出买入信号才买入
  - OR：任一因子发出买入信号即买入
- **卖出信号**：多个因子使用 OR 逻辑（任一卖出信号即卖出）
- **风控因子**：独立执行，优先级最高（触发即卖出）

---

## 5. 前端页面设计

### 5.1 策略构建器页面（新增 `StrategyBuilder.tsx`）

布局：

```
┌─────────────────────────────────────────────────────┐
│ 策略名称: [_________]  策略描述: [_________]  保存 │
├────────────┬────────────────────────────────────────┤
│  因子库     │  策略画布                              │
│            │                                        │
│ [搜索框]   │  ┌─────────────────────────────┐      │
│            │  │ 买入信号因子                  │      │
│ ▸ 趋势类   │  │ ┌─────────┐ AND/OR ┌──────┐│      │
│   · MA金叉 │  │ │MA金叉   │        │RSI   ││      │
│   · 均线支撑│  │ │[配置]   │        │[配置]││      │
│            │  │ └─────────┘        └──────┘│      │
│ ▸ 动量类   │  └─────────────────────────────┘      │
│   · MACD  │  ┌─────────────────────────────┐      │
│   · RSI   │  │ 卖出信号因子                  │      │
│            │  │ ┌─────────┐ ┌────────────┐  │      │
│ ▸ 量能类   │  │ │固定止损 │ │追踪止损    │  │      │
│   · 量比  │  │ │[配置]   │ │[配置]      │  │      │
│            │  │ └─────────┘ └────────────┘  │      │
│ ▸ 形态类   │  └─────────────────────────────┘      │
│            │  ┌─────────────────────────────┐      │
│ ▸ 风控类   │  │ 风控因子（始终生效）          │      │
│   · 止损  │  │ ┌─────────┐ ┌────────────┐  │      │
│   · 止盈  │  │ │固定止损 │ │最大持仓    │  │      │
│            │  │ │[配置]   │ │[配置]      │ │      │
│            │  │ └─────────┘ └────────────┘  │      │
│            │  └─────────────────────────────┘      │
│            │  [预览代码] [运行回测]                 │
└────────────┴────────────────────────────────────────┘
```

### 5.2 因子卡片组件

每个已添加的因子显示为可折叠卡片：
- 因子名称 + 分类标签
- 参数配置表单（根据因子 `params` 定义动态渲染）
- 删除按钮

---

## 6. 后端 API 设计（新增/修改）

### 6.1 因子相关 API（新增）

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/v1/factors` | 获取所有因子列表（按分类） |
| `GET` | `/api/v1/factors/{factor_id}` | 获取单个因子详情（含参数定义） |
| `POST` | `/api/v1/factors/{factor_id}/compute` | 测试因子计算（传入数据和参数，返回信号） |

### 6.2 策略相关 API（修改）

| Method | Path | 说明 |
|--------|------|------|
| `POST` | `/api/v1/strategies` | 新建策略（传入因子配置，后端生成代码） |
| `PUT` | `/api/v1/strategies/{id}` | 更新策略因子配置 |
| `GET` | `/api/v1/strategies/{id}/code` | 查看生成的策略代码 |
| `POST` | `/api/v1/strategies/{id}/generate` | 重新生成策略代码 |

### 6.3 策略配置数据结构

```json
{
  "name": "MA+RSI双因子策略",
  "description": "均线金叉配合RSI超卖买入",
  "buy_signals": {
    "logic": "AND",
    "factors": [
      {
        "factor_id": "trend_ma_cross",
        "params": {"short_period": 5, "long_period": 20}
      },
      {
        "factor_id": "momentum_rsi",
        "params": {"period": 14, "oversold": 30, "overbought": 70}
      }
    ]
  },
  "sell_signals": {
    "factors": [
      {
        "factor_id": "risk_fixed_stop",
        "params": {"stop_loss_pct": 5.0}
      }
    ]
  },
  "risk_factors": [
    {
      "factor_id": "risk_max_hold",
      "params": {"max_days": 5}
    }
  ]
}
```

---

## 7. 数据库变更

### 7.1 `strategies` 表新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `factor_config` | JSON | 因子配置（取代原来的 code） |
| `generated_code` | TEXT | 生成的策略代码（只读） |
| `code_hash` | VARCHAR | 代码哈希（防止重复生成） |

### 7.2 新增 `factors` 表（可选，也可直接从文件系统读取）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR | 因子ID |
| `name` | VARCHAR | 因子名称 |
| `category` | VARCHAR | 分类 |
| `description` | TEXT | 描述 |
| `params_schema` | JSON | 参数定义 |
| `signal_type` | VARCHAR | buy/sell/both |
| `is_active` | BOOLEAN | 是否启用 |

---

## 8. 实施计划

| 阶段 | 内容 | 状态 |
|------|------|------|
| **Phase 1** | 因子库框架搭建（Factor base class + 5个核心因子） | 待确认 |
| **Phase 2** | 前端策略构建器页面（StrategyBuilder） | 待确认 |
| **Phase 3** | 策略代码生成引擎 | 待确认 |
| **Phase 4** | 因子计算 API（实时预览信号） | 待确认 |
| **Phase 5** | 完善因子库（15+ 因子） | 待确认 |
| **Phase 6** | 策略模板市场 | 待确认 |

---

## 9. AI 策略生成接口（新增）

### 9.1 功能描述

用户用自然语言描述策略意图，AI 将其翻译为因子组合配置（或可直接执行的 Python 代码），降低策略创建门槛。

**示例输入**：
> "我想做一个均线金叉策略，5日均线上穿20日均线时买入，跌破买入价5%止损"

**AI 输出**（因子组合配置）：
```json
{
  "name": "AI生成的均线金叉策略",
  "description": "5日均线上穿20日均线买入，5%止损",
  "buy_signals": {
    "logic": "AND",
    "factors": [
      {
        "factor_id": "trend_ma_cross",
        "params": {"short_period": 5, "long_period": 20}
      }
    ]
  },
  "sell_signals": {
    "factors": [
      {
        "factor_id": "risk_fixed_stop",
        "params": {"stop_loss_pct": 5.0}
      }
    ]
  },
  "risk_factors": []
}
```

### 9.2 API 设计

| Method | Path | 说明 |
|--------|------|------|
| `POST` | `/api/v1/ai/generate-strategy` | 自然语言 → 策略配置 |

**请求体**：
```json
{
  "prompt": "5日均线上穿20日均线买入，跌破买入价5%止损"
}
```

**响应**：
```json
{
  "code": 200,
  "data": {
    "name": "AI生成的均线金叉策略",
    "factor_config": { ... },  // 因子组合配置
    "explanation": "已为您配置均线金叉买入因子和5%固定止损..." // AI解释
  }
}
```

### 9.3 技术实现方案

**方案A（推荐）：LLM + Few-shot Prompt**
- 后端调用 LLM API（OpenAI / 混元 / 本地 Ollama）
- Prompt 中注入因子库元数据（所有因子的 ID、名称、参数）
- 要求 LLM 输出结构化 JSON（因子组合配置）
- 后端校验 JSON 合法性后保存

**方案B：规则解析（MVP 过渡）**
- 关键词匹配（"金叉" → `trend_ma_cross`，"止损" → `risk_fixed_stop`）
- 正则提取参数（"5日" → `short_period=5`）
- 不依赖外部 API，但覆盖场景有限

**推荐先实现方案B（MVP），再升级到方案A**

### 9.4 前端交互

在 `StrategyBuilder` 页面新增「AI 助手」入口：

```
┌─────────────────────────────────────────────────────┐
│ [AI 助手] 按钮                                      │
├─────────────────────────────────────────────────────┤
│  💡 用自然语言描述你的策略想法...                    │
│  ┌─────────────────────────────────┐ [生成策略]     │
│  │ 5日均线上穿20日均线买入...       │               │
│  └─────────────────────────────────┘               │
│                                                     │
│  AI 生成的策略预览：                                 │
│  ✓ 买入信号: MA金叉 (5, 20)                        │
│  ✓ 卖出信号: 固定止损 (5%)                          │
│  [采纳并应用] [重新生成] [手动调整]                  │
└─────────────────────────────────────────────────────┘
```

---

## 10. 回测与策略执行功能设计

> 状态：已确认，开始 coding
> 目标：验证策略在历史某日推荐的股票在后续 3/7/15 天的表现；执行策略获得当前推荐股票

---

### 10.1 核心逻辑

**回测（验证策略有效性）**：
```
设置截止日（cutoff_date）→ 用截止日及之前的数据运行策略
→ 选出评分最高的 5-10 只股票
→ 追踪这些股票在截止日后 3/7/15 天的涨跌幅
→ 汇总展示（平均收益、胜率等指标）
```

**执行策略（获得当前推荐）**：
```
用今日及之前的数据运行策略 → 选出评分最高的 5-10 只股票
→ 展示在页面，作为今日/明日买入参考
```

> 执行策略 = 回测的特例（cutoff_date = 今日），复用同一套引擎。

---

### 10.2 用户操作流程

#### 回测流程
1. 在策略详情页点击「运行回测」
2. 选择截止日（cutoff_date），可选填写追踪天数（默认 3/7/15）
3. 提交后异步执行，轮询状态直到 completed
4. 查看回测报告（推荐股票列表 + 后续表现 + 汇总指标）

#### 执行策略流程
1. 在策略列表页或详情页点击「执行策略」
2. 用今日数据运行，立即返回推荐股票
3. 展示推荐结果（股票列表 + 评分 + 信号说明）

---

### 10.3 回测引擎设计（后端）

**核心文件**：`backend/app/services/backtest_engine.py`

#### 执行步骤

```
输入：strategy_id, cutoff_date, track_days=[3,7,15]
  │
  ├─ 1. 加载截止日及之前的所有历史数据（从 stock_db.sqlite）
  │
  ├─ 2. 运行策略代码（动态加载策略的 Python 文件）
  │      → 对全市场股票计算信号得分
  │      → 选出得分最高的 5-10 只股票
  │
  ├─ 3. 对每只推荐股票，查询其在 cutoff_date 后 N 天的收盘价
  │      → 计算 N 天涨跌幅：（第N天收盘价 - 截止日收盘价）/ 截止日收盘价
  │
  └─ 4. 汇总结果
         → 每只股票：ts_code, name, score, return_3d, return_7d, return_15d
         → 汇总指标：avg_return_3d, avg_return_7d, avg_return_15d, win_rate_3d, ...
```

#### 策略执行接口（Python 函数签名）

策略生成的 Python 文件需实现：

```python
def run_strategy(data: dict) -> list[dict]:
    """
    运行策略，返回推荐股票列表

    Args:
        data: {
            "cutoff_date": "20260525",   # 截止日，格式 YYYYMMDD
            "stocks": [...],              # 股票基础信息（来自 stocks 表）
            "daily": {...},               # 日线数据，按 ts_code 索引，每个值是日期->OHLC 的 dict
        }

    Returns:
        list[dict]: 推荐股票列表，按得分降序排序，例如：
        [
            {"ts_code": "000001.SZ", "name": "平安银行", "score": 85.2, "signal": "MA金叉+RSI超卖"},
            ...
        ]
    """
```

#### 数据源
- **数据库路径**（固定）：`/Users/aklu/workbuddy/2026-05-22-21-48-44/data/stock_db.sqlite`
- **数据范围**：过去 5 年，全市场 A 股日级别交易数据
- **表结构**：
  - `stocks` 表：股票基础信息
    - `ts_code` (TEXT, PK) — Tushare 代码，如 `000001.SZ`
    - `symbol` (TEXT) — 股票代码，如 `000001`
    - `name` (TEXT) — 股票名称
    - `market` (TEXT) — 市场代码
    - `industry_l1/l2/l3` (TEXT) — 行业分类
    - `concepts` (TEXT) — 概念标签（JSON 数组）
    - `total_shares` (INTEGER) — 总股本（股）
    - `float_shares` (INTEGER) — 流通股本（股）
  - `daily` 表：日线行情
    - `ts_code` (TEXT) — Tushare 代码
    - `trade_date` (TEXT) — 交易日期，格式 `YYYYMMDD`
    - `open/high/low/close` (REAL) — OHLC
    - `vol` (REAL) — 成交量（手）
    - `amount` (REAL) — 成交额（千元）
    - `adj_close` (REAL) — 复权收盘价
    - `market_cap` (REAL) — 总市值（亿元）
    - `circ_market_cap` (REAL) — 流通市值（亿元）
    - **主键**：`(ts_code, trade_date)`
    - **索引**：`idx_daily_date(trade_date)`、`idx_daily_code(ts_code)`

---

### 10.4 回测报告数据结构

**数据库模型**：`BacktestReport`（表名：`backtest_reports`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer (PK) | 主键 |
| `strategy_id` | Integer (FK) | 关联策略 ID |
| `name` | String(255) | 报告名称（自动生成：策略名+截止日） |
| `status` | String(50) | 状态：pending → running → completed / failed |
| `cutoff_date` | String(8) | 截止日，格式 `YYYYMMDD` |
| `config` | Text (JSON) | 配置（track_days 等） |
| `recommendations` | Text (JSON) | 推荐股票列表（完成后填充） |
| `summary` | Text (JSON) | 汇总指标（完成后填充） |
| `error_message` | Text | 错误信息（失败时填充） |
| `started_at` | DateTime | 开始执行时间 |
| `completed_at` | DateTime | 完成时间 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

**recommendations 字段内容**（推荐股票列表）：

```json
[
  {
    "ts_code": "000001.SZ",
    "name": "平安银行",
    "score": 85.2,
    "signal": "MA金叉+RSI超卖",
    "return_3d": 0.023,    // 3天后涨跌幅（2.3%）
    "return_7d": 0.051,    // 7天后涨跌幅
    "return_15d": 0.112    // 15天后涨跌幅
  }
]
```

**summary 字段内容**（汇总指标）：

```json
{
  "total_recommendations": 8,
  "avg_return_3d": 0.018,
  "avg_return_7d": 0.042,
  "avg_return_15d": 0.087,
  "win_rate_3d": 0.75,      // 3天胜率（涨跌幅>0的比例）
  "win_rate_7d": 0.625,
  "win_rate_15d": 0.875,
  "best_return_15d": 0.215,  // 15天最高涨幅
  "worst_return_15d": -0.032 // 15天最大跌幅
}
```

---

### 10.5 后端 API 设计

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/v1/backtests` | 获取回测报告列表（分页、按 strategy_id 筛选） |
| `POST` | `/api/v1/backtests` | 提交回测任务（异步执行，立即返回 202） |
| `GET` | `/api/v1/backtests/{id}` | 获取回测报告详情 |
| `DELETE` | `/api/v1/backtests/{id}` | 删除回测报告 |
| `POST` | `/api/v1/strategies/{id}/execute` | 执行策略（同步，立即返回推荐结果） |

**提交回测请求体**
```json
{
  "strategy_id": 1,
  "cutoff_date": "20260501",
  "track_days": [3, 7, 15]
}
```

**响应（提交后立即返回）**
```json
{
  "code": 0,
  "data": {
    "id": 1,
    "strategy_id": 1,
    "name": "MA+RSI双因子策略_20260501",
    "status": "pending",
    "cutoff_date": "20260501",
    "created_at": "2026-05-25T14:00:00"
  }
}
```

**执行策略请求**
```
POST /api/v1/strategies/{id}/execute
```
无需请求体（cutoff_date 默认为今日）。

**执行策略响应**（同步返回）
```json
{
  "code": 0,
  "data": {
    "strategy_id": 1,
    "strategy_name": "MA+RSI双因子策略",
    "cutoff_date": "20260525",
    "recommendations": [
      {
        "ts_code": "000001.SZ",
        "name": "平安银行",
        "score": 85.2,
        "signal": "MA金叉+RSI超卖"
      }
    ],
    "total": 8
  }
}
```

---

### 10.6 前端页面设计

#### 10.6.1 回测表单页（`/strategies/:id/backtest`）

从策略详情页点击「运行回测」进入。

```
┌─────────────────────────────────────────────────────┐
│  回测配置 - MA+RSI双因子策略                      │
├─────────────────────────────────────────────────────┤
│  截止日（必选）：                                 │
│  [DatePicker: 2026-05-01]                        │
│                                                     │
│  追踪天数：[✓3天] [✓7天] [✓15天]               │
│                                                     │
│            [取消]  [提交回测]                      │
└─────────────────────────────────────────────────────┘
```

#### 10.6.2 回测报告列表页（`/backtests`）

```
┌─────────────────────────────────────────────────────┐
│  回测报告                [前往策略列表]             │
├─────────────────────────────────────────────────────┤
│  [状态筛选: 全部 ▼]                               │
│                                                     │
│  ID | 策略名称 | 截止日 | 状态 | 3天收益 | 创建时间 | 操作 │
│  ───────────────────────────────────────────────  │
│   3 | MA策略   | 0501  | ✅完成 | +1.8% | 05-25 | 查看 删除 │
│   2 | RSI策略  | 0420  | ✅完成 | -0.5% | 05-20 | 查看 删除 │
│   1 | 双因子   | 0510  | ⏳运行中| —     | 05-25 | 查看      │
│                                                     │
│  [< 上一页  1 / 3  下一页 >]                     │
└─────────────────────────────────────────────────────┘
```

#### 10.6.3 回测报告详情页（`/backtests/:id`）

```
┌─────────────────────────────────────────────────────┐
│  回测报告 - MA+RSI双因子策略_20260501             │
├─────────────────────────────────────────────────────┤
│  截止日：2026-05-01  |  状态：✅ 已完成           │
│  执行时间：2026-05-25 14:00                       │
│                                                     │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐         │
│  │3天平均│ │7天平均│ │15天平│ │3天胜 │  (卡片)  │
│  │ +1.8% │ │ +4.2%│ │ +8.7%│ │ 75%  │         │
│  └──────┘ └──────┘ └──────┘ └──────┘         │
│                                                     │
│  推荐股票及后续表现：                                │
│  ─────────────────────────────────────────────  │
│  股票  | 得分 | 信号说明   | 3天涨跌 | 7天涨跌 | 15天涨跌 │
│  平安银行 | 85.2 | MA金叉  | +2.3%  | +5.1%  | +11.2%  │
│  XX科技  | 78.5 | RSI超卖 | +1.2%  | +3.8%  | +8.7%   │
│  ...                                              │
│                                                     │
│  [下载 JSON]                                        │
└─────────────────────────────────────────────────────┘
```

#### 10.6.4 策略执行结果页（`/strategies/:id/execute` 或弹窗）

```
┌─────────────────────────────────────────────────────┐
│  策略执行结果 - MA+RSI双因子策略   2026-05-25      │
├─────────────────────────────────────────────────────┤
│  数据截止日：2026-05-25                             │
│                                                     │
│  推荐股票（按得分排序）：                            │
│  ─────────────────────────────────────────────  │
│  排名 | 股票  | 得分 | 信号说明   | 最新价 | 操作 │
│  1   | 平安银行 | 85.2 | MA金叉  | 12.50  | 加入自选 │
│  2   | XX科技  | 78.5 | RSI超卖 | 25.30  | 加入自选 │
│  ...                                              │
│                                                     │
│            [关闭]                                   │
└─────────────────────────────────────────────────────┘
```

---

### 10.7 实施计划（回测功能）

| 阶段 | 内容 | 状态 |
|------|------|------|
| **Step 1** | 创建 BacktestReport 数据库模型和 Pydantic schemas | 待开始 |
| **Step 2** | 实现回测引擎 `backtest_engine.py`（加载数据 → 运行策略 → 追踪表现） | 待开始 |
| **Step 3** | 实现回测 API（`POST /api/v1/backtests`、`GET /api/v1/backtests/{id}` 等） | 待开始 |
| **Step 4** | 实现策略执行 API（`POST /api/v1/strategies/{id}/execute`） | 待开始 |
| **Step 5** | 前端回测表单页（`/strategies/:id/backtest`） | 待开始 |
| **Step 6** | 前端回测报告列表页和详情页 | 待开始 |
| **Step 7** | 前端策略执行结果页/弹窗 | 待开始 |
| **Step 8** | 增加 E2E 测试 | 待开始 |

---

## 11. 待讨论问题

1. **因子代码存储方式**（已确认）：✅ 文件系统，每个因子一个 `.py`
2. **策略代码生成方式**：模板渲染（Jinja2）vs AST拼接？推荐模板渲染
3. **因子参数优化**：是否需要支持参数自动优化（遗传算法/网格搜索）？（v2 再做）
4. **AI 接口 LLM 选择**：OpenAI API / 腾讯混元 / 本地 Ollama / 其他？
5. **高级模式**：✅ 保留，允许高级用户自定义因子（写Python代码）

---

## 11. 实施计划（确认后执行）

| 阶段 | 内容 | 预估时间 |
|------|------|----------|
| **Phase 1** | 因子库框架 + 15个核心因子（文件系统） | 1天 |
| **Phase 2** | 后端 API（因子列表、策略生成引擎、代码渲染） | 1天 |
| **Phase 3** | 前端策略构建器页面（StrategyBuilder） | 1天 |
| **Phase 4** | AI 策略生成接口（先规则解析 MVP） | 0.5天 |
| **Phase 5** | 整合测试 + 清理旧代码（上传策略相关） | 0.5天 |

**总计：约 4 天可完成基础版本**

---

*此文档已根据用户反馈更新（2026-05-25）：*
- *✅ 确认先用 15 个因子，后续扩展*
- *✅ 因子代码用文件系统存储*
- *✅ 不做实时信号预览，先做日K级别*
- *✅ 保留高级模式（用户自定义因子）*
- *✅ 新增 AI 接口，支持自然语言 → 策略配置*

*请确认 AI 接口的 LLM 选择，以及实施计划是否可接受。确认后开始编码。*
