# AIpicking - A 股量化交易平台

A 股量化策略管理、回测与 AI 智能选股平台。

## 技术栈

### 前端
- React 18 + TypeScript + Vite + Ant Design 6
- Zustand 状态管理 + ECharts 图表 + Monaco Editor 代码编辑

### 后端
- FastAPI + SQLAlchemy async + SQLite (aiosqlite)
- Pandas + NumPy 数据处理
- DeepSeek 大模型（K 线分析 + 代码生成）

## 核心功能

### 1. 策略管理
- 上传策略文件、可视化因子构建器、AI 参考选股
- Monaco 代码编辑器在线编辑
- 策略版本管理、标签分类

### 2. 回测系统
- 单日回测 + 批量周期回测
- 推荐股票未来 [3, 7, 15] 天表现追踪
- K 线图 + 收益曲线可视化
- 异步线程池执行，不阻塞服务

### 3. AI 参考个股选股（新）
- 输入个股 + 日期，DeepSeek 提取 50+ 量化指标实际值
- 对全市场股票按相似度距离打分排序
- 自动生成指标计算代码（含运行时验证）

### 4. 用户系统
- JWT 认证（access + refresh token）
- admin / user 角色分离，数据隔离

## 项目结构

```
AIpicking/
├── frontend/
│   └── src/
│       ├── pages/          # 页面（含 AIStrategyBuilder）
│       ├── services/       # API 调用（含 aiService）
│       ├── stores/         # Zustand stores（含 aiStrategyStore）
│       └── types/          # TypeScript types（含 aiStrategy.ts）
├── backend/
│   └── app/
│       ├── api/            # REST 路由（含 AI 端点）
│       ├── services/       # 业务逻辑（含 llm_service, ai_strategy_service）
│       ├── models/         # 数据模型（含 AIStrategyTask）
│       └── factors/        # 量化因子库（5 大类 16 因子）
├── docs/superpowers/       # 开发文档
├── deploy.sh               # 一键部署脚本
└── restart.sh              # 开发环境重启脚本
```

## 快速开始

```bash
# 后端
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 编辑 .env，填入 DEEPSEEK_API_KEY
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 前端
cd frontend
npm install
npm run dev

# 访问 http://localhost:5173
# 管理员: admin / admin123
```

## .env 配置

```bash
DATABASE_URL=sqlite+aiosqlite:///./data/database/aipicking.db
STOCK_DB_PATH=/path/to/stock_db.sqlite      # A 股日线数据
DEEPSEEK_API_KEY=sk-xxx                      # DeepSeek API key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TIMEOUT=60
CORS_ORIGINS=http://localhost:5173
```

## 服务器部署

```bash
sudo ./deploy.sh                    # 一键部署

# 日常更新
cd /opt/AIpicking
git pull
cd backend && ./venv/bin/pip install -r requirements.txt -q
cd ../frontend && npm install --silent && npm run build
systemctl restart aipicking

# 查看日志
journalctl -u aipicking -f
```

## API

- Swagger UI: http://localhost:8000/docs
- `/api/v1/ai/analyze-stock` — AI 参考选股
- `/api/v1/strategies` — 策略 CRUD
- `/api/v1/backtests` — 回测
- `/api/v1/auth/login` — 登录

## 许可证

MIT
