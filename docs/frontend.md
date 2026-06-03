# Frontend

## Tech Stack

React 18 + TypeScript + Vite + Ant Design 6 + Zustand + ECharts

## Routes

| 路由 | 页面 | 说明 |
|------|------|------|
| `/login` | Login | 绕过 AppLayout |
| `/dashboard` | Dashboard | 仪表盘 |
| `/education` | EducationPage | 学习中心首页 |
| `/education/:category/:slug` | EducationDetailPage | 学习文章详情 |
| `/strategies` | Strategy list | 含"可视化构建"和"AI 参考选股"按钮 |
| `/strategies/builder` | Visual factor builder | 因子组合 UI |
| `/strategies/ai-builder` | AI Strategy Builder | 多步骤向导（详见 ai-strategy.md） |
| `/strategies/:id` | Strategy detail | 含代码查看器 |
| `/strategies/:id/edit` | Code editor | Monaco 编辑器 |
| `/strategies/:id/backtest` | Backtest form | 回测表单（单日 / 批量模式切换） |
| `/backtests` | BacktestList | **简单回测** — 统一页面，Radio.Group 切换单策略回测 / 批量回测 |
| `/backtests/batch` | → 重定向到 `/backtests` | 批量回测列表已合并到简单回测页面 |
| `/backtests/batch/:id` | BatchBacktestDetail | 批量回测详情 |
| `/backtests/:id` | Backtest detail | 单回测详情 |
| `/backtests/trade-sim` | TradeSimList | **交易模拟** — 统一页面，Radio.Group 切换单日 / 批量 |
| `/backtests/trade-sim/batch/:id` | BatchTradeSimDetail | 批量交易模拟详情 |
| `/backtests/trade-sim/:id` | TradeSimDetail | 单日交易模拟详情 |
| `/users` | Admin user management | 仅 admin |

### 导航结构

左侧菜单：

1. **仪表盘** (`/dashboard`)
2. **学习中心** (`/education`)
3. **策略管理** (`/strategies`)
4. **简单回测** (`/backtests`) — 单页面内含「单策略回测」/「批量回测」Radio 切换
5. **交易模拟** (`/backtests/trade-sim`) — 单页面内含「单日交易模拟」/「批量交易模拟」Radio 切换
6. **用户管理** (`/users`) — 仅 admin

## Key Files

### Entry & Config
- `src/App.tsx` — 路由定义
- `src/services/api.ts` — 共享 Axios（auth 拦截器 + 自动刷新 token）

### Services (`src/services/`)
`authService`, `userService`, `strategyService`, `backtestService`, `tradeSimService`, `factorService`, `aiService`, `stockService`, `educationService`

### Stores (`src/stores/`)
`authStore`, `strategyStore`, `backtestStore`, `themeStore`, `aiStrategyStore`, `onboardingStore`

### Types (`src/types/`)
`auth.ts`, `strategy.ts`, `backtest.ts`, `tradeSim.ts`, `factor.ts`, `aiStrategy.ts`

### Pages (`src/pages/`)
- `BacktestList.tsx` — 简单回测统一页面（单策略 + 批量回测合并）
- `TradeSimList.tsx` — 交易模拟统一页面（单日 + 批量合并）
- `BacktestForm.tsx` — 回测表单（单日 / 批量模式切换，含交易模拟入口）
- `AIStrategyBuilder.tsx` — 双栏布局：提交表单 → 轮询 → 指标审查
- `Dashboard.tsx` — 仪表盘（统计卡片 + 快捷操作）
- `BatchBacktestDetail.tsx` — 批量回测详情
- `BatchTradeSimDetail.tsx` — 批量交易模拟详情
- `TradeSimDetail.tsx` — 单日交易模拟详情
- `BacktestDetail.tsx` — 单回测详情
- `StrategyDetail.tsx` — 策略详情
- `EducationPage.tsx` / `EducationDetailPage.tsx` — 学习中心

### Components (`src/components/`)
- `Layout/AppLayout.tsx` — 全局布局（侧边栏 + 顶栏 + 内容区）
- `OnboardingWalkthrough.tsx` — 新用户操作引导
- `TaskHistoryPanel.tsx` — 可复用任务历史侧边栏
- `shared/` — PageHeader, StatusTag, ReturnLabel, StockSearchLookup 等共享组件
