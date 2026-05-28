# 技术方案 (Plan)

**项目**: AIpicking 量化交易平台  
**版本**: 2.0  
**日期**: 2026-05-24  
**状态**: 待审批

---

## 1. 系统架构

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         浏览器 (Web UI)                       │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP/REST API
┌───────────────────────────▼─────────────────────────────────┐
│                     前端层 (Frontend)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
│  │ 策略管理  │  │ 回测报告  │  │ 共用组件  │                │
│  └──────────┘  └──────────┘  └──────────┘                │
│  React + TypeScript + Ant Design + ECharts                  │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP/REST API
┌───────────────────────────▼─────────────────────────────────┐
│                     后端层 (Backend)                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
│  │ API 路由  │  │ 业务逻辑  │  │ 回测引擎  │                │
│  └──────────┘  └──────────┘  └──────────┘                │
│  FastAPI + Python 3.11+                                    │
└───────────────────────────┬─────────────────────────────────┘
                            │ SQL
┌───────────────────────────▼─────────────────────────────────┐
│                     数据层 (Database)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
│  │ aipicking │  │   stock   │  │           │                │
│  │   .db     │  │  _db.sqlite │  │           │                │
│  └──────────┘  └──────────┘  └──────────┘                │
│  主数据库 (SQLite)  股票历史数据库 (SQLite, 只读)             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 技术栈详解

#### 前端技术栈
- **框架**: React 18.2+ with TypeScript 5.0+
- **构建工具**: Vite 4+（快速热更新）
- **UI 组件库**: Ant Design 5.12+
- **状态管理**: Zustand 4+（轻量、TypeScript 友好）
- **路由**: React Router v6.20+
- **HTTP 客户端**: Axios 1.6+
- **代码编辑器**: Monaco Editor 0.44+（VS Code 同款）
- **图表库**: ECharts 5.4+（Apache ECharts for React）
- **文件上传**: react-dropzone
- **表单处理**: React Hook Form + Zod（类型安全的表单验证）
- **样式**: CSS Modules 或 Tailwind CSS（可选）

#### 后端技术栈
- **框架**: FastAPI 0.109+
- **Python 版本**: 3.11+（支持类型提示增强）
- **数据验证**: Pydantic v2（高性能数据验证）
- **数据库 ORM**: SQLAlchemy 2.0+（异步支持，仅用于主数据库）
- **数据库驱动**: aiosqlite（异步 SQLite 驱动）
- **跨域处理**: FastAPI CORS Middleware
- **任务队列**: 初期使用 asyncio 后台任务，后期可迁移至 Celery
- **回测引擎**: 自建轻量回测引擎（基于 Pandas，参考 WorkBuddy 设计）
- **数据处理**: Pandas 2.1+, NumPy 1.26+
- **代码解析**: ast（Python 内置 AST 模块，用于策略代码验证）
- **文件操作**: 原生 Python os、shutil（用于策略脚本文件管理）

#### 外部数据源
- **股票历史数据库**: `/Users/aklu/workbuddy/2026-05-22-21-48-44/data/stock_db.sqlite`
  - 用于回测功能，提供历史行情数据
  - 表结构定义文件：`/Users/aklu/workbuddy/2026-05-22-21-48-44/data/init_db.py`
  - **重要**：如果数据库结构需要变更，用户会更新 `init_db.py`，后端需要同步更新
  - 表结构：
    - `stocks`: 股票基本信息（代码、名称、行业、概念、股本等）
    - `daily`: 日线行情数据（OHLC、成交量、成交额、复权收盘价、市值等）
  - 数据加载：回测引擎直接从该数据库读取历史数据（只读模式）

#### 数据库架构说明
项目使用两个 SQLite 数据库：
1. **aipicking.db**（项目主数据库）
   - 存储：策略（strategies）、回测报告（backtest_reports）
   - 位置：`/Users/aklu/CodeBuddy/AIpicking/backend/data/database/`
   - 由 SQLAlchemy 自动创建和管理

2. **stock_db.sqlite**（股票历史数据库）
   - 存储：股票基本信息（stocks）、日线行情（daily）
   - 位置：`/Users/aklu/workbuddy/2026-05-22-21-48-44/data/`
   - 由外部脚本 `init_db.py` 创建和管理
   - 后端以只读模式连接，用于回测数据查询

#### 开发工具链
- **包管理**: pnpm 8+（前端），pip + venv（后端）
- **代码规范**: 
  - 前端: ESLint 8+ + Prettier 3+
  - 后端: Black 23+ + Ruff 0.1+（快速 Python linter）
- **类型检查**:
  - 前端: TypeScript 编译器
  - 后端: mypy 1.8+
- **测试**:
  - 前端: Vitest + React Testing Library
  - 后端: pytest 7.4+ + pytest-asyncio
- **Git 钩子**: pre-commit（代码提交前自动检查）

---

## 2. 项目结构详细设计

