# 市场热度页面 — 设计文档

**日期**: 2026-06-05  
**状态**: 设计中  
**关联**: 数据管线文档 `docs/data-pipeline.md`

## 1. 背景与目标

### 1.1 现状

数据管线已采集以下市场数据，但前端无展示：

| 数据表 | 内容 | 采集来源 |
|--------|------|----------|
| `daily_sector_flow` | 行业/概念板块资金流向 | 东财 data.eastmoney.com |
| `daily_hot_stocks` | 每日热门股票（涨幅/换手率/上涨原因） | 同花顺 zx.10jqka.com.cn |
| `daily_hot_themes` | 从热门股提取的主题标签 | 从 hot_stocks.reason 提取 |
| `daily_northbound_flow` | 北向资金（沪深股通净流入） | hexin.cn |
| `daily_dragon_tiger` | 龙虎榜（席位买卖） | 东财 |

这些数据仅在回测引擎中被策略引用，前端用户看不到市场全貌。

### 1.2 目标

新增「市场热度」页面，让用户：

1. **一秒感知市场温度** — 核心 KPI 概览
2. **看清资金流向** — 板块热力图、北向趋势
3. **追踪市场热点** — 主题词云、热门股票

### 1.3 非目标

- 不新增数据采集管线（复用现有数据）
- 不修改现有 Dashboard 页面
- 不涉及策略或回测逻辑

---

## 2. 页面布局

路由 `/market-heat`，在侧边栏 `AppLayout` 中新增菜单项「市场热度」（图标 `FireOutlined`）。

### 2.1 3 层信息架构

```
┌─────────────────────────────────────────────────┐
│ 第一层: KPI 卡片行                                │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐            │
│ │ 市场  │ │ 北向  │ │ 涨跌  │ │ 领涨  │            │
│ │ 温度  │ │ 资金  │ │  比   │ │ 板块  │            │
│ └──────┘ └──────┘ └──────┘ └──────┘            │
├─────────────────────────────────────────────────┤
│ 第二层: 可视化分析区                             │
│ ┌──────────────────┐ ┌──────────┐               │
│ │  板块资金流热力图  │ │ 热门主题  │               │
│ │  (Treemap)       │ │  词云     │               │
│ └──────────────────┘ └──────────┘               │
├─────────────────────────────────────────────────┤
│ 第三层: 明细数据 (Tab 切换)                       │
│ [热门股票] [龙虎榜] [北向趋势] [板块排名]          │
│ ┌──────────────────────────────────────────────┐ │
│ │  Ant Design Table + 迷你趋势图                 │ │
│ └──────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

- **日期选择器**: 页面右上角，默认最新交易日
- **响应式**: KPI 大屏 4 列/中屏 2 列/小屏堆叠；热力图+词云大屏并排/中屏上下

---

## 3. 下钻交互

### 3.1 交互流程

不跳转页面，使用 Ant Design `Drawer` 组件（宽度 640px）从右侧滑出详情。

| 触发源 | 抽屉内容 |
|--------|----------|
| 点击热力图板块 | 近10日资金流趋势 + 成分股 Top5 + 关联主题 |
| 点击词云主题词 | 关联股票列表（涨幅/换手率/DDE）+ 主题热度变化 |
| 点击龙虎榜股票行 | 买卖席位明细（机构/游资标识）+ 近30日上榜记录 |
| 点击热门股票行 | **跳转**策略详情页（复用已有路由） |
| 点击 KPI 卡片 | 滚动到对应下方区域 |

### 3.2 状态管理

Zustand store 管理抽屉状态：

```typescript
interface DrawerState {
  open: boolean;
  type: 'sector' | 'theme' | 'dragon' | null;
  params: { code?: string; name?: string; date?: string };
}
```

抽屉内图表数据通过独立 API 按需加载（打开抽屉时才请求）。

---

## 4. 后端 API

### 4.1 路由

在 `main.py` 中注册：

```python
from .api import market_heat
app.include_router(market_heat.router, prefix="/api/v1/market-heat", tags=["market-heat"])
```

### 4.2 端点清单

所有端点需要认证（`Depends(get_current_user)`），返回统一信封。

| 方法 | 路径 | 参数 | 数据源 | 说明 |
|------|------|------|--------|------|
| GET | `/overview` | trade_date (可选) | daily + hot_stocks + northbound + sector_flow | 4 个 KPI |
| GET | `/sectors` | trade_date, sector_type | daily_sector_flow | 热力图数据 |
| GET | `/sectors/{code}` | trade_date, days=10 | sector_flow + daily | 板块详情（抽屉） |
| GET | `/themes` | trade_date, limit=20 | hot_themes + hot_stocks | 词云数据 |
| GET | `/themes/{name}` | trade_date | hot_stocks | 主题详情（抽屉） |
| GET | `/hot-stocks` | trade_date, page, page_size | hot_stocks | 热门股分页 |
| GET | `/dragon-tiger` | trade_date, page, page_size | dragon_tiger + seats | 龙虎榜分页 |
| GET | `/northbound` | days=30 | northbound_flow | 北向趋势 |
| GET | `/available-dates` | days=20 | sector_flow | 日期选择器数据 |

### 4.3 市场温度算法

综合评分 5 维度，每维度 0-20 分，满分 100：

| 维度 (权重) | 计算方式 | 理由 |
|-------------|----------|------|
| 资金面 (20) | 北向净流入方向+规模 | 外资是市场风向标 |
| 涨跌结构 (20) | 上涨家数 / 总家数 | 反映市场广度 |
| 情绪面 (20) | 涨停数 + 涨停/跌停比 | 极端情绪指标 |
| 板块集中度 (20) | 资金流入 Top3 板块占比 | 集中度≈结构性行情强度 |
| 热度延续 (20) | 热门主题较前日变化 | 热点持续性判断 |

温度区间：0-30 冰点 · 30-50 偏冷 · 50-70 中性 · 70-85 偏热 · 85-100 过热

### 4.4 新增文件

```
backend/app/
├── api/market_heat.py              # 路由层
└── services/market_heat_service.py # 业务层（SQL + 温度计算）
```

---

## 5. 前端实现

### 5.1 新增文件

```
frontend/src/
├── services/marketHeatService.ts   # API 调用（axios 封装）
├── stores/marketHeatStore.ts       # Zustand 状态管理
├── pages/MarketHeat.tsx            # 主页面（组装子组件）
└── components/market-heat/
    ├── TemperatureCard.tsx         # KPI 卡片（渐变背景）
    ├── SectorTreemap.tsx           # ECharts Treemap
    ├── ThemeWordCloud.tsx          # ECharts WordCloud（需 echarts-wordcloud）
    ├── SectorDrawer.tsx            # 板块详情抽屉
    └── ThemeDrawer.tsx             # 主题详情抽屉
