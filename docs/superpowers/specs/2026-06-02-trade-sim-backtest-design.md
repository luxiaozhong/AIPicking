# 交易模拟回测 — 设计文档

> 日期：2026-06-02 | 状态：待实现

## 概述

在现有回测系统（"截止日选股 → 追踪 N 日涨跌幅"）基础上，新增**交易模拟模式**。用户输入投资总额，资金平均分配到策略评分最高的前 N 只股票，逐日追踪股价并执行止损/止盈条件，生成逐笔交易明细和汇总报表。

---

## 一、架构

### 1.1 整体方案

采用**方案 B：独立引擎 + 独立存储 + 共用页面**。

- 新建 `TradeSimEngine` 类（组合复用 `BacktestEngine` 的数据加载）
- 新建 `trade_sim_reports` 表
- API 路由和前端页面通过 mode 参数共用，模式切换在 `BacktestForm` 中完成

### 1.2 新增文件

```
backend/app/
├── services/
│   ├── trade_sim_engine.py          # 新增：交易模拟引擎核心
│   └── trade_sim_service.py         # 新增：业务逻辑层
├── models/
│   └── trade_sim.py                 # 新增：TradeSimReport 模型
├── schemas/
│   └── trade_sim.py                 # 新增：Pydantic 请求/响应
├── api/
│   └── trade_sims.py                # 新增：API 路由
└── factors/
    └── trade_sim_stops.py           # 新增：止损止盈因子注册表

frontend/src/
├── pages/
│   ├── BacktestForm.tsx             # 改造：增加模式切换 + 交易模拟表单
│   ├── BacktestDetail.tsx           # 改造：按模式渲染不同报表
│   └── TradeSimDetail.tsx           # 新增：交易模拟报表组件
├── types/
│   └── tradeSim.ts                  # 新增：TypeScript 类型
└── services/
    └── tradeSimService.ts           # 新增：API 调用封装
```

### 1.3 改造文件

| 文件 | 改动 |
|------|------|
| `backend/app/main.py` | 注册 `trade_sims` 路由 |
| `frontend/src/App.tsx` | 无需改路由，详情页按模式切换 |
| `frontend/src/pages/BacktestForm.tsx` | 顶部增加模式切换，条件渲染表单 |
| `frontend/src/pages/BacktestDetail.tsx` | 检测 mode 字段，渲染不同报表组件 |
| `frontend/src/services/backtestService.ts` | 新增提交交易模拟回测的方法 |
| `frontend/src/stores/backtestStore.ts` | 新增交易模拟相关 state |

---

## 二、数据模型

### 2.1 trade_sim_reports 表