### 2.1 前端项目结构 (`frontend/`)

```
frontend/
├── public/                      # 静态资源
│   ├── index.html
│   └── favicon.ico
├── src/
│   ├── assets/                  # 图片、字体等
│   ├── components/              # 可复用组件
│   │   ├── Layout/             # 布局组件（Header、Sidebar）
│   │   ├── StrategyEditor/     # 策略编辑器组件
│   │   ├── BacktestChart/      # 回测图表组件
│   │   └── common/             # 通用组件（Button、Modal 等）
│   ├── pages/                   # 页面组件
│   │   ├── StrategyList/       # 策略列表页
│   │   ├── StrategyUpload/     # 策略上传页（新增）
│   │   ├── StrategyEdit/       # 策略编辑页
│   │   ├── StrategyDetail/     # 策略详情页
│   │   ├── BacktestList/       # 回测报告列表页
│   │   └── BacktestDetail/     # 回测报告详情页
│   ├── services/                # API 调用服务
│   │   ├── api.ts              # Axios 实例配置
│   │   ├── strategyService.ts  # 策略相关 API
│   │   └── backtestService.ts  # 回测相关 API
│   ├── stores/                  # Zustand 状态管理
│   │   ├── strategyStore.ts
│   │   └── backtestStore.ts
│   ├── types/                   # TypeScript 类型定义
│   │   ├── strategy.ts
│   │   └── backtest.ts
│   ├── utils/                   # 工具函数
│   │   ├── format.ts           # 格式化函数（日期、数字）
│   │   └── constants.ts        # 常量定义
│   ├── App.tsx                  # 根组件
│   ├── main.tsx                 # 入口文件
│   └── routes.tsx               # 路由配置
├── package.json
├── tsconfig.json
├── vite.config.ts
└── .eslintrc.cjs
```

### 2.2 后端项目结构 (`backend/`)

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 应用入口
│   ├── config.py                # 配置管理（环境变量）
│   ├── database.py              # 数据库连接和会话管理（仅主数据库）
│   ├── api/                     # API 路由
│   │   ├── __init__.py
│   │   ├── strategies.py        # 策略相关路由（含上传接口）
│   │   ├── backtests.py         # 回测相关路由
│   │   └── deps.py             # 依赖注入（数据库会话等）
│   ├── models/                  # 数据模型
│   │   ├── __init__.py
│   │   ├── strategy.py         # 策略模型
│   │   ├── backtest.py         # 回测报告模型
│   │   └── base.py             # 基础模型类
│   ├── schemas/                 # Pydantic schemas（请求/响应）
│   │   ├── __init__.py
│   │   ├── strategy.py
│   │   └── backtest.py
│   ├── services/                # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── strategy_service.py  # 策略 CRUD 逻辑
│   │   ├── backtest_service.py # 回测业务逻辑
│   │   └── backtest_engine.py  # 回测引擎核心（参考 WorkBuddy）
│   ├── strategies/              # 策略插件目录
│   │   ├── __init__.py
│   │   └── examples/           # 示例策略
│   │       ├── old_duck_head.py      # 老鸭头策略
│   │       └── trend_upstart.py     # 趋势启动捕捉策略
│   └── utils/                  # 工具函数
│       ├── __init__.py
│       ├── validator.py         # 策略代码验证（AST 检查）
│       ├── data_loader.py      # 数据加载（从 stock_db.sqlite 读取）
│       └── report_generator.py # 报告生成（JSON + HTML）
├── tests/                       # 测试代码
│   ├── __init__.py
│   ├── test_strategies.py
│   ├── test_backtests.py
│   └── test_backtest_engine.py
├── data/                        # 数据目录
│   ├── database/                # SQLite 数据库文件
│   │   └── aipicking.db       # 主数据库
│   └── reports/                # 回测报告文件
│       ├── json/                # JSON 格式报告
│       └── html/                # HTML 格式报告
├── requirements.txt              # Python 依赖列表
└── README.md
```

---

## 3. 数据库设计

### 3.1 ER 图

```
┌─────────────────┐       ┌─────────────────────┐
│   strategies     │       │   backtest_reports   │
├─────────────────┤       ├─────────────────────┤
│ PK id           │───────│ FK strategy_id       │
│    name         │   1:N │    status            │
│    description  │       │    params            │
│    file_path    │       │    config            │
│    params_schema│       │    summary           │
│    tags         │       │    results           │
│    status       │       │    json_report_path  │
│    created_at   │       │    html_report_path  │
│    updated_at   │       └─────────────────────┘
│    version      │
└─────────────────┘

