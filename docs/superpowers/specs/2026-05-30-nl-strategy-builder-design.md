# 自然语言策略构建器 — 设计文档

**日期**: 2026-05-30  
**状态**: 待实现  
**关联**: Idea 20 — 增强可视化构建 AI 助手功能

---

## 概述

在 `/strategies/builder` 可视化构建器中增加「相似度匹配」模式。用户用自然语言描述想要的股票特征（技术指标或交易思路），DeepSeek 识别因子并建议参考值，用户确认调整后系统生成相似度匹配策略代码。AI 生成的新因子自动沉淀到因子库，供后续复用。

## 核心决策

| 维度 | 决定 |
|------|------|
| 入口位置 | `/strategies/builder` 页面，新增「相似度匹配」tab |
| 因子匹配策略 | 优先匹配已有因子（内置 + AI 历史生成），未匹配的由 DeepSeek 生成后入库 |
| 输入范围 | 技术指标描述 + 交易思路，两者都支持 |
| 策略类型 | 相似度匹配策略（与 AI 参考选股输出格式一致） |
| 参考值来源 | DeepSeek 建议 + 用户可编辑（混合模式） |
| 复用目标 | AI 参考选股的 LLM 调用、代码生成、验证、SSE 进度、策略组装全链路 |

---

## 1. UI 布局

### 1.1 模式切换

Builder 页面顶部增加两个 tab：

```
[🔧 信号策略]  [🎯 相似度匹配 NEW]
```

- **信号策略**：现有 builder 功能，手工选择因子组合 buy/sell 信号，输出 buy/sell 信号策略。UI 完全不变。
- **相似度匹配**：新增 AI 助手面板，自然语言输入 → AI 识别因子 → 确认 → 生成相似度策略。

### 1.2 相似度匹配模式布局

```
┌─────────────────────────────────────────┐
│ 🤖 AI 助手 — 用自然语言描述你想要的股票特征   │
├─────────────────────────────────────────┤
│ [输入框：如"底部放量反弹、MACD金叉..."]  [分析→] │
├─────────────────────────────────────────┤
│ DeepSeek 识别到的策略思路摘要...              │
├─────────────────────────────────────────┤
│ 识别到的因子（可编辑参考值）：                 │
│ ┌───────────────────────────────────────┐ │
│ │ ✓ 已有  RSI 14日      动量类  参考值:[30]  ✕│ │
│ │ ✓ 已有  MACD 金叉      趋势类  参考值:[1]   ✕│ │
│ │ 🆕 生成 底部放量确认    量能类  参考值:[2.5] ✕│ │
│ └───────────────────────────────────────┘ │
│                    [重新输入]  [确认 → 生成策略] │
└─────────────────────────────────────────┘
```

### 1.3 关键交互

- **✓ 已有**：因子库中已存在（绿色标签），确认后直接复用，无需重新生成代码
- **🆕 生成**：因子库中不存在（黄色标签），确认后由 DeepSeek 生成代码并入库
- **参考值编辑**：点击数值直接输入修改，DeepSeek 建议但用户未手动修改过的用黄色边框高亮
- **删除因子**：点击 ✕ 移除不需要的因子
- **分析进度**：分析中显示 loading 状态，生成中通过 SSE 显示"正在生成第 X/N 个因子代码..."
- **切出保护**：切换到「信号策略」tab 时弹窗确认："切换将丢失当前 AI 分析结果，是否继续？"

---

## 2. 后端架构

### 2.1 API 端点

新增 3 个端点，与现有 AI 参考选股端点并行：

| 端点 | 说明 |
|------|------|
| `POST /api/v1/ai/analyze-nl` | 提交自然语言分析。Body: `{prompt, model?}`。返回 `{task_id, status}` |
| `GET /api/v1/ai/analyze-nl/{task_id}` | 轮询任务状态/结果（不含 stream 时的降级方案） |
| `GET /api/v1/ai/analyze-nl/{task_id}/stream` | SSE 实时推送状态变化 + 进度 |
| `POST /api/v1/ai/confirm-nl-strategy` | 确认因子列表，触发异步策略生成。Body: `{task_id, strategy_name?, indicators}` |

扩展已有端点：

