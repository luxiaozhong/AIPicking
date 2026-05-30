# AI 参考选股 — P2 长期改进 Backlog

> 版本: 2.0 | 日期: 2026-05-30 | 状态: 规划中
>
> P0/P1 重构已完成并归档至 [archive/specs/2026-05-30-ai-strategy-refactor.md](../archive/specs/2026-05-30-ai-strategy-refactor.md)

## 背景

AI 参考选股功能经 P0/P1 重构后，已支持并行策略生成、SSE 实时推送、phase 状态机、DeepSeek 重试等。以下 P2 项目为长期改进，旨在进一步提升可靠性和可维护性。

## (f) 任务模型独立化

**当前问题：** `AIStrategyTask.result_json` 为 Text 字段，塞入整个 JSON（50+ 指标 + 进度 + 策略结果），无法结构化查询。

**改进方向：**
- `indicator_values` 单独建表，每个指标一行：`task_id`, `name`, `category`, `value`, `params`, `computation`
- `generation_progress` 字段独立到 `ai_strategy_tasks` 表
- 支持跨任务查询：`SELECT * FROM indicator_values WHERE name LIKE '%RSI%' AND value < 30`
- 支持指标值历史趋势分析（同一股票多次分析对比）

**预估工作量：** 2-3 天

## (g) 任务队列 (Celery / ARQ)

**当前问题：** `asyncio.create_task` fire-and-forget，服务器重启丢失任务，无水平扩展。

**改进方向：**
- Celery + Redis 或 ARQ（纯 async）替换 `asyncio.create_task`
- 任务持久化，重启自动恢复
- 内置重试 + 超时
- Worker 进程独立管理
- 支持多 worker 水平扩展

**预估工作量：** 2-3 天

## (h) 前端状态机 (XState)

**当前问题：** Zustand store 手动管理 `phase` 枚举 + `taskId` + `progress`，缺少形式化状态转换约束。

**改进方向：**
- XState 5 定义正式状态图
- 明确合法状态转换，防止非法组合
- 可视化状态图便于理解和调试
- 自动生成 TypeScript 类型

**预估工作量：** 1-2 天

## 提醒

已设置 2026-06-14 提醒评估推进时机。
