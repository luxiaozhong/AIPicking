# 任务列表 (Tasks)

**项目**: AIpicking 量化交易平台  
**版本**: 2.0  
**日期**: 2026-05-24  
**状态**: 待审批

---

## 任务概览

| 阶段 | 任务 ID | 任务名称 | 预估时间 | 依赖 | 状态 |
|------|----------|----------|----------|------|------|
| MVP | T001 | 初始化前端项目 | 1h | 无 | ✅ 已完成 |
| MVP | T002 | 初始化后端项目 | 1h | 无 | ✅ 已完成 |
| MVP | T003 | 配置开发环境 | 30min | T001, T002 | ✅ 已完成 |
| MVP | T004 | 实现策略模型 | 2h | T002 | ✅ 已完成 |
| MVP | T005 | 实现回测报告模型 | 2h | T002, T004 | ✅ 已完成 |
| MVP | T006 | 实现策略上传 API | 3h | T004 | ✅ 已完成 |
| MVP | T007 | 实现策略管理 UI | 4h | T001, T006 | ✅ 已完成 |
| MVP | T008 | 实现策略代码验证器 | 2h | T004 | ✅ 已完成 |
| MVP | T009 | 实现回测引擎 | 6h | T005 | ✅ 已完成 |
| MVP | T010 | 实现回测 API | 3h | T005, T009 | ✅ 已完成 |
| MVP | T011 | 实现回测报告 UI | 4h | T007, T010 | ⏳ 待开始 |
| MVP | T012 | 实现报告导出功能 | 2h | T010 | ⏳ 待开始 |
| MVP | T013 | 编写单元测试 | 4h | T006-T012 | ⏳ 待开始 |
| MVP | T014 | 集成测试和优化 | 3h | T001-T013 | ⏳ 待开始 |

**总预估时间**: 约 37.5 小时  
**已完成时间**: 约 7.5 小时  
**剩余时间**: 约 30 小时

---

## 详细任务说明

### MVP 阶段（核心功能）

#### T001: 初始化前端项目 ✅ 已完成
- **描述**: 使用 Vite 创建 React + TypeScript 项目
- **详细步骤**:
  1. 使用 `npm create vite@latest frontend -- --template react-ts` 创建项目
  2. 安装依赖：`npm install antd react-router-dom axios zustand echarts @monaco-editor/react`
  3. 配置 `vite.config.ts`（路径别名、代理）
  4. 配置 `tsconfig.app.json`（路径别名）
  5. 创建基础目录结构：`components/`, `pages/`, `services/`, `stores/`, `types/`, `utils/`
  6. 创建 `.env.development`（配置后端 API 地址）
  7. 清理默认文件（`App.css`, `index.css`, `assets/react.svg`）
- **验收标准**:
  - [x] 项目能正常启动（`npm run dev`）
  - [x] 能访问 `http://localhost:5173`
  - [x] 路径别名配置正确（`@/` 指向 `src/`）
  - [x] API 代理配置正确（`/api` 代理到 `localhost:8000`）
- **实际用时**: 1 小时
- **完成日期**: 2026-05-24

#### T002: 初始化后端项目 ✅ 已完成
- **描述**: 创建 Python FastAPI 项目结构
- **详细步骤**:
  1. 创建项目目录：`backend/`
  2. 创建虚拟环境：`python3 -m venv venv`
  3. 创建 `requirements.txt`（依赖列表）
  4. 创建基础目录结构：`app/`, `app/api/`, `app/models/`, `app/schemas/`, `app/services/`, `tests/`, `data/`
  5. 创建 `app/__init__.py`, `app/config.py`, `app/database.py`
  6. 创建 `app/models/base.py`, `app/models/strategy.py`, `app/models/backtest.py`
  7. 创建 `app/main.py`（FastAPI 应用入口）
  8. 创建 `app/api/__init__.py`, `app/api/strategies.py`, `app/api/backtests.py`
  9. 创建 `.env`（环境变量）
- **验收标准**:
  - [x] 项目能正常启动（`uvicorn app.main:app --reload`）
  - [x] 能访问 `http://localhost:8000/docs`（Swagger UI）
  - [x] CORS 中间件配置正确（允许前端 `localhost:5173`）
