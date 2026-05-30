# AI 参考选股 重构 Spec

> 版本: 1.1 | 日期: 2026-05-30 | 状态: P0/P1 已完成，P2 规划中

## 背景

AI 参考选股功能经过初始迭代后，存在以下架构问题：

1. **策略生成阶段**：50+ 个指标的 compute_value 代码串行调用 DeepSeek，耗时 4 分钟以上，无进度反馈
2. **状态机混乱**：`status: 'polling'` 同时承载"等待 K 线分析"和"等待策略生成"两种语义，`submitting` 布尔值作为侧面区分，已导致状态残留 bug
3. **前端渲染重复**：历史分析面板在 3 个渲染分支中各写一遍，逻辑略有差异
4. **轮询脆弱**：固定间隔无退避，无超时上限，页面离开后状态残留
5. **异常处理不足**：DeepSeek 调用无重试，错误静默吞掉，后台任务 fire-and-forget

## 已完成 (P0/P1)

| 优先级 | 项目 | Commit | 说明 |
|--------|------|--------|------|
| P0 (a) | 策略生成并行化 + 进度反馈 | `29ed85f` | Semaphore 5 并发，progress 字段实时写入 DB |
| P0 (b) | 状态机 status→phase 单一枚举 | `f0ba518` | `idle → submitting → analyzing → review → generating → completed` |
| P1 (c) | 轮询改 SSE | `b8423de` | `GET /ai/analyze-stock/{task_id}/stream` 实时推送 |
| P1 (d) | TaskHistoryPanel 共享组件 | `6665f89` | 消除三处重复，统一加载/空态/列表渲染 |
| P1 (e) | DeepSeek 重试 | `7417c12` | tenacity 指数退避 3 次 (2s→4s→8s) |
| 额外 | 后台任务超时控制 | `7417c12` | 分析 120s / 生成 300s |
| 额外 | 浏览器回退死循环 | `75f8b72` | 跳转后清除 generatedStrategyId |
| 额外 | review/completed 状态区分 | `75f8b72` | 指标就绪 vs 策略已生成 |

## 非目标（本次）

无 — 所有 P0/P1 项目均已完成。

## 未来规划 (P2 — 长期改进)

以下改进已评估但暂不实施，待时机成熟时推进。

### P2 (f): 任务模型独立化

**当前问题：** `AIStrategyTask.result_json` 是一个 Text 字段塞入整个 JSON（50+ 指标 + 进度 + 策略结果），无法结构化查询。

**改进方向：**
- `indicator_values` 单独建表，每个指标一行，含 `task_id`, `name`, `category`, `value`, `params`
- `generation_progress` 字段独立到任务表
- 支持跨任务查询："过去哪些股票 RSI 低于 30？"
- 支持指标值历史趋势分析

**预估工作量：** 2-3 天

### P2 (g): 任务队列 (Celery / ARQ)

**当前问题：** `asyncio.create_task` fire-and-forget，服务器重启丢失任务，无重试机制，无水平扩展。

**改进方向：**
- Celery + Redis 或 ARQ（纯 async）替换 `asyncio.create_task`
- 任务持久化，重启自动恢复
- 内置重试 + 超时
- Worker 进程独立管理
- 支持多 worker 水平扩展

**预估工作量：** 2-3 天

### P2 (h): 前端状态机 (XState)

**当前问题：** Zustand store 中手动管理 `phase` 枚举 + `taskId` + `progress` 组合，虽然已大幅改善，但仍缺少形式化的状态转换约束。

**改进方向：**
- 用 XState 5 定义正式状态图
- 明确合法状态转换，防止非法组合
- 可视化状态图，便于理解和调试
- 自动生成 TypeScript 类型

**预估工作量：** 1-2 天

## 详细设计

### 1. 状态机拆分

**现状：**
```
status: 'idle' | 'submitting' | 'polling' | 'completed' | 'failed'
submitting: boolean  (侧面区分"分析中" vs "生成中")
```