┌─────────────────────┐
│   strategy_runs      │
├─────────────────────┤
│ FK strategy_id       │
│    params            │
│    backtest_id       │
│    created_at        │
└─────────────────────┘
```

### 3.2 详细表结构

#### 3.2.1 `strategies` 表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | 策略 ID |
| name | VARCHAR(255) | NOT NULL, UNIQUE | 策略名称 |
| description | TEXT | | 策略描述 |
| file_path | TEXT | NOT NULL | 策略脚本文件路径（相对路径）|
| params_schema | TEXT | | 参数 JSON Schema（可选）|
| tags | TEXT | | 标签（逗号分隔）|
| status | VARCHAR(50) | DEFAULT 'active' | 状态（active/archived/deleted）|
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| version | INTEGER | DEFAULT 1 | 版本号 |

**索引**:
- `idx_strategies_status` ON strategies(status)
- `idx_strategies_name` ON strategies(name)

**变更说明**:
- 移除 `code` 字段（策略代码不再存储在数据库中，而是存储在文件中）
- 新增 `file_path` 字段（指向策略脚本文件的路径）

#### 3.2.2 `backtest_reports` 表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | 报告 ID |
| strategy_id | INTEGER | FK, NOT NULL | 关联策略 ID |
| strategy_run_id | INTEGER | FK | 关联策略运行 ID |
| name | VARCHAR(255) | | 报告名称 |
| status | VARCHAR(50) | DEFAULT 'pending' | 状态（pending/running/completed/failed）|
| params | TEXT | NOT NULL | 回测参数 JSON |
| config | TEXT | NOT NULL | 回测配置 JSON |
| summary | TEXT | | 汇总统计 JSON（完成后填充）|
| results | TEXT | | 逐日结果 JSON（完成后填充）|
| json_report_path | TEXT | | JSON 报告文件路径 |
| html_report_path | TEXT | | HTML 报告文件路径 |
| error_message | TEXT | | 错误信息（失败时填充）|
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| started_at | TIMESTAMP | | 开始执行时间 |
| completed_at | TIMESTAMP | | 完成时间 |

**索引**:
- `idx_backtests_strategy` ON backtest_reports(strategy_id)
- `idx_backtests_status` ON backtest_reports(status)
- `idx_backtests_created` ON backtest_reports(created_at DESC)

**变更说明**:
- 移除 `metrics`、`equity_curve`、`trades` 字段（这些数据现在存储在 `summary` 和 `results` 字段中，格式参考 WorkBuddy）
- 新增 `config` 字段（回测配置，包含交易成本、风控参数等）
- 新增 `summary` 字段（汇总统计，包含有效日、总交易数、平均涨幅、胜率等）
- 新增 `results` 字段（逐日结果，包含每日选股结果、涨幅等）
- 新增 `json_report_path` 和 `html_report_path` 字段（报告文件路径）

#### 3.2.3 `strategy_runs` 表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | 运行 ID |
| strategy_id | INTEGER | FK, NOT NULL | 关联策略 ID |
| params | TEXT | NOT NULL | 实际使用的参数 JSON |
| backtest_id | INTEGER | FK | 关联的回测报告 ID |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**索引**:
- `idx_runs_strategy` ON strategy_runs(strategy_id)

### 3.3 数据库迁移策略

使用 SQLAlchemy 的迁移工具 `Alembic` 管理 schema 变更：

```bash
# 初始化迁移环境
alembic init migrations

# 创建迁移脚本
alembic revision --autogenerate -m "Initial migration"

# 应用迁移
alembic upgrade head
```

---

## 4. API 设计详细规范

### 4.1 统一响应格式

**成功响应**:
```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

**错误响应**:
```json
{
  "code": 40001,
  "message": "Strategy not found",
  "errors": ["detail": "..."]
}
```

**错误码定义**:
- `0`: 成功
- `40001-40099`: 请求错误（参数验证失败、资源不存在等）
- `50001-50099`: 服务器错误（回测失败、代码执行错误等）

### 4.2 策略管理 API

#### 4.2.1 获取策略列表
```
GET /api/v1/strategies
Query 参数:
  - page: 页码（默认 1）
  - limit: 每页数量（默认 20，最大 100）
  - search: 搜索关键词（按名称模糊匹配）
  - tags: 标签筛选（逗号分隔）
  - status: 状态筛选（active/archived/deleted）

响应:
{
  "code": 0,
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "limit": 20
  }
}
```

#### 4.2.2 上传策略脚本
```
POST /api/v1/strategies/upload
Content-Type: multipart/form-data

请求体:
  - file: 策略脚本文件（.py）
  - name: 策略名称（可选，默认使用文件名）
  - description: 策略描述（可选）
  - tags: 标签（可选，逗号分隔）

响应: 201 Created
{
  "code": 0,
  "message": "策略上传成功",
  "data": {
    "id": 1,
    "name": "老鸭头策略",
    "description": "...",
    "file_path": "strategies/examples/1_老鸭头策略.py",
    "status": "active",
    "created_at": "2026-05-24T17:00:00Z",
    "updated_at": "2026-05-24T17:00:00Z",
    "version": 1
  }
}

错误响应: 400 Bad Request
{
  "code": 40001,
  "message": "策略脚本验证失败",
  "errors": [
    "缺少必需函数: check_old_duck_head",
    "缺少必需函数: run"
  ]
}
```

