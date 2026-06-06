# 市场热度页面 — 设计与实现

**日期**: 2026-06-05（设计）/ 2026-06-06（更新）  
**状态**: 已实现  
**关联**: 
- 数据管线文档 `docs/data-pipeline.md`
- 板块涨跌幅分布 `docs/superpowers/specs/2026-06-06-board-change-distribution-design.md`

## 1. 背景与目标

### 1.1 数据源

数据管线已采集以下市场数据：

| 数据表 | 内容 | 采集来源 |
|--------|------|----------|
| `daily_sector_flow` | 行业/概念板块资金流向 | 东财 data.eastmoney.com |
| `daily_hot_stocks` | 每日热门股票（涨幅/换手率/上涨原因） | 同花顺 zx.10jqka.com.cn |
| `daily_hot_themes` | 从热门股提取的主题标签 | 从 hot_stocks.reason 提取 |
| `daily_northbound_flow` | 北向资金（深股通净流入+买入+卖出） | 东财深股通 |
| `daily_dragon_tiger` | 龙虎榜（席位买卖） | 东财 |
| `daily_market_temperature` | 市场温度（持久化，幂等 upsert） | 由 market_heat_service 计算写入 |
| `daily_board_temperature` | 四大指数板块温度（持久化，幂等 upsert） | 由 market_heat_service 计算写入 |

### 1.2 目标

「市场热度」页面让用户：

1. **一秒感知市场温度** — 全市场温度 + 四大指数板块温度
2. **看清资金流向** — 板块热力图、北向趋势图
3. **追踪市场热点** — 主题词云、热门股票、龙虎榜
4. **下钻明细** — 涨跌分布（支持板块筛选）、领涨/领跌板块个股

---

## 2. 页面布局

路由 `/market-heat`，侧边栏菜单项「市场热度」（图标 `FireOutlined`）。

### 2.1 实际布局

