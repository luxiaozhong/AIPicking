# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Commands

```bash
# Backend
cd backend && source venv/bin/activate
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
npm run test:e2e:ui                  # Playwright in UI mode
```

## Architecture

### Authentication (JWT)

**Roles:** `admin` (sees all data + user management) / `user` (own data only, no user management page).

**Token flow:** `POST /api/v1/auth/login` → `{access_token (30min), refresh_token (7d), user}`. Frontend stores tokens in localStorage. Shared Axios instance (`frontend/src/services/api.ts`) injects `Authorization: Bearer` header and auto-refreshes on 401.

**Backend auth deps:**
- `app/middleware/auth.py::get_current_user` — validates JWT, loads User, injects into route
- `app/middleware/auth.py::require_admin` — chains get_current_user + checks `role == "admin"`

**Data isolation:** `strategies`, `backtest_reports`, `strategy_runs` have `user_id` FK → `users.id`. Service layer filters by `user_id` for regular users; admin sees all.

**Default admin:** `admin` / `admin123` (seeded on startup if no admin exists).

**Migration:** `python migrate_add_auth.py` (idempotent).

**API response format**: Custom envelope `{code: int, message: str, data: ...}`. `code: 0` means success. Auth endpoints follow same format. User management endpoints return unwrapped responses (Pydantic models).

### Backend (FastAPI + SQLAlchemy async + SQLite via aiosqlite)

**Data flow**: `API routes` → `Services` → `Models/Engine` → `SQLite`

- `app/main.py` — App entry point, CORS config, route registration
- `app/config.py` — Settings via env vars (`DATABASE_URL`, `STOCK_DB_PATH`, etc.). `STOCK_DB_PATH` points to an external SQLite DB with `stocks` and `daily` tables (A-share market data).
- `app/database.py` — Async SQLAlchemy engine + `get_db` dependency injection
- `app/models/` — SQLAlchemy models: `Strategy` (core entity), `BacktestReport` (associated by `strategy_id` FK), `StrategyRun`
- `app/api/` — REST routers: `strategies`, `backtests`, `factors`, `ai`, `auth` (login/refresh/me), `users` (admin CRUD)
- `app/middleware/auth.py` — `get_current_user` and `require_admin` FastAPI dependencies
- `app/services/` — Business logic layer. `strategy_service.py` handles both file-upload and factor-config creation paths. `backtest_service.py` creates backtests as async background tasks.
- `app/strategies/examples/` — Uploaded/built strategy `.py` files (naming: `{id}_{name}.py`)

**Strategy creation has two paths**:
1. **Upload** (`POST /api/v1/strategies/upload`): User uploads a `.py` file; validated for syntax + required functions
2. **Factor builder** (`POST /api/v1/strategies`): User selects factors via `FactorConfig` JSON; `code_generator.py` auto-generates Python strategy code from the factor combination

**Backtest engine** (`app/services/backtest_engine.py`):
- Sandboxes strategy code via AST validation (blocks `os`, `sys`, `exec`, `eval`, etc.) + restricted builtins
- Supports both `run(data)` function interface (new) and `Strategy` class with `generate_signals(df)` (legacy, wrapped)
- Loads stock data from external `STOCK_DB_PATH`, runs strategy at a cutoff date, then tracks recommended stocks' performance over `[3, 7, 15]` days

**Factor library** (`app/factors/`) — Organized by category:
- `momentum/` — KDJ, MACD, RSI
- `trend/` — Breakout, MA cross, MA support
- `volume/` — OBV, turnover, volume ratio
- `pattern/` — Engulfing, hammer, morning star
- `risk/` — Fixed stop, take profit, trailing stop

**API response format**: Custom envelope `{code: int, message: str, data: ...}`. `code: 0` means success.

### Frontend (React 18 + TypeScript + Vite + Ant Design 6 + Zustand + ECharts + Monaco Editor)

- `src/App.tsx` — Routes: `/login`, `/dashboard`, `/strategies` (list), `/strategies/builder` (visual factor builder), `/strategies/:id` (detail), `/strategies/:id/edit` (code editor), `/strategies/:id/backtest`, `/backtests` (list), `/backtests/:id` (detail), `/users` (admin-only user management)
- `src/services/api.ts` — Shared Axios instance with auth interceptors (auto token injection + 401 refresh)
- `src/services/` — API clients: `authService`, `userService`, `strategyService`, `backtestService`, `factorService`, `aiService`
- `src/stores/` — Zustand stores: `authStore` (login/logout/init), `strategyStore`, `backtestStore`, `themeStore`
- `src/types/` — TypeScript interfaces: `auth.ts` (UserInfo, LoginRequest, etc.), `strategy.ts`, `backtest.ts`, `factor.ts`
- `src/pages/LoginPage.tsx` — Centered login form, bypasses AppLayout
- `src/pages/UserManagement.tsx` — Admin CRUD table for user accounts
- `src/components/Auth/ProtectedRoute.tsx` — Auth guard component with optional `requireAdmin` prop
- `src/pages/StrategyBuilder.tsx` — Visual factor combination UI where users pick factors by category and configure parameters to generate strategies
- Vite proxies `/api` to `localhost:8000` in dev mode

### Environment

- Backend `.env` sets `DEBUG`, `CORS_ORIGINS`, `STOCK_DB_PATH`
- Frontend `.env.development` sets `VITE_API_BASE_URL`
