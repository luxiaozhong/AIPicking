# 重构规格：AI 分析进度粒度改进

**版本**: 1.0
**状态**: 草稿
**创建日期**: 2026-05-30
**最后更新**: 2026-05-30
**作者**: AI Assistant (基于 Code Review)
**优先级**: 🟢 P2 — 消除用户等待焦虑

---

## 1. 背景与动机

### 当前状态

AIStrategyBuilder 在"分析中"（analyzing）阶段只显示一个静态 spinner 和一段文字：

```
┌─────────────────────────────────────────┐
│           ◌ (Spinner)                   │
│                                         │
│   DeepSeek 正在分析K线数据               │
│   识别量化指标中...                      │
│                                         │
│   最长可能需要 60 秒                     │
└─────────────────────────────────────────┘
```

**问题**：
- 用户不知道系统在干什么（获取数据？调用 LLM？解析结果？）
- 没有进度条或百分比，无法判断还要等多久
- 如果 LLM 超时或卡住，用户无从得知，只能干等
- 60 秒在 UX 上是"临界焦虑区"——足够让人怀疑系统是否挂了

### 目标

将"分析中"的黑盒过程拆解为可见的阶段步骤，给用户清晰的进度反馈。

---

## 2. 后端分析流程（当前）

分析过程在 `ai_strategy_service.py` 的 `_run_analysis` 中执行：

```
1. 获取 K 线数据 (stock_service)
   ↓
2. 构建 Prompt (llm_service._build_analysis_prompt)
   ↓
3. 调用 DeepSeek API (llm_service.analyze_stock)
   ↓
4. 解析 LLM 返回的指标 (ai_strategy_service._parse_indicators)
   ↓
5. 更新 task status → review
```

当前这 5 个步骤的状态变更只有一次：`analyzing` → `review`（或 `failed`）。

---

## 3. 设计方案

### 3.1 阶段化进度

将 `analyzing` 拆分为 4 个可见阶段：

| 阶段 | phase 值 | 说明 | 预计耗时 | 进度 % |
|------|----------|------|----------|--------|
| 1. 数据准备 | `fetching_data` | 从 stock_db 获取 K 线数据 | 1-3s | 5-15% |
| 2. LLM 分析 | `llm_analyzing` | 调用 DeepSeek API 分析 | 10-50s | 15-85% |
| 3. 解析指标 | `parsing` | 解析和校验 LLM 返回结果 | 1-3s | 85-95% |
| 4. 完成 | `review`（不变） | 展示结果供用户确认 | — | 100% |

### 3.2 数据模型变更

#### `ai_task` 表 / `result_json` 新增字段

```json
{
  // 现有字段...
  "progress": {
    "phase": "llm_analyzing",
    "phase_label": "正在调用 DeepSeek 分析K线数据...",
    "percent": 45,
    "started_at": "2026-05-30T14:00:00Z",
    "estimated_remaining_seconds": 30
  }
}
```

#### Pydantic Schema 变更

`schemas/` 中 AI 任务 status 响应新增 `progress` 字段：

```python
class AIProgress(BaseModel):
    phase: str  # fetching_data | llm_analyzing | parsing
    phase_label: str
    percent: int  # 0-100
    started_at: datetime | None = None
    estimated_remaining_seconds: int | None = None

class AITaskResponse(BaseModel):
    # ... 现有字段
    progress: AIProgress | None = None
```

### 3.3 后端改动

#### `ai_strategy_service.py` — `_run_analysis` 方法

```python
async def _run_analysis(self, task_id: int):
    task = await self._get_task(task_id)

    # 阶段 1: 数据准备
    await self._update_progress(task_id, {
        "phase": "fetching_data",
        "phase_label": "正在获取K线数据...",
        "percent": 5
    })
    df = await self.stock_service.get_kline(task.stock_code)

    # 阶段 2: LLM 分析
    await self._update_progress(task_id, {
        "phase": "llm_analyzing",
        "phase_label": "DeepSeek 正在分析K线数据，识别技术指标...",
        "percent": 15,
        "estimated_remaining_seconds": 50
    })
    llm_result = await self.llm_service.analyze_stock(df, task.stock_code)

    # 阶段 3: 解析
    await self._update_progress(task_id, {
        "phase": "parsing",
        "phase_label": "正在解析AI识别结果...",
        "percent": 85,
        "estimated_remaining_seconds": 5
    })
    indicators = self._parse_indicators(llm_result)

    # 完成
    await self._update_task(task_id, {
        "phase": "review",
        "progress": None,  # 清除 progress
        "result_json": {..., "indicators": indicators}
    })
```