```
┌─────────────────────────────────────────────────────────┐
│ 第一行: KPI 卡片 (5 列固定网格)                           │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐           │
│ │ 市场  │ │上证主板│ │科创板 │ │深证主板│ │创业板 │           │
│ │ 温度  │ │ 温度  │ │ 温度  │ │ 温度  │ │ 温度  │           │
│ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘           │
├─────────────────────────────────────────────────────────┤
│ 第二行: KPI + 领涨/领跌 (响应式 auto-fit, min 200px)       │
│ ┌──────┐ ┌──────┐ ┌────────────┐ ┌────────────┐        │
│ │ 北向  │ │ 涨跌  │ │ 🏆 领涨板块 │ │ 📉 领跌板块 │        │
│ │ 资金  │ │  比   │ │ (2子项并排) │ │ (2子项并排) │        │
│ └──────┘ └──────┘ └────────────┘ └────────────┘        │
├─────────────────────────────────────────────────────────┤
│ 第三行: 可视化分析区                                     │
│ ┌──────────────────┐ ┌──────────┐                       │
│ │  板块资金流热力图  │ │ 热门主题  │                       │
│ │  (Treemap)       │ │  词云     │                       │
│ │  [行业|概念] 切换  │ │          │                       │
│ └──────────────────┘ └──────────┘                       │
│                        ┌──────────────────────────────┐ │
│                        │ Tab 明细: [热门股票][龙虎榜]   │ │
│                        └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

- **日期选择器**: 页面右上角，默认最新交易日，仅可选有数据的日期
- **刷新按钮**: 日期选择器旁
- **响应式**: KPI 第一行固定 5 列；第二行 `auto-fit, minmax(200px, 1fr)`

---

## 3. 下钻交互

### 3.1 交互流程

| 触发源 | 目标 | 展示内容 |
|--------|------|----------|
| 点击「市场温度」卡片 | Modal 弹窗 | 近 60 日市场温度趋势图（5 维度 tooltip） |
| 点击「北向资金」卡片 | KpiDetailModal | 近 10 日买入/卖出/净额柱状图 |
| 点击「涨跌比」卡片 | KpiDetailModal | 涨跌幅度分布柱状图 + 板块筛选 Segmented（全部/上证/深圳/科创/创业） |
| 点击「领涨/领跌板块」子项 | KpiDetailModal | 板块内个股 Top 15 表格（涨幅/收盘价） |
| 点击四大指数板块温度卡片 | Modal 弹窗 | 该板块近 60 日温度趋势图（3 维度 tooltip） |
| 点击热力图板块 | SectorDrawer（右侧滑出） | 近 10 日资金流趋势 + 成分股 Top5 |
| 点击词云主题词 | ThemeDrawer（右侧滑出） | 关联股票列表（涨幅/换手率/DDE） |
| 点击龙虎榜/热门股票行 | StockKLineModal | 个股 K 线图（弹窗） |

### 3.2 KPI 详情弹窗（KpiDetailModal）

统一管理 4 种 KPI 下钻视图，通过 `type` prop 切换：

| type | 数据源 | 图表类型 |
|------|--------|----------|
| `northbound` | `GET /northbound?days=10` | ECharts 柱状图（买入/卖出/净额） |
| `advance_decline` | `GET /change-distribution?board=` | ECharts 柱状图（8 区间涨跌分布）+ Segmented 板块切换 |
| `leading_sector` | `GET /leading-sector-stocks?sort_order=desc` | Ant Table（涨幅前 15） |
| `lagging_sector` | `GET /leading-sector-stocks?sort_order=asc` | Ant Table（跌幅前 15） |

涨跌分布图特征：
- 8 个区间：-10%以下 / -10%~-5% / -5%~-2% / -2%~0% / 0%~2% / 2%~5% / 5%~10% / 10%以上
- 负区间绿色系，正区间红色系，颜色深浅与数量成正比
- 上方汇总：涨 N 家 | 跌 N 家 | 涨跌比 X%
- 板块切换时自动重新请求，显示 loading 状态

### 3.3 状态管理

不跳转页面：
- **Modal 弹窗**: 温度趋势、板块温度趋势、KPI 详情、K 线图——由页面级 `useState` 控制
- **Drawer 抽屉**: 板块详情、主题详情——由 Zustand store 的 `drawer` 状态控制

```typescript
// page-level state (MarketHeat.tsx)
const [klineStock, setKlineStock] = useState<{ts_code, name} | null>(null);
const [kpiDetail, setKpiDetail] = useState<{type, sectorName?} | null>(null);
const [temperatureModalOpen, setTemperatureModalOpen] = useState(false);
const [boardTempModal, setBoardTempModal] = useState<{boardCode, boardName} | null>(null);

