# 资金流向页面重构：板块主力资金流折线图 + 趋势追踪

> 状态：实施完成，待用户联调验证（2026-07-15）
> 目标：删除「行业资金流热力图」和「个股资金流」两个无帮助模块，新增「板块主力资金流折线图」和「趋势追踪（潜力板块）」
> 关联总文档：`SPEC.md`

## 1. 背景与问题

当前 `frontend/src/pages/FundFlow.tsx`（资金流向页）包含 4 层：

- **Layer 1 市场总览**：KPI + 四大指数 + 资金广度（保留）
- **Layer 2 板块/题材轮动**：行业/题材切换 + 主力净流入 Top 10 柱状图（保留）+ **行业资金流热力图**（删除）
- **Layer 3 个股资金流**：全市场个股排名大表（删除）
- 顶部 header 的「搜索个股资金流」抽屉（单只股票深度查看，保留）

用户反馈：热力图与个股资金流大表对"观察板块资金动向"帮助不大；希望改为：
1. 一张**各板块主力资金流折线图**，直观看出"最近哪些板块在持续流入"；
2. 一个**趋势追踪**模块（参考指数资金流页 `IndexFundFlow.tsx` 的「趋势追踪 / RankingTrend」），按板块主力净流入的**排名变化**追踪"潜力板块"。

## 2. 需求清单

| 编号 | 类型 | 描述 |
|------|------|------|
| R1 | 删除 | 删除「行业资金流热力图」卡片（`FundFlow.tsx` 899-907 行） |
| R2 | 删除 | 删除「个股资金流」Layer 3 大表及相关代码（453-973 行中个股表格部分） |
| R3 | 新增 | **板块主力资金流折线图**：多系列折线，x=交易日，每条线=一个板块，y=主力净流入(亿)；支持 行业/题材 切换、Top N 选择、每日/累计 切换 |
| R4 | 新增 | **趋势追踪**：参考 `RankingTrend`，按板块主力净流入排名变化追踪潜力板块（排名上升=资金持续进入） |

## 3. 方案与接口设计

### 3.1 板块主力资金流折线图（R3）

- **数据源**：复用现有 `GET /fund-flow/heatmap`（`FundFlowService.get_sector_heatmap`）。
  该接口已返回近 N 日 `每个板块每日` 的 `main_net_yi`（亿），数据结构：
  `{ type, days, rows: [{ trade_date, sector_name, main_net_yi }] }`。
- **无需新增后端接口**。前端把 `rows` 按板块 pivot 成多系列：
  - `dates = 去重排序的交易日`
  - 每板块一条 series：`data = dates.map(d => 该板块该日 main_net_yi)`
- **交互**：
  - 跟 Layer 2 的 `Segmented`（行业/题材）联动（复用 `store.sectorType`）。
  - Top N 选择（10/15/20）：按"窗口内累计净流入(亿)"取绝对值最大的 N 个板块（同时覆盖流入/流出两端，便于对比）。
  - 数值模式切换：`每日净流入` / `N日累计`（默认每日；累计 = 该板块截至当日的最近 N 日滚动和，平滑噪声，更利于"观察持续流入"）。
  - 颜色：净流入为红色、净流出为绿色（与全站 A 股配色一致：红=涨/流入）。
- **heatmap 查询天数**：将初始化与切换时的 `fetchHeatmap(20, ...)` 提升到 **30 天**，给折线图与趋势追踪更长的历史窗口（接口 `le=60`，安全）。

### 3.2 趋势追踪（R4）

- **参考对象**：`IndexFundFlow.tsx` 的「趋势追踪」`RankingTrend` 组件 + 后端 `get_index_ranking_trend`。
  其逻辑：对**每只股票**按"每日 5 日滚动累计主力净流入"排序得每日排名 → 计算 `improvement = 首日排名 − 末日排名`（>0 表示排名上升=潜力股），并附带 5日/15日累计、排名轨迹 sparkline。
- **板块版镜像**：
  - 新增后端接口 `GET /fund-flow/sector-ranking-trend?sector_type=industry&days=30`，
    复用 heatmap 的每日板块聚合数据，在 Python 侧计算：
    1. 每板块每日的 5 日 / 15 日滚动累计 `main_net_yi`；
    2. 每日按"5 日滚动累计"对**所有板块**排名；
    3. 输出与 `RankingTrendData` 同构的数据，仅把 `ts_code`→`sector_name`、`stock_name`→`sector_name`：
       `{ items: [{ sector_name, dates[], ranks[], flows5d[], flows15d[], flows[], improvement, current_rank, current_flow_5d, current_flow_15d, current_flow }] }`
  - **复用 `RankingTrend` 组件**（泛化）：增加可选 `nameField` 与可选 `onItemClick`，板块场景下不钻取个股；sparkline（排名轨迹）逻辑完全复用。
- **为什么放后端而非前端**：与现有指数 ranking-trend 架构一致；滚动窗口/排名计算在服务端更正确、可复用；返回结构可直接喂给 `RankingTrend`。

### 3.3 数据形状对齐（前后端复用）

```
# 后端新增返回（板块版 RankingTrendData）
RankingTrendItem {
  sector_name: str        # 板块名（原 ts_code 位置）
  dates: str[]            # 参与排名的交易日
  ranks: int[]            # 每日排名（1=最强）
  flows5d: number[]       # 每日 5 日滚动累计(亿)
  flows15d: number[]      # 每日 15 日滚动累计(亿)
  flows: number[]         # 每日主力净流入(亿)
  improvement: int        # 首日排名 - 末日排名（>0 上升）
  current_rank: int
  current_flow_5d: number
  current_flow_15d: number
  current_flow: number
}
```