```sql
CREATE TABLE trade_sim_reports (
    id              SERIAL PRIMARY KEY,
    strategy_id     INT NOT NULL REFERENCES strategies(id),
    user_id         INT NOT NULL,
    cutoff_date     DATE NOT NULL,             -- 选股截止日

    -- 用户输入参数
    config          JSONB NOT NULL DEFAULT '{}',
    /*
    {
      "total_amount": 100000,       // 投资总额
      "top_n": 5,                   // 选前N只
      "max_hold_days": 60,          // 强制平仓天数
      "stop_factors": [             // 启用的止损止盈因子
        {
          "id": "stop_prev_low",
          "enabled": true,
          "params": { "ref_days": 20 }
        },
        {
          "id": "stop_ma10_cross",
          "enabled": true,
          "params": { "coefficient": 0.93, "buffer_days": 2 }
        },
        {
          "id": "take_profit_pct",
          "enabled": true,
          "params": { "profit_pct": 5.0 }
        }
      ]
    }
    */

    -- 交易明细（每只选中股票一笔交易）
    trades          JSONB NOT NULL DEFAULT '[]',
    /*
    [
      {
        "ts_code": "000001.SZ",
        "name": "平安银行",
        "score": 85,
        "allocated_amount": 20000,  // 分配金额
        "shares": 1600.0,           // 理论股数（总金额/N / 开盘价）
        "buy_price": 12.50,         // 买入价（截止日后首个交易日开盘价）
        "buy_date": "2026-01-05",
        "sell_price": 13.15,        // 卖出价
        "sell_date": "2026-01-15",
        "sell_reason": "止盈5%",    // 触发原因 or "强制平仓" or "数据缺失"
        "hold_days": 8,             // 实际持有交易日数
        "return_pct": 5.20,         // 收益率(%)
        "high_price": 13.20,        // 持仓期间最高价
        "low_price": 12.30,         // 持仓期间最低价
        "max_drawdown": -2.10,      // 最大回撤(%)
        "daily_tracking": [         // 每日追踪数据
          {
            "date": "2026-01-05",
            "open": 12.50,
            "close": 12.55,
            "high": 12.60,
            "low": 12.45,
            "ma10": 12.30,
            "prev_low_ref": 11.80,  // 前低参考价（若启用）
            "ma10_stop_line": 11.44,// MA10止损线（若启用）
            "return_pct": 0.40,     // 当日浮盈
            "status": "holding"     // holding | stopped | take_profit | force_close
          }
        ]
      }
    ]
    */

    -- 汇总
    summary         JSONB NOT NULL DEFAULT '{}',
    /*
    {
      "total_trades": 5,
      "win_count": 3,               // 盈利笔数
      "lose_count": 2,              // 亏损笔数
      "win_rate": 60.0,             // 胜率(%)
      "avg_return": 2.15,           // 平均回报率(%)
      "avg_win": 5.80,              // 平均盈利(%)
      "avg_loss": -3.25,            // 平均亏损(%)
      "profit_loss_ratio": 1.78,    // 盈亏比
      "max_consecutive_wins": 4,    // 最大连续盈利笔数（按买入日期排序计算）
      "max_consecutive_losses": 2,  // 最大连续亏损笔数（按买入日期排序计算）
      "return_distribution": {      // 收益分布
        "lt_minus10": 0,            // < -10%
        "minus10_0": 2,             // -10% ~ 0
        "0_5": 2,                   // 0 ~ 5%
        "5_10": 1,                  // 5% ~ 10%
        "gt_10": 0                  // > 10%
      }
    }
    */

    status          VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/running/completed/failed
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 三、止损止盈因子设计

### 3.1 注册机制

每个因子定义在 `trade_sim_stops.py` 中，通过注册表管理：

```python
@dataclass
class ParamDef:
    name: str           # 参数名
    type: type          # int / float
    default: Any        # 默认值
    description: str    # 中文描述

@dataclass  
class TriggerResult:
    reason: str         # 触发描述，如 "破前低止损（20日前收盘价 11.80）"

class StopFactorRegistry:
    """止损止盈因子注册表"""
    _factors: Dict[str, dict] = {}
    
    @classmethod
    def register(cls, id: str, name: str, params: List[ParamDef], check_fn: Callable):
        cls._factors[id] = {"name": name, "params": params, "check": check_fn}
    
    @classmethod
    def get_all(cls) -> Dict:
        """返回所有已注册因子（用于前端展示可选列表）"""
        ...
    
    @classmethod
    def get_check_fn(cls, id: str) -> Callable:
        """获取检查函数"""
        ...
```

### 3.2 内置因子

#### 因子 1：破前低止损 (`stop_prev_low`)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ref_days` | int | 20 | 前低参考天数 |

触发条件：`当日收盘价 < ref_days 个交易日前的收盘价`

#### 因子 2：MA10 跌破止损 (`stop_ma10_cross`)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `coefficient` | float | 0.93 | MA10 系数 |
| `buffer_days` | int | 2 | 缓冲确认天数 |

触发条件：**连续** `buffer_days` 个交易日收盘价 < MA10 × coefficient。期间任一天收盘价回到止损线上方，计数重置。

#### 因子 3：固定止盈 (`take_profit_pct`)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `profit_pct` | float | 5.0 | 止盈百分比 |

触发条件：`(当日收盘价 - 买入价) / 买入价 × 100 >= profit_pct`

### 3.3 扩展方式

新增因子只需在 `trade_sim_stops.py` 中：
1. 编写 `check_fn(df, position, params) -> TriggerResult | None` 函数
2. 调用 `StopFactorRegistry.register(id, name, params, check_fn)` 注册

