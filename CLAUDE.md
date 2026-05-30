# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
cd frontend && npm run dev           # Dev server (port 5173, proxies /api to :8000)
npm run build                        # TypeScript check + Vite build
npm run lint                         # ESLint
npm run test:e2e                     # Playwright E2E tests

# Full dev restart
./restart.sh                         # Backend :8000 + Frontend :5173
nohup bash restart.sh > /tmp/aipicking.log 2>&1 &  # Run in background
```

## Architecture

### Authentication (JWT)

**Roles:** `admin` (sees all data + user management) / `user` (own data only, no user management page).

**Token flow:** `POST /api/v1/auth/login` → `{access_token (30min), refresh_token (7d), user}`. Frontend stores tokens in localStorage. Shared Axios instance (`frontend/src/services/api.ts`) injects `Authorization: Bearer` header and auto-refreshes on 401.

**Backend auth deps:**
- `app/middleware/auth.py::get_current_user` — validates JWT, loads User, injects into route
- `app/middleware/auth.py::require_admin` — chains get_current_user + checks `role == "admin"`

**Data isolation:** `strategies`, `backtest_reports`, `strategy_runs`, `ai_strategy_tasks` have `user_id` FK → `users.id`. Service layer filters by `user_id` for regular users; admin sees all.

**Default admin:** `admin` / `admin123` (seeded on startup if no admin exists).

### Backend (FastAPI + SQLAlchemy async + SQLite via aiosqlite)

**Dependencies:** `httpx` (DeepSeek API calls), `python-dotenv` (.env loading).

**Data flow**: `API routes` → `Services` → `Models/Engine` → `SQLite`

**Key modules:**

- `app/main.py` — App entry point, CORS config, route registration
- `app/config.py` — Settings via env vars loaded by `python-dotenv`. New keys: `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_TIMEOUT`.
- `app/database.py` — Async SQLAlchemy engine + `get_db` / `async_session` for background tasks
- `app/models/` — `Strategy`, `BacktestReport`, `StrategyRun`, `AIStrategyTask`
- `app/api/` — Routers: `strategies`, `backtests`, `factors`, `ai`, `auth`, `users`, `stocks`
- `app/middleware/auth.py` — `get_current_user`, `require_admin`
- `app/services/` — Business logic:
  - `strategy_service.py` — Upload & factor-config strategy creation
  - `backtest_service.py` — Backtests run in **thread pool** (`loop.run_in_executor`) to avoid blocking event loop
  - `backtest_engine.py` — AST sandbox + strategy execution + performance tracking
  - `llm_service.py` — DeepSeek API calls for K-line analysis and indicator code generation
  - `ai_strategy_service.py` — Similarity-based strategy code generator with **runtime validation** of AI-generated code
  - `code_generator.py` — Legacy factor-config strategy code generator (buy/sell signals)

### AI Reference Stock Strategy (`/ai/analyze-stock`)

**Flow:**
1. User submits stock code + date → backend fetches K-line data
2. `_run_analysis` (async background task, **120s timeout**) sends data to DeepSeek
3. DeepSeek extracts **50+ quantitative indicator VALUES** (not buy/sell signals):
   - RSI, MACD, KDJ, OBV, Bollinger Bands, ATR, ADX, CCI, etc.
4. Frontend polls `GET /ai/analyze-stock/{task_id}` until complete (phase: `analyzing`)
5. User reviews indicators on `/strategies/ai-builder` (phase: `review`), can filter/add
6. User confirms → backend marks task "generating", starts `_run_generation`
7. `_run_generation` calls DeepSeek **concurrently** (Semaphore 5, **300s timeout**) for each indicator's compute function
8. Progress tracked in `result_json.progress` → frontend shows "正在生成第 X/N 个指标..."
9. Each function (`compute_value(df, params) -> float`) passes **runtime validation**
10. Strategy assembled: similarity-matching via normalized distance to reference values

**DeepSeek calls:** Auto-retry 3x with exponential backoff (2s→4s→8s) via tenacity; covers HTTPStatusError, ConnectError, ReadTimeout.

**Frontend phase states (single source of truth):**
- `idle` → `submitting` → `analyzing` → `review` → `generating` → `completed`
- Any state → `failed` on error
- `resumeInProgressTask` recovers stale `analyzing`/`generating` state on page revisit

**Key components:**
- `frontend/src/pages/AIStrategyBuilder.tsx` — multi-phase wizard with shared `<TaskHistoryPanel/>`
- `frontend/src/components/TaskHistoryPanel.tsx` — reusable task history sidebar (loading/empty/list states)
- `frontend/src/stores/aiStrategyStore.ts` — Zustand store with single `phase` enum (no `submitting` boolean)
- `backend/app/services/llm_service.py` — DeepSeek API with retry (tenacity)
- `backend/app/services/ai_strategy_service.py` — concurrent code generation + runtime validation
- `backend/app/api/ai.py` — route handlers + background tasks with timeout

**Strategy type:** Similarity matching (not buy/sell signals). Returns top 10 closest stocks.

**API endpoints:**
- `POST /ai/analyze-stock` — Submit analysis task
- `GET /ai/analyze-stock/{task_id}` — Poll task status/result (includes `progress` field during generation)
- `GET /ai/analyze-stock/tasks` — User's task history (MUST be defined before `/{task_id}` route)
- `POST /ai/confirm-strategy` — Confirm indicators, trigger async generation
- `POST /ai/generate-strategy` — Legacy keyword-based strategy (rule parsing, not LLM)

### Strategy Code Display

`GET /strategies/{id}` returns `code_content` via fallback: `file_path` file → `generated_code` field. AI-generated strategies have empty `file_path` and show from `generated_code`.

### Backtest Engine

- Runs in thread pool (`loop.run_in_executor`) to prevent event loop blocking from CPU-intensive pandas operations
- Sandboxes strategy code via AST validation (blocks `os`, `sys`, `exec`, `eval`, etc.)
- Supports `run(data)` function interface for both buy/sell and similarity strategies
- Recommendation must include `signal` field

### Volume Column Compatibility

Factor functions should handle both `volume` and `vol` column names. Existing volume factors (OBV, turnover, volume_ratio) updated to try `volume` first, fall back to `vol`.

### Factor Library (`app/factors/`)

- `momentum/` — KDJ, MACD, RSI
- `trend/` — Breakout, MA cross, MA support
- `volume/` — OBV, turnover, volume ratio
- `pattern/` — Engulfing, hammer, morning star
- `risk/` — Fixed stop, take profit, trailing stop

### API Response Format

Custom envelope `{code: int, message: str, data: ...}`. `code: 0` means success.

### Frontend (React 18 + TypeScript + Vite + Ant Design 6 + Zustand + ECharts)

**Routes:**
- `/login` — Login page (bypasses AppLayout)
- `/dashboard` — Dashboard
- `/strategies` — Strategy list (with "可视化构建" and "AI 参考选股" buttons)
- `/strategies/builder` — Visual factor builder (factor combination UI)
- `/strategies/ai-builder` — **AI Reference Stock Strategy** (multi-step wizard)
- `/strategies/:id` — Strategy detail with code viewer
- `/strategies/:id/edit` — Code editor (Monaco)
- `/strategies/:id/backtest` — Backtest form
- `/backtests` — Backtest list
- `/backtests/:id` — Backtest detail
- `/users` — Admin user management

**Key files:**
- `src/App.tsx` — Route definitions
- `src/services/api.ts` — Shared Axios with auth interceptors + auto-refresh
- `src/services/` — `authService`, `userService`, `strategyService`, `backtestService`, `factorService`, `aiService`, `stockService`
- `src/stores/` — `authStore`, `strategyStore`, `backtestStore`, `themeStore`, `aiStrategyStore`
- `src/types/` — `aiStrategy.ts` (new), `auth.ts`, `strategy.ts`, `backtest.ts`, `factor.ts`
- `src/pages/AIStrategyBuilder.tsx` — New: two-column layout, submit form → polling → indicator review

### Environment

- Backend `.env` — `DATABASE_URL`, `STOCK_DB_PATH`, `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_TIMEOUT`, `CORS_ORIGINS`
- Frontend `.env.development` / `.env.production` — `VITE_API_BASE_URL`
- `.env` is loaded by `python-dotenv` in `config.py`, NOT auto-loaded by uvicorn. Must install `python-dotenv`.

### Server Deployment

```bash
# systemd
systemctl restart aipicking

# manual update
cd /opt/AIpicking
git pull
pip install -r backend/requirements.txt    # includes httpx, python-dotenv
cd frontend && npm install --silent && npm run build
systemctl restart aipicking

# Check .env has:
#   DEEPSEEK_API_KEY=sk-xxx
#   DEEPSEEK_BASE_URL=https://api.deepseek.com
#   DEEPSEEK_TIMEOUT=60
```