**改为：**
```
phase: 'idle' | 'submitting' | 'analyzing' | 'review' | 'generating' | 'completed' | 'failed'
```

| phase | 含义 | UI 表现 |
|-------|------|---------|
| `idle` | 初始状态 | 左侧提交表单，右侧历史面板 |
| `submitting` | 正在提交分析请求 | 提交按钮 loading |
| `analyzing` | DeepSeek 正在分析 K 线 | "正在分析 K 线数据..." |
| `review` | 分析完成，等待用户确认指标 | 指标表格 + 确认按钮 |
| `generating` | 正在生成策略代码 | "正在生成策略代码 (12/50)..." |
| `completed` | 策略已生成 | 跳转策略详情页 |
| `failed` | 出错 | 显示错误信息 |

移除 `submitting` 布尔值，所有信息由 `phase` 单一来源表达。

### 2. 前端组件抽取

将三个渲染分支中重复的"历史分析"面板抽为 `<TaskHistoryPanel>` 组件：

```tsx
interface TaskHistoryPanelProps {
  tasks: AnalysisTask[];
  loading: boolean;
  currentTaskId: string | null;
  onTaskClick: (taskId: string) => void;
}
```

该组件统一处理：加载态、空态、任务列表（含状态标签、当前任务高亮、点击交互）。

### 3. 策略生成并行化

`match_and_generate()` 中改为并发调用 DeepSeek，限制并发数 5：

```python
sem = asyncio.Semaphore(5)

async def generate_one(ind):
    async with sem:
        code = await generate_indicator_code(...)
        _validate_code(code)
        return result

results = await asyncio.gather(*[generate_one(ind) for ind in indicators])
```

同时在任务 `result_json` 中增加 `progress` 字段：
```json
{"progress": {"completed": 12, "total": 50}}
```

### 4. 后端进度端点

新增 `GET /ai/analyze-stock/{task_id}/progress`，返回：
```json
{"code": 0, "data": {"phase": "generating", "completed": 12, "total": 50}}
```

前端在 `generating` 阶段轮询此端点显示实时进度，而非无差别轮询主结果端点。

### 5. DeepSeek 调用重试

使用 `tenacity` 库添加指数退避重试：

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError))
)
async def _call_deepseek(...):
```

### 6. 轮询优化

- 增加递增退避：2s → 4s → 8s → 16s（上限 30s）
- 增加最大轮询时长：5 分钟超时自动标记失败
- `cancelPolling` 同步清理 phase 状态

### 7. 后台任务容错

- 在 `_run_analysis` 和 `_run_generation` 中增加超时控制（`asyncio.wait_for`）
- 增加心跳时间戳字段 `last_heartbeat`，前端可检测僵尸任务

## 影响范围

### 后端
- `app/api/ai.py` — 新增 progress 端点，重构路由
- `app/services/llm_service.py` — 加重试
- `app/services/ai_strategy_service.py` — 并行化 + 进度
- `app/models/ai_task.py` — 新增 last_heartbeat 字段
- `requirements.txt` — 新增 tenacity

### 前端
- `src/pages/AIStrategyBuilder.tsx` — 重构为单一渲染分支 + TaskHistoryPanel
- `src/components/TaskHistoryPanel.tsx` — 新建
- `src/stores/aiStrategyStore.ts` — 状态机重构
- `src/types/aiStrategy.ts` — 类型更新
- `src/services/aiService.ts` — 新增进度 API

## 验收标准

1. ✅ 历史分析面板在全部状态下行为一致
2. ✅ 策略生成阶段显示实时进度（如 "正在生成策略代码 (12/50)"）
3. ✅ 策略生成耗时从 ~250s 降至 ~50s（并行 5 个）
4. ✅ 离开页面再返回，状态正确恢复或重置
5. ✅ DeepSeek 调用失败时自动重试 3 次
6. ✅ 后端测试覆盖新增逻辑
7. ✅ CLAUDE.md 更新反映架构变更
