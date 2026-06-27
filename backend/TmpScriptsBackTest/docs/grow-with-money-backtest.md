# grow_with_money 策略回测文档

## 概述

`grow_with_money` 是一组基于**主力资金净流入**排名的选股回测脚本，对标 **国证成长100（980080）** 指数成分股。核心逻辑：在每个调仓日，计算过去 M 日累计主力净流入，取 Top N 等权买入。已持仓且未跌出前 N 的股票不动（减少换手）。

提供了**周频**和**日频**两种调仓模式，均支持止损开关。

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `backtest_grow_with_money.py` | **周频调仓**回测脚本（每周五调仓） |
| `backtest_grow_with_money_daily.py` | **日频调仓**回测脚本（每个交易日调仓） |
| `backtest_grow_with_money_{index}.html` | 周频回测结果（全区间 2025-01 ~ 2026-06），文件名含指数代码 |
| `backtest_grow_with_money_{index}_daily.html` | 日频回测结果，文件名含指数代码 |
| `backtest_grow_with_money_{index}_rebase.html` | 周频回测报告，**净值基准化**（需 `--rebase-date`） |
| `backtest_grow_with_money_{index}_daily_rebase.html` | 日频回测报告，**净值基准化**（需 `--rebase-date`） |
| `backtest_grow_with_money_daily_v1.py` | **日频调仓回测脚本 · T+1 开盘价成交**（V1） |
| `backtest_grow_with_money_{index}_daily_v1.html` | 日频 V1 回测报告 |
| `backtest_grow_with_money_{index}_daily_v1_rebase.html` | 日频 V1 回测报告，**净值基准化**（需 `--rebase-date`） |
| `backtest_grow_with_money_daily_v2.py` | **日频调仓回测脚本 · T+1 开盘 + 最低分数过滤**（V2） |
| `backtest_grow_with_money_{index}_daily_v2.html` | 日频 V2 回测报告 |
| `backtest_grow_with_money_{index}_daily_v2_rebase.html` | 日频 V2 回测报告，**净值基准化**（需 `--rebase-date`） |

### 临时批量对比脚本

| 文件 | 说明 |
|------|------|
| `_run_2026_combined.py` | 2026 年日频 M=1/3/5 × Top=3/5 六曲线对比（T+0 收盘版） |
| `_run_2026_v1_combined.py` | 同上，T+1 开盘版（V1） |
| `backtest_grow_with_money_980080_daily_2026_combined.html` | 2026 日频 T+0 对比报告 |
| `backtest_grow_with_money_980080_daily_v1_2026_combined.html` | 2026 日频 T+1 对比报告 |

---

## 策略逻辑

### 选股流程

```
每个调仓日：
  1. 获取 980080（国证成长100）当前成分股
  2. 过滤：排除 ST、非 stock 类型
  3. 计算过去 M 日累计主力净流入（daily_stock_fund_flow.main_net_flow）
  4. 按累计净流入降序排列，取 Top N
  5. 已在持仓 & 仍在 Top N → 不动（省换手）
  6. 新增 → 等权买入；剔除 → 卖出
```

### 交易规则

| 项目 | 设定 |
|------|------|
| 起始资金 | 1000（净值基准） |
| 仓位分配 | 等权（1/N） |
| 印花税（卖出） | 0.1% |
| 佣金（买卖） | 0.03% |
| 卖出总费率 | 0.13%（印花税 + 佣金） |
| 买入总费率 | 0.03%（仅佣金） |
| 止损（可选） | 个股跌破成本价 -8% 止损卖出 |