#### `_update_progress` 辅助方法

```python
async def _update_progress(self, task_id: int, progress: dict):
    task = await self._get_task(task_id)
    result = json.loads(task.result_json or '{}')
    result['progress'] = progress
    task.result_json = json.dumps(result, ensure_ascii=False)
    task.updated_at = datetime.utcnow()
    await self.db.commit()
```

### 3.4 前端改动

#### `AIStrategyBuilder.tsx` — 分析阶段 UI

```tsx
// 阶段配置
const PHASE_CONFIG = {
  fetching_data: {
    icon: <DatabaseOutlined />,
    label: '获取K线数据',
    description: '正在从数据库加载股票历史行情...',
    percent: [5, 15],
  },
  llm_analyzing: {
    icon: <ThunderboltOutlined />,
    label: 'AI 指标分析',
    description: 'DeepSeek 正在识别技术指标，最多可能需要60秒',
    percent: [15, 85],
  },
  parsing: {
    icon: <CodeOutlined />,
    label: '解析结果',
    description: '正在解析和校验AI识别结果...',
    percent: [85, 95],
  },
};
```

#### 进度 UI 组件

使用 Ant Design 的 `Steps` 组件展示阶段：

```
┌─────────────────────────────────────────┐
│   AI 正在分析 K线数据                     │
│                                         │
│   ✓ 获取K线数据          已完成 (2.3s)   │
│   → AI 指标分析          进行中...       │
│     ████████░░░░░░░░  45%              │
│     预计剩余 ~30 秒                      │
│     识别到 12 个指标...                  │
│   ○ 解析结果             等待中          │
│                                         │
│   [取消分析]                            │
└─────────────────────────────────────────┘
```

#### 轮询频率调整

- `fetching_data` / `parsing` 阶段：每 1 秒轮询（变化快）
- `llm_analyzing` 阶段：每 3 秒轮询（变化慢，减少请求）

### 3.5 生成阶段同样适用

`_run_generation`（生成指标代码）也可以应用相同的阶段化：

| 阶段 | 说明 |
|------|------|
| `generating_indicator` | 正在生成第 X/N 个指标的计算函数 |
| `validating_code` | 正在验证生成的代码 |
| `assembling_strategy` | 正在组装策略（已有，保持） |

当前已有 `progress` 字段显示 "正在生成第 X/N 个指标..."，这是好的，保持一致即可。

---

## 4. 实施步骤

### Step 1: 扩展数据模型

- `result_json` 中的 `progress` 字段定义
- Pydantic schema 新增 `AIProgress`
- API 响应格式同步更新

**预估**: 20 分钟

### Step 2: 后端阶段化改造

- `ai_strategy_service.py` `_run_analysis` 方法添加阶段更新
- 新增 `_update_progress` 辅助方法
- `_run_generation` 已有的 progress 保持不变

**预估**: 30 分钟

### Step 3: 前端进度 UI

- AIStrategyBuilder 分析阶段替换 spinner 为 Steps + Progress
- 根据 `progress.phase` 动态切换展示
- 轮询频率按阶段调整

**预估**: 40 分钟

### Step 4: 测试

- 单元测试：验证各阶段的 progress 更新
- E2E 测试：验证前端正确展示各阶段

**预估**: 20 分钟

---

## 5. 验收标准

- [ ] 分析过程中，前端展示 ≥3 个可见阶段
- [ ] 每个阶段有明确的图标、标题、描述
- [ ] LLM 分析阶段有进度条和预估剩余时间
- [ ] 轮询频率随阶段变化（快阶段 1s，慢阶段 3s）
- [ ] 阶段切换在 0.5 秒内反映到 UI
- [ ] `review` 阶段后 progress 字段被清除
- [ ] 错误时 phase 切换到 `failed`，progress 清除
- [ ] 现有轮询逻辑不退化

---

## 6. 向后兼容

- 旧 task（没有 `progress` 字段的）在 `analyzing` 阶段仍显示传统 spinner
- `progress` 为可选字段，旧 API 响应不做适配也能正常展示

---

**变更日志**:
- 2026-05-30: 初始版本创建（基于 Code Review 发现）
