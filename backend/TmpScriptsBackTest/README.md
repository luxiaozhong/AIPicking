# 策略翻译 & 批量回测分析 操作手册

将外部系统的量化策略翻译为本后端回测框架可执行策略，并进行全量历史回测分析的完整流程。

---

## 一、策略翻译：外部策略 → 后端 run(data) 接口

### 1.1 接口差异

| 维度 | 外部系统（原始） | 本后端（翻译后） |
|------|-----------------|-----------------|
| 接口 | 类继承 + 直接查 DB | `run(data: dict) -> list[dict]` |
| 数据获取 | 自行连接 PostgreSQL | 回测引擎切片后传入 `data` dict |
| 数据格式 | ORM 对象 | dict 列表（可直接 `pd.DataFrame(rows)`） |
| 注册 | `@register` 装饰器 | `seed_strategies.py` 添加记录 |
| 输出 | 不限数量 | `MAX_RECOMMENDATIONS=10`（批量分析时可临时改大） |

### 1.2 data dict 结构

```python
data = {
    "cutoff_date": "20260525",          # str, YYYYMMDD
    "stocks": [                          # 全量股票基础信息
        {
            "ts_code": "300001.SZ",      # 含后缀 .SZ / .SH
            "symbol": "300001",
            "name": "特锐德",
            "market": "创业板",
            "industry_l1": "...",        # 一级行业
            "industry_l2": "...",
            "industry_l3": "...",
            "concepts": "...",           # 概念标签
            "total_shares": 2000000000,  # 总股本（股）
            "float_shares": 1200000000,  # 流通股本（股）
        },
        ...
    ],
    "daily": {                           # 日线数据，按 ts_code 分组
        "300001.SZ": [
            {
                "trade_date": "20260101",
                "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2,
                "vol": 50000,            # 成交量（单位可能混用，见 1.4）
                "amount": 510000,        # 成交额（元）
                "adj_close": 10.2,       # 复权收盘价
                "market_cap": ...,       # 总市值（可能为 None）
                "circ_market_cap": ...,  # 流通市值（可能为 None）
            },
            ...
        ],
        ...
    },
    "config": {                          # 可选参数覆盖
        "drawdown_pct": 18.0,
        "market_timing": False,
    }
}
```

### 1.3 翻译步骤

#### Step 1: 分析原始策略

1. 识别数据依赖：用了哪些表、哪些字段
2. 梳理过滤条件：板块、ST、市值、上市天数等
3. 梳理信号逻辑：核心选股逻辑（硬过滤 → 打分 → 排序）
4. 识别预计算指标：如 `ma20`、`vol_ma20`（后端需动态计算）

#### Step 2: 编写 run(data) 函数

```python
def run(data):
    cutoff_date = data.get("cutoff_date", "")
    stocks = data.get("stocks", [])
    daily = data.get("daily", {})
    config = data.get("config", {}) or {}

    # 1. 参数覆盖（用 config 覆盖模块级默认值）
    # 2. 大盘择时（可选）
    # 3. 遍历 daily 中的每只股票
    #     ├─ 板块过滤
    #     ├─ ST 过滤
    #     ├─ 市值过滤
    #     ├─ 数据量过滤
    #     ├─ 核心检测函数
    #     └─ 打分
    # 4. 按评分降序，返回 Top N
    return recommendations[:TOP_PICKS]
```

#### Step 3: 关键注意事项

1. **股票代码格式**：后端用 `ts_code`（如 `300001.SZ`），不是纯数字 `code`
2. **市场标识**：通过 `ts_code.startswith("300")` 判断，不用 `market` 字段
3. **预计算指标**（ma20, vol_ma20 等）：用 pandas rolling 动态计算
4. **数据最少天数**：`len(df) < MIN_HISTORY` 过滤，替代 `list_date`（后端 stocks 表无此字段）
5. **参数覆盖**：用 `global` 声明 + `config.get()` 覆盖默认值
6. **输出格式**：
   ```python
   {
       "ts_code": "300001.SZ",
       "name": "特锐德",
       "score": 85,                       # int
       "signal": "回撤18.5%→... 换手3.2%",  # str
       "breakdown": {"drawdown": 18, ...},  # dict, 评分明细
       "details": {"drawdown_pct": 18.5, ...},  # dict, 完整诊断
   }
   ```

#### Step 4: 注册到 seed_strategies.py

```python
{
    "name": "Oversold Bounce",
    "description": "科技股超跌反弹策略...",
    "file_path": "app/strategies/examples/oversold_bounce.py",
    "tags": "超跌反弹,量价,创业板,科创板,技术面",
},
```

### 1.4 常见坑

