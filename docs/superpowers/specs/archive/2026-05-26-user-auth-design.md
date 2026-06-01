# User Authentication & Authorization Spec

> Status: Implemented (2026-05-26)
> Target: Add JWT-based login with admin/regular user roles

---

## 1. Overview

Add user authentication and role-based authorization to AIpicking.

- **Admin**: sees all data, all features, can CRUD users via user management page. Strategy list shows "创建者" column.
- **Regular user**: sees only own data, can access all pages except user management

---

## 2. Database Changes

### 2.1 New `users` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | autoincrement |
| `username` | VARCHAR(50) UNIQUE NOT NULL | login name |
| `password_hash` | VARCHAR(255) NOT NULL | bcrypt hashed |
| `role` | VARCHAR(20) DEFAULT 'user' | `admin` or `user` |
| `is_active` | INTEGER DEFAULT 1 | soft disable (SQLite boolean) |
| `created_at` | DATETIME | auto |
| `updated_at` | DATETIME | auto |

### 2.2 Add `user_id` to existing tables

| Table | New Column | FK | Notes |
|-------|-----------|----|-------|
| `strategies` | `user_id` INTEGER NOT NULL | → users.id | indexed |
| `backtest_reports` | `user_id` INTEGER NOT NULL | → users.id | indexed |
| `strategy_runs` | `user_id` INTEGER NOT NULL | → users.id | indexed |

### 2.3 Seed data

On startup (in `main.py`), if no admin exists, create default admin:
- username: `admin`, password: `<admin-password>`
- Existing data in tables: `user_id` set to admin's id via migration script

### 2.4 Migration

Run `python migrate_add_auth.py` to add `users` table, `user_id` columns, indexes, backfill existing data, and create default admin. Idempotent — safe to re-run.

---

## 3. Backend API

### 3.1 Auth endpoints (public except `/me`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/auth/login` | No | Login → `{access_token, refresh_token, user}` |
| `POST` | `/api/v1/auth/refresh` | No | Refresh → new `access_token` |
| `GET` | `/api/v1/auth/me` | Yes | Get current user info |

**Token config:**
- Access token: 30 min expiry
- Refresh token: 7 day expiry
- JWT payload: `{sub: user_id, role: user_role, type: "access"|"refresh"}`

### 3.2 User management endpoints (admin only)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/users` | List users (paginated, with search) |
| `POST` | `/api/v1/users` | Create user |
| `PUT` | `/api/v1/users/{id}` | Update user (username, password, role, is_active) |
| `DELETE` | `/api/v1/users/{id}` | Deactivate user (soft: `is_active=false`, cannot self-deactivate) |

### 3.3 Auth dependencies

- `app/middleware/auth.py::get_current_user` — extracts JWT, loads user from DB, injects `User` into route
- `app/middleware/auth.py::require_admin` — chains `get_current_user`, checks `user.role == "admin"`, raises 403

### 3.4 Modified existing endpoints

All strategy and backtest endpoints now require `current_user: User = Depends(get_current_user)`.

**Service layer filtering logic:**
- Regular users: `WHERE user_id = ?` on all CRUD + ownership check on single-resource access (403 if not owner)
- Admin users: no user_id filter, sees all data

**Strategy response** now includes `user_id` and `owner_name` (from eagerly-loaded `owner` relationship) for admin visibility.

---

## 4. Frontend

### 4.1 New pages

| Route | Component | Access |
|-------|-----------|--------|
| `/login` | `LoginPage` | Public |
| `/users` | `UserManagement` | Admin only |

### 4.2 Modified components

**AppLayout** — Header right side: user dropdown (username, role label, logout). Sidebar: admin sees extra "用户管理" menu item. Login page bypasses layout entirely.

**App.tsx** — Auth initialization on mount (check token → refresh if needed → redirect to `/login` if fail). All routes wrapped in `ProtectedRoute`. `/users` requires `requireAdmin` prop.

### 4.3 State management

