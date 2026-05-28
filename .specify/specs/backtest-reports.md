# 功能规格：回测报告 (Backtest Reports)

**版本**: 2.0  
**状态**: 草稿  
**创建日期**: 2026-05-24  
**最后更新**: 2026-05-24  
**作者**: AI Assistant

---

## 1. 概述

允许用户提交策略回测任务，查看回测结果和生成的可视化报告。回测报告参考 WorkBuddy 项目的格式，包含汇总统计、逐日结果、JSON 和 HTML 两种输出格式。

---

## 2. 用户故事

### US-101: 提交回测任务
**作为** 量化交易者，  
**我希望** 能够选择策略和参数提交回测任务，  
**以便** 我可以评估策略的历史表现。

**验收标准**:
- [ ] 选择要回测的策略
- [ ] 配置回测参数（起始日期、结束日期、初始资金、交易成本等）
- [ ] 配置风控参数（止损、止盈、持仓数量等）
- [ ] 提交后显示任务 ID 和状态（排队中、运行中、完成、失败）
- [ ] 支持批量回测（多组参数组合）

### US-102: 查看回测报告列表
**作为** 量化交易者，  
**我希望** 能够查看所有回测报告，  
**以便** 我可以比较不同策略或参数的表现。

**验收标准**:
- [ ] 以表格形式展示报告列表
- [ ] 显示策略名称、回测时间段、收益率、夏普比率等关键指标
- [ ] 支持按策略名称、日期范围、收益筛选
- [ ] 支持按创建时间排序（默认倒序）
- [ ] 点击报告可查看详情

### US-103: 查看回测报告详情
**作为** 量化交易者，  
**我希望** 能够查看单个回测报告的详细信息，  
**以便** 我可以深入分析策略表现。

**验收标准**:
- [ ] 显示汇总统计（有效日、总交易数、次日/三日/五日平均涨幅、胜率）
- [ ] 显示逐日选股结果表格（选股日、代码、名称、收盘价、涨幅、得分）
- [ ] 显示收益率曲线图（可选）
- [ ] 支持报告导出（JSON、HTML）

### US-104: 删除回测报告
**作为** 量化交易者，  
**我希望** 能够删除不需要的回测报告，  
**以便** 保持报告列表整洁。

**验收标准**:
- [ ] 删除前弹出确认对话框
- [ ] 删除后报告从列表消失
- [ ] 不删除关联的策略

### US-105: 导出回测报告
**作为** 量化交易者，  
**我希望** 能够导出回测报告，  
**以便** 我可以在本地查看或分享给他人。

**验收标准**:
- [ ] 支持导出为 JSON 格式（结构化数据）
- [ ] 支持导出为 HTML 格式（可视化报告）
- [ ] 导出文件命名规范：`backtest_{strategy_name}_{start_date}_{end_date}.{json|html}`

---

## 3. 功能需求

### 3.1 回测引擎

回测引擎负责执行策略并生成报告数据。核心流程：

```
输入: 策略脚本 + 回测参数 + 历史数据（从 stock_db.sqlite 读取）
  ↓
1. 初始化回测引擎（设置参数、加载数据）
2. 按时间顺序遍历历史数据（T+1 规则）
3. 每个交易日：
   a. 检查存量持仓的止盈止损（T+1 保护，跳过当日买入）
   b. T+2 强制清仓
   c. 执行新买入（昨日选股信号），固定 15% 仓位
   d. 记录组合净值
   e. 收盘选股，为次日准备
4. 计算指标
  ↓
输出: 回测结果（汇总统计、逐日结果、交易记录）
```

**关键特性**:
- **T+1 规则**: 严格模拟 A 股 T+1 交易制度（当日买入，次日才能卖出）
- **双轨制风控**: 主板（10%）和科创板/创业板（20%）使用不同的止损止盈参数
- **固定比例仓位**: 每只股票占用 15% 组合价值
- **时间止损**: T+1 收盘检查，T+2 强制清仓