- **实际用时**: 1 小时
- **完成日期**: 2026-05-24

#### T003: 配置开发环境 ✅ 已完成
- **描述**: 创建项目配置文件和文档
- **详细步骤**:
  1. 创建 `.gitignore`（排除 `node_modules`, `__pycache__`, `.env`, `data/database/*.db`）
  2. 创建 `frontend/.env.development`（配置后端 API 地址）
  3. 更新 `backend/.env`（配置数据库连接）
  4. 创建 `README.md`（项目说明、安装和运行指南）
- **验收标准**:
  - [x] `.gitignore` 配置正确
  - [x] 前端能正常代理到后端
  - [x] `README.md` 包含完整的安装和运行指南
- **实际用时**: 30 分钟
- **完成日期**: 2026-05-24

#### T004: 实现策略模型 ✅ 已完成
- **描述**: 创建策略相关的数据模型和 API
- **详细步骤**:
  1. 更新 `app/models/strategy.py`（添加 `file_path` 字段，移除 `code` 字段）
  2. 创建 `app/schemas/__init__.py`, `app/schemas/strategy.py`（Pydantic schemas）
  3. 创建 `app/services/strategy_service.py`（策略业务逻辑）
  4. 更新 `app/api/strategies.py`（策略相关 API 路由）
  5. 更新 `app/main.py`（注册策略 API 路由）
  6. 创建 `tests/test_strategies.py`（策略相关 API 的单元测试）
- **验收标准**:
  - [x] 策略模型能正确创建表
  - [x] 策略 CRUD API 能正常工作
  - [x] 单元测试通过
- **实际用时**: 2 小时
- **完成日期**: 2026-05-24

#### T005: 实现回测报告模型 ✅ 已完成
- **描述**: 创建回测报告相关的数据模型和 API
- **详细步骤**:
  1. 更新 `app/models/backtest.py`（添加 `summary`, `results`, `json_report_path`, `html_report_path` 字段）
  2. 创建 `app/schemas/backtest.py`（Pydantic schemas）
  3. 创建 `app/services/backtest_service.py`（回测业务逻辑）
  4. 更新 `app/api/backtests.py`（回测相关 API 路由）
  5. 创建 `tests/test_backtests.py`（回测相关 API 的单元测试）
- **验收标准**:
  - [x] 回测报告模型能正确创建表
  - [x] 回测报告 CRUD API 能正常工作
  - [x] 单元测试通过
- **实际用时**: 2 小时
- **完成日期**: 2026-05-24

#### T006: 实现策略上传 API 🔄 进行中
- **描述**: 创建策略脚本上传 API（支持文件上传和验证）
- **详细步骤**:
  1. 更新 `app/api/strategies.py`，添加 `POST /api/v1/strategies/upload` 接口（支持 `multipart/form-data`）
  2. 更新 `app/api/strategies.py`，添加 `GET /api/v1/strategies/:id/download` 接口（下载策略脚本）
  3. 更新 `app/api/strategies.py`，添加 `PUT /api/v1/strategies/:id/code` 接口（更新策略代码）
  4. 更新 `app/services/strategy_service.py`，添加策略脚本验证逻辑（检查必需函数）
  5. 更新 `app/services/strategy_service.py`，添加策略脚本保存逻辑（保存到 `strategies/examples/` 目录）
  6. 创建 `tests/test_strategy_upload.py`（策略上传 API 的单元测试）
- **验收标准**:
  - [ ] 能上传策略脚本文件（.py）
  - [ ] 上传时自动验证策略接口（检查 `check_xxx` 和 `run` 函数）
  - [ ] 验证失败时返回详细错误信息
  - [ ] 验证成功时保存到数据库和文件系统
  - [ ] 能下载策略脚本文件
  - [ ] 能更新策略代码（上传新文件或在线编辑）
  - [ ] 单元测试通过
- **预估时间**: 3 小时
- **依赖**: T004
- **状态**: 🔄 进行中