**`authStore`** (Zustand): `user`, `isAuthenticated`, `loading`, `error`. Actions: `login()`, `logout()`, `initialize()`, `clearError()`.

**`api.ts`** (shared Axios instance): request interceptor injects `Authorization: Bearer <token>`; response interceptor handles 401 → automatic refresh with queue → redirect to `/login` on failure.

**`authService`**: `login()`, `refresh()`, `getMe()`, `logout()`, `getToken()`. Token storage in `localStorage`.

**`userService`**: `getUsers()`, `createUser()`, `updateUser()`, `deleteUser()`.

### 4.4 Strategy list — admin creator column

When admin views the strategy list (`StrategyList.tsx`), a "创建者" column shows the `owner_name` for each strategy. Regular users don't see this column.

---

## 5. Implementation File Map

### Backend (new)
- `backend/app/models/user.py` — User model
- `backend/app/schemas/auth.py` — LoginRequest, TokenResponse, LoginResponse, RefreshRequest, UserInfo
- `backend/app/schemas/user.py` — UserCreate, UserUpdate, UserResponse, UserListResponse
- `backend/app/services/auth_service.py` — JWT encode/decode, bcrypt hash/verify, user CRUD, seed_admin
- `backend/app/middleware/auth.py` — get_current_user, require_admin FastAPI dependencies
- `backend/app/api/auth.py` — POST /login, POST /refresh, GET /me
- `backend/app/api/users.py` — GET/POST/PUT/DELETE /users
- `backend/migrate_add_auth.py` — Idempotent migration script

### Backend (modified)
- `backend/app/config.py` — Added JWT_SECRET_KEY
- `backend/app/main.py` — Register auth/users routers, seed admin on startup
- `backend/app/models/__init__.py` — Import User, wire relationships
- `backend/app/models/strategy.py` — Added user_id FK, owner relationship, owner_name property
- `backend/app/models/backtest.py` — Added user_id FK, owner relationship
- `backend/app/schemas/strategy.py` — Added user_id, owner_name to StrategyResponse
- `backend/app/api/strategies.py` — Auth dependency on all endpoints, pass user_id to services
- `backend/app/api/backtests.py` — Auth dependency on all endpoints, pass user info to services
- `backend/app/services/strategy_service.py` — user_id filtering, eager-load owner relationship
- `backend/app/services/backtest_service.py` — user_id filtering, ownership checks
- `backend/requirements.txt` — Added python-jose, passlib, bcrypt (pinned 4.0.1 for passlib compat)

### Frontend (new)
- `frontend/src/types/auth.ts` — Auth TypeScript interfaces
- `frontend/src/services/api.ts` — Shared Axios instance with auth interceptors
- `frontend/src/services/authService.ts` — Auth API calls
- `frontend/src/services/userService.ts` — User management API calls
- `frontend/src/stores/authStore.ts` — Auth Zustand store
- `frontend/src/pages/LoginPage.tsx` — Login form
- `frontend/src/pages/UserManagement.tsx` — User CRUD table
- `frontend/src/components/Auth/ProtectedRoute.tsx` — Auth route guard

### Frontend (modified)
- `frontend/src/App.tsx` — Auth init, protected routes, login/users routes
- `frontend/src/components/Layout/AppLayout.tsx` — User dropdown, conditional sidebar, login skip
- `frontend/src/types/strategy.ts` — Added user_id, owner_name
- `frontend/src/pages/StrategyList.tsx` — Admin sees "创建者" column
- `frontend/src/services/strategyService.ts` — Use shared api client
- `frontend/src/services/backtestService.ts` — Use shared api client, fix types

---

## 6. Default Credentials

```
Username: admin
Password: <admin-password>
```

---

## 7. Known Limitations & Future Work

- No password change on first login (admin should change password manually)
- No password reset flow (email-based)
- No OAuth / SSO integration
- No API rate limiting
- No audit logging
- `passlib` requires `bcrypt==4.0.1` (not latest 5.x) due to API incompatibility
