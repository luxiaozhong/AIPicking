# 量化交易平台 - 项目原则 (Constitution)

## 项目概述
构建一个用于 A 股量化交易的策略管理和回测平台，帮助用户管理量化策略并查看回测报告。

## 技术栈决策

### 前端
- **框架**: React 18 + TypeScript
- **UI 组件库**: Ant Design 5
- **状态管理**: Zustand（轻量级，适合中型项目）
- **图表**: ECharts 或 Recharts（用于回测报告可视化）
- **HTTP 客户端**: Axios
- **路由**: React Router v6

### 后端
- **框架**: Python 3.11+ with FastAPI
- **数据库**: SQLite 3（开发阶段），可迁移至 PostgreSQL（生产）
- **ORM**: SQLAlchemy 2.0+ 或原生 sqlite3
- **数据加工**: Pandas, NumPy
- **回测引擎**: 自研或集成 Backtrader

### 开发工具
- **包管理**: pnpm (前端), poetry 或 pip (后端)
- **代码规范**: ESLint + Prettier (前端), Black + Ruff (后端)
- **版本控制**: Git

## 开发原则

### 1. 代码质量
- 所有 Python 代码必须通过 type hints 和 mypy 类型检查
- 前端使用 TypeScript，禁止 `any` 类型
- 关键业务逻辑必须有单元测试覆盖（目标覆盖率 >70%）

### 2. 数据安全
- 交易策略代码隔离执行，避免恶意代码
- 数据库访问使用参数化查询，防止 SQL 注入
- 敏感配置（如交易账户）不提交到版本控制

### 3. 性能要求
- API 响应时间 < 500ms（95th percentile）
- 回测任务支持异步执行，避免阻塞 UI
- 历史数据查询使用索引优化

### 4. 用户体验
- 响应式设计，支持桌面和移动端访问
- 回测报告支持交互式图表（缩放、悬停查看详情）
- 操作反馈及时（加载状态、错误提示）

### 5. 可扩展性
- 策略以插件形式管理，支持热加载
- 数据源抽象接口，方便接入新的数据源
- 前端组件化，便于功能迭代

### 6. 策略脚本规范（新增）
- 策略脚本必须是独立的 Python 文件
- 策略脚本必须实现以下标准接口：
  - `check_xxx(df, pick_dt)` - 形态识别函数，返回 `{"passed": bool, "score": int, "details": {}, "breakdown": {}}`
  - `run(pick_date, all_data, meta_df)` - 选股函数，返回精选股票列表
  - `backtest(start_date, end_date)` - 回测函数（可选，由后端统一回测引擎执行）
- 策略脚本必须通过安全验证（AST 检查禁止的操作）
- 策略脚本支持参数配置（通过 JSON 配置文件）

### 7. A 股交易规则（新增）
- 严格模拟 A 股 T+1 交易制度（当日买入，次日才能卖出）
- 支持双轨制风控（主板 10% vs 科创板/创业板 20%）
- 支持时间止损（T+1 收盘检查，T+2 强制清仓）
- 交易成本模型包含：佣金 + 印花税（仅卖出）+ 滑点

## 项目结构

```
AIpicking/
├── frontend/               # React 前端项目
│   ├── src/
│   │   ├── components/    # 可复用组件
│   │   ├── pages/         # 页面组件
│   │   ├── services/      # API 调用服务
│   │   ├── stores/        # 状态管理
│   │   └── utils/         # 工具函数
│   └── package.json
│
├── backend/               # Python 后端项目
│   ├── app/
│   │   ├── api/          # API 路由
│   │   ├── models/       # 数据模型
│   │   ├── services/     # 业务逻辑
│   │   └── strategies/   # 策略插件目录
│   ├── tests/
│   └── main.py
│
├── data/                  # 数据存储
│   ├── database/          # SQLite 数据库文件
│   └── market_data/       # 历史行情数据
│
├── docs/                  # 项目文档
└── .specify/              # Spec Kit 配置
```

## 核心功能模块

### MVP 阶段（当前迭代）
1. **策略管理**
   - 创建、编辑、删除策略
   - 策略代码编辑器（支持语法高亮）
   - 策略参数配置

2. **回测报告**
   - 回测任务提交和状态查询
   - 回测结果展示（收益曲线、指标表格）
   - 报告历史记录

### 未来迭代
- 实时行情监控
- 交易信号提醒
- 风险管理系统
- 自动交易执行

## 技术债务管理
- 使用 TODO 注释标记待完成功能
- 定期重构策略执行模块
- 数据库 schema 变更使用迁移脚本

## 禁止事项
- ❌ 不使用 class components（React）
- ❌ 不使用 `any` 类型（TypeScript）
- ❌ 不提交包含敏感信息的代码
- ❌ 不在生产环境使用 SQLite（需迁移至 PostgreSQL）

---
*本文档是项目的"宪法"，所有后续开发和决策都应遵循这些原则。*
