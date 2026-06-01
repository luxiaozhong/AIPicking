# AI Reference Stock Strategy

路由：`/ai/analyze-stock`，前端页面：`/strategies/ai-builder`。

## 策略类型

**相似度匹配**（非买卖信号）。通过归一化距离匹配参考股票，返回 top 10 最相似股票。

## 完整流程

1. 用户提交股票代码 + 日期 → 后端获取 K 线数据
2. `_run_analysis`（异步后台任务，**120s 超时**）将数据发送给 DeepSeek
3. DeepSeek 提取 **50+ 个量化指标值**（不是买卖信号）：
   - RSI, MACD, KDJ, OBV, Bollinger Bands, ATR, ADX, CCI 等
4. 前端轮询 `GET /ai/analyze-stock/{task_id}` 直到完成（phase: `analyzing`）
5. 用户在 `/strategies/ai-builder` 审查指标（phase: `review`），可以筛选/添加
6. 用户确认 → 后端标记任务为 "generating"，启动 `_run_generation`
7. `_run_generation` **并发**调用 DeepSeek（Semaphore 5，**300s 超时**），每个指标生成一个计算函数
8. 进度通过 `result_json.progress` 追踪 → 前端显示"正在生成第 X/N 个指标..."
9. 每个函数（`compute_value(df, params) -> float`）通过**运行时校验**
10. 策略组装：通过归一化距离匹配参考值

## DeepSeek 调用

- 自动重试 3 次，指数退避（2s → 4s → 8s），通过 tenacity 实现
- 覆盖 HTTPStatusError、ConnectError、ReadTimeout

## 前端状态机（唯一数据源）

```
idle → submitting → analyzing → review → generating → completed
任意状态 → failed（出错时）
```

`resumeInProgressTask` 在页面重访时恢复卡住的 `analyzing`/`generating` 状态。

## 关键组件

| 文件 | 作用 |
|------|------|
| `frontend/src/pages/AIStrategyBuilder.tsx` | 多阶段向导，共享 `<TaskHistoryPanel/>` |
| `frontend/src/components/TaskHistoryPanel.tsx` | 可复用的任务历史侧边栏（loading/empty/list 状态） |
| `frontend/src/stores/aiStrategyStore.ts` | Zustand store，单一 `phase` 枚举（无 `submitting` 布尔值） |
| `backend/app/services/llm_service.py` | DeepSeek API + 重试（tenacity） |
| `backend/app/services/ai_strategy_service.py` | 并发代码生成 + 运行时校验 |
| `backend/app/api/ai.py` | 路由处理 + 后台任务（带超时） |

## API Endpoints

| Method | Path | 说明 |
|--------|------|------|
| `POST` | `/ai/analyze-stock` | 提交分析任务 |
| `GET` | `/ai/analyze-stock/{task_id}` | 轮询任务状态/结果（生成期间含 `progress` 字段） |
| `GET` | `/ai/analyze-stock/tasks` | 用户任务历史（**必须**定义在 `/{task_id}` 路由之前） |
| `POST` | `/ai/confirm-strategy` | 确认指标，触发异步生成 |
| `POST` | `/ai/generate-strategy` | 旧版关键词策略（规则解析，非 LLM） |