| 问题 | 原因 | 解决 |
|------|------|------|
| vol 单位不一致 | 创业板 vol=手(×100股)，科创板混合 | `amount/(close×vol)` 比率自适应检测 |
| market_cap 字段为 None | daily 表该字段不可靠 | 用 `total_shares × close / 1e8` 计算 |
| 20260527 等异常日 | 全板成交量骤降 200 倍 | 阶段二增加 amount 校验 + 1% vol 下限 |
| 大盘择时过滤全部 | 指数在上涨趋势中 | 确认逻辑正确，非 bug，可设 `market_timing=False` |
| list_date 缺失 | stocks 表未加载该字段 | 用 `MIN_HISTORY=60` 天等效替代 |
| 换手率 100% | float_shares 缺失/偏小 | 设 100% cap，标注科创板换手率不可靠 |

---

## 二、批量回测 & HTML 报表生成

### 2.1 脚本结构

参考 `tmpScriptsBackTest/batch_backtest_2022_2025.py`，核心流程：

```
┌─────────────────────────────────────────────┐
│ 1. 一次性加载全部历史数据                       │
│    - stocks 表（全量）                         │
│    - daily 表（DATA_START ~ DATA_END）         │
│    - 按 ts_code 分组成 dict                    │
├─────────────────────────────────────────────┤
│ 2. 预计算大盘择时                              │
│    - 从 399006.SZ 取创业板指日线               │
│    - 逐日计算 MA20 偏离                        │
│    - 筛选偏离 ≥1.5% 的日期                     │
├─────────────────────────────────────────────┤
│ 3. 遍历超跌日，切片运行策略                     │
│    - sliced = {code: rows[rows <= cutoff]}    │
│    - strategy.run({"cutoff_date": ..., ...})  │
│    - 收集全部结果（TOP_PICKS=99999）            │
├─────────────────────────────────────────────┤
│ 4. 获取前向价格                                │
│    - 对每只选中股票查 T+0, T+7, T+15 收盘价     │
│    - 对四大指数同样获取                         │
├─────────────────────────────────────────────┤
│ 5. 计算表现指标                                │
│    - 当日/7日/15日涨跌幅                        │
│    - 上涨占比、平均收益、最大盈亏                │
├─────────────────────────────────────────────┤
│ 6. 生成 HTML 报表                              │
│    - 关键指标卡片                               │
│    - 按年/月汇总表                              │
│    - 每日详细列表                                │
│    - 评分与收益关系                              │
│    - 大盘择时分析                                │
└─────────────────────────────────────────────┘
```

### 2.2 脚本模板

```python
# 1. 数据加载（一次性）
session = SyncSession()
stmt = select(Daily.__table__).where(
    Daily.trade_date.between(DATA_START, DATA_END)
).order_by(Daily.ts_code, Daily.trade_date)
daily_rows = [dict(row._mapping) for row in session.execute(stmt)]

# 按 ts_code 分组
daily_data = defaultdict(list)
for row in daily_rows:
    daily_data[row["ts_code"]].append(row)

# 2. 预计算大盘择时
def precompute_market_oversold(daily_data, trading_days):
    rows = daily_data["399006.SZ"]
    closes = [r["close"] for r in rows if r["close"]]
    oversold = set()
    for i in range(20, len(closes)):
        ma20 = sum(closes[i-20:i]) / 20
        if (ma20 - closes[i]) / ma20 * 100 >= 1.5:
            oversold.add(date)
    return oversold

# 3. 加载策略（直接 import）
spec = importlib.util.spec_from_file_location("s", strategy_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original_top = module.TOP_PICKS
module.TOP_PICKS = 99999  # 不限制数量

# 4. 按日切片运行
for cutoff_date in sorted_oversold_days:
    sliced = {code: [r for r in rows if r["trade_date"] <= cutoff_date]
              for code, rows in daily_data.items()}
    results = module.run({
        "cutoff_date": cutoff_date,
        "stocks": stocks_data,
        "daily": sliced,
        "config": {},
    })
    if results:
        all_results[cutoff_date] = results

module.TOP_PICKS = original_top

# 5. 获取前向价格
def get_forward_prices(session, ts_codes, signal_date_str, calendar_days_list):
    # 对每个 code 查询 signal_date 之后的交易日
    # 对每个 days，找 >= signal_date + days 的第一条
    ...

# 6. 生成 HTML（用 f-string 拼接，内嵌 CSS）
```

### 2.3 数据范围设定

```python
YEAR_START = "20220101"   # 回测起始
YEAR_END   = "20251231"   # 回测截止
DATA_START = "20210701"   # 180 天前（保证滚动指标可计算）
DATA_END   = "20260215"   # 15 天缓冲（保证前向价格可查）
```

### 2.4 性能优化

| 策略 | 效果 |
|------|------|
| 预计算大盘择时 | 过滤掉 ~60% 交易日，减少策略执行次数 |
| 一次性加载全部数据 | 避免每个日期重复 SQL 查询 |
| 内存切片（dict comprehension） | 比重复查 DB 快 100x |
| 按需获取前向价格 | 只查有信号的股票 |

