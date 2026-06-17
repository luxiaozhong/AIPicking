# MACD 页面 — 回测推荐策略 + 回测批次两级选择器

## 背景

指数 MACD 页面底部的"最新回测推荐"目前固定查询全局最新一条 completed 回测。
用户希望能选择策略、再选择该策略的具体回测批次，查看不同回测的推荐结果。

## 需求

1. 一级下拉：策略选择，列出所有有已完成回测的策略
2. 二级下拉：回测批次选择，列出选中策略最近 10 条已完成回测（按日期降序）
3. 默认选中最新回测的策略 + 该策略最新一条回测
4. 切换策略自动刷新二级下拉和推荐个股
5. 切换回测批次自动刷新推荐个股
6. 点击个股行为不变：上方 MACD 图 + 预判

## 设计

### 后端

无改动。复用现有接口：
- `GET /api/v1/backtests?status=completed&limit=200` — 获取策略列表
- `GET /api/v1/backtests?strategy_id=X&status=completed&limit=10` — 获取某策略最近回测
- `GET /api/v1/backtests/{id}` — 获取单条回测详情

### 前端

仅修改 `frontend/src/pages/IndexMACD.tsx`。

#### 新增状态

- `availableStrategies: {id: number, name: string}[]` — 策略下拉选项
- `selectedStrategyId: number | null` — 当前选中策略
- `availableBacktests: {id: number, cutoffDate: string}[]` — 回测下拉选项
- `selectedBacktestId: number | null` — 当前选中回测
- `currentRecs` (原 `latestRecs`) — 当前展示的推荐数据

#### 三个 useEffect

```
① 首次加载 ([]):
   GET /backtests?status=completed&limit=200
   → 提取唯一策略 → 填充 availableStrategies
   → 默认选中第一条的 strategy_id

② 策略切换 ([selectedStrategyId]):
   GET /backtests?strategy_id=X&status=completed&limit=10
   → 填充 availableBacktests
   → 默认选中最新一条 → 直接使用列表中的 recommendations 展示

③ 回测切换 ([selectedBacktestId]):
   GET /backtests/{id}
   → 获取完整回测详情 → 更新 currentRecs
```

#### UI 改动

卡片标题栏：策略 `<Select>` + 回测日期 `<Select>` 两个下拉框并排。