## 4. 前端改动清单

- `frontend/src/pages/FundFlow.tsx`
  - 删除热力图卡片（R1）、删除 Layer 3 个股资金流大表及 `stockColumns/boardStockColumns/expandedRowRender/trendCache/handleExpand/handleStockSelect/searchedStock/stockSearchValue` 等只在 Layer 3 用的代码。
  - 新增卡片：「板块主力资金流趋势（折线图）」嵌入 `SectorFlowLineChart`；「趋势追踪（潜力板块）」嵌入（泛化后的）`RankingTrend`。
  - `Segmented`（行业/题材）联动控制：Top10 柱状图 + 折线图 + 趋势追踪（新增 `fetchSectorRankingTrend` 在切换时触发）。
  - 保留 header 的「搜索个股资金流」抽屉（`StockFundFlowDetail`），保留 Layer 1 的板块个股钻取 Drawer。
- `frontend/src/components/fund-flow/SectorFlowLineChart.tsx`（新增）
  - props：`rows: HeatmapRow[]`、`sectorType`、`topN`、`mode('daily'|'cum')`、`loading`。
  - 内部 pivot + 渲染多系列折线（ReactECharts）。
- `frontend/src/components/index-fund-flow/RankingTrend.tsx`（泛化）
  - 增加 `nameField?: 'stock_name' | 'sector_name'` 与可选 `onItemClick?`，使板块场景可直接复用；sparkline 逻辑不变。
- `frontend/src/services/fundFlowService.ts`
  - 新增 `getSectorRankingTrend(sectorType, days)` → `/fund-flow/sector-ranking-trend`。
  - 复用 `HeatmapRow` 类型；新增 `SectorRankingTrendItem` / `SectorRankingTrendData` 类型（或复用 `RankingTrendItem`）。
- `frontend/src/stores/fundFlowStore.ts`
  - 新增 `sectorRankingTrend` state + `fetchSectorRankingTrend(sectorType?, days?)` action（含 loading/error）。
  - `fetchHeatmap` 默认天数 20 → 30。
  - 移除仅 Layer 3 使用的 action（`fetchStockRanking`/`fetchStockTrend` 若别处无引用可移，但个股抽屉仍依赖 `fetchStockTrend` → 保留）。

## 5. 后端改动清单

- `backend/app/services/fund_flow_service.py`
  - 新增 `get_sector_ranking_trend(db, sector_type='industry', days=30)`：
    镜像 `get_index_ranking_trend` 算法（先取每日板块聚合，再算 5/15 日滚动累计、每日排名、`improvement` 等），但数据源为板块聚合（`get_sector_heatmap` 的同构查询，按 `industry_l1` / `concepts` 展开）。
- `backend/app/api/fund_flow.py`
  - 新增 `GET /fund-flow/sector-ranking-trend`（参数 `sector_type`、`days`，与 `heatmap` 一致的范围限制）。

## 6. 页面布局草图（重构后）

```
┌─────────────────────────────────────────────────────────────┐
│ 资金流向   [日期选择] [搜索个股资金流 🔍]                      │
├─────────────────────────────────────────────────────────────┤
│ Layer 1 市场总览                                              │
│  [KPI卡片×6]  [板块卡片×4(点击钻取个股)]                      │
│  [四大指数主力净流入趋势]      [资金广度趋势]                  │
├─────────────────────────────────────────────────────────────┤
│ Layer 2 板块/题材轮动          [Segmented: 行业 | 题材]        │
│  [主力净流入 Top 10 ↑/↓ 柱状图]                              │
│  ── 新增：板块主力资金流趋势（折线图） ──                      │
│  [ 行业/题材 | Top N: 10/15/20 | 每日/累计 ]                  │
│  [ 多系列折线：每板块一条线，红=流入 绿=流出 ]                │
│  ── 新增：趋势追踪（潜力板块） ──                              │
│  [ 表格：趋势 | 板块 | 今日变化 | 当前排名 | 5日累计          │
│           | 15日累计 | 排名轨迹(sparkline) | 今日主力 ]        │
└─────────────────────────────────────────────────────────────┘
（已删除：行业资金流热力图卡片、个股资金流 Layer 3 大表）
```

## 7. 实施计划

| 步骤 | 内容 | 说明 |
|------|------|------|
| Step 1 | 后端 `get_sector_ranking_trend` + 路由 | 镜像指数 ranking-trend，数据源改为板块聚合 |
| Step 2 | 前端 service + store 扩展 | `getSectorRankingTrend`、store state/action、heatmap 天数提至 30 |
| Step 3 | 新增 `SectorFlowLineChart` 组件 | 由 heatmap.rows pivot 出多系列折线 |
| Step 4 | 泛化 `RankingTrend` 支持板块 | 增加 `nameField`/可选 `onItemClick` |
| Step 5 | 改造 `FundFlow.tsx` | 删热力图+Layer3，插入折线图与趋势追踪卡片，Segmented 联动 |
| Step 6 | 自测 | 启动前后端，验证折线图/趋势追踪渲染、行业/题材切换、日期切换 |

## 8. 已确认假设（用户 2026-07-15 回复"都行"）

1. **顶部「搜索个股资金流」抽屉**：保留。
2. **Layer 1 板块卡片点击 → 板块个股 Top10 钻取 Drawer**：保留。
3. **趋势追踪位置**：放 Layer 2 内、折线图下方（纵向流式布局）。
4. **折线图配色**：红=流入、绿=流出（全站 A 股配色）。
