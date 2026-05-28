# 回测推荐清单 — 点击股票弹出 K 线图

## 概述

回测/执行结果页面的推荐清单中，点击股票代码（`ts_code`）弹出一个 Modal，展示该股票过去一年的 K 线图（含均线、成交量）。

## 适用页面

- `BacktestDetail` — 单日回测报告详情
- `BatchBacktestDetail` — 批量回测详情（每日下钻表格）
- `StrategyDetail` — 策略详情 → 执行结果 Tab

## 方案

三个独立文件 + 一个后端接口：

### 后端

**新增接口：** `GET /api/v1/stocks/kline?ts_code=000001.SZ&days=365`

- 使用 query parameter 传 `ts_code`（代码含 `.`，避免 FastAPI path parameter 解析问题）
- 数据源：外部 `stock_db.sqlite` 的 `daily` 表
- 返回字段：`trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
- 按 `trade_date` 升序排列

响应格式：

```json
{
  "code": 0,
  "data": {
    "ts_code": "000001.SZ",
    "name": "平安银行",
    "items": [
      {
        "trade_date": "20250528",
        "open": 12.50,
        "high": 12.80,
        "low": 12.40,
        "close": 12.65,
        "vol": 123456,
        "amount": 1560000000
      }
    ]
  }
}
```

在 `backend/app/api/stocks.py` 新增路由，`stock_service.py` 新增 `get_kline` 方法。

### 前端

#### 1. `frontend/src/hooks/useKLineData.ts`

自定义 hook，封装请求逻辑：

```ts
function useKLineData(ts_code: string | null, days: number = 365) {
  // 返回: { data, loading, error }
}
```

- `ts_code` 为 `null` 时不发起请求
- 以 `ts_code + days` 为 key 做 session 级缓存（避免重复请求）

#### 2. `frontend/src/components/charts/KLineChart.tsx`

纯 ECharts 图表组件，使用 `candlestick` 类型，分上下两个 grid：

| 区域 | 占比 | 内容 |
|------|------|------|
| 主图 | 70% | K 线（红涨绿跌）+ MA5（白）/MA10（黄）/MA20（紫）/MA60（蓝）叠加线 |
| 成交量 | 30% | 柱状图，红涨绿跌，与主图共享 X 轴联动缩放 |

- 均线由前端基于 `close` 数据计算
- Tooltip 十字光标，显示日期、OHLC、各均线值
- Props: `{ data: KLineItem[], loading?: boolean, height?: number }`

#### 3. `frontend/src/components/shared/StockKLineModal.tsx`

Modal 壳组件：

```ts
interface StockKLineModalProps {
  ts_code: string;
  name?: string;
  open: boolean;
  onClose: () => void;
  days?: number; // 默认 365
}
```

- 宽度 900px，`footer={null}`，`destroyOnClose`
- 标题：`{name}（{ts_code}）— 近一年 K 线图`
- 加载中显示 Spin，错误显示 Alert
- 内部组合 `useKLineData` + `KLineChart`

### 页面接入方式

每个使用页只需两步：

1. 新增一个 state：`const [selectedStock, setSelectedStock] = useState<RecommendationItem | null>(null)`
2. 在 `ts_code` 列 render 中将其渲染为 `<a>` 点击链接，并在页面底部放一个 `<StockKLineModal>` 实例

```tsx
// ts_code 列:
render: (code: string, record: RecommendationItem) => (
  <a onClick={() => setSelectedStock(record)}>{code}</a>
)

// 页面底部:
<StockKLineModal
  ts_code={selectedStock?.ts_code ?? ''}
  name={selectedStock?.name}
  open={!!selectedStock}
  onClose={() => setSelectedStock(null)}
/>
```

### StockService

`frontend/src/services/stockService.ts` 新增方法：

```ts
async getKLine(tsCode: string, days: number = 365): Promise<KLineData>
```

### 涉及文件

| 文件 | 操作 |
|------|------|
| `backend/app/api/stocks.py` | 新增路由 |
| `backend/app/services/stock_service.py` | 新增 `get_kline` 方法 |
| `frontend/src/services/stockService.ts` | 新增 `getKLine` 方法 |
| `frontend/src/types/stock.ts` | 新增 `KLineItem`, `KLineData` 类型 |
| `frontend/src/hooks/useKLineData.ts` | **新增** |
| `frontend/src/components/charts/KLineChart.tsx` | **新增** |
| `frontend/src/components/shared/StockKLineModal.tsx` | **新增** |
| `frontend/src/pages/BacktestDetail.tsx` | 接入 Modal |
| `frontend/src/pages/BatchBacktestDetail.tsx` | 接入 Modal |
| `frontend/src/pages/StrategyDetail.tsx` | 接入 Modal |