### 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--index` | `980080` | 指数代码（需 `index_constituents` 表有数据） |
| `--top` | `3 5 10` | 持仓数量（可同时跑多个） |
| `--lookback` | `5` | 主力净流入回溯天数 M |
| `--stop-loss` | `false` | 是否启用止损 |
| `--stop-loss-pct` | `0.08` | 止损阈值（8%） |
| `--rebase-date` | `None` | 基准日（如 `2025-04-07`），自动生成 rebase 版报告 |
| `--bt-start` | `2025-01-01` | 回测起始日 |
| `--bt-end` | `2026-06-19` | 回测截止日 |
| `--data-start` | `2024-12-01` | 数据库查询起始日（需早于 `--bt-start`，保证 lookback 数据充足） |
| `--data-end` | `2026-06-30` | 数据库查询截止日（需晚于 `--bt-end`，保证前向价格可查） |

---

## 两条回测线的差异

| 维度 | 周频（base） | 日频（daily） |
|------|-------------|---------------|
| 调仓频率 | 每周五（或最近交易日） | 每个交易日 |
| 调仓日生成 | `gen_fridays()` + 假期顺延 | 直接遍历所有交易日 |
| 数据点数 | ~77 个（周频点） | ~352 个（日频点） |
| 收益标注 | "周收益" | "日收益" |
| 控制台输出 | 每个调仓日都打印 | 周五 + 前 4 日打印，其余静默 |
| HTML 文件名 | `backtest_grow_with_money.html` | `backtest_grow_with_money_daily.html` |

**关键差异**：日频版本换手更频繁，能更快捕捉资金流向变化，但交易费用也更高。

---

## T+0 收盘 vs T+1 开盘（V1）

日频脚本有两个版本：

| 版本 | 脚本 | 成交价 | 说明 |
|------|------|--------|------|
| **base** | `backtest_grow_with_money_daily.py` | T+0 收盘价 | 当日资金流用于当日收盘决策，存在 look-ahead bias |
| **V1** | `backtest_grow_with_money_daily_v1.py` | T+1 开盘价 | 当日收盘后决策，次日开盘成交，更贴近实战 |

V1 的参数和用法与 base 完全一致，唯一区别：
- 加载 `open` 价格用于交易执行
- 当日排名 → 次日开盘买入/卖出
- 第 1 个交易日无持仓（需等次日开盘建仓）
- HTML 文件名加 `_v1` 后缀

**实战意义**：T+1 开盘才是可执行的策略。T+0 收盘版更适合评估"如果资金流数据实时可用"的理想情况。

---

## V2 · 最低分数过滤

V2 在 V1（T+1 开盘）基础上增加 `--min-score` 参数：当日 5 日累计主力净流入低于指定值的股票不买入（卖出规则不变）。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--min-score` | `0` | 最低主力净流入（**万**），低于此值不买入。5亿=50000 |

### 2026 实测

| 最低分数 | 净值 | 总收益 | 说明 |
|---------|------|--------|------|
| 无限制 | 3068.68 | +206.87% | V2 默认 |
| 5亿 | 2802.19 | +180.22% | 过滤约 20% 低分候选 |
| 8亿 | 2215.48 | +121.55% | 大量时间持仓不足 |
| 10亿 | 1055.76 | +5.58% | 频繁空仓，基本不赚钱 |

**结论**：Top 3 内部再加分数过滤**不提升收益**。高门槛导致持仓不足、现金闲置。Top 3 的集中度已经足够，分数低的 Top 3 股票仍然是当天相对最好的选择。

---

## 数据依赖

### 数据库表

| 表 | 用途 | 关键字段 |
|----|------|----------|
| `index_constituents` | 获取 980080 成分股 | `index_code`, `ts_code` |
| `daily` | 股价 & 交易日历 | `ts_code`, `trade_date`, `close` |
| `daily_stock_fund_flow` | 主力净流入数据 | `ts_code`, `trade_date`, `main_net_flow` |
| `stocks` | 过滤 ST 和类型 | `ts_code`, `type`, `name` |

### 数据时间范围

通过 `--data-start` / `--data-end` / `--bt-start` / `--bt-end` 参数控制（默认值如下）：

```python
# 数据库加载范围（默认）
--data-start 2024-12-01
--data-end   2026-06-30