| 变更 | 说明 |
|------|------|
| `GET /api/v1/ai/analyze-stock/tasks` | 增加可选 `task_type` 过滤参数，前端可分别查询不同类型的任务历史 |

### 2.2 数据模型

扩展 `AIStrategyTask`（`ai_strategy_tasks` 表）：

```python
# 新增字段
task_type = Column(String(20), default="stock_reference", index=True)
# 值: "stock_reference" | "natural_language"
```

现有 `ts_code`、`date`、`kline_summary` 字段在 `task_type='natural_language'` 时可为空。`user_prompt` 存储自然语言输入原文。状态机 `status` 保持不变：`processing → review → generating → completed / failed`。

新增 `AIFactor` 表（`ai_factors`）：

```python
class AIFactor(BaseModel):
    __tablename__ = "ai_factors"
    
    factor_id = Column(String(100), unique=True, index=True)  # 如 "ai_volume_bottom_breakout"
    name = Column(String(100))           # 因子名称
    category = Column(String(50))        # 分类
    description = Column(Text)           # 描述
    params_schema = Column(Text)         # JSON 参数定义
    file_path = Column(String(200))      # .py 文件路径
    created_by = Column(Integer, ForeignKey("users.id"))
    usage_count = Column(Integer, default=0)
```

### 2.3 服务层

```
ai_nl_service.py（新）
├── analyze_natural_language(prompt, model) → dict
│   └── 调用 DeepSeek（新 system prompt）识别因子+参考值
│
factor_registry.py（扩展 __init__.py）
├── match_factors(indicators) → list[dict]   # 名称+描述模糊匹配
├── save_ai_factor(name, category, code, ...) → factor_id  # 写入.py + DB
└── reload_factors()                         # 热加载（已有）
│
llm_service.py（复用）
├── _call_deepseek(system_prompt, user_msg, model)  # API 调用+重试
└── generate_indicator_code(name, description, params, computation)  # 代码生成
│
ai_strategy_service.py（复用）
├── match_and_generate_with_progress(task, indicators, ...)  # 并发生成+验证
├── _validate_code(code)                                     # AST+运行时+NaN
├── _assemble_similarity_strategy(name, ts_code, fns)        # 策略组装
└── _name_to_fn(name)                                        # 函数名生成
```

### 2.4 新 System Prompt

`NL_ANALYSIS_SYSTEM_PROMPT` — 自然语言因子识别：

```
你是一位量化策略分析师。根据用户的自然语言描述，识别其中涉及的量化因子/指标，
并给出每个因子的参考值。

任务：
1. 从用户描述中提取所有量化因子概念
2. 每个因子给出：name, category, description, params, ref_value（浮点数）, computation
3. 如果用户描述的是交易思路（如"底部放量"），将其映射为可计算的因子组合
4. ref_value 反映用户描述的"理想状态"数值

严格按 JSON 格式返回，不要有任何额外文字：
{
  "summary": "对用户策略思路的概述",
  "strategy_type": "similarity",
  "indicators": [
    {
      "name": "RSI 14日",
      "category": "动量类",
      "description": "14日相对强弱指标，值越低表示超卖",
      "params": {"period": 14},
      "ref_value": 30.0,
      "computation": "RSI = 100 - 100/(1 + RS)..."
    }
  ]
}
```

---

## 3. 数据流

### Phase 1: 提交分析

1. 用户在相似度匹配 tab 输入自然语言 → 点击「分析」
2. 前端 `POST /ai/analyze-nl {prompt}`，phase → `submitting`
3. 后端创建 `AIStrategyTask(task_type='natural_language', status='processing')`
4. `asyncio.create_task(_run_nl_analysis)` 后台执行
5. 前端收到 task_id → 连接 SSE → phase → `analyzing`

### Phase 2: DeepSeek 因子识别

1. 调用 `ai_nl_service.analyze_natural_language(prompt)`（120s 超时）
2. DeepSeek 返回 JSON: `{summary, indicators: [{name, category, ref_value, params, computation}]}`
3. 对每个 indicator 调用 `factor_registry.match_factors()`：
   - 名称 difflib 相似度 + 关键词匹配，阈值 > 0.7 判定为匹配
   - 搜索范围：内置因子 + `ai_factors` 表
   - 结果分 `matched`（已有因子）和 `new`（待生成）