#### 4.2.3 获取策略详情
```
GET /api/v1/strategies/:id

响应:
{
  "code": 0,
  "data": {
    "id": 1,
    "name": "老鸭头策略",
    "description": "...",
    "file_path": "strategies/examples/1_老鸭头策略.py",
    "params_schema": { ... },
    "tags": ["均线", "趋势跟踪"],
    "status": "active",
    "created_at": "2026-05-24T17:00:00Z",
    "updated_at": "2026-05-24T17:00:00Z",
    "version": 1
  }
}
```

#### 4.2.4 下载策略脚本
```
GET /api/v1/strategies/:id/download

响应:
  - Content-Type: `application/octet-stream`
  - Content-Disposition: `attachment; filename="strategy_name.py"`
  - Body: 策略脚本文件内容
```

#### 4.2.5 更新策略元数据
```
PUT /api/v1/strategies/:id
Content-Type: application/json

请求体: (部分更新，仅传递要修改的字段)
{
  "name": "新名称",
  "description": "新描述",
  "tags": ["新标签"]
}

响应: 200 OK
{
  "code": 0,
  "data": {
    "id": 1,
    "version": 2,
    ...
  }
}
```

#### 4.2.6 更新策略代码
```
PUT /api/v1/strategies/:id/code
Content-Type: multipart/form-data

请求体:
  - file: 新的策略脚本文件（.py）（可选）
  - code: 策略代码文本（可选，与 file 二选一）

响应: 200 OK
{
  "code": 0,
  "message": "策略代码更新成功",
  "data": {
    "id": 1,
    "version": 2,
    ...
  }
}
```

#### 4.2.7 删除策略
```
DELETE /api/v1/strategies/:id

响应: 204 No Content
```

### 4.3 回测报告 API

#### 4.3.1 提交回测任务
```
POST /api/v1/backtests
Content-Type: application/json

请求体:
{
  "strategy_id": 1,
  "params": { "short_window": 5, "long_window": 20 },
  "config": {
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "initial_cash": 1000000,
    "commission": 0.00025,
    "stamp_duty": 0.001,
    "slippage": 0.001,
    "position_size": 0.15,
    "max_positions": 5,
    "main_stop_loss": -0.04,
    "gem_stop_loss": -0.05,
    "main_take_profit": 0.06,
    "gem_take_profit": 0.08,
    "benchmark": "000300.SH"
  }
}

响应: 202 Accepted
{
  "code": 0,
  "message": "回测任务已提交",
  "data": {
    "id": 1,
    "status": "pending",
    "created_at": "2026-05-24T17:00:00Z"
  }
}
```

#### 4.3.2 获取回测报告列表
```
GET /api/v1/backtests
Query 参数:
  - page: 页码（默认 1）
  - limit: 每页数量（默认 20，最大 100）
  - strategy_id: 按策略 ID 筛选
  - status: 按状态筛选（pending/running/completed/failed）
  - start_date: 按回测开始日期筛选
  - end_date: 按回测结束日期筛选

响应:
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": 1,
        "strategy_name": "老鸭头策略",
        "status": "completed",
        "period": "20260512~20260512",
        "summary": {
          "days": 1,
          "total": 8,
          "avg_day1": 1.56,
          "win_rate1": 75.0
        },
        "created_at": "2026-05-24T17:00:00Z",
        "completed_at": "2026-05-24T17:05:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "limit": 20
  }
}
```

#### 4.3.3 获取回测报告详情
```
GET /api/v1/backtests/:id

响应:
{
  "code": 0,
  "data": {
    "id": 1,
    "strategy_id": 1,
    "strategy_name": "老鸭头策略",
    "status": "completed",
    "period": "20260512~20260512",
    "params": { ... },
    "config": { ... },
    "summary": { ... },
    "results": [ ... ],
    "json_report_path": "reports/json/backtest_老鸭头策略_20260512_20260512.json",
    "html_report_path": "reports/html/backtest_老鸭头策略_20260512.html",
    "created_at": "...",
    "completed_at": "..."
  }
}
```

#### 4.3.4 获取 JSON 格式报告
```
GET /api/v1/backtests/:id/json

响应:
  - Content-Type: `application/json`
  - Content-Disposition: `attachment; filename="backtest_{strategy_name}_{start_date}_{end_date}.json"`
  - Body: 回测报告 JSON 数据
```

#### 4.3.5 获取 HTML 格式报告
```
GET /api/v1/backtests/:id/html

响应:
  - Content-Type: `text/html`
  - Body: 回测报告 HTML 内容（可在浏览器中直接查看）
```

#### 4.3.6 删除回测报告
```
DELETE /api/v1/backtests/:id

响应: 204 No Content
```

---

## 5. 前端路由设计

