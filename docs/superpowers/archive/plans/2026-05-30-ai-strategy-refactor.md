# AI 参考选股 重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 AI 参考选股功能 — 抽取共享组件、清理状态机、并行化策略生成、增加 DeepSeek 重试、改进进度反馈

**Architecture:** 前端状态机从 `status + submitting` 双变量改为单一 `phase` 枚举。后端策略生成从串行改为并发（Semaphore 限流 5），进度写入任务 JSON 供前端轮询。历史分析面板抽取为独立组件消除三处重复代码。

**Tech Stack:** React 18 + TypeScript + Zustand + Ant Design 6 | FastAPI + SQLAlchemy async + DeepSeek API + tenacity

---

### Task 1: 抽取 TaskHistoryPanel 共享组件

**Files:**
- Create: `frontend/src/components/TaskHistoryPanel.tsx`
- Modify: `frontend/src/pages/AIStrategyBuilder.tsx`

- [ ] **Step 1: 创建 TaskHistoryPanel 组件**

```tsx
// frontend/src/components/TaskHistoryPanel.tsx
import React from 'react';
import { Card, List, Tag, Space, Typography, Spin, Empty } from 'antd';
import type { AnalysisTask } from '@/types/aiStrategy';

const { Text } = Typography;

interface TaskHistoryPanelProps {
  tasks: AnalysisTask[];
  loading: boolean;
  currentTaskId: string | null;
  onTaskClick: (taskId: string) => void;
}

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  completed: { color: 'green', label: '已完成' },
  processing: { color: 'blue', label: '分析中' },
  generating: { color: 'blue', label: '生成中' },
  failed: { color: 'red', label: '失败' },
};

const TaskHistoryPanel: React.FC<TaskHistoryPanelProps> = ({
  tasks,
  loading,
  currentTaskId,
  onTaskClick,
}) => {
  return (
    <Card title="历史分析" size="small">
      {loading ? (
        <Spin style={{ display: 'block', textAlign: 'center' }} />
      ) : tasks.length === 0 ? (
        <Empty description="暂无分析记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          size="small"
          dataSource={tasks}
          renderItem={(t) => {
            const cfg = STATUS_CONFIG[t.status] || { color: 'default', label: t.status };
            const isClickable = t.status === 'completed';
            const isActive = t.task_id === currentTaskId;
            return (
              <List.Item
                style={{
                  cursor: isClickable ? 'pointer' : 'default',
                  background: isActive ? '#f0f5ff' : undefined,
                }}
                onClick={() => {
                  if (isClickable) onTaskClick(t.task_id);
                }}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Text strong>{t.ts_code}</Text>
                      <Tag color={cfg.color}>{cfg.label}</Tag>
                    </Space>
                  }
                  description={`${t.date} · ${(t.created_at || '').slice(0, 16)}`}
                />
              </List.Item>
            );
          }}
        />
      )}
    </Card>
  );
};

export default TaskHistoryPanel;
```

- [ ] **Step 2: 在 AIStrategyBuilder 中替换三处历史分析面板**

在 `AIStrategyBuilder.tsx` 顶部添加 import：
```tsx
import TaskHistoryPanel from '@/components/TaskHistoryPanel';
```

三处 `<Card title="历史分析" size="small">...</Card>` 分别替换为：

```tsx
<TaskHistoryPanel
  tasks={tasks}
  loading={tasksLoading}
  currentTaskId={taskId}
  onTaskClick={loadTask}
/>
```

三处替换位置：
1. 第 315 行附近（idle/submitting/failed 分支）
2. 第 383 行附近（polling 分支）
3. 第 511 行附近（completed 分支）

- [ ] **Step 3: 验证构建通过**

```bash
cd frontend && npm run build
```

Expected: 无 TypeScript 错误，构建成功

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/TaskHistoryPanel.tsx frontend/src/pages/AIStrategyBuilder.tsx
git commit -m "refactor: 抽取 TaskHistoryPanel 共享组件，消除三处重复代码"
```

---

### Task 2: 重构前端状态机（status → phase）

**Files:**
- Modify: `frontend/src/types/aiStrategy.ts`
- Modify: `frontend/src/stores/aiStrategyStore.ts`
- Modify: `frontend/src/pages/AIStrategyBuilder.tsx`

- [ ] **Step 1: 更新类型定义**

在 `frontend/src/types/aiStrategy.ts` 中添加：

```typescript
export type AnalysisPhase =
  | 'idle'
  | 'submitting'
  | 'analyzing'
  | 'review'
  | 'generating'
  | 'completed'
  | 'failed';