4. SSE 推送 `status='review'` + indicators（带 matched/new 标记）
5. 前端 phase → `review`

### Phase 3: 用户审核确认

1. 前端展示因子列表：✓ 已有（绿色）+ 🆕 生成（黄色）
2. 参考值默认显示 DeepSeek 建议值，可编辑，未修改的高亮
3. 用户可删除不需要的因子
4. 用户点击「确认 → 生成策略」
5. 前端 `POST /ai/confirm-nl-strategy {task_id, indicators}`，phase → `generating`

### Phase 4: 策略代码生成

1. `asyncio.create_task(_run_nl_generation)` 后台执行（300s 超时）
2. 对已有因子：直接从因子库获取 compute 函数，无需 LLM 调用
3. 对新因子：
   - 调用 `llm_service.generate_indicator_code()`（Semaphore(5) 并发）
   - AST 语法验证 + 运行时验证 + NaN 检测
   - 通过的：写入 `app/factors/ai_generated/{name}.py` + `ai_factors` 表
   - 失败的：记入 `failed_factors` 列表
4. 组装相似度策略代码（复用 `_assemble_similarity_strategy`）
5. 创建 `Strategy` 记录，task 标记 `completed`
6. SSE 推送进度 "第 X/N 个" + 最终 `strategy_id`
7. 前端 phase → `completed`，可跳转到策略详情

### 与 AI 参考选股的流程对比

| | AI 参考选股 | 自然语言策略 |
|---|---|---|
| 输入 | 股票代码 + 日期 | 自然语言描述 |
| 因子来源 | K线实际计算值 | DeepSeek 推断建议 |
| 参考值 | K线实际值（不可改） | DeepSeek 建议值（可编辑） |
| 是否有 K线获取 | 有 | 无 |
| 代码生成 | 全量生成 | 仅新因子生成 |
| 策略组装 | 相似度策略 | 相同 |

---

## 4. 因子库集成

### 4.1 双重存储

- **文件存储**：`app/factors/ai_generated/{name}.py`，格式与内置因子一致（`FACTOR_META` + `compute(df, params)`），可直接执行
- **数据库存储**：`ai_factors` 表，记录元数据、溯源信息、使用次数

### 4.2 因子匹配引擎

- 输入：DeepSeek 返回的 indicator `{name, description, category}`
- 方法：名称 difflib 模糊匹配 + 描述关键词匹配
- 搜索范围：`FACTOR_REGISTRY`（内置因子）+ `ai_factors` 表（AI 历史生成）
- 阈值：相似度 > 0.7 判定为匹配
- 输出：`{matched: true/false, factor_id: "..." | null}`

### 4.3 热加载

新因子写入 `ai_generated/` 目录后调用 `reload_factors()`，后续请求立即可用。下次用户描述类似概念时，匹配引擎直接命中，不再重复生成。

### 4.4 .py 文件模板

```python
"""底部放量确认因子 — AI 自动生成"""
FACTOR_META = {
    "id": "ai_volume_bottom_breakout",
    "name": "底部放量确认",
    "category": "量能类",
    "source": "ai_generated",
    "params": [
        {"name": "vol_ratio", "type": "float", "default": 2.0, "description": "放量倍数阈值"}
    ],
}

import pandas as pd
import numpy as np

def compute(df, params):
    vol_ratio = params.get("vol_ratio", 2.0)
    if len(df) < 20:
        return float('nan')
    # DeepSeek 生成的逻辑...
    return float(result)
```

---

## 5. 异常处理

### 5.1 分析阶段（Phase 2）

| 场景 | 处理 | 状态 |
|------|------|------|
| DeepSeek 超时 (120s) | `asyncio.wait_for` + catch → task 标记 failed，提示"分析超时，请重试" | failed |
| DeepSeek API 错误 | tenacity 自动重试 3 次（指数退避 2s→4s→8s），全部失败 → failed | failed |
| 未识别到任何因子 | `indicators = []` → 前端提示"未能识别到量化因子，请更具体地描述" | review（空） |
| JSON 解析失败 | 正则兜底提取 `{...}`，仍失败 → failed | failed |
| 输入过短 (< 5 字) | 前端 + 后端双重校验 → 400 | 400 |

### 5.2 生成阶段（Phase 4）

