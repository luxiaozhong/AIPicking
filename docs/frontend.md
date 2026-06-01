# Frontend

## Tech Stack

React 18 + TypeScript + Vite + Ant Design 6 + Zustand + ECharts

## Routes

| 路由 | 页面 | 说明 |
|------|------|------|
| `/login` | Login | 绕过 AppLayout |
| `/dashboard` | Dashboard | 仪表盘 |
| `/strategies` | Strategy list | 含"可视化构建"和"AI 参考选股"按钮 |
| `/strategies/builder` | Visual factor builder | 因子组合 UI |
| `/strategies/ai-builder` | AI Strategy Builder | 多步骤向导（详见 ai-strategy.md） |
| `/strategies/:id` | Strategy detail | 含代码查看器 |
| `/strategies/:id/edit` | Code editor | Monaco 编辑器 |
| `/strategies/:id/backtest` | Backtest form | 回测表单 |
| `/backtests` | Backtest list | 回测列表 |
| `/backtests/:id` | Backtest detail | 回测详情 |
| `/users` | Admin user management | 仅 admin |

## Key Files

### Entry & Config
- `src/App.tsx` — 路由定义
- `src/services/api.ts` — 共享 Axios（auth 拦截器 + 自动刷新 token）

### Services (`src/services/`)
`authService`, `userService`, `strategyService`, `backtestService`, `factorService`, `aiService`, `stockService`

### Stores (`src/stores/`)
`authStore`, `strategyStore`, `backtestStore`, `themeStore`, `aiStrategyStore`

### Types (`src/types/`)
`auth.ts`, `strategy.ts`, `backtest.ts`, `factor.ts`, `aiStrategy.ts`

### Pages (`src/pages/`)
- `AIStrategyBuilder.tsx` — 双栏布局：提交表单 → 轮询 → 指标审查
- `TaskHistoryPanel.tsx` (`src/components/`) — 可复用任务历史侧边栏
