# MACD 交互学习页 — 设计文档

**日期**: 2026-05-29  
**状态**: 待实现  
**前置**: 教育功能 Phase 1（学习中心基础框架）已上线

---

## 概述

将 MACD 文章详情页升级为交互式学习页面，用户可通过预置案例或自选股票，在真实 K 线图上观察 MACD 指标，调节参数实时查看变化，按步骤引导理解信号含义。

## 页面结构

上下布局，4 个区域：

```
┌─────────────────────────────────────┐
│ Zone 1: 案例选择器                    │
│ [预设案例下拉] 或 [搜索股票] [查看]      │
├─────────────────────────────────────┤
│ Zone 2: 交互图表 (ECharts)            │
│ ┌─────────────────────────────────┐ │
│ │  K 线 + 信号标注层               │ │
│ │  (金叉/死叉/背离/零轴穿越)         │ │
│ ├─────────────────────────────────┤ │
│ │  MACD 指标面板                   │ │
│ │  (DIF + DEA + 柱状图 + 对比虚线)   │ │
│ └─────────────────────────────────┘ │
├─────────────────────────────────────┤
│ Zone 3: 步骤导航                     │
│  ●──○──○──○  当前步骤说明  [下一步→]  │
├─────────────────────────────────────┤
│ Zone 4a: 步骤讲解  │ Zone 4b: 参数面板│
│ (Markdown 文案)    │ [快线] ──●──   │
│                    │ [慢线] ──●──   │
│                    │ [信号] ──●──   │
│                    │ [恢复默认]      │
├─────────────────────────────────────┤
│ ☐ 显示默认参数对比线                    │
└─────────────────────────────────────┘
```

## Zone 1: 案例选择器

- 预设案例下拉菜单（预设 3 个经典案例）
- 股票搜索输入框（复用 StockSearchLookup 交互模式）
- 选择案例或搜索股票 → Zone 2 图表加载对应 K 线数据

### 预置案例

预置案例的**信号标注点通过案例配置预定义**（手动标注时间 + 类型 + 文案），确保教学准确性。

| 案例 | 股票 | 时间段 | 教学重点 |
|------|------|--------|----------|
| 金叉买入 | 贵州茅台 600519 | 2020-01 ~ 2020-06 | DIF 上穿 DEA 形成金叉买入信号 |
| 顶背离卖出 | 宁德时代 300750 | 2021-09 ~ 2022-03 | 价格新高 MACD 未新高形成顶背离 |
| 底背离反弹 | 比亚迪 002594 | 2022-03 ~ 2022-08 | 价格新低 MACD 未新低形成底背离 |

### 自选股票模式

当用户通过搜索框自选股票时：
- 图表正常显示 K 线 + MACD，参数可调
- 信号标注改为**前端算法自动检测**（金叉死叉、背离），不显示步骤导航
- 显示提示条："自选模式 — 无步骤引导，自由探索"

## Zone 2: 交互图表

基于现有 `KLineChart` 组件扩展，新增：

### MACD 计算（前端实时）

```
EMA(today) = Price(today) * (2/(N+1)) + EMA(yesterday) * (1 - 2/(N+1))
DIF = EMA(close, FAST) - EMA(close, SLOW)
DEA = EMA(DIF, SIGNAL)
MACD_BAR = 2 * (DIF - DEA)
```

参数默认值：`FAST=12, SLOW=26, SIGNAL=9`。参数变化时前端即时重算，无需请求后端。

### 信号标注

- **金叉**：DIF 上穿 DEA → 图上方绿色箭头 + 日期标签
- **死叉**：DIF 下穿 DEA → 图上方红色箭头 + 日期标签
- **顶背离**：价格创新高 + MACD DIF 未创新高 → 连线 + 标签
- **底背离**：价格创新低 + MACD DIF 未创新低 → 连线 + 标签
- **零轴穿越**：DIF/DEA 穿越零线 → 水平虚线标记

### 参数对比模式

勾选"显示默认参数对比线"后，图上额外绘制默认参数 (12,26,9) 的 DIF/DEA 虚线，与当前参数实线形成对比。

### 图表布局