| 场景 | 处理 | 状态 |
|------|------|------|
| 代码生成超时 (300s) | `asyncio.wait_for` + catch → failed，提示"生成超时，请减少指标数量" | failed |
| 个别因子生成失败 | 记入 `failed_factors`，成功项继续组装 | completed |
| 全部因子生成失败 | 无法组装策略 → failed | failed |
| 代码验证失败 | AST/运行时/NaN 任一失败 → 该因子标记 failed，不影响其他 | completed（部分）|
| 因子文件写入冲突 | `factor_id` 含 hash，`ai_factors` 表检查去重，已存在则复用 | 复用 |
| 重复提交 (60s 内) | 后端检查相同 user_id + task_type + user_prompt | 400 |

### 5.3 前端边界

| 场景 | 处理 |
|------|------|
| SSE 连接断开 | 现有 `resumeInProgressTask()` 恢复机制 |
| 页面刷新时正在生成 | `loadTask()` 检测 status=generating → 自动重连 SSE |
| 组件卸载 | `clearTimeout` + SSE disconnect（现有逻辑） |
| 参考值为空 | 前端校验：必填且为数字 → 不合法时「确认」disabled |
| 切出模式 | 确认对话框防止误操作丢失 AI 分析结果 |

### 5.4 已有逻辑（无需新开发）

- DeepSeek 自动重试（tenacity, 3次, 指数退避）
- 代码沙箱验证（AST + 导入白名单 + 运行时 + NaN）
- 并发生成限流（Semaphore(5)）
- SSE 进度推送
- 任务状态恢复（resumeInProgressTask）
- 后台任务超时（asyncio.wait_for）

---

## 6. 前端状态机

与 AI 参考选股完全一致，`aiStrategyStore` 通过 `task_type` 区分来源：

```
idle → submitting → analyzing → review → generating → completed
  ↑                                    ↓         ↓
  └────────────────── failed ←─────────┴─────────┘
```

## 7. 路由与组件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `frontend/src/pages/StrategyBuilder.tsx` | 修改 | 增加模式切换 tab，嵌入相似度匹配面板 |
| `frontend/src/components/AINLAssistant.tsx` | 新增 | 相似度匹配 AI 助手面板组件 |
| `frontend/src/stores/aiStrategyStore.ts` | 修改 | 增加 `taskType` 状态，增加 `submitNL` / `confirmNL` action |
| `frontend/src/services/aiService.ts` | 修改 | 新增 `analyzeNL` / `confirmNLStrategy` API 调用 |
| `frontend/src/types/aiStrategy.ts` | 修改 | 新增请求/响应类型 |

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/app/api/ai.py` | 修改 | 新增 3 个端点 + 后台任务函数 |
| `backend/app/services/ai_nl_service.py` | 新增 | 自然语言分析 + 新 system prompt |
| `backend/app/factors/__init__.py` | 修改 | 增加 `match_factors()` + 扫描 `ai_generated/` 目录 |
| `backend/app/models/ai_task.py` | 修改 | 增加 `task_type` 字段 |
| `backend/app/models/ai_factor.py` | 新增 | AI 生成因子 ORM 模型 |
| `backend/app/factors/ai_generated/` | 新增 | AI 因子 .py 文件存储目录 |

---

## 8. 测试要点

- [ ] NL 分析：正常输入返回因子列表 + 参考值
- [ ] NL 分析：无意义输入返回空 indicators
- [ ] NL 分析：DeepSeek 超时 → failed + 错误提示
- [ ] 因子匹配：已有因子（如"RSI"）正确匹配到 `momentum_rsi`
- [ ] 因子匹配：新因子（如"底部放量"）标记为待生成
- [ ] 代码生成：已有因子跳过 LLM 调用，直接复用
- [ ] 代码生成：新因子生成成功 → 代码验证通过 → 写入 .py + DB
- [ ] 因子入库：重复描述不再生成新因子（匹配命中）
- [ ] 策略组装：生成的相似度策略代码通过 AST 验证
- [ ] SSE 进度：生成过程中推送正确的 completed/total
- [ ] 参考值编辑：用户修改后的值传递到策略生成
- [ ] 模式切换：切换 tab 时弹确认框
- [ ] 页面恢复：刷新后自动恢复 generating 状态的进度