### 5.1 路由表

| 路径 | 页面组件 | 说明 |
|------|----------|------|
| `/` | Home | 首页（重定向至 /strategies）|
| `/strategies` | StrategyList | 策略列表 |
| `/strategies/upload` | StrategyUpload | 上传策略（新增）|
| `/strategies/:id` | StrategyDetail | 策略详情 |
| `/strategies/:id/edit` | StrategyEdit | 编辑策略 |
| `/strategies/:id/backtest` | BacktestForm | 提交回测 |
| `/backtests` | BacktestList | 回测报告列表 |
| `/backtests/:id` | BacktestDetail | 回测报告详情 |
| `/about` | About | 关于页面 |
| `*` | NotFound | 404 页面 |

### 5.2 路由守卫

- 策略编辑/详情页：检查策略 ID 是否存在，不存在则重定向至列表页
- 回测详情页：轮询检查回测状态（如果状态为 `pending` 或 `running`）

---

## 6. 回测引擎设计（参考 WorkBuddy）

### 6.1 核心类设计

```python
# backtest_engine.py

import pandas as pd
import sqlite3
from typing import Dict, List, Any
from datetime import datetime


class BacktestEngine:
    """A股 T+1 短线回测引擎（参考 WorkBuddy 设计）"""
    
    def __init__(
        self,
        strategy_code: str,
        params: Dict[str, Any],
        config: Dict[str, Any],
        db_path: str
    ):
        """
        初始化回测引擎
        
        参数:
            strategy_code: 策略代码（字符串）
            params: 策略参数（字典）
            config: 回测配置（字典）
            db_path: 股票历史数据库路径
        """
        self.strategy_code = strategy_code
        self.params = params
        self.config = config
        self.db_path = db_path
        
        # 资金相关
        self.initial_cash = config.get('initial_cash', 1_000_000)
        self.cash = self.initial_cash
        self.commission = config.get('commission', 0.00025)
        self.stamp_duty = config.get('stamp_duty', 0.001)
        self.slippage = config.get('slippage', 0.001)
        
        # 仓位相关
        self.position_size = config.get('position_size', 0.15)  # 单只股票仓位比例
        self.max_positions = config.get('max_positions', 5)  # 最大持仓数
        
        # 风控参数
        self.main_stop_loss = config.get('main_stop_loss', -0.04)
        self.gem_stop_loss = config.get('gem_stop_loss', -0.05)
        self.main_take_profit = config.get('main_take_profit', 0.06)
        self.gem_take_profit = config.get('gem_take_profit', 0.08)
        
        # 状态相关
        self.positions = {}  # {ts_code: {"qty": int, "cost": float, "buy_date": str}}
        self.trades = []  # 交易记录
        self.portfolio_history = []  # 组合净值历史
        self.today_bought_codes = set()  # 当日买入的股票代码（T+1 保护）
        
        # 加载策略
        self.strategy_funcs = self._load_strategy()
    
    def _load_strategy(self) -> Dict[str, callable]:
        """
        加载策略代码（安全检查）
        
        返回:
            策略函数字典（{"check": check_func, "run": run_func}）
        """
        # 1. 使用 AST 检查禁止的操作
        is_valid, error_msg = self._validate_strategy(self.strategy_code)
        if not is_valid:
            raise ValueError(f"策略代码验证失败: {error_msg}")
        
        # 2. 编译策略代码
        code_obj = compile(self.strategy_code, "<strategy>", "exec")
        
        # 3. 执行代码，获取策略函数
        strategy_globals = {}
        exec(code_obj, strategy_globals)
        
        # 4. 查找 check_xxx 和 run 函数
        funcs = {}
        for name, obj in strategy_globals.items():
            if name.startswith('check_') and callable(obj):
                funcs['check'] = obj
            elif name == 'run' and callable(obj):
                funcs['run'] = obj
        
        if 'check' not in funcs or 'run' not in funcs:
            raise ValueError("策略代码缺少必需函数（check_xxx 或 run）")
        
        return funcs
    
    def _validate_strategy(self, code: str) -> tuple[bool, str]:
        """
        验证策略代码安全性
        
        返回:
            (is_valid, error_message)
        """
        import ast
        
        FORBIDDEN_IMPORTS = {'os', 'sys', 'subprocess', 'builtins'}
        FORBIDDEN_FUNCS = {'exec', 'eval', 'open', '__import__'}
        
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"语法错误: {e}"
        
        for node in ast.walk(tree):
            # 检查 import 语句
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_IMPORTS:
                        return False, f"禁止导入模块: {alias.name}"
            
            # 检查函数调用
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in FORBIDDEN_FUNCS:
                        return False, f"禁止调用函数: {node.func.id}"
        
        return True, ""
    
    def run(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        执行回测
        
        参数:
            start_date: 回测起始日期（格式：YYYY-MM-DD）
            end_date: 回测结束日期（格式：YYYY-MM-DD）
        
        返回:
            回测结果（汇总统计 + 逐日结果）
        """
        # 1. 加载历史数据
        all_data, meta_df, sector_index, benchmark_data = self._load_data(start_date, end_date)
        
        # 2. 获取交易日列表
        trade_dates = sorted(all_data[list(all_data.keys())[0]]['trade_date'].unique())
        trade_dates = [d for d in trade_dates if start_date <= d <= end_date]
        
        # 3. 按时间顺序遍历数据
        yesterday_picks = []  # 昨日选股结果
        
        for i, trade_date in enumerate(trade_dates):
            # 3.1 检查存量持仓的止盈止损（T+1 保护，跳过当日买入）
            self._check_stops(trade_date)
            
            # 3.2 T+2 强制清仓
            self._check_t2_force_close(trade_date)
            
            # 3.3 执行新买入（昨日选股信号），固定 15% 仓位
            if yesterday_picks:
                self._execute_buy(trade_date, yesterday_picks)
                yesterday_picks = []
            
            # 3.4 记录组合净值
            self._record_portfolio(trade_date)
            
            # 3.5 收盘选股，为次日准备
            if i < len(trade_dates) - 1:  # 最后一天不需要选股
                pick_date = trade_dates[i + 1]
                yesterday_picks = self._run_strategy(pick_date, all_data, meta_df)
        
        # 4. 计算指标
        summary, results = self._calculate_metrics()
        
        return {
            "summary": summary,
            "results": results
        }
    
    def _load_data(self, start_date: str, end_date: str) -> tuple:
        """
        从 stock_db.sqlite 加载历史数据
        
        返回:
            (all_data, meta_df, sector_index, benchmark_data)
        """
        conn = sqlite3.connect(self.db_path)
        
        # 1. 加载日线数据
        daily_df = pd.read_sql_query(
            f"SELECT * FROM daily WHERE trade_date BETWEEN '{start_date}' AND '{end_date}'",
            conn
        )
        
        # 2. 加载股票元数据
        meta_df = pd.read_sql_query("SELECT * FROM stocks", conn)
        
        conn.close()
        
        # 3. 按股票代码分组
        all_data = {}
        for ts_code, group in daily_df.groupby('ts_code'):
            all_data[ts_code] = group.sort_values('trade_date').reset_index(drop=True)
        
        # 4. 构建板块指数（可选）
        sector_index = self._build_sector_index(daily_df, meta_df)
        
        # 5. 加载基准指数（可选）
        benchmark_data = self._load_benchmark_data(start_date, end_date)
        
        return all_data, meta_df, sector_index, benchmark_data
    
    def _build_sector_index(self, daily_df: pd.DataFrame, meta_df: pd.DataFrame) -> pd.DataFrame:
        """构建板块指数"""
        # 实现参考 WorkBuddy 的 build_sector_index 函数
        pass
    
    def _load_benchmark_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """加载基准指数数据"""
        # 实现参考 WorkBuddy 的 get_benchmark_data 函数
        pass
    
    def _check_stops(self, trade_date: str):
        """检查存量持仓的止盈止损（T+1 保护）"""
        for ts_code in list(self.positions.keys()):
            # 跳过当日买入的股票（T+1 规则）
            if ts_code in self.today_bought_codes:
                continue
            
            position = self.positions[ts_code]
            cost = position['cost']
            
            # 获取当前价格
            current_price = self._get_price(ts_code, trade_date)
            if current_price is None:
                continue
            
            # 计算收益率
            return_pct = (current_price - cost) / cost
            
            # 判断是否为双创板
            is_gem = self._is_gem_board(ts_code)
            
            # 检查止损
            stop_loss = self.gem_stop_loss if is_gem else self.main_stop_loss
            if return_pct <= stop_loss:
                self._execute_sell(ts_code, trade_date, "止损")
                continue
            
            # 检查止盈
            take_profit = self.gem_take_profit if is_gem else self.main_take_profit
            if return_pct >= take_profit:
                self._execute_sell(ts_code, trade_date, "止盈")
                continue
    
    def _check_t2_force_close(self, trade_date: str):
        """T+2 强制清仓"""
        for ts_code in list(self.positions.keys()):
            position = self.positions[ts_code]
            buy_date = position['buy_date']
            
            # 计算持有天数
            buy_date_dt = datetime.strptime(buy_date, "%Y-%m-%d")
            trade_date_dt = datetime.strptime(trade_date, "%Y-%m-%d")
            hold_days = (trade_date_dt - buy_date_dt).days
            
            if hold_days >= 2:
                self._execute_sell(ts_code, trade_date, "T+2强制清仓")
    
    def _execute_buy(self, trade_date: str, picks: List[Dict]):
        """执行买入操作"""
        # 计算可用资金
        available_cash = self.cash
        
        # 计算每只股票的目标仓位
        target_value = min(
            available_cash * self.position_size,
            self.initial_cash * self.position_size
        )
        
        # 买入选中的股票
        for pick in picks[:self.max_positions]:
            ts_code = pick['ts_code']
            
            # 如果已经持有，跳过
            if ts_code in self.positions:
                continue
            
            # 获取买入价格
            buy_price = self._get_price(ts_code, trade_date)
            if buy_price is None:
                continue
            
            # 计算买入数量（整百）
            qty = int(target_value / buy_price / 100) * 100
            if qty <= 0:
                continue
            
            # 计算交易成本
            amount = qty * buy_price
            cost = amount * self.commission + amount * self.slippage
            
            # 检查资金是否充足
            if cost > self.cash:
                continue
            
            # 执行买入
            self.cash -= cost
            self.positions[ts_code] = {
                "qty": qty,
                "cost": buy_price,
                "buy_date": trade_date
            }
            self.today_bought_codes.add(ts_code)
            
            # 记录交易
            self.trades.append({
                "date": trade_date,
                "ts_code": ts_code,
                "action": "buy",
                "price": buy_price,
                "qty": qty,
                "amount": amount,
                "cost": cost
            })
    
    def _execute_sell(self, ts_code: str, trade_date: str, reason: str):
        """执行卖出操作"""
        if ts_code not in self.positions:
            return
        
        position = self.positions[ts_code]
        
        # 获取卖出价格
        sell_price = self._get_price(ts_code, trade_date)
        if sell_price is None:
            return
        
        # 计算交易收入
        amount = position['qty'] * sell_price
        cost = amount * self.commission + amount * self.stamp_duty + amount * self.slippage
        
        # 执行卖出
        self.cash += amount - cost
        del self.positions[ts_code]
        
        # 记录交易
        self.trades.append({
            "date": trade_date,
            "ts_code": ts_code,
            "action": "sell",
            "price": sell_price,
            "qty": position['qty'],
            "amount": amount,
            "cost": cost,
            "pnl": amount - cost - (position['cost'] * position['qty']),
            "reason": reason
        })
    
    def _record_portfolio(self, trade_date: str):
        """记录组合净值"""
        # 计算持仓市值
        positions_value = 0
        for ts_code, position in self.positions.items():
            current_price = self._get_price(ts_code, trade_date)
            if current_price is not None:
                positions_value += position['qty'] * current_price
        
        # 计算组合净值
        total_value = self.cash + positions_value
        
        # 记录
        self.portfolio_history.append({
            "date": trade_date,
            "cash": self.cash,
            "positions_value": positions_value,
            "total_value": total_value,
            "returns": (total_value - self.initial_cash) / self.initial_cash
        })
    
    def _run_strategy(self, pick_date: str, all_data: Dict, meta_df: pd.DataFrame) -> List[Dict]:
        """
        执行策略选股
        
        参数:
            pick_date: 选股日期
            all_data: 所有股票的数据
            meta_df: 股票元数据
        
        返回:
            选股结果列表
        """
        # 调用策略的 run 函数
        run_func = self.strategy_funcs['run']
        picks = run_func(pick_date, all_data, meta_df)
        
        return picks
    
    def _get_price(self, ts_code: str, trade_date: str, field: str = 'close') -> float:
        """获取某股票某日的价格数据"""
        # 实现从 all_data 中查找价格
        pass
    
    def _is_gem_board(self, ts_code: str) -> bool:
        """判断是否为创业板(300)或科创板(688)"""
        return ts_code.startswith("300") or ts_code.startswith("301") or ts_code.startswith("688")
    
    def _calculate_metrics(self) -> tuple:
        """
        计算回测指标
        
        返回:
            (summary, results)
        """
        # 1. 计算汇总统计
        summary = self._calculate_summary()
        
        # 2. 整理逐日结果
        results = self._format_results()
        
        return summary, results
    
    def _calculate_summary(self) -> Dict:
        """计算汇总统计"""
        # 实现参考 WorkBuddy 的 metrics.py
        pass
    
    def _format_results(self) -> List[Dict]:
        """整理逐日结果"""
        # 实现参考 WorkBuddy 的 reports 格式
        pass
```