### 2.5 HTML 报表内容

| 章节 | 内容 |
|------|------|
| 关键指标卡片 | 总信号数、日均信号、7/15日平均收益、最大盈亏 |
| 一、按年汇总 | 每年信号天数、总信号、平均收益、上涨率 |
| 二、每日汇总（按月） | 每个有信号日期的选出数量、占比、平均收益 |
| 三、评分与收益关系 | 按评分区间统计平均收益 |
| 四、大盘择时分析 | 每年超跌天数、信号天数、信号率 |

---

## 三、现有文件

| 文件 | 说明 |
|------|------|
| `README.md` | 本手册 |
| `batch_backtest_2022_2025.py` | 超跌反弹策略 2022-2025 批量回测脚本 |
| `batch_backtest_2020_2023.py` | 超跌反弹策略 2020-2023 批量回测脚本 |
| `batch_backtest_2022_2025_1d_3d.py` | 超跌反弹策略 2022-2025 1日/3日持有期批量回测脚本 |
| `analysis_oversold_bounce.py` | 超跌反弹分析 v1 |
| `analysis_oversold_bounce_v2.py` | 超跌反弹分析 v2 |
| `oversold_bounce.py` | 超跌反弹策略模块 |
| `run_daily_backtests.py` | 每日批量回测运行脚本 |
| `generate_trend_upstart_report.py` | 从 `batch_backtest_reports` 表读取数据生成 HTML 报告的模板脚本 |
| `oversold-bounce-2022-2025-report.html` | 超跌反弹策略 2022-2025 HTML 报告（7日/15日持有期） |
| `oversold-bounce-2022-2025-1d-3d-report.html` | 超跌反弹策略 2022-2025 HTML 报告（1日/3日持有期） |
| `oversold-bounce-2020-2023-report.html` | 超跌反弹策略 2020-2023 HTML 报告 |
| `oversold-bounce-performance-report.html` | 超跌反弹策略 2026 表现分析报告 |
| `oversold-bounce-performance-report.md` | 超跌反弹策略 2026 表现分析 Markdown 报告 |
| `trend-upstart-flow-report202601-05.html` | Trend Upstart Flow 批量回测报告 |
| `trend-upstart-flow-report.html` | Trend Upstart Flow 批量回测报告（旧版） |
| `backtest_grow_with_money.py` | 主力资金流选股 · 周频调仓回测脚本（支持 `--index` 参数指定指数） |
| `backtest_grow_with_money_daily.py` | 主力资金流选股 · 日频调仓回测脚本（支持 `--index` 参数指定指数） |
| `backtest_grow_with_money_*.html` | 主力资金流策略 HTML 报告（文件名含指数代码，如 `_980080_`） |
| `backtest_divergence_strategy.py` | 背离策略回测脚本 |
| `backtest_divergence_strategy.html` | 背离策略 HTML 回测报告 |

**策略文件位置**：`backend/app/strategies/examples/oversold_bounce.py`

**补充文档**：
| 文档 | 说明 |
|------|------|
| [`docs/grow-with-money-backtest.md`](docs/grow-with-money-backtest.md) | grow_with_money 策略回测完整文档 |

---

## 四、快速参考

### 运行批量回测

```bash
cd backend && source venv/bin/activate
python tmpScriptsBackTest/batch_backtest_2022_2025.py
```

### 运行时监控

脚本每处理 10 天输出一次进度：
```
[20/360] 20220315: 0只
[200/360] 20231215: 1只 (累计信号天: 5)
[240/360] 20240416: 133只 (累计信号天: 45)
```

### 查看 HTML 报表

```bash
open backend/tmpScriptsBackTest/oversold-bounce-2022-2025-report.html
```

### 注意事项

- 脚本使用同步数据库连接（`SyncSession`），不能在 async 环境中运行
- 直接 `importlib` 加载策略模块，绕过了沙箱的 `exec()` 限制
- 注意恢复 `TOP_PICKS` 原值，避免影响后续正常回测
- HTML 内嵌 CSS，可直接在浏览器打开，无需服务器

---

## 五、生成新报告

### 数据库相关

- 批量回测结果存储在 `batch_backtest_reports` 表（ORM: `BatchBacktestReport`）
- `daily_results` 字段为 JSON 数组，每条含 `cutoff_date`、`recommendations`（每只股票含 `return_3d/7d/15d`）、`summary`
- 查询需用异步 session：`from app.database import AsyncSessionLocal`

### 报告规范

- HTML 样式参考现有报告，保持一致
- 列名用中文，百分比用 `pos`（红涨）/`neg`（绿跌）CSS class
- 无远期数据的日期（如15日后超出回测截止日）显示 "N/A"
- 脚本放在此目录下，`export PYTHONPATH` 包含 `backend/` 后运行