// Zustand store state
drawer: { open: boolean; type: 'sector' | 'theme' | null; code: string | null; name: string | null }
```

---

## 4. 后端 API

### 4.1 路由

```python
from .api import market_heat
app.include_router(market_heat.router, prefix="/api/v1/market-heat", tags=["market-heat"])
```

### 4.2 端点清单

所有端点需要认证（`Depends(get_current_user)`），返回统一信封 `{code, message, data}`。

| 方法 | 路径 | 参数 | 数据源 | 说明 |
|------|------|------|--------|------|
| GET | `/overview` | trade_date (可选) | daily + sector_flow + northbound + board_temperature | 全市场温度 + 四大板块温度 + 北向 + 涨跌比 + 领涨/领跌板块 |
| GET | `/sectors` | trade_date, sector_type | daily_sector_flow | 热力图数据 |
| GET | `/sectors/{code}` | trade_date, days=10 | sector_flow + daily + stocks | 板块详情（抽屉） |
| GET | `/themes` | trade_date, limit=20 | daily_hot_themes | 词云数据 |
| GET | `/themes/{name}` | trade_date | daily_hot_stocks | 主题关联股票（抽屉） |
| GET | `/hot-stocks` | trade_date, page, page_size | daily_hot_stocks + daily | 热门股分页 |
| GET | `/dragon-tiger` | trade_date, page, page_size | daily_dragon_tiger + daily_dragon_tiger_seat | 龙虎榜分页（含席位） |
| GET | `/northbound` | days=30 | daily_northbound_flow | 北向资金日趋势（含买入/卖出额） |
| GET | `/available-dates` | days=20 | daily | 日期选择器可用日期 |
| GET | `/change-distribution` | trade_date, board (可选) | daily | 涨跌幅度分段统计（8 区间柱状图，可选板块筛选） |
| GET | `/leading-sector-stocks` | sector_name, trade_date, sort_order | daily + stocks | 板块内个股 Top 15（sort_order=desc 涨幅靠前，asc 跌幅靠前） |
| GET | `/temperature-history` | days=60 | daily_market_temperature | 全市场温度历史趋势 |
| GET | `/board-temperatures` | trade_date (可选) | daily_board_temperature | 四大指数板块温度（最新/指定日） |
| GET | `/board-temperature-history/{board_code}` | board_code, days=60 | daily_board_temperature | 指定板块温度历史趋势 |

### 4.3 全市场温度算法

综合评分 5 维度，每维度 0-20 分，满分 100：

| 维度 (权重) | 计算方式 | 理由 |
|-------------|----------|------|
| 资金面 (20) | 北向净流入方向+规模 | 外资是市场风向标 |
| 涨跌结构 (20) | 上涨家数 / 总家数（日内 close>open） | 反映市场广度 |
| 情绪面 (20) | 涨停数 + 涨停/跌停比（标准日涨跌幅 ≥9.8%/≤-9.8%） | 极端情绪指标 |
| 板块集中度 (20) | 资金流入 Top3 板块占比（倒U型评分，30%-50% 满分） | 结构性行情强度 |
| 热度延续 (20) | 热门主题 Jaccard 相似度（今日 vs 前日） | 热点持续性 |

温度区间：0-30 冰点 · 30-50 偏冷 · 50-70 中性 · 70-85 偏热 · 85-100 过热

### 4.4 四大指数板块温度算法

板块定义及 ts_code 正则：

| board_code | board_name | ts_code 正则 |
|------------|------------|-------------|
| `sh_main` | 上证主板 | `^[56]0[0-5]` |
| `sh_star` | 科创板 | `^688` |
| `sz_main` | 深证主板 | `^00[0-3]` |
| `sz_chi` | 创业板 | `^30[01]` |

3 维度评分，满分 100（权重与全市场不同）：

| 维度 (权重) | 计算方式 |
|-------------|----------|
| 涨跌结构 (40) | 上涨家数 / 总家数 × 50，上限 40 |
| 情绪面 (30) | 涨停/跌停比 × 活跃度因子（触及涨跌停占比/3%），上限 30 |
| 量能活跃度 (30) | 当日成交额 / 近 20 日日均成交额 × 15，上限 30 |

温度区间同全市场（0-30 冰点 · 30-50 偏冷 · ... · 85-100 过热）。

### 4.5 涨跌分布算法

使用**日内涨跌** `(close - open) / open * 100`（与涨跌比 KPI 的 `close > open` 判断一致），分 8 个区间统计个股数量。当 `board` 参数不为空时，追加 `ts_code ~ 'pattern'` 条件过滤对应板块。

**注意**: 领涨/领跌板块个股弹窗使用**标准日涨跌幅** `(close - pre_close) / pre_close * 100`（与市场惯例一致），两者公式不同，各有用途。

---

## 5. 前端实现

### 5.1 文件清单

```
frontend/src/
├── services/marketHeatService.ts     # API 调用 + 类型定义（ChangeBucket, LeadingStock, BoardTemperatureItem 等）
├── stores/marketHeatStore.ts         # Zustand 状态管理（日期、概览、板块、主题、热门股、龙虎榜、温度历史、抽屉）
├── pages/MarketHeat.tsx              # 主页面（组装子组件 + Modal 管理 + K 线弹窗）
└── components/market-heat/
    ├── TemperatureCard.tsx           # KPI 卡片行（5 列市场+板块温度 + 响应式第二行）
    ├── KpiDetailModal.tsx            # KPI 下钻弹窗（北向图表/涨跌分布/板块个股表格）
    ├── SectorTreemap.tsx             # ECharts Treemap（板块资金流热力图）
    ├── ThemeWordCloud.tsx            # ECharts WordCloud（热门主题词云）
    ├── SectorDrawer.tsx              # 板块详情抽屉（资金流趋势 + 成分股）
    └── ThemeDrawer.tsx               # 主题详情抽屉（关联股票列表）