```

### 5.2 依赖

- 现有: antd, echarts, echarts-for-react, zustand, axios
- 新增: `echarts-wordcloud`（ECharts 词云扩展）

### 5.3 数据流

```
MarketHeat.tsx
  ├── useEffect → store.fetchOverview(date)
  ├── useEffect → store.fetchSectors(date, type)
  ├── useEffect → store.fetchThemes(date)
  └── 用户交互:
       ├── 切换日期 → store.setDate() → 重新 fetch 所有数据
       ├── 切换行业/概念 → store.setSectorType() → fetchSectors()
       ├── 点击板块 → store.openDrawer('sector', code) → 抽屉内 fetch 详情
       └── 点击主题 → store.openDrawer('theme', name) → 抽屉内 fetch 详情
```

### 5.4 路由注册

在 `App.tsx` 中新增：

```tsx
<Route path="/market-heat" element={<MarketHeat />} />
```

在 `AppLayout.tsx` 菜单中新增：

```tsx
{ key: '/market-heat', icon: <FireOutlined />, label: '市场热度' }
```

---

## 6. 测试考虑

| 层级 | 测试内容 |
|------|----------|
| 后端 Service | 市场温度计算逻辑（mock 数据验证各维度得分） |
| 后端 API | 各端点返回正确结构 + 空数据容错 |
| 前端 Store | fetch 状态变化（loading → data/error） |
| 前端组件 | 各组件渲染 + 空状态 + 交互事件 |
| E2E | Playwright 测试页面加载 → 点击热力图 → 打开抽屉完整流程 |

---

## 7. 风险与边界

- **数据可用性**: 非交易日无数据，API 需返回空状态而非报错
- **词云库**: `echarts-wordcloud` 需确认与 ECharts 6 兼容，若不兼容则改用柱状图/列表
- **性能**: 单日 sector_flow 约 500 条，前端渲染无压力；历史趋势查询按需分页
- **日期选择器可用日期**: 从 sector_flow 表 DISTINCT trade_date 获取，只显示有数据的交易日

---

## 8. 未来扩展

以下不在本次范围，但设计预留了扩展空间：

- 新增「概念轮动」时间轴，展示热门概念的兴起/衰减
- 大盘指数 K 线叠加市场温度曲线
- 板块资金流异动预警
- 接入 L2 逐笔数据实现盘中实时热度