#### T007: 实现策略管理 UI ⏳ 待开始
- **描述**: 创建策略管理的前端页面（列表、上传、编辑、详情、删除）
- **详细步骤**:
  1. 创建 `frontend/src/pages/StrategyUpload.tsx`（策略上传页）
  2. 更新 `frontend/src/pages/StrategyList.tsx`（添加上传按钮）
  3. 更新 `frontend/src/pages/StrategyEdit.tsx`（集成 Monaco Editor）
  4. 更新 `frontend/src/pages/StrategyDetail.tsx`（添加下载按钮）
  5. 创建 `frontend/src/components/StrategyUpload/`（策略上传组件）
  6. 创建 `frontend/src/services/strategyService.ts`（策略相关 API 调用）
  7. 创建 `frontend/src/stores/strategyStore.ts`（策略状态管理）
- **验收标准**:
  - [ ] 策略列表页能正常显示策略
  - [ ] 策略上传页能上传策略脚本文件
  - [ ] 策略编辑页能编辑策略代码（Monaco Editor）
  - [ ] 策略详情页能查看策略信息和下载脚本
  - [ ] 能删除策略（软删除）
- **预估时间**: 4 小时
- **依赖**: T001, T006
- **状态**: ⏳ 待开始

#### T008: 实现策略代码验证器 ✅ 已完成
- **描述**: 创建策略代码验证器（AST 检查禁止的操作）
- **详细步骤**:
  1. 创建 `app/utils/validator.py`（策略代码验证器）
  2. 实现 `check_required_functions(code)` 函数（检查必需函数）
  3. 实现 `validate_security(code)` 函数（检查禁止的操作）
  4. 更新 `app/services/strategy_service.py`，在创建/更新策略时调用验证器
- **验收标准**:
  - [x] 能检查策略代码是否包含必需函数（`check_xxx` 和 `run`）
  - [x] 能检查策略代码是否包含禁止的操作（`os`, `sys`, `subprocess` 等）
  - [x] 验证失败时返回详细错误信息
- **实际用时**: 2 小时
- **完成日期**: 2026-05-24

#### T009: 实现回测引擎 ⏳ 待开始
- **描述**: 创建回测引擎核心（参考 WorkBuddy 设计，支持 T+1、双轨制风控）
- **详细步骤**:
  1. 创建 `app/services/backtest_engine.py`（回测引擎核心类）
  2. 实现 `BacktestEngine.__init__()` 方法（初始化回测引擎）
  3. 实现 `BacktestEngine._load_data()` 方法（从 `stock_db.sqlite` 加载历史数据）
  4. 实现 `BacktestEngine._load_strategy()` 方法（加载策略代码）
  5. 实现 `BacktestEngine._check_stops()` 方法（检查止盈止损，T+1 保护）
  6. 实现 `BacktestEngine._check_t2_force_close()` 方法（T+2 强制清仓）
  7. 实现 `BacktestEngine._execute_buy()` 方法（执行买入操作）
  8. 实现 `BacktestEngine._execute_sell()` 方法（执行卖出操作）
  9. 实现 `BacktestEngine._record_portfolio()` 方法（记录组合净值）
  10. 实现 `BacktestEngine.run()` 方法（执行回测主循环）
  11. 实现 `BacktestEngine._calculate_summary()` 方法（计算汇总统计）
  12. 实现 `BacktestEngine._format_results()` 方法（整理逐日结果）
- **验收标准**:
  - [ ] 能正确加载历史数据（从 `stock_db.sqlite`）
  - [ ] 能正确加载策略代码
  - [ ] 能正确模拟 T+1 交易规则
  - [ ] 能正确执行双轨制风控（主板 10% vs 双创 20%）
  - [ ] 能正确执行时间止损（T+1 收盘检查，T+2 强制清仓）
  - [ ] 能正确计算汇总统计（有效日、总交易数、平均涨幅、胜率等）
  - [ ] 能正确整理逐日结果（选股日、代码、名称、收盘价、涨幅、得分等）
- **预估时间**: 6 小时
- **依赖**: T005
- **状态**: ⏳ 待开始

