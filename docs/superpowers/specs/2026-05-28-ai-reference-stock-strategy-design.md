# 参考个股选股策略 — 设计文档

**日期**: 2026-05-28  
**状态**: 已确认

## 概述

用户给定一个个股代码和时间点，系统获取该时间点前 1-3 个月的 K 线数据，提交给 DeepSeek 大模型分析量化指标。用户确认/增删指标后，系统匹配现有因子代码或生成新代码，最终组装为可执行策略。

## 架构

### 整体方案：异步任务 + 轮询

```
前端提交 → POST /api/v1/ai/analyze-stock → {task_id, status: "processing"}
         → 前端轮询 GET /api/v1/ai/analyze-stock/{task_id} → 指标列表
用户确认 → POST /api/v1/ai/confirm-strategy → 组装策略 → 跳转详情页
```

选择异步方案的理由：DeepSeek 分析 K 线数据需 15-30 秒，同步等待体验差。项目已有异步回测的先例可复用。

## API 设计

### POST /api/v1/ai/analyze-stock

提交分析任务。

请求：
```json
{
  "ts_code": "600519.SH",
  "date": "2026-05-01",
  "model": "deepseek-chat",
  "prompt": "重点关注底部反转信号（可选）"
}
```

响应：
```json
{
  "code": 0,
  "data": {
    "task_id": "uuid",
    "status": "processing"
  }
}
```

### GET /api/v1/ai/analyze-stock/{task_id}

轮询分析结果。

响应 (processing)：
```json
{
  "code": 0,
  "data": { "status": "processing" }
}
```

响应 (completed)：
```json
{
  "code": 0,
  "data": {
    "status": "completed",
    "summary": "该股在观察期内呈现震荡上行趋势...",
    "indicators": [
      {
        "name": "RSI超卖反弹",
        "category": "动量类",
        "description": "RSI低于30后出现反弹信号",
        "signal_type": "buy",
        "reason": "K线显示该股多次在RSI低于30后出现明显反弹...",
        "params": { "period": 14, "oversold": 30 },
        "code_required": false,
        "matched_factor_id": "momentum_rsi"
      }
    ],
    "kline_summary": {
      "start_date": "2026-02-01",
      "end_date": "2026-05-01",
      "trading_days": 58,
      "price_change_pct": 12.5
    }
  }
}
```

### POST /api/v1/ai/confirm-strategy

用户确认指标后，匹配因子、生成缺失代码、组装策略。

请求：
```json
{
  "task_id": "uuid",
  "strategy_name": "策略名称（可选，默认AI生成）",
  "indicators": [
    {
      "name": "RSI超卖反弹",
      "category": "动量类",
      "signal_type": "buy",
      "params": { "period": 14, "oversold": 30 },
      "matched_factor_id": "momentum_rsi"
    },
    {
      "name": "布林带下轨反弹",
      "category": "趋势类",
      "signal_type": "buy",
      "params": { "period": 20, "std_multiplier": 2 },
      "matched_factor_id": null,
      "code_reference": "价格触及布林带下轨后回升..."
    }
  ],
  "buy_logic": "AND"
}
```

响应：
```json
{
  "code": 0,
  "data": {
    "strategy_id": 123,
    "factor_config": { ... },
    "generated_factors": ["trend_bollinger"],
    "failed_factors": []
  }
}
```

### GET /api/v1/ai/analyze-stock/tasks

获取当前用户的历史分析任务列表（按时间倒序）。

## DeepSeek 集成

### 配置

- `DEEPSEEK_API_KEY` — 环境变量
- `DEEPSEEK_BASE_URL` — 默认 `https://api.deepseek.com`
- `DEEPSEEK_TIMEOUT` — 默认 60s
- 模型选择：`deepseek-chat` / `deepseek-reasoner`，用户在前端选择

### 新增模块：`app/services/llm_service.py`

```
analyze_kline(df, ts_code, name, date, model, user_prompt?) → 结构化指标列表
generate_factor_code(name, description, params, reference) → Python 模块代码
```

### Prompt 结构（分析阶段）

System prompt 定义角色（量化分析师）和严格的 JSON 输出格式要求。

User message 包含：
- 股票信息（代码、名称、截止日期、时间范围）
- K 线数据（紧凑表格：date, open, high, low, close, vol）
- 用户可选 prompt

