# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Quick Commands

```bash
# Backend
cd backend && source venv/bin/activate
pip install -r requirements.txt        # First time / after pull
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pytest                               # Run all tests
pytest tests/test_strategies.py -v   # Single test file
ruff check .                         # Lint Python
black .                              # Format Python

# Frontend
cd frontend && npm run dev           # Dev server (:5173, proxies /api → :8000)
npm run build                        # TypeScript check + Vite build
npm run lint                         # ESLint
npm run test:e2e                     # Playwright E2E tests

# Full dev restart
./restart.sh                         # Backend :8000 + Frontend :5173
```

## Architecture at a Glance

- **Backend**: FastAPI + SQLAlchemy async + PostgreSQL（SQLite 已废弃）
- **Frontend**: React 18 + TypeScript + Vite + Ant Design 6 + Zustand + ECharts
- **Auth**: JWT（access_token 30min + refresh_token 7d），角色分 admin/user
- **AI**: DeepSeek API，相似度选股（非买卖信号），返回 top 10
- **回测**: AST 沙箱 + 线程池执行，详见 `docs/backtest-engine.md`
- **交易模拟**: 策略选股 → 资金分配 → 逐日追踪 → 止损止盈，详见 `docs/trade-sim.md`

## Key Conventions

### 必须遵守的规则

1. **API 响应格式**: 统一信封 `{code: int, message: str, data: ...}`，`code: 0` 表示成功
2. **数据库查询**: 非核心表必须用 `select(Model.__table__)`（Core 级别），**禁止** `select(Model)`（ORM 级别）。否则 `dict(row._mapping)` 返回 `{'ModelName': <object>}`，破坏 `row["column_name"]` 取值
3. **成交量列**: 因子函数需要同时兼容 `volume` 和 `vol`，先取 `volume`，找不到再回退 `vol`
4. **.env 加载**: 由 `python-dotenv` 在 `config.py` 中手动加载，uvicorn 不会自动加载
5. **部署方式**: 代码变更必须通过 git push → 服务器 git pull，**禁止** scp/sftp 直接拷贝文件到服务器。服务器上跑脚本、查日志等运维命令可以直接 SSH。详见 `docs/deployment.md`
6. **分支规范**: 任何文档设计新建和改动前都必须在 **feature branch** 上进行，**禁止**直接提交到 `main` 分支。**在写第一行代码之前就要创建并切换到 feature branch**，不是 commit 前才切。分支命名：`feat/<描述>`、`fix/<描述>`、`refactor/<描述>`。工作流：切分支 → 写代码 → commit → push → PR/merge → 切回 main → git pull → 同步到服务器
7. 所有日期格式都遵循数据库日期格式 ‘YYYY-MM-DD‘

### 路由定义顺序

`GET /ai/analyze-stock/tasks` 必须定义在 `GET /ai/analyze-stock/{task_id}` **之前**，否则 FastAPI 会把 `tasks` 当成 `task_id` 参数。

## Module Map

```
backend/app/
├── main.py          — 入口，CORS，路由注册
├── config.py        — 环境变量
├── database.py      — 异步 engine + get_db / async_session
├── models/          — Strategy, BacktestReport, BatchBacktestReport, StrategyRun, AIStrategyTask, TradeSimReport, BatchTradeSimReport
├── api/             — strategies, backtests, batch_backtests, trade_sims, factors, ai, auth, users, stocks, education
├── middleware/       — get_current_user, require_admin
├── services/        — strategy, backtest, backtest_engine, trade_sim_engine, trade_sim_service, llm, ai_strategy, code_generator
└── factors/         — momentum/, trend/, volume/, pattern/, risk/, trade_sim_stops.py

frontend/src/
├── App.tsx          — 路由定义
├── services/        — api.ts (Axios + auth 拦截器), *Service
├── stores/          — auth, strategy, backtest, theme, aiStrategy (Zustand)
├── pages/           — 策略管理、简单回测（含单策略/批量切换）、交易模拟、仪表盘 等
└── components/      — TaskHistoryPanel, Layout/AppLayout, OnboardingWalkthrough 等
```

## Deep Dives

当你需要深入了解某个主题时，先读对应的文档，再开始写代码：

| 主题 | 文档 |
|------|------|
| 认证流程、后端模块详情、环境配置 | `docs/architecture.md` |
| 回测引擎、REQUIRED_DATA、因子库 | `docs/backtest-engine.md` |
| 历史数据采集管线、cron 定时任务、日志 | `docs/data-pipeline.md` |
| AI 选股完整流程、状态机、DeepSeek 调用 | `docs/ai-strategy.md` |
| 前端路由、组件、状态管理 | `docs/frontend.md` |
| 交易模拟引擎、止损止盈因子 | `docs/trade-sim.md` |
| 部署、systemd、手动更新 | `docs/deployment.md` |
| Oversold manually report | `docs/oversold-bounce-strategy.md` |
| 临时回测脚本与 HTML 报告 | `backend/TmpScriptsBackTest/` |

## TmpScriptsBackTest — 临时回测报告目录

`backend/TmpScriptsBackTest/` 存放独立的批量回测脚本和生成的 HTML 报告，不走 FastAPI 应用流程。

文件清单、数据库说明、报告规范等全部内容详见 [`backend/TmpScriptsBackTest/README.md`](backend/TmpScriptsBackTest/README.md)。