#### T010: 实现回测 API ⏳ 待开始
- **描述**: 创建回测相关的 API（提交回测任务、获取回测报告、导出报告）
- **详细步骤**:
  1. 更新 `app/api/backtests.py`，添加 `POST /api/v1/backtests` 接口（提交回测任务）
  2. 更新 `app/api/backtests.py`，添加 `GET /api/v1/backtests/:id` 接口（获取回测报告详情）
  3. 更新 `app/api/backtests.py`，添加 `GET /api/v1/backtests/:id/json` 接口（获取 JSON 格式报告）
  4. 更新 `app/api/backtests.py`，添加 `GET /api/v1/backtests/:id/html` 接口（获取 HTML 格式报告）
  5. 更新 `app/services/backtest_service.py`，添加回测任务提交逻辑（异步执行）
  6. 创建 `app/utils/report_generator.py`（报告生成器，生成 JSON 和 HTML 报告）
  7. 创建 `tests/test_backtest_api.py`（回测 API 的单元测试）
- **验收标准**:
  - [ ] 能提交回测任务（异步执行）
  - [ ] 能获取回测报告详情
  - [ ] 能导出 JSON 格式报告
  - [ ] 能导出 HTML 格式报告
  - [ ] 单元测试通过
- **预估时间**: 3 小时
- **依赖**: T005, T009
- **状态**: ⏳ 待开始

#### T011: 实现回测报告 UI ⏳ 待开始
- **描述**: 创建回测报告的前端页面（列表、详情、提交回测）
- **详细步骤**:
  1. 创建 `frontend/src/pages/BacktestList.tsx`（回测报告列表页）
  2. 创建 `frontend/src/pages/BacktestDetail.tsx`（回测报告详情页）
  3. 更新 `frontend/src/pages/StrategyDetail.tsx`（添加提交回测按钮）
  4. 创建 `frontend/src/components/BacktestList/`（回测列表组件）
  5. 创建 `frontend/src/components/BacktestDetail/`（回测详情组件）
  6. 创建 `frontend/src/components/BacktestForm/`（提交回测表单组件）
  7. 创建 `frontend/src/services/backtestService.ts`（回测相关 API 调用）
  8. 创建 `frontend/src/stores/backtestStore.ts`（回测状态管理）
- **验收标准**:
  - [ ] 回测报告列表页能正常显示报告
  - [ ] 回测报告详情页能正常显示报告详情（汇总统计、逐日结果表格）
  - [ ] 能提交回测任务
  - [ ] 能导出回测报告（JSON、HTML）
- **预估时间**: 4 小时
- **依赖**: T007, T010
- **状态**: ⏳ 待开始

#### T012: 实现报告导出功能 ⏳ 待开始
- **描述**: 创建报告导出功能（JSON、HTML）
- **详细步骤**:
  1. 更新 `app/utils/report_generator.py`，实现 `generate_json_report()` 函数（生成 JSON 报告）
  2. 更新 `app/utils/report_generator.py`，实现 `generate_html_report()` 函数（生成 HTML 报告）
  3. 更新 `frontend/src/pages/BacktestDetail.tsx`，添加导出按钮（JSON、HTML）
  4. 创建 `frontend/src/components/ExportButtons/`（导出按钮组件）
- **验收标准**:
  - [ ] 能导出 JSON 格式报告
  - [ ] 能导出 HTML 格式报告
  - [ ] 导出文件命名规范：`backtest_{strategy_name}_{start_date}_{end_date}.{json|html}`
- **预估时间**: 2 小时
- **依赖**: T010
- **状态**: ⏳ 待开始

#### T013: 编写单元测试 ⏳ 待开始
- **描述**: 编写单元测试，确保代码质量
- **详细步骤**:
  1. 编写 `tests/test_strategies.py`（策略管理 API 的单元测试）
  2. 编写 `tests/test_strategy_upload.py`（策略上传 API 的单元测试）
  3. 编写 `tests/test_backtests.py`（回测报告 API 的单元测试）
  4. 编写 `tests/test_backtest_engine.py`（回测引擎的单元测试）
  5. 编写 `tests/test_validator.py`（策略代码验证器的单元测试）
  6. 编写前端单元测试（可选）
- **验收标准**:
  - [ ] 后端单元测试覆盖率 > 60%
  - [ ] 前端单元测试覆盖率 > 60%（可选）