数据量估算：90 个交易日 × ~60 字符/行 ≈ 5400 字符 ≈ 1500 tokens，总输入约 2500-3000 tokens。

### 响应解析

- Pydantic 模型校验 JSON schema
- 解析失败自动重试 1 次（附加错误信息）
- 重试仍失败 → 标记 task failed

## 因子匹配 & 代码生成

### 匹配策略（按优先级）

1. AI 标记 `code_required=false` 且给出 `matched_factor_id` → 直接使用
2. 名称相似度 > 80%（difflib.SequenceMatcher）→ 自动匹配
3. 用户手动选择（确认页可下拉关联现有因子）
4. 都不匹配 → 标记为"需要生成新代码"

### 新因子代码生成

1. 调用 DeepSeek 生成 Python 模块，严格遵循现有格式：`FACTOR_META` dict + `compute(df, params)` 函数
2. 校验：AST 语法检查 + 导入白名单（pandas, numpy）+ compute 函数签名
3. 保存到 `app/factors/{category}/{name_slug}.py`
4. 下次服务重启自动注册（复用 `__init__.py` 的自动发现机制）
5. 校验失败重试 1 次，仍失败标记该因子为"需人工编写"

### 策略组装

复用现有 `code_generator.generate_strategy_code()` + `strategy_service`，生成完整 `run(data)` 策略代码并保存。

## 前端设计

### 新页面：`/strategies/ai-builder`

两栏布局：

**左栏 — 三步流程**：
1. **提交表单**：股票搜索框、日期选择器、模型下拉框、可选 prompt 文本域、提交按钮
2. **分析进度**：loading 动画 + 状态文字，每 2 秒轮询
3. **确认指标**：AI 总结 + 指标表格（名称、类别、类型、参数、匹配因子、依据），勾选/取消、行内编辑参数、从因子库下拉添加新指标、确认按钮

**右栏 — 历史任务列表**：显示当前用户的分析任务，按时间倒序。已完成任务可点击跳回确认步骤。

### 导航入口

`StrategyList` 页面，"可视化构建"按钮旁加 "AI 参考选股" 按钮。

### 路由与状态

- URL 参数 `?task_id=xxx` 支持直接加载已完成任务的确认页
- 新 Zustand store：`aiStrategyStore`（管理当前任务状态、轮询、指标列表）

### GET /api/v1/ai/analyze-stock/tasks

获取当前用户的历史分析任务。

响应：
```json
{
  "code": 0,
  "data": {
    "tasks": [
      {
        "task_id": "uuid",
        "ts_code": "600519.SH",
        "date": "2026-05-01",
        "status": "completed",
        "created_at": "2026-05-28T10:30:00"
      }
    ]
  }
}
```

支持 `?limit=20&offset=0` 分页参数。

## 数据库模型

### AIStrategyTask（新表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| user_id | FK → users.id | 所属用户 |
| status | VARCHAR | processing / completed / failed |
| ts_code | VARCHAR | 股票代码 |
| date | VARCHAR | 截止日期 |
| model | VARCHAR | 使用的模型 |
| user_prompt | TEXT | 用户可选 prompt |
| kline_summary | JSON | K 线数据摘要 |
| result_json | JSON | AI 分析结果（指标列表） |
| error_message | TEXT | 错误信息 |
| created_at | DATETIME | 创建时间 |

## 错误处理

| 场景 | 处理 |
|------|------|
| 股票代码不存在 | 前端搜索框已有校验，后端返回 404 |
| 股票无 K 线数据 | 返回错误"该股票在指定时间内无数据" |
| DeepSeek API 不可用 | 重试 1 次，失败后 task 标记 failed |
| DeepSeek 返回非 JSON | 重试 1 次，仍失败则标记 failed |
| 因子代码生成语法错误 | 重试 1 次，仍失败标记为"需人工编写" |
| 分析超时 | 60s 超时，标记 failed |
| 重复提交 | 同一用户相同股票+日期 1 分钟内去重提示 |

## 可选增强（做完核心功能后可选）

- 每个指标在 K 线图上的信号可视化预览
- 实时 streaming 展示 DeepSeek 分析过程
- 批量多股票分析
- 历史任务支持删除