无需修改引擎或其他代码。

---

## 四、TradeSimEngine 核心逻辑

### 4.1 类设计

```python
class TradeSimEngine:
    def __init__(self, strategy_code: str, strategy_params: dict, config: dict):
        # 组合 BacktestEngine 实例，复用数据加载 + 策略执行
        self._backtest_engine = BacktestEngine(strategy_code, strategy_params, config)
        self.config = config
    
    def run(self, cutoff_date: str) -> Dict[str, Any]:
        """主入口，返回 {trades, summary}"""
    
    def _get_stock_candidates(self, cutoff_date: str) -> List[dict]:
        """运行策略选股，按score降序取前N只"""
    
    def _load_tracking_data(self, ts_codes: List[str], cutoff_date: str) -> dict:
        """加载截止日后的日线数据"""
    
    def _simulate_trade(self, ts_code: str, buy_date: str, daily: list, position: dict) -> dict:
        """模拟单只股票的一笔交易"""
    
    def _check_stop_conditions(self, daily_slice: list, position: dict, day_idx: int) -> TriggerResult | None:
        """按序检查所有启用的止损止盈因子"""
    
    def _calculate_summary(self, trades: List[dict]) -> dict:
        """汇总统计"""
```

### 4.2 主流程

```
run(cutoff_date)
├── 1. 策略选股：复用 _backtest_engine 的数据加载 + 策略执行
│   └── 按 score 降序排序，取前 top_n 只；若无 score 则按名称排序
│
├── 2. 加载追踪数据：查询 daily 表，获取截止日后所有日线
│   └── 优先使用 adj_close（复权价），备选 close
│
├── 3. 逐股模拟 _simulate_trade():
│   ├── a. 找到截止日后第一个交易日 → 买入价 = 当日开盘价
│   ├── b. 初始化 position={buy_price, buy_date, buy_idx, high_price, low_price, max_drawdown}
│   ├── c. 每日循环（从买入日起）：
│   │   ├── 更新 high_price, low_price, max_drawdown
│   │   ├── 遍历 stop_factors，依次 check()
│   │   ├── 任一触发 → 卖出价 = 次日开盘价（最后一天用收盘价）
│   │   ├── 超过 max_hold_days 未触发 → 强制平仓，卖出价 = 当日收盘价
│   │   └── 记录 daily_tracking 数据
│   └── d. 计算 return_pct = (sell_price - buy_price) / buy_price * 100
│
├── 4. 汇总统计 _calculate_summary():
│   ├── 总交易笔数、胜率
│   ├── 平均回报率、平均盈利、平均亏损
│   ├── 盈亏比、最大连续盈亏
│   └── 收益分布
│
└── 5. 返回 {trades, summary}
```

### 4.3 关键处理规则

| 场景 | 处理方式 |
|------|---------|
| 买入日无开盘价 | 跳过该股票，不计入交易 |
| 追踪期间停牌（连续无数据） | 标记 `sell_reason="数据缺失"`，记录最后有效日 |
| 除权除息 | MA10 和价格比较均基于 `adj_close`（复权价） |
| 因子检查顺序 | 按 config 中 stop_factors 数组顺序，先触发先生效 |
| 缓冲计数重置 | MA10 跌破因子的 buffer_days 计数，任一天回到线上方则重置为 0 |
| 强制平仓 | 超过 max_hold_days 个交易日仍未触发任何条件 |

---

## 五、API 设计

### 5.1 路由

所有路由前缀：`/api/v1/trade-sims`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/` | 提交交易模拟回测（异步，返回 202） |
| GET | `/` | 查询列表（支持 strategy_id/status 筛选） |
| GET | `/{id}` | 查询详情（含 trades + summary） |
| DELETE | `/{id}` | 删除 |

### 5.2 请求 Schema

```python
class TradeSimCreate(BaseModel):
    strategy_id: int
    cutoff_date: str                    # YYYY-MM-DD
    total_amount: float                 # 投资总额
    top_n: int = 5                      # 选前N只
    max_hold_days: int = 60             # 强制平仓天数
    stop_factors: List[StopFactorConfig]