### 3.2 回测参数配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| start_date | Date | 1 年前 | 回测起始日期 |
| end_date | Date | 今天 | 回测结束日期 |
| initial_cash | Float | 1,000,000 | 初始资金（元）|
| commission | Float | 0.00025 | 佣金费率（双边）|
| stamp_duty | Float | 0.001 | 印花税率（仅卖出）|
| slippage | Float | 0.001 | 滑点（价格比例）|
| position_size | Float | 0.15 | 单只股票仓位比例（15%）|
| max_positions | Integer | 5 | 最大持仓数 |
| main_stop_loss | Float | -0.04 | 主板止损比例（-4%）|
| gem_stop_loss | Float | -0.05 | 双创止损比例（-5%）|
| main_take_profit | Float | 0.06 | 主板止盈比例（+6%）|
| gem_take_profit | Float | 0.08 | 双创止盈比例（+8%）|
| benchmark | String | "000300.SH" | 基准指数 |

### 3.3 回测报告数据格式

#### 3.3.1 JSON 报告格式

**文件命名**: `backtest_{strategy_name}_{start_date}_{end_date}.json`

**结构示例**:
```json
{
  "strategy": "OldDuckHead",           // 策略名称
  "period": "20260512~20260512",       // 回测区间
  "cap_range": "300-5000亿",           // 市值范围
  "config": {                           // 回测配置
    "initial_cash": 1000000,
    "commission": 0.00025,
    "stamp_duty": 0.001,
    "slippage": 0.001,
    "position_size": 0.15,
    "max_positions": 5,
    "main_stop_loss": -0.04,
    "gem_stop_loss": -0.05,
    "main_take_profit": 0.06,
    "gem_take_profit": 0.08
  },
  "summary": {                          // 汇总统计
    "days": 1,                         // 有效交易日数
    "total": 8,                        // 总交易数
    "avg_day1": 1.56,                 // 次日平均涨幅
    "avg_day2": -3.38,                // 三日平均涨幅
    "avg_day4": -1.92,                // 五日平均涨幅
    "win_rate1": 75.0,                // 次日胜率
    "win_rate2": 12.5,                // 三日胜率
    "win_rate4": 25.0                  // 五日胜率
  },
  "results": [                          // 逐日结果
    {
      "pick": "20260512",               // 选股日
      "trades": [                       // 当日选中股票
        {
          "code": "600236",
          "name": "桂冠电力",
          "pick_close": 11.94,          // 选股日收盘价
          "day0_gain": -1.97,          // 当日涨幅
          "day1_gain": 0.25,           // 次日涨幅
          "day2_gain": -6.78,          // 三日涨幅
          "day4_gain": -9.72,          // 五日涨幅
          "score": 96,
          "details": { ... }            // 技术指标详情
        },
        ...
      ]
    }
  ]
}
```

#### 3.3.2 HTML 报告格式

**文件命名**: `backtest_{strategy_name}_{date}.html`

**报告结构**:
1. **标题区** - 策略名称、市值范围、回测周期
2. **说明区** - 形态逻辑、筛选条件、回测结果摘要
3. **汇总卡片** - 4个指标卡片
   - 有效日
   - 次日均值 + 胜率
   - 三日均值 + 胜率
   - 五日均值 + 胜率
4. **详细表格** - 逐股展示
   - 选股日、代码、名称、收盘价
   - 当日涨幅、次日涨幅、三日涨幅、五日涨幅
   - 得分

**HTML 样式特点**:
- 深色主题（background: #0f172a）
- 响应式表格布局
- 涨幅用颜色区分（红色=上涨，绿色=下跌）

---

## 4. 数据模型

### 4.1 数据库表结构 (SQLite)

```sql
-- 回测报告表
CREATE TABLE backtest_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    strategy_run_id INTEGER,  -- 关联的策略运行实例
    name VARCHAR(255),  -- 报告名称（自动生成或用户自定义）
    status VARCHAR(50) DEFAULT 'pending',  -- pending, running, completed, failed
    params TEXT NOT NULL,  -- 回测参数 JSON
    config TEXT NOT NULL,  -- 回测配置 JSON
    metrics TEXT,  -- 回测指标 JSON（完成后填充）
    equity_curve TEXT,  -- 权益曲线数据 JSON（完成后填充，可选）
    trades TEXT,  -- 交易记录 JSON（完成后填充）
    summary TEXT,  -- 汇总统计 JSON（完成后填充）
    results TEXT,  -- 逐日结果 JSON（完成后填充）
    json_report_path TEXT,  -- JSON 报告文件路径
    html_report_path TEXT,  -- HTML 报告文件路径
    error_message TEXT,  -- 失败时的错误信息
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,  -- 开始执行时间
    completed_at TIMESTAMP,  -- 完成时间
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);

-- 索引
CREATE INDEX idx_backtest_strategy ON backtest_reports(strategy_id);
CREATE INDEX idx_backtest_status ON backtest_reports(status);
CREATE INDEX idx_backtest_created ON backtest_reports(created_at DESC);
```

