# Architecture

## Tech Stack

- **Backend**: FastAPI + SQLAlchemy async + PostgreSQL
- **Frontend**: React 18 + TypeScript + Vite + Ant Design 6 + Zustand + ECharts
- **Auth**: JWT (access_token 30min + refresh_token 7d)
- **AI**: DeepSeek API (via httpx + tenacity retry)

## Authentication (JWT)

**Roles**: `admin` (全量数据 + 用户管理) / `user` (仅自己的数据，无用户管理页面)。

**Token flow**: `POST /api/v1/auth/login` → `{access_token (30min), refresh_token (7d), user}`。前端存 localStorage，共享 Axios 实例（`frontend/src/services/api.ts`）自动注入 `Authorization: Bearer` 头并在 401 时自动刷新。

**Backend auth deps**:
- `app/middleware/auth.py::get_current_user` — 校验 JWT，加载 User，注入路由
- `app/middleware/auth.py::require_admin` — 链式调用 get_current_user + 检查 `role == "admin"`

**Data isolation**: `strategies`, `backtest_reports`, `strategy_runs`, `ai_strategy_tasks` 有 `user_id` FK → `users.id`。Service 层对普通用户按 `user_id` 过滤，admin 看全部。

**Default admin**: `admin`（启动时若无 admin 则自动创建，密码通过 `ADMIN_DEFAULT_PASSWORD` 环境变量设置或自动生成随机密码输出到日志）。

## Backend Module Map

```
app/
├── main.py          — 入口，CORS，路由注册
├── config.py        — 环境变量配置（DEEPSEEK_API_KEY, DATABASE_URL 等）
├── database.py      — 异步 SQLAlchemy engine + get_db / async_session
├── models/          — Strategy, BacktestReport, BatchBacktestReport, StrategyRun, AIStrategyTask, TradeSimReport, BatchTradeSimReport
├── api/             — strategies, backtests, batch_backtests, trade_sims, factors, ai, auth, users, stocks, education
├── middleware/       — auth.py (get_current_user, require_admin)
├── services/
│   ├── strategy_service.py      — 策略创建（上传 & factor-config）
│   ├── backtest_service.py      — 回测编排与生命周期管理
│   ├── backtest_engine.py       — 策略执行 + 性能跟踪（详见 backtest-engine.md）
│   ├── trade_sim_engine.py      — 交易模拟引擎（详见 trade-sim.md）
│   ├── trade_sim_service.py     — 交易模拟编排与生命周期管理
│   ├── llm_service.py           — DeepSeek API 调用（带 tenacity 重试）
│   ├── ai_strategy_service.py   — 相似度选股代码生成 + 运行时校验
│   └── code_generator.py        — 旧版 factor-config 策略代码生成
└── factors/
    ├── momentum/   — KDJ, MACD, RSI
    ├── trend/      — Breakout, MA cross, MA support
    ├── volume/     — OBV, turnover, volume ratio
    ├── pattern/    — Engulfing, hammer, morning star
    ├── risk/       — Fixed stop, take profit, trailing stop
    └── trade_sim_stops.py — 交易模拟止损止盈因子注册表
```

## API Response Format

全部 API 返回统一信封：`{code: int, message: str, data: ...}`。`code: 0` 表示成功。

## Strategy Code Display

`GET /strategies/{id}` 返回 `code_content`，回退链：`file_path` 文件 → `generated_code` 字段。AI 生成的策略 `file_path` 为空，从 `generated_code` 展示。

## Volume Column Compatibility

因子函数需同时兼容 `volume` 和 `vol` 列名。存量因子（OBV, turnover, volume_ratio）已改为先取 `volume`，找不到再回退 `vol`。

## Environment

- **Backend `.env`**: `DATABASE_URL`, `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_TIMEOUT`, `CORS_ORIGINS`
- **Frontend `.env.development` / `.env.production`**: `VITE_API_BASE_URL`
- `.env` 由 `python-dotenv` 在 `config.py` 中加载，uvicorn 不会自动加载。必须安装 `python-dotenv`。
- `STOCK_DB_PATH` / SQLite 已废弃，全部走 PostgreSQL。历史脚本 `sync_market_data.py` 后续也需改为 PG。
