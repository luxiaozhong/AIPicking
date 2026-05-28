# AIpicking - A 股量化交易平台

一个用于 A 股量化交易的策略管理和回测平台，帮助用户管理量化策略并查看回测报告。

## 技术栈

### 前端
- React 18 + TypeScript
- Vite (构建工具)
- Ant Design (UI 组件库)
- React Router (路由)
- Zustand (状态管理)
- ECharts (图表)
- Monaco Editor (代码编辑器)

### 后端
- FastAPI (Python Web 框架)
- SQLAlchemy (ORM)
- SQLite (开发数据库)
- Pandas + NumPy (数据处理)
- Pydantic (数据验证)

## 项目结构

```
AIpicking/
├── frontend/               # React 前端项目
│   ├── src/
│   │   ├── components/    # 可复用组件
│   │   ├── pages/         # 页面组件
│   │   ├── services/      # API 调用服务
│   │   ├── stores/        # 状态管理
│   │   └── types/         # TypeScript 类型定义
│   └── package.json
│
├── backend/               # Python 后端项目
│   ├── app/
│   │   ├── api/          # API 路由
│   │   ├── models/       # 数据模型
│   │   ├── schemas/       # Pydantic schemas
│   │   └── services/     # 业务逻辑
│   ├── data/              # 数据存储
│   └── main.py
│
├── .specify/              # Spec Kit 配置
└── README.md
```

## 快速开始

### 前端开发

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 访问 http://localhost:5173
```

### 后端开发

```bash
# 进入后端目录
cd backend

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境 (macOS/Linux)
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 访问 http://localhost:8000/docs (Swagger UI)
```

## 核心功能

### 1. 策略管理
- 创建、编辑、删除策略
- 策略代码编辑器（Python）
- 策略参数配置

### 2. 回测报告
- 提交回测任务
- 查看回测结果（收益曲线、指标）
- 回测报告导出

## 开发路线图

### Phase 1: MVP (进行中)
- [x] 项目初始化
- [ ] 数据库模型设计
- [ ] 策略管理 CRUD API + UI
- [ ] 回测引擎核心实现
- [ ] 回测报告展示

### Phase 2: 增强功能
- [ ] 策略参数配置 UI
- [ ] 代码编辑器集成
- [ ] 回测报告导出
- [ ] 策略模板库

### Phase 3: 高级功能
- [ ] 实时行情监控
- [ ] 交易信号提醒
- [ ] 风险管理模块
- [ ] 自动交易执行

## API 文档

后端启动后，访问以下地址查看 API 文档：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 贡献指南

本项目使用 Spec Kit 进行规范驱动开发。在贡献代码前，请阅读 `.specify/` 目录下的文档。

## 许可证

MIT License

## 联系方式

如有问题或建议，请提交 Issue。