- **预估时间**: 4 小时
- **依赖**: T006-T012
- **状态**: ⏳ 待开始

#### T014: 集成测试和优化 ⏳ 待开始
- **描述**: 进行集成测试，优化性能和用户体验
- **详细步骤**:
  1. 进行端到端测试（从策略上传到回测报告生成）
  2. 优化前端性能（代码分割、懒加载等）
  3. 优化后端性能（数据库查询优化、缓存等）
  4. 优化用户体验（加载状态、错误提示、操作反馈等）
  5. 修复 bug
- **验收标准**:
  - [ ] 所有功能能正常工作
  - [ ] 前端性能符合要求（策略列表加载 < 1s，回测报告加载 < 2s）
  - [ ] 后端性能符合要求（API 响应时间 < 500ms）
  - [ ] 用户体验良好（操作流畅、反馈及时）
- **预估时间**: 3 小时
- **依赖**: T001-T013
- **状态**: ⏳ 待开始

---

## 任务优先级

| 优先级 | 任务 ID | 任务名称 | 原因 |
|----------|----------|----------|------|
| P0 | T006 | 实现策略上传 API | 核心功能，缺少则无法上传策略 |
| P0 | T009 | 实现回测引擎 | 核心功能，缺少则无法回测 |
| P1 | T007 | 实现策略管理 UI | 核心功能，缺少则无法管理策略 |
| P1 | T010 | 实现回测 API | 核心功能，缺少则无法提交回测 |
| P1 | T011 | 实现回测报告 UI | 核心功能，缺少则无法查看报告 |
| P2 | T012 | 实现报告导出功能 | 重要功能，提升用户体验 |
| P2 | T013 | 编写单元测试 | 重要功能，确保代码质量 |
| P3 | T014 | 集成测试和优化 | 优化功能，提升性能和体验 |

---

## 风险和问题

### 风险

| 风险 | 影响 | 缓解措施 | 负责人 |
|------|------|----------|----------|
| 策略代码执行安全性 | 高 | 实现 AST 代码检查 + 沙箱环境 | AI |
| 回测性能（大数据量）| 中 | 使用 Pandas 向量化操作，避免 Python 循环 | AI |
| 前端状态管理复杂性 | 中 | 使用 Zustand，保持 store 简洁 | AI |
| SQLite 并发写入 | 低 | 开发阶段影响不大，生产环境迁移至 PostgreSQL | AI |
| 两个数据库同步 | 中 | 明确分工：stock_db.sqlite 由用户管理，aipicking.db 由系统管理 | 用户 + AI |

### 问题

| 问题 | 状态 | 解决方案 | 负责人 |
|------|------|----------|----------|
| 回测任务队列使用什么实现？| 开放 | 初期使用 asyncio 后台任务，后期可迁移至 Celery | AI |
| 是否支持分布式回测？| 开放 | 后期可考虑，初期不支持 | AI |
| 报告导出格式优先级？| 开放 | JSON + HTML，PDF 后期考虑 | AI |
| 是否支持回测结果对比？| 开放 | 后期可考虑，初期不支持 | AI |

---

## 进度跟踪

### 已完成任务

- [x] T001: 初始化前端项目
- [x] T002: 初始化后端项目
- [x] T003: 配置开发环境
- [x] T004: 实现策略模型
- [x] T005: 实现回测报告模型
- [x] T008: 实现策略代码验证器

### 进行中任务

- [ ] T006: 实现策略上传 API

### 待开始任务

- [ ] T007: 实现策略管理 UI
- [ ] T009: 实现回测引擎
- [ ] T010: 实现回测 API
- [ ] T011: 实现回测报告 UI
- [ ] T012: 实现报告导出功能
- [ ] T013: 编写单元测试
- [ ] T014: 集成测试和优化

---

## 变更日志

- 2026-05-24: 初始版本创建
- 2026-05-24: 版本 2.0 - 调整为基于 WorkBuddy 项目的任务列表（策略脚本上传、T+1 回测引擎、JSON + HTML 报告格式）

---

*本文档是任务列表，详细描述了项目的任务分解和进度跟踪。在批准后可开始任务执行。*

*版本 2.0 - 调整为基于 WorkBuddy 项目的任务列表*
