# MACD 页面 — 回测推荐策略选择器

## 背景

指数 MACD 页面底部的"最新回测推荐"目前固定查询全局最新一条 completed 回测。
用户希望能选择策略，查看不同策略的推荐结果。

## 需求

1. 策略下拉框：列出所有有已完成回测的策略
2. 默认选中最新有回测结果的策略
3. 切换策略后自动刷新推荐个股
4. 点击个股行为不变：上方 MACD 图 + 预判

## 设计

### 后端

无改动。现有 `GET /api/v1/backtests?strategy_id=X&status=completed&limit=1` 已支持按策略筛选。

### 前端

仅修改 `frontend/src/pages/IndexMACD.tsx`。

#### 新增状态

- `availableStrategies: {id: number, name: string}[]` — 下拉框可选项
- `selectedStrategyId: number | null` — 当前选中策略

#### 逻辑拆分

原逻辑（一个 useEffect）：

```
GET /backtests?status=completed&limit=1 → 展示推荐
```

新逻辑（两个 useEffect）：

```
1. 首次加载：GET /backtests?status=completed&limit=200
   → 提取唯一 (strategy_id, strategy_name)
   → 填充 availableStrategies
   → 默认 selectedStrategyId = 第一条的 strategy_id
   → 同时展示第一条的推荐

2. 策略切换：GET /backtests?strategy_id=X&status=completed&limit=1
   → 更新 latestRecs
```

#### UI 改动

卡片标题栏：将静态 `<Tag>` 替换为 `<Select>` 下拉框，选项为 `availableStrategies`。

当选中策略无回测数据时，显示空状态提示。
