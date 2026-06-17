# StrategyTracker 支持指数选择

**日期**: 2026-06-16
**状态**: 待决策

## 背景

当前 StrategyTracker（策略跟踪）页面调用 `grow_with_money` 策略获取每日推荐时，`index_code` 参数**没有被前端传入**，完全依赖策略代码中的硬编码默认值 `"980080"`（国证成长 100）。

这意味着用户无法在 StrategyTracker 页面上切换指数，始终只能看到国证成长 100 成分股的推荐结果。

## 现状分析

### 参数传递路径

```
StrategyTracker.tsx
  → strategyTrackerService.getRecommendations(sid, date, false, 5, 10)
    → GET /strategy-tracker/recommendations?strategy_id=85&m=5&n=10
      → strategy_tracker.py: strategy_config = {"M": m, "N": n}
        → backtest_engine.run_live(cutoff_date)
          → grow_with_money.py: config.get("index_code", "980080")  ← 永远走默认值
```

### 对比：BacktestForm 页面

BacktestForm 页面**已经支持**指数选择：
- 读取策略的 `params_schema`，动态渲染表单字段
- 用户在 UI 上可以修改 `index_code` 等参数
- 参数通过 `config` 传给后端

### 当前默认值位置

| 位置 | 文件 | 行号 |
|------|------|------|
| 策略硬编码 | `backend/app/strategies/examples/grow_with_money.py:28` | `DEFAULT_INDEX_CODE = "980080"` |
| params_schema 默认值 | `backend/app/seed_strategies.py:95-99` | `"index_code": {"default": "980080", "label": "指数代码"}` |
| 策略跟踪器 API | `backend/app/api/strategy_tracker.py:137` | `strategy_config = {"M": m, "N": n}` — **缺 index_code** |

## 改动方案

### 改动范围：4 个文件，约 20 行代码

#### 1. 后端 API — `backend/app/api/strategy_tracker.py`

`get_recommendations()` 端点加一个可选参数：

```python
index_code: str = Query("980080", description="指数代码，默认国证成长100"),
```

两处使用：
- `strategy_config = {"M": m, "N": n, "index_code": index_code}`（L137）
- `cache_key = json.dumps({"M": m, "N": n, "index_code": index_code}, sort_keys=True)`（L141）

> 加入 cache_key 确保切换指数后不会命中旧指数的缓存。

#### 2. 前端服务 — `frontend/src/services/strategyTrackerService.ts`

`getRecommendations()` 方法加 `indexCode` 参数：

```typescript
async getRecommendations(
  strategyId: number, date?: string, forceRefresh?: boolean,
  m?: number, n?: number, indexCode?: string,
): Promise<RecommendationsResponse> {
  const response = await api.get(`${BASE}/recommendations`, {
    params: { strategy_id: strategyId, date, force_refresh: forceRefresh, m, n, index_code: indexCode },
  });
  return response.data;
},
```

#### 3. 前端页面 — `frontend/src/pages/StrategyTracker.tsx`

三处小改动：

**a) 加载策略时解析 `params_schema`**

在 `useEffect` 加载策略列表时（L150-158），额外解析当前策略的 `params_schema`，提取 `index_code` 的默认值。

**b) 加指数下拉框**

在工具栏（L428 策略选择器旁边）加一个 `Select` 组件，选项来源于已有 API `/fund-flow/index/indices`。

**c) 传参**

调用 `getRecommendations()` 时（L183）传入用户选择的 `indexCode`。

#### 4. 不需要改的文件

| 文件 | 原因 |
|------|------|
| `grow_with_money.py` | 已支持 `config.get("index_code", DEFAULT_INDEX_CODE)` |
| `BacktestEngine` (`backtest_engine.py`) | config 透传，无需改动 |
| `StrategyDailyRec` 模型 | `config` 列存 JSON，加字段自动兼容旧缓存 |
| 指数列表 API | `/fund-flow/index/indices` 已存在，可直接复用 |

### 兼容性

- 旧缓存（不带 `index_code` 字段的 `cache_key`）不会被新请求命中，首次会重新计算 → 正确行为
- 前端未传 `index_code` 时，后端默认值 `"980080"` 保持现有行为不变
- 其他策略如果不使用 `index_code` 参数，不受影响

## 其他可选指数

数据库中 `index_constituents` 表包含多个指数的成分股，可通过 `SELECT DISTINCT index_code, index_name FROM index_info` 查看完整列表。

已知相关指数（`grow_with_money` 体系已创建策略的）：
- `980080` — 国证成长 100
- 上证成长 / 深证成长 / 创业成长 / 科创成长 等

## 风险

- 低风险，改动量小，逻辑清晰
- 唯一注意点：`cache_key` 必须包含 `index_code`，否则指数切换后命中错误缓存