ECharts `grid` 分两个面板：
- 上方面板：K 线蜡烛图 (70% 高度) + 信号标注 markPoint/markLine
- 下方面板：MACD 指标 (30% 高度) — DIF 线 + DEA 线 + 柱状图 + 零轴参考线

## Zone 3: 步骤导航

每个案例预定义 4 个学习步骤。步骤数据结构：

```typescript
interface LearningStep {
  step: number;           // 1-4
  title: string;          // 步骤标题
  content: string;        // Markdown 讲解文案（Zone 4a 渲染）
  chartHighlight?: {      // 图表高亮配置
    annotationIds: string[];  // 当前步骤要显示的标注 ID
    defaultParams?: boolean;  // 是否使用默认参数
  };
}
```

步骤切换时：图表标注显隐 → Zone 4a 文案切换 → 参数面板可选联动（某一步可能提示用户调参）。

## Zone 4a: 步骤讲解

渲染当前步骤的 Markdown 文案。内容在案例配置中预定义。若当前为自由探索模式（无步骤），显示通用 MACD 知识介绍。

## Zone 4b: 参数面板

- 3 个滑块：快线 EMA (2-50)、慢线 EMA (5-100)、信号线 EMA (2-30)
- 拖动滑块 → Zone 2 MACD 实时重算
- 「恢复默认」按钮 → 重置为 12/26/9

## 数据流

```
用户选择案例 → getKline(stock, days) → K 线数据
                                          ↓
                              前端计算 MACD(数据, 参数)
                                          ↓
                              渲染 K 线图 + MACD 面板
                                          ↓
                              标注信号点 (markPoint/markLine)
                                          ↓
用户拖动参数滑块 → 重新计算 MACD → 图表实时刷新
                                          ↓
用户切换步骤 → 标注显隐控制 + 文案切换
```

### API 依赖

| API | 用途 | 已有？ |
|-----|------|--------|
| `GET /api/v1/stocks/kline?ts_code=X&days=N` | 获取 K 线数据 | ✅ 已有 |
| `GET /api/v1/education/articles/{slug}` | 获取 MACD 文章基础内容 | ✅ 已有 |

### 新增内容文件

```
backend/content/education/macd-interactive/
├── cases.yaml              # 案例配置（股票、时间段、信号标注点、步骤定义）
└── steps/                  # 每个案例的步骤 Markdown 文案
    ├── case-1-step-1.md
    ├── case-1-step-2.md
    ...
```

## 前端组件

### 新增组件

| 组件 | 文件 | 职责 |
|------|------|------|
| `InteractiveMACDPage` | `pages/InteractiveMACDPage.tsx` | 页面容器，管理 4 个 Zone 的状态联动 |
| `CaseSelector` | `components/education/CaseSelector.tsx` | Zone 1: 案例下拉 + 股票搜索 |
| `MACDInteractiveChart` | `components/education/MACDInteractiveChart.tsx` | Zone 2: 扩展 KLineChart，叠加 MACD 指标 + 信号标注 |
| `StepNavigator` | `components/education/StepNavigator.tsx` | Zone 3: 步骤圆点 + 上一步/下一步 |
| `ParameterPanel` | `components/education/ParameterPanel.tsx` | Zone 4b: 参数滑块 |

### 修改组件

| 组件 | 变更 |
|------|------|
| `EducationDetailPage.tsx` | 当 slug === 'macd' 时渲染 `InteractiveMACDPage` 替代纯 Markdown |
| `KLineChart.tsx` | 可选抽离 `calcEMA` / `calcMACD` 工具函数到 `utils/indicators.ts` |

### 路由

不变。`/education/indicators/macd` 自动变为交互模式。

## 错误处理

- K 线数据加载失败 → Zone 2 显示 "数据加载失败，请重试"，其他区域仍可用
- 案例配置解析失败 → 降级到纯文章模式（现有 Markdown 渲染）
- 自选股票无数据 → 提示 "该股票暂无数据"

## 不在范围

- 其他指标（RSI、KDJ 等）的交互页面 — 仅做 MACD 作为第一个
- 移动端适配 — 桌面端优先
- 用户自定义保存参数配置
- 回测功能集成

## 参考来源

- TradingView 指标面板参数调整模式
- TradingView Bar Replay 历史信号回溯
- 同花顺/东方财富指标参数修改交互