export interface GenerationProgress {
  completed: number;
  total: number;
}
```

- [ ] **Step 2: 重构 aiStrategyStore — 状态定义和初始值**

`frontend/src/stores/aiStrategyStore.ts`:

将：
```typescript
interface AIStrategyState {
  taskId: string | null;
  status: 'idle' | 'submitting' | 'polling' | 'completed' | 'failed';
  error: string | null;
  result: AnalysisResult | null;
  indicators: IndicatorItem[];
  buyLogic: 'AND' | 'OR';
  tasks: AnalysisTask[];
  tasksLoading: boolean;
  submitting: boolean;
  generatedStrategyId: number | null;
```

改为：
```typescript
interface AIStrategyState {
  taskId: string | null;
  phase: AnalysisPhase;
  error: string | null;
  result: AnalysisResult | null;
  indicators: IndicatorItem[];
  buyLogic: 'AND' | 'OR';
  tasks: AnalysisTask[];
  tasksLoading: boolean;
  generatedStrategyId: number | null;
  progress: GenerationProgress | null;
```

初始值：
```typescript
export const useAIStrategyStore = create<AIStrategyState>((set, get) => ({
  taskId: null,
  phase: 'idle',
  error: null,
  result: null,
  indicators: [],
  buyLogic: 'OR',
  tasks: [],
  tasksLoading: false,
  generatedStrategyId: null,
  progress: null,
```

- [ ] **Step 3: 更新 submitAnalysis**

```typescript
submitAnalysis: async (tsCode, date, model, prompt) => {
    set({ phase: 'submitting', error: null });
    try {
      const res = await aiService.analyzeStock({ ts_code: tsCode, date, model, prompt });
      if (res.code === 0) {
        const taskId = res.data.task_id;
        set({ taskId, phase: 'analyzing' });
        get().pollResult(taskId);
      } else {
        set({ phase: 'idle', error: res.message || '提交失败' });
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({ phase: 'failed', error: err.response?.data?.message || '提交分析失败' });
    }
  },
```

- [ ] **Step 4: 更新 pollResult**

```typescript
pollResult: async (taskId: string) => {
    const poll = async () => {
      try {
        const res = await aiService.getAnalysisResult(taskId);
        if (res.code !== 0) {
          _schedulePoll(poll, 2000);
          return;
        }

        const data = res.data;
        if (data.status === 'completed') {
          // 区分：有 strategy_id 表示策略已生成，否则是分析完成等待确认
          if (data.strategy_id) {
            set({ phase: 'completed', generatedStrategyId: data.strategy_id });
          } else {
            set({
              phase: 'review',
              result: data,
              indicators: data.indicators || [],
              error: null,
            });
          }
          get().fetchTasks();
        } else if (data.status === 'failed') {
          set({ phase: 'failed', error: data.error_message || '分析失败' });
          get().fetchTasks();
        } else if (data.status === 'generating') {
          // 正在生成策略代码，更新进度
          set({ phase: 'generating' });
          _schedulePoll(poll, 2000);
        } else {
          // processing
          _schedulePoll(poll, 2000);
        }
      } catch {
        _schedulePoll(poll, 3000);
      }
    };
    _schedulePoll(poll, 2000);
  },
```

- [ ] **Step 5: 更新 clearAnalysis**

```typescript
clearAnalysis: () => {
    _clearPollTimer();
    set({
      taskId: null,
      phase: 'idle',
      error: null,
      result: null,
      indicators: [],
      progress: null,
    });
  },
```

- [ ] **Step 6: 更新 confirmAndGenerate**

```typescript
confirmAndGenerate: async (strategyName) => {
    const { taskId, indicators, buyLogic } = get();
    set({ phase: 'generating', progress: null });
    try {
      const res = await aiService.confirmStrategy({
        task_id: taskId!,
        strategy_name: strategyName,
        indicators: indicators as unknown as Record<string, unknown>[],
      });

      if (res.code === 0 && res.data.status === 'generating') {
        return new Promise<number>((resolve, reject) => {
          const poll = async () => {
            try {
              const r = await aiService.getAnalysisResult(taskId!);
              // 更新进度
              if (r.data.progress) {
                set({ progress: r.data.progress });
              }
              if (r.data.status === 'completed' && r.data.strategy_id) {
                const sid = r.data.strategy_id;
                try {
                  await strategyService.getStrategy(sid);
                } catch {
                  _schedulePoll(poll, 1500);
                  return;
                }
                set({ generatedStrategyId: sid, phase: 'completed', progress: null });
                resolve(sid);
              } else if (r.data.status === 'failed') {
                set({ phase: 'failed', error: r.data.error_message || '生成失败', progress: null });
                reject(new Error(r.data.error_message));
              } else {
                _schedulePoll(poll, 2000);
              }
            } catch {
              _schedulePoll(poll, 3000);
            }
          };
          _schedulePoll(poll, 2000);
        });
      } else if (res.code === 0 && res.data.strategy_id) {
        set({ generatedStrategyId: res.data.strategy_id, phase: 'completed' });
        return res.data.strategy_id;
      } else {
        set({ phase: 'failed', error: res.message || '生成策略失败' });
        throw new Error(res.message);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({ phase: 'failed', error: err.response?.data?.message || '生成策略失败', progress: null });
      throw e;
    }
  },
```

- [ ] **Step 7: 更新 loadTask**

```typescript
loadTask: async (taskId: string) => {
    set({ taskId });
    try {
      const res = await aiService.getAnalysisResult(taskId);
      const data = res.data;
      if (res.code === 0 && data.status === 'completed') {
        if (data.strategy_id) {
          set({ phase: 'completed', generatedStrategyId: data.strategy_id });
        } else {
          set({
            phase: 'review',
            result: data,
            indicators: data.indicators || [],
            error: null,
          });
        }
      } else if (data.status === 'failed') {
        set({ phase: 'failed', error: data.error_message });
      } else if (data.status === 'processing') {
        set({ phase: 'analyzing' });
        get().pollResult(taskId);
      } else if (data.status === 'generating') {
        set({ phase: 'generating' });
        get().pollResult(taskId);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({ phase: 'failed', error: err.response?.data?.message || '加载任务失败' });
    }
  },
```

- [ ] **Step 8: 更新 resumeInProgressTask**

```typescript
resumeInProgressTask: async () => {
    try {
      const res = await aiService.getTasks();
      if (res.code !== 0) return;
      const tasks: AnalysisTask[] = res.data.tasks || [];
      const inProgress = tasks.find(
        (t) => t.status === 'processing' || t.status === 'generating'
      );
      if (inProgress) {
        get().loadTask(inProgress.task_id);
        return;
      }

      // 恢复 stale 状态：store 仍处于 analyzing/generating 但任务已完成
      const { taskId, phase } = get();
      if ((phase === 'analyzing' || phase === 'generating') && taskId) {
        const currentTask = tasks.find((t) => t.task_id === taskId);
        if (currentTask?.status === 'completed') {
          get().loadTask(taskId);
        } else if (currentTask?.status === 'failed') {
          set({ phase: 'failed', error: '任务执行失败' });
        } else if (!currentTask) {
          set({ phase: 'idle', taskId: null, error: null });
        }
      }
    } catch {
      // silent
    }
  },
```

- [ ] **Step 9: 更新 cancelPolling**

```typescript
cancelPolling: () => {
    _clearPollTimer();
  },
```

（保持不变，`phase` 不重置以支持恢复）

- [ ] **Step 10: 重构 AIStrategyBuilder 渲染逻辑**

将所有 `status ===` 改为 `phase ===`，`submitting` 引用改为 `phase === 'generating'`：

```tsx
// 替换：
// status === 'idle' → phase === 'idle'
// status === 'submitting' → phase === 'submitting'
// status === 'failed' → phase === 'failed'
// status === 'polling' → phase === 'analyzing'
// status === 'completed' (before confirm) → phase === 'review'
// submitting === true → phase === 'generating'
```

具体渲染分支：

```tsx
// Branch 1: idle / submitting / failed
if (phase === 'idle' || phase === 'submitting' || phase === 'failed') {
  // 左侧：提交表单
  // 右侧：<TaskHistoryPanel ... />
}

// Branch 2: analyzing (was "polling" for analysis)
if (phase === 'analyzing') {
  // 左侧：spinner + "DeepSeek 正在分析 K 线数据..."
  // 右侧：<TaskHistoryPanel ... />
}

// Branch 3: generating (was "completed" + submitting)
if (phase === 'generating') {
  // 左侧：spinner + "DeepSeek 正在生成策略代码..." + 进度
  // 右侧：<TaskHistoryPanel ... />
}

// Branch 4: review (was "completed" without submitting)
// 左侧：指标表格 + 确认按钮
// 右侧：<TaskHistoryPanel ... />
```

左侧 generating 阶段的进度显示：
```tsx
{progress && (
  <Text type="secondary">
    正在生成第 {progress.completed}/{progress.total} 个指标的计算代码...
  </Text>
)}
```

- [ ] **Step 11: 验证构建通过**

```bash
cd frontend && npm run build
```

Expected: 无 TypeScript 错误

- [ ] **Step 12: Commit**

```bash
git add frontend/src/types/aiStrategy.ts frontend/src/stores/aiStrategyStore.ts frontend/src/pages/AIStrategyBuilder.tsx
git commit -m "refactor: 重构状态机 status→phase 单一枚举，移除 submitting 布尔值"
```

---

### Task 3: 策略生成并行化 + 进度字段

**Files:**
- Modify: `backend/app/services/ai_strategy_service.py`
- Modify: `backend/app/api/ai.py`

- [ ] **Step 1: 重构 match_and_generate 为并发**

```python
# backend/app/services/ai_strategy_service.py

import asyncio

async def match_and_generate(
    task: AIStrategyTask,
    indicators: list[dict],
    strategy_name: str,
    buy_logic: str,
    user_id: int,
) -> dict:
    """为每个指标并发生成 compute_value 代码，组装成相似度策略"""
    generated = []
    failed = []
    indicator_fns = []

    sem = asyncio.Semaphore(5)  # 限制并发数

    async def generate_one(ind: dict, idx: int):
        name = ind.get("name", "")
        ref_value = ind.get("value", 0)
        params = ind.get("params", {})

        async with sem:
            try:
                code = await generate_indicator_code(
                    name=name,
                    description=ind.get("description", ""),
                    params=params,
                    computation=ind.get("computation", ""),
                )
                _validate_code(code)
                fn_name = _name_to_fn(name)
                return {
                    "name": name,
                    "ref_value": ref_value,
                    "params": params,
                    "fn_name": fn_name,
                    "code": code,
                    "index": idx,
                    "ok": True,
                }
            except Exception as e:
                return {"name": name, "error": str(e), "index": idx, "ok": False}

    tasks_coros = [generate_one(ind, i) for i, ind in enumerate(indicators)]
    results = await asyncio.gather(*tasks_coros)

    # 按原始顺序排序
    results.sort(key=lambda r: r["index"])

    for r in results:
        if r["ok"]:
            indicator_fns.append((r["name"], r["ref_value"], r["params"], r["fn_name"], r["code"]))
            generated.append(r["name"])
        else:
            failed.append({"name": r["name"], "error": r["error"]})

    strategy_code = _assemble_similarity_strategy(strategy_name, task.ts_code, indicator_fns)

    return {
        "factor_config": {
            "indicators": [
                {"name": n, "value": v, "params": p}
                for n, v, p, _, _ in indicator_fns
            ]
        },
        "generated_code": strategy_code,
        "generated_factors": generated,
        "failed_factors": failed,
    }
```

- [ ] **Step 2: 在 _run_generation 中写入进度**

修改 `backend/app/api/ai.py` 中的 `_run_generation`：

```python
async def _run_generation(
    task_id: str,
    indicators: list[dict],
    strategy_name: str,
    user_id: int,
):
    from ..database import async_session

    session = await async_session()
    try:
        task = (
            await session.execute(
                select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
            )
        ).scalar_one()

        total = len(indicators)

        # 重写 match_and_generate 调用，改为带进度回调的版本
        # 方案：在 ai_strategy_service 中增加一个带进度回调的重载
        from ..services.ai_strategy_service import match_and_generate_with_progress

        async def update_progress(completed: int):
            """更新任务进度到 DB"""
            task.result_json = json.dumps(
                {"progress": {"completed": completed, "total": total}},
                ensure_ascii=False,
            )
            await session.commit()

        result = await match_and_generate_with_progress(
            task=task,
            indicators=indicators,
            strategy_name=strategy_name,
            buy_logic="OR",
            user_id=user_id,
            on_progress=update_progress,
        )

        # ... 后续保存策略逻辑不变 ...
```

或者更简单的方案：直接在 `_run_generation` 中逐个处理并更新进度，不修改 `match_and_generate` 的接口。但这会退回到串行。更好的方案是让并发版本支持进度回调。

实际采用方案：在 `ai_strategy_service.py` 中新增 `match_and_generate_with_progress`：

```python
async def match_and_generate_with_progress(
    task: AIStrategyTask,
    indicators: list[dict],
    strategy_name: str,
    buy_logic: str,
    user_id: int,
    on_progress=None,
) -> dict:
    """带进度回调的并发版本"""
    generated = []
    failed = []
    indicator_fns = []
    completed_count = 0
    lock = asyncio.Lock()

    sem = asyncio.Semaphore(5)

    async def generate_one(ind: dict, idx: int):
        nonlocal completed_count
        name = ind.get("name", "")
        ref_value = ind.get("value", 0)
        params = ind.get("params", {})

        async with sem:
            try:
                code = await generate_indicator_code(
                    name=name,
                    description=ind.get("description", ""),
                    params=params,
                    computation=ind.get("computation", ""),
                )
                _validate_code(code)
                fn_name = _name_to_fn(name)
                result_item = {
                    "name": name, "ref_value": ref_value, "params": params,
                    "fn_name": fn_name, "code": code, "index": idx, "ok": True,
                }
            except Exception as e:
                result_item = {"name": name, "error": str(e), "index": idx, "ok": False}

            async with lock:
                completed_count += 1
                if on_progress:
                    await on_progress(completed_count)

            return result_item

    tasks_coros = [generate_one(ind, i) for i, ind in enumerate(indicators)]
    results = await asyncio.gather(*tasks_coros)

    results.sort(key=lambda r: r["index"])
    for r in results:
        if r["ok"]:
            indicator_fns.append((r["name"], r["ref_value"], r["params"], r["fn_name"], r["code"]))
            generated.append(r["name"])
        else:
            failed.append({"name": r["name"], "error": r["error"]})

    strategy_code = _assemble_similarity_strategy(strategy_name, task.ts_code, indicator_fns)

    return {
        "factor_config": {
            "indicators": [
                {"name": n, "value": v, "params": p}
                for n, v, p, _, _ in indicator_fns
            ]
        },
        "generated_code": strategy_code,
        "generated_factors": generated,
        "failed_factors": failed,
    }
```

然后在 `_run_generation` 中调用此版本，传入 `on_progress` 回调。

- [ ] **Step 3: 更新 get_analysis_result 返回进度**

在 `backend/app/api/ai.py` 的 `get_analysis_result` 端点中，解析并返回 progress：

```python
result = json.loads(task.result_json or "{}")
strategy_id = result.get("strategy_id")
progress = result.get("progress")  # 新增
kline_summary = json.loads(task.kline_summary or "{}")
return {
    "code": 0,
    "data": {
        "status": "completed",
        "summary": result.get("summary", ""),
        "indicators": result.get("indicators", []),
        "kline_summary": kline_summary,
        "strategy_id": strategy_id,
        "generated_factors": result.get("generated_factors", []),
        "failed_factors": result.get("failed_factors", []),
        "progress": progress,  # 新增
    },
}
```

- [ ] **Step 4: 后端测试验证**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/ -v
```

Expected: 现有测试全部通过

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai_strategy_service.py backend/app/api/ai.py
git commit -m "feat: 策略生成并行化（Semaphore 5）+ 进度字段写入 DB"
```

---

### Task 4: DeepSeek 调用增加重试

**Files:**
- Modify: `backend/app/services/llm_service.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 安装 tenacity**

```bash
cd backend && source venv/bin/activate && pip install tenacity
```

- [ ] **Step 2: 更新 requirements.txt**

在 `backend/requirements.txt` 中添加：
```
tenacity>=8.0
```

- [ ] **Step 3: 为 _call_deepseek 添加重试**

```python
# backend/app/services/llm_service.py
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import httpx

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((
        httpx.HTTPStatusError,
        httpx.ConnectError,
        httpx.ReadTimeout,
    )),
)
async def _call_deepseek(system_prompt: str, user_msg: str, model: str) -> str:
    """调用 DeepSeek API（自动重试 3 次，指数退避）"""
    if not settings.DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY 未配置")

    async with httpx.AsyncClient(timeout=settings.DEEPSEEK_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.3,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
```

- [ ] **Step 4: 验证导入**

```bash
cd backend && source venv/bin/activate && python -c "from app.services.llm_service import _call_deepseek; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm_service.py backend/requirements.txt
git commit -m "feat: DeepSeek 调用增加指数退避重试（最多 3 次）"
```

---

### Task 5: 后台任务超时控制

**Files:**
- Modify: `backend/app/api/ai.py`

- [ ] **Step 1: 为 _run_analysis 添加超时**

```python
async def _run_analysis(task_id, items, stock_name, req):
    from ..database import async_session
    from ..services.llm_service import analyze_kline as _llm_analyze

    session = await async_session()
    try:
        task = (await session.execute(
            select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
        )).scalar_one()

        # 120 秒超时
        result = await asyncio.wait_for(
            _llm_analyze(
                df_rows=items, ts_code=req.ts_code,
                stock_name=stock_name, date=req.date,
                model=req.model, user_prompt=req.prompt,
            ),
            timeout=120,
        )

        task.result_json = json.dumps(result, ensure_ascii=False)
        task.status = "completed"
        await session.commit()

    except asyncio.TimeoutError:
        task = (await session.execute(
            select(AIStrategyTask).where(AIStrategyTask.task_id == task_id)
        )).scalar_one()
        task.status = "failed"
        task.error_message = "分析超时（120 秒）"
        await session.commit()
    except Exception as e:
        # ... 现有错误处理 ...
    finally:
        await session.close()
```

- [ ] **Step 2: 为 _run_generation 添加超时**

```python
# 300 秒超时（因为有 50+ 个指标需要生成）
result = await asyncio.wait_for(
    match_and_generate_with_progress(...),
    timeout=300,
)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/ai.py
git commit -m "feat: 后台分析/生成任务增加超时控制（120s/300s）"
```

---

### Task 6: 更新 CLAUDE.md 文档

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 更新 AI Reference Stock Strategy 章节**

将 CLAUDE.md 中 "### AI Reference Stock Strategy" 部分更新为反映新架构：

```markdown
### AI Reference Stock Strategy (`/ai/analyze-stock`)

**Flow:**
1. User submits stock code + date → backend fetches K-line data
2. `_run_analysis` (async background task, 120s timeout) sends data to DeepSeek
3. DeepSeek extracts **50+ quantitative indicator VALUES** (not buy/sell signals)
4. Frontend polls `GET /ai/analyze-stock/{task_id}` until complete
5. User reviews indicators on `/strategies/ai-builder` (phase: `review`), can edit/add
6. User confirms → `POST /ai/confirm-strategy` → backend marks task "generating"
7. `_run_generation` calls DeepSeek **concurrently** (Semaphore 5, 300s timeout) for each indicator's compute function
8. Progress tracked in task's `result_json.progress` field
9. Each function (`compute_value(df, params) -> float`) passes **runtime validation**
10. Strategy assembled: similarity-matching via normalized distance to reference values

**Frontend phase states:**
- `idle` → `submitting` → `analyzing` → `review` → `generating` → `completed`
- Any state → `failed` on error
- `resumeInProgressTask` recovers stale state on page revisit

**DeepSeek calls:** Auto-retry 3x with exponential backoff (via tenacity)
```

- [ ] **Step 2: 更新 Quick Commands 部分**

确认 `pip install -r requirements.txt` 涵盖了 tenacity 依赖。

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: 更新 CLAUDE.md 反映 AI 参考选股重构后的架构"
```

---

### Task 7: 端到端验证

- [ ] **Step 1: 启动后端**

```bash
cd backend && source venv/bin/activate && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: 启动前端**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: 手动测试流程**

1. 登录 → 进入 AI 参考选股
2. 搜索股票 → 选择日期 → 提交 AI 分析
3. 观察：右侧历史面板显示"分析中"标签
4. 等待分析完成 → 指标表格出现
5. 编辑指标 → 确认生成策略
6. 观察：显示实时进度 "正在生成 (X/50)..."
7. 中途离开页面再返回 → 状态正确恢复
8. 策略生成完成 → 自动跳转策略详情

- [ ] **Step 4: Commit any fixes**

如有问题修复，提交。否则标记完成。

---

### Task 8: 前端生成阶段进度 UI 已确认

（已在 Task 2 Step 10 中包含，此任务作为显式检查点）

- [ ] **验证 generating phase 的进度显示正确**

确认 `AIStrategyBuilder.tsx` 中 generating 分支包含：
```tsx
{progress && (
  <div style={{ textAlign: 'center', marginTop: 16 }}>
    <Text type="secondary">
      正在生成第 {progress.completed}/{progress.total} 个指标的计算代码...
    </Text>
  </div>
)}
```