# 实际回测范围（默认）
--bt-start   2025-01-01
--bt-end     2026-06-19
```

设计原因：
- 从 2024-12-01 开始加载，保证回测初期（2025-01 初）有足够的 lookback 数据
- 到 2026-06-19 截止，留 11 天缓冲保证前向价格可查（如需）
- 如需自定义区间，务必保证 `data-start` 早于 `bt-start` 至少 lookback 天，`data-end` 晚于 `bt-end`

---

## HTML 报告结构

所有报告均使用 **ECharts** 渲染，内嵌 CSS/JS，可直接浏览器打开。包含：

### 1. 净值曲线图
- 横轴：日期
- 纵轴：净值（起始=1000）
- 6 条曲线：Top 3 / 5 / 10 × 无止损 / 有止损
  - Top 3: 红色系（`#ff6b6b` 实线 / `#ff9999` 虚线）
  - Top 5: 黄色系（`#ffd93d` 实线 / `#ffee80` 虚线）
  - Top 10: 绿色系（`#6bcb77` 实线 / `#99dd99` 虚线）
  - 虚线 = 开启止损的曲线

### 2. 终值统计卡片
- 每个策略组合的最终净值
- 总收益率百分比

### 3. Rebase 版本特有
- 基准日 2025-04-07 归一化为 1000
- 图表中增加 markLine 标注基准线 y=1000
- 方便横向对比不同时间区间的表现

---

## 运行方式

```bash
cd backend && source venv/bin/activate

# 周频回测（默认 980080, Top 3/5/10, M=5, 无止损）
python TmpScriptsBackTest/backtest_grow_with_money.py

# 日频回测 + 止损 + rebase
python TmpScriptsBackTest/backtest_grow_with_money_daily.py --stop-loss --rebase-date 2025-04-07

# 指定指数（如 900001）
python TmpScriptsBackTest/backtest_grow_with_money.py --index 900001 --top 5 --stop-loss

# 自定义回测区间
python TmpScriptsBackTest/backtest_grow_with_money.py --bt-start 2025-06-01 --bt-end 2026-06-19 --data-start 2025-04-01 --data-end 2026-06-30

# V1（T+1 开盘）日频回测
python TmpScriptsBackTest/backtest_grow_with_money_daily_v1.py --top 3 5 --lookback 5

# 自定义 lookback + 止损阈值
python TmpScriptsBackTest/backtest_grow_with_money_daily.py --top 3 5 --lookback 10 --stop-loss --stop-loss-pct 0.1
```

输出：
- 控制台：逐日交易明细（持仓、保留、卖出、买入、换手率、费用）
- HTML 报告：自动生成在脚本同目录下，文件名含指数代码

---

## 关于 Rebase 版本

通过 `--rebase-date YYYY-MM-DD` 参数自动生成 rebase 版本，无需独立脚本：

- 以指定日期为基准日（净值=1000），所有曲线的净值重新归一化
- 例如 `--rebase-date 2025-04-07`：以 2025 年关税冲击后市场低点为基准，更清晰看到反弹行情表现
- 图表中包含 markLine（y=1000 虚线）标记基准线
- 基准日若不在周频数据点中，自动选择最近交易日

---

## 多参数对比回测

当需要对比多个 lookback 和 Top N 组合在同一张图上时，使用临时脚本来批量调用并合并结果。

### 脚本模板

```python
# 文件名随意，放在 TmpScriptsBackTest/ 下，运行完可删除
# 核心思路：import run() → 循环不同参数调用 → 合并生成一张大图

from TmpScriptsBackTest.backtest_grow_with_money_daily import run

LOOKBACKS = [1, 3, 5]
TOPS = [3, 5]
# 每个 (lookback, top) 组合跑一次
for lb in LOOKBACKS:
    for top in TOPS:
        pts = run(top, lb, "980080", 0,
                  bt_start="2026-01-01", bt_end="2026-06-26",
                  data_start="2025-11-01", data_end="2026-06-27")
        # 收集 pts 后合并到一张 ECharts 图
```