### 6.2 策略代码验证器

为了安全执行用户编写的策略代码，需要实现代码验证器（参考 WorkBuddy 的 validator.py）：

```python
# validator.py

import ast


class StrategyValidator:
    """策略代码验证器"""
    
    FORBIDDEN_IMPORTS = {'os', 'sys', 'subprocess', 'builtins'}
    FORBIDDEN_FUNCS = {'exec', 'eval', 'open', '__import__'}
    
    @classmethod
    def validate(cls, code: str) -> tuple[bool, str]:
        """
        验证策略代码安全性
        
        返回: (is_valid, error_message)
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"语法错误: {e}"
        
        for node in ast.walk(tree):
            # 检查 import 语句
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in cls.FORBIDDEN_IMPORTS:
                        return False, f"禁止导入模块: {alias.name}"
            
            # 检查函数调用
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in cls.FORBIDDEN_FUNCS:
                        return False, f"禁止调用函数: {node.func.id}"
        
        return True, ""
    
    @classmethod
    def check_required_functions(cls, code: str) -> tuple[bool, List[str]]:
        """
        检查策略代码是否包含必需函数
        
        返回: (has_required_funcs, missing_funcs)
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return False, ["语法错误"]
        
        has_check = False
        has_run = False
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name.startswith('check_'):
                    has_check = True
                elif node.name == 'run':
                    has_run = True
        
        missing = []
        if not has_check:
            missing.append("check_xxx")
        if not has_run:
            missing.append("run")
        
        return len(missing) == 0, missing
```