---

## 5. API 接口设计

### 5.1 回测相关 API

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/backtests` | 提交回测任务 |
| GET | `/api/v1/backtests` | 获取回测报告列表 |
| GET | `/api/v1/backtests/:id` | 获取单个报告详情 |
| GET | `/api/v1/backtests/:id/json` | 获取 JSON 格式报告 |
| GET | `/api/v1/backtests/:id/html` | 获取 HTML 格式报告 |
| DELETE | `/api/v1/backtests/:id` | 删除回测报告 |

### 5.2 请求/响应示例

**提交回测 - POST /api/v1/backtests**

请求体:
```json
{
  "strategy_id": 1,
  "params": {
    "short_window": 5,
    "long_window": 20
  },
  "backtest_config": {
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "initial_cash": 1000000,
    "commission": 0.00025,
    "stamp_duty": 0.001,
    "slippage": 0.001,
    "position_size": 0.15,
    "max_positions": 5,
    "main_stop_loss": -0.04,
    "gem_stop_loss": -0.05,
    "main_take_profit": 0.06,
    "gem_take_profit": 0.08,
    "benchmark": "000300.SH"
  }
}
```

响应:
```json
{
  "code": 0,
  "message": "回测任务已提交",
  "data": {
    "id": 1,
    "status": "pending",
    "created_at": "2026-05-24T17:00:00Z"
  }
}
```

**获取报告列表 - GET /api/v1/backtests?page=1&limit=20**

响应:
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": 1,
        "strategy_name": "老鸭头策略",
        "status": "completed",
        "period": "20260512~20260512",
        "summary": {
          "days": 1,
          "total": 8,
          "avg_day1": 1.56,
          "win_rate1": 75.0
        },
        "created_at": "2026-05-24T17:00:00Z",
        "completed_at": "2026-05-24T17:05:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "limit": 20
  }
}
```

**获取 JSON 报告 - GET /api/v1/backtests/:id/json**

响应：
- Content-Type: `application/json`
- Content-Disposition: `attachment; filename="backtest_{strategy_name}_{start_date}_{end_date}.json"`
- Body: 回测报告 JSON 数据

**获取 HTML 报告 - GET /api/v1/backtests/:id/html**

响应：
- Content-Type: `text/html`
- Body: 回测报告 HTML 内容（可在浏览器中直接查看）

---

## 6. 前端组件设计

### 6.1 回测列表页 (`/backtests`)

**组件结构**:
```
<BacktestList>
  <Filters>  <!-- 筛选器：策略、日期范围、状态 -->
  <Table>    <!-- 报告列表表格 -->
    <Column>策略名称</Column>
    <Column>状态</Column>
    <Column>回测区间</Column>
    <Column>次日收益率</Column>
    <Column>次日胜率</Column>
    <Column>操作</Column>
  </Table>
  <Pagination />
</BacktestList>
```

### 6.2 回测详情页 (`/backtests/:id`)

**组件结构**:
```
<BacktestDetail>
  <Header>  <!-- 报告标题、状态、操作按钮 -->
  <SummaryCards>  <!-- 汇总卡片 -->
    <Card>有效日</Card>
    <Card>次日均值 + 胜率</Card>
    <Card>三日均值 + 胜率</Card>
    <Card>五日均值 + 胜率</Card>
  </SummaryCards>
  <ResultsTable>  <!-- 逐日结果表格 -->
    <Column>选股日</Column>
    <Column>代码</Column>
    <Column>名称</Column>
    <Column>收盘价</Column>
    <Column>当日涨幅</Column>
    <Column>次日涨幅</Column>
    <Column>三日涨幅</Column>
    <Column>五日涨幅</Column>
    <Column>得分</Column>
  </ResultsTable>
  <ExportButtons>  <!-- 导出按钮 -->
    <Button>导出 JSON</Button>
    <Button>导出 HTML</Button>
  </ExportButtons>
</BacktestDetail>
```