### 参考脚本

[`_run_2026_combined.py`](../_run_2026_combined.py) — 2026 年日频 M=1/3/5 × Top=3/5 六曲线对比，生成 [`backtest_grow_with_money_980080_daily_2026_combined.html`](../backtest_grow_with_money_980080_daily_2026_combined.html)。

### 关键点

- 不同 lookback 跑出的日期序列长度可能不同，需对齐到最长序列（前向填充）
- 给每条曲线分配不同的颜色/线型以区分
- 这种临时脚本用后即弃，核心回测逻辑仍然复用 `run()` 函数

---

## 关键设计细节

### 1. "同股不动" 机制

```python
old = set(holdings.keys())
sell_c = old - tgt   # 跌出 Top N → 卖出
buy_c = tgt - old    # 新进入 Top N → 买入
keep_c = old & tgt   # 已在仓 & 仍在 Top N → 不动
```

这避免了微小排名波动导致的频繁换手，节省交易成本。

### 2. 止损检查

止损在**每个交易日**都检查（不限于调仓日），一旦触发立即卖出：

```python
if (current_price / cost_basis - 1) < -stop_loss_pct:
    sell()
```

### 3. 假期处理

周频版本内置了 2025-2026 年 A 股假期列表，周五若为假期则顺延到下一个交易日。日频版本直接用 `daily` 表的所有交易日，天然跳过假期。

### 4. 数据库连接

使用 `psycopg2` 同步连接，直接从 `.env` 读取 `DATABASE_URL`。不依赖 FastAPI 的异步 session。

---

## 回测场景矩阵

| 场景 | 调仓频率 | 止损 | 对应脚本/参数 |
|------|---------|------|-------------|
| 周频 · 纯资金流 | 每周五 | ❌ | `backtest_grow_with_money.py` |
| 周频 · 资金流 + 止损 | 每周五 | ✅ 8% | `backtest_grow_with_money.py --stop-loss` |
| 日频 · 纯资金流（T+0 收盘） | 每日 | ❌ | `backtest_grow_with_money_daily.py` |
| 日频 · 资金流 + 止损（T+0 收盘） | 每日 | ✅ 8% | `backtest_grow_with_money_daily.py --stop-loss` |
| 日频 · 纯资金流（**T+1 开盘**） | 每日 | ❌ | `backtest_grow_with_money_daily_v1.py` |
| 日频 · 资金流 + 止损（**T+1 开盘**） | 每日 | ✅ 8% | `backtest_grow_with_money_daily_v1.py --stop-loss` |
| 日频 · T+1 开盘 + **分数过滤** | 每日 | ❌ | `backtest_grow_with_money_daily_v2.py --min-score 50000` |

每个场景都支持 3 个 Top N 参数同时运行（3 / 5 / 10）。

---

## 后续跟踪回测建议

当需要针对最新数据做跟踪回测时：

1. **通过参数指定日期**（无需修改代码）：
   - `--data-start` / `--data-end`：数据加载范围
   - `--bt-start` / `--bt-end`：回测区间
   - `HOLIDAYS`：新增年份的假期（需在源码中添加）

2. **更新成分股数据**：
   - 确保 `index_constituents` 表有最新成分股数据
   - 确保 `daily_stock_fund_flow` 表有新日期的资金流数据

3. **如需新 rebase 报告**：
   - 选定新的基准日（如某个市场转折点）
   - 对输出数据做归一化处理

4. **参数组合**：
   - 默认 M=5（一周资金流），可尝试 M=10（两周）、M=20（一个月）
   - 默认 Top N=3/5/10，可尝试更多组合
   - 止损阈值可调整（8% 是经验值）