---

## 7. 部署方案

### 7.1 开发环境

**前端**:
```bash
cd frontend
npm install
npm run dev  # 启动开发服务器，默认 http://localhost:5173
```

**后端**:
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**数据库**: 
- 主数据库：`backend/data/database/aipicking.db`（自动创建）
- 股票历史数据库：`/Users/aklu/workbuddy/2026-05-22-21-48-44/data/stock_db.sqlite`（只读模式）

### 7.2 生产环境（未来）

- **前端**: 构建静态文件，部署至 Nginx 或 CDN
- **后端**: 使用 Gunicorn + Uvicorn Worker 运行 FastAPI 应用
- **数据库**: 
  - 主数据库迁移至 PostgreSQL
  - 股票历史数据库可继续使用 SQLite（只读）
- **进程管理**: 使用 Supervisor 或 systemd 管理后端进程
- **反向代理**: Nginx

---

## 8. 开发路线图 (Roadmap)

### Phase 1: MVP (2-3 周)
- [x] 项目初始化（前端 + 后端脚手架）
- [x] 数据库模型设计和迁移
- [ ] 策略上传功能（前端 + 后端 API）
- [ ] 策略管理 CRUD API + UI（列表、详情、删除、下载）
- [ ] 回测引擎核心实现（参考 WorkBuddy，支持 T+1、双轨制风控）
- [ ] 回测任务提交和状态查询 API + UI
- [ ] 回测报告展示（汇总统计 + 逐日结果表格）
- [ ] 回测报告导出（JSON + HTML）
- [ ] 单元测试（覆盖率 > 60%）