```

### 5.2 依赖

- 现有: antd, echarts, echarts-for-react, zustand, axios, dayjs
- 新增: `echarts-wordcloud`（ECharts 词云扩展，2.x）

### 5.3 数据流

```
MarketHeat.tsx
  ├── useEffect(fetchAvailableDates) → 获取可用日期列表，设置默认日期
  ├── useEffect(fetchTemperatureHistory) → 获取全市场温度历史（页面加载时）
  ├── useEffect(当 tradeDate 变化):
  │     ├── store.fetchOverview()    → KPI 卡片 + 四大板块温度
  │     ├── store.fetchSectors()     → 热力图数据
  │     ├── store.fetchThemes()      → 词云数据
  │     ├── store.fetchHotStocks(1)  → 热门股 Table
  │     ├── store.fetchDragonTiger(1)→ 龙虎榜 Table
  │     └── store.fetchNorthbound()  → 北向趋势（备用）
  │
  └── 用户交互:
       ├── 切换日期 → store.setTradeDate() → 触发全部 fetch
       ├── 切换行业/概念 → store.setSectorType() → fetchSectors()
       ├── 点击市场温度卡片 → setTemperatureModalOpen(true) → Modal 展示温度趋势图
       ├── 点击板块温度卡片 → setBoardTempModal() + fetchBoardTemperatureHistory()
       ├── 点击北向/涨跌比/领涨领跌 → setKpiDetail() → KpiDetailModal 按需加载
       │     └── 涨跌比弹窗内切换板块 → Segmented onChange → 重新请求 change-distribution
       ├── 点击热力图板块 → store.openDrawer('sector', ...) → SectorDrawer 按需加载
       ├── 点击词云主题 → store.openDrawer('theme', ...) → ThemeDrawer 按需加载
       └── 点击股票名 → setKlineStock() → StockKLineModal
```

### 5.4 路由注册

在 `App.tsx` 中：
```tsx
<Route path="/market-heat" element={<MarketHeat />} />
```

在 `AppLayout.tsx` 菜单中：
```tsx
{ key: '/market-heat', icon: <FireOutlined />, label: '市场热度' }
```

---

## 6. 后端文件

```
backend/app/
├── api/market_heat.py              # 路由层（14 个端点，含统一信封返回 + 认证）
└── services/market_heat_service.py # 业务层
    ├── 概览 KPI: get_overview, _calc_temperature, save_temperature
    ├── 板块温度: _calc_board_temp, save_board_temperatures, get_board_temperatures, get_board_temperature_history
    ├── 板块资金流: get_sectors, get_sector_detail
    ├── 涨跌分布: get_change_distribution (含 board 筛选)
    ├── 板块个股: get_leading_sector_stocks (含 sort_order)
    ├── 主题: get_themes, get_theme_detail
    ├── 明细: get_hot_stocks, get_dragon_tiger, get_northbound
    └── 工具: _get_latest_date_for, _enrich_with_daily, get_available_dates, get_temperature_history
```

---

## 7. 注意事项

### 7.1 涨跌幅公式差异

| 场景 | 公式 | 原因 |
|------|------|------|
| 涨跌比 KPI 卡片 | `close > open`（日内） | 快速判断当日方向 |
| 涨跌分布柱状图 | `(close-open)/open`（日内） | 与 KPI 卡片口径一致 |
| 领涨/领跌板块个股 | `(close-pre_close)/pre_close`（标准日涨跌幅） | 与市场惯例一致，用户预期 |

### 7.2 板块过滤正则

板块过滤使用 PostgreSQL `~` 正则操作符，通过 `sa_text()` 注入 SQL。正则来源为硬编码的 `BOARD_DEFINITIONS` 常量，不存在 SQL 注入风险。

### 7.3 数据可用性

- 非交易日无数据，API 返回空列表/空状态而非报错
- 指定日期无数据时自动回退到最新有数据的交易日（sectors、sector_detail）
- 日期选择器仅显示有数据的交易日（从 daily 表 DISTINCT trade_date）

---

## 8. 未来扩展

以下不在本次范围，但设计预留了扩展空间：

- 新增「概念轮动」时间轴，展示热门概念的兴起/衰减
- 大盘指数 K 线叠加市场温度曲线
- 板块资金流异动预警
- 接入 L2 逐笔数据实现盘中实时热度
- 涨跌分布增加标准日涨跌幅模式（与日内模式可切换）