class StopFactorConfig(BaseModel):
    id: str                             # 因子ID
    enabled: bool
    params: Dict[str, Any] = {}
```

### 5.3 响应 Schema

```python
class TradeSimResponse(BaseModel):
    id: int
    strategy_id: int
    cutoff_date: str
    config: dict
    trades: List[TradeItem]
    summary: TradeSimSummary
    status: str
    created_at: datetime

class TradeItem(BaseModel):
    ts_code: str
    name: str
    score: float
    allocated_amount: float
    shares: float
    buy_price: float
    buy_date: str
    sell_price: float | None
    sell_date: str | None
    sell_reason: str | None
    hold_days: int | None
    return_pct: float | None
    high_price: float | None
    low_price: float | None
    max_drawdown: float | None
    daily_tracking: List[DailyTrackingItem]

class DailyTrackingItem(BaseModel):
    date: str
    open: float
    close: float
    high: float
    low: float
    ma10: float | None
    prev_low_ref: float | None
    ma10_stop_line: float | None
    return_pct: float
    status: str                        # holding | stopped | take_profit | force_close

class TradeSimSummary(BaseModel):
    total_trades: int
    win_count: int
    lose_count: int
    win_rate: float
    avg_return: float
    avg_win: float
    avg_loss: float
    profit_loss_ratio: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    return_distribution: ReturnDistribution

class ReturnDistribution(BaseModel):
    lt_minus10: int = Field(alias="lt_-10")
    minus10_0: int = Field(alias="-10_0")
    zero_5: int = Field(alias="0_5")
    five_10: int = Field(alias="5_10")
    gt_10: int = Field(alias="gt_10")

    class Config:
        populate_by_name = True
```

---

## 六、前端设计

### 6.1 表单（BacktestForm.tsx）

在现有表单顶部新增模式切换 `Radio.Group`，值存入 Zustand store：

- **模式一：简单回测** → 渲染现有表单（不变）
- **模式二：交易模拟** → 渲染新表单：

| 字段 | 组件 | 校验 |
|------|------|------|
| 投资总额（元） | InputNumber | > 0，必填 |
| 持仓股票数 N | InputNumber | 1-20，默认 5 |
| 强制平仓天数 | InputNumber | 1-365，默认 60 |
| 止损止盈条件 | 动态卡片列表 | 至少启用一个 |

**止损止盈条件卡片**：每张卡片包含 Checkbox（启用）、因子名称、参数输入（对应因子定义的 params）。

### 6.2 报表详情（TradeSimDetail.tsx）

**汇总区**：Ant Design Statistic 卡片组，4 列布局：

- 第一行：总交易笔数 | 胜率 | 平均回报率 | 平均亏损率
- 第二行：盈亏比 | 最大连续盈利 | 最大连续亏损

**收益分布**：ECharts 柱状图（5 个区间）。

**逐笔交易明细表**：Ant Design Table，默认列：股票名称、分数、买入价、卖出价、持有天数、收益率、最大回撤、卖出原因，支持展开行（`expandable`）。

**展开行内容**：嵌套一个小表格展示每日追踪数据（日期、开盘价、收盘价、MA10、止损线、浮盈、状态），加一个简单的收盘价迷你折线图（ECharts）。

### 6.3 提交后的流程

1. 表单提交 → POST `/api/v1/trade-sims` → 返回 202 + id
2. 跳转到详情页，轮询状态直到 completed/failed
3. 状态变为 completed → 渲染报表

---

## 七、错误处理

| 场景 | 处理 |
|------|------|
| 策略选不出股票 | 返回 `trades: []`，summary 全部为 0，不报错 |
| 策略代码执行异常 | 返回 status=failed，记录 error_message |
| 选中股票全部无开盘价 | 同上，trades 为空 |
| 追踪数据不完整 | 单只股票标记为"数据缺失"，不影响其他股票 |
| 用户未启用任何止损止盈条件 | 前端校验拦截 |
| 并发提交 | 异步队列（线程池），状态轮询 |