### 6.3 提交回测表单 (`/strategies/:id/backtest`)

**组件结构**:
```
<BacktestForm>
  <StrategyInfo>  <!-- 策略基本信息（只读） -->
  <BacktestConfig>  <!-- 回测配置 -->
    <DatePicker>起始日期</DatePicker>
    <DatePicker>结束日期</DatePicker>
    <InputNumber>初始资金</InputNumber>
    <InputNumber>佣金费率</InputNumber>
    <InputNumber>印花税率</InputNumber>
    <InputNumber>滑点</InputNumber>
    <InputNumber>单只股票仓位比例</InputNumber>
    <InputNumber>最大持仓数</InputNumber>
  </BacktestConfig>
  <RiskConfig>  <!-- 风控配置 -->
    <InputNumber>主板止损</InputNumber>
    <InputNumber>双创止损</InputNumber>
    <InputNumber>主板止盈</InputNumber>
    <InputNumber>双创止盈</InputNumber>
  </RiskConfig>
  <SubmitButton>
</BacktestForm>
```

---

## 7. 可视化设计

### 7.1 汇总卡片

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ 有效日       │ 次日均值     │ 三日均值     │ 五日均值     │
│  1          │  +1.56%    │  -3.38%    │  -1.92%    │
│             │  胜率 75%   │  胜率 12.5% │  胜率 25%   │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

### 7.2 逐日结果表格

- 行：逐日选股结果
- 列：选股日、代码、名称、收盘价、当日涨幅、次日涨幅、三日涨幅、五日涨幅、得分
- 颜色：红色（上涨）、绿色（下跌）
- 交互：点击行展开查看详细信息

### 7.3 收益率曲线图（可选）

- X 轴: 日期
- Y 轴（左）: 累计收益率（%）
- Y 轴（右）: 基准指数收益率（%）
- 交互: 缩放、悬停显示具体数值、图例开关
- 标记: 买卖点标记（可选）

---

## 8. 非功能需求

### 8.1 性能
- 回测任务提交响应时间 < 1 秒（仅提交，不包含执行）
- 回测报告列表加载 < 2 秒（50 条记录）
- 回测执行时间 < 10 分钟（1 年数据，每日选股）
- 支持长时间回测（异步执行，避免超时）

### 8.2 可扩展性
- 回测引擎支持插件化（可替换不同引擎）
- 报告可视化支持自定义指标
- 支持批量回测和参数优化

### 8.3 可靠性
- 回测失败时有详细错误日志
- 回测任务支持断点续跑（可选）
- 数据库定期备份

---

## 9. 依赖和约束

### 9.1 前端依赖
- Ant Design 5+（表格、卡片、表单、按钮等组件）
- ECharts 5+（可选，用于收益率曲线图）
- FileSaver.js（导出功能）
- react-table（可选，用于复杂表格）

### 9.2 后端依赖
- FastAPI（API 框架）
- Pandas 2.1+（数据处理）
- NumPy 1.26+（数值计算）
- SQLite3（数据存储）
- Jinja2（可选，用于 HTML 报告生成）

### 9.3 约束
- 回测仅支持历史数据，不支持实时交易
- 初始版本不支持高频数据（分钟级以下）
- 策略执行使用单线程（避免并发问题）

---

## 10. 开放问题

- [ ] 回测任务队列使用什么实现（Celery、RQ、还是简单的内存队列）？
- [ ] 是否支持分布式回测（多机器并行）？
- [ ] 报告导出格式优先级（JSON vs HTML vs PDF）？
- [ ] 是否支持回测结果对比（多报告对比图表）？
- [ ] 是否支持收益率曲线图（需要计算权益曲线）？

---

## 11. 验收标准总结

- [x] **US-101**: 提交回测任务
- [x] **US-102**: 查看回测报告列表
- [x] **US-103**: 查看回测报告详情
- [x] **US-104**: 删除回测报告
- [x] **US-105**: 导出回测报告

---

**变更日志**:
- 2026-05-24: 初始版本创建
- 2026-05-24: 版本 2.0 - 调整为 WorkBuddy 的报告格式（JSON + HTML）