### Phase 2: 增强功能 (2-3 周)
- [ ] 策略在线编辑（Monaco Editor 集成）
- [ ] 策略参数配置 UI（基于 JSON Schema 动态表单）
- [ ] 回测配置 UI（风控参数、交易成本等）
- [ ] 收益率曲线图（ECharts，可选）
- [ ] 策略模板库（内置示例策略）
- [ ] 月度收益热力图（可选）
- [ ] 交易记录表格展示

### Phase 3: 高级功能 (未来)
- [ ] 实时行情监控（WebSocket）
- [ ] 交易信号提醒（邮件、微信）
- [ ] 风险管理模块
- [ ] 策略版本控制（Git 集成）
- [ ] 分布式回测（Celery + Redis）
- [ ] 自动交易执行（实盘对接）

---

## 9. 风险和挑战

### 9.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 策略代码执行安全性 | 高 | 实现 AST 代码检查 + 沙箱环境 |
| 回测性能（大数据量）| 中 | 使用 Pandas 向量化操作，避免 Python 循环 |
| 前端状态管理复杂性 | 中 | 使用 Zustand，保持 store 简洁 |
| SQLite 并发写入 | 低 | 开发阶段影响不大，生产环境迁移至 PostgreSQL |
| 两个数据库同步 | 中 | 明确分工：stock_db.sqlite 由用户管理，aipicking.db 由系统管理 |

### 9.2 非技术风险

- **数据质量**: 历史数据准确性影响回测结果 → 使用可靠数据源（如 Tushare、AkShare）
- **过度优化**: 策略过拟合历史数据 → 引入样本外测试、交叉验证

---

## 10. 附录

### 10.1 参考资料

- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [Ant Design 官方文档](https://ant.design/)
- [WorkBuddy 项目](/Users/aklu/workbuddy/2026-05-22-task-7/)（参考其策略格式和回测引擎设计）
- [Spec Kit 中文网](https://docs.spec.xin/)

### 10.2 相关工具

- **数据获取**: Tushare, AkShare, Baostock
- **回测框架**: Backtrader, Zipline, vnpy
- **代码编辑器**: Monaco Editor, CodeMirror

---

**审批记录**:
- [ ] 待审批
- [ ] 已批准
- [ ] 需修改

**审批意见**:
...

---

*本文档是技术方案，详细描述了系统的技术实现细节。在批准后可开始任务分解和实现。*

*版本 2.0 - 调整为基于 WorkBuddy 项目的设计方案（策略脚本上传、T+1 回测引擎、JSON + HTML 报告格式）*
