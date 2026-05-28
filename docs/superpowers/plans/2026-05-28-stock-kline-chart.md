# 点击股票弹出 K 线图 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在回测推荐清单中点击股票代码，弹出 Modal 展示该股票过去一年的 K 线图（含 MA5/10/20/60、成交量）。

**Architecture:** 后端新增 `/api/v1/stocks/kline` 查询接口，从外部 `stock_db.sqlite` 的 `daily` 表取 OHLCV 数据。前端新增 `useKLineData` hook（数据层）、`KLineChart`（纯 ECharts 渲染）、`StockKLineModal`（Modal 壳），以独立可复用组件的方式组合。三个页面各加少量接入代码。

**Tech Stack:** FastAPI + SQLite（后端），React + TypeScript + Ant Design + ECharts（前端）

---

### Task 1: 后端 — stock_service 新增 get_kline 方法

**Files:**
- Modify: `backend/app/services/stock_service.py`

- [ ] **Step 1: 添加 get_kline 静态方法**

```python
@staticmethod
def get_kline(ts_code: str, days: int = 365) -> dict:
    """获取单只股票的日 K 线数据"""
    conn = sqlite3.connect(settings.STOCK_DB_PATH)
    conn.row_factory = sqlite3.Row

    # 获取股票名称
    stock = conn.execute(
        "SELECT name FROM stocks WHERE ts_code = ?", (ts_code,)
    ).fetchone()

    # 获取最近 N 个交易日的 OHLCV 数据
    rows = conn.execute(
        """
        SELECT trade_date, open, high, low, close, vol, amount
        FROM daily
        WHERE ts_code = ?
        ORDER BY trade_date DESC
        LIMIT ?
        """,
        (ts_code, days),
    ).fetchall()
    conn.close()

    items = [dict(r) for r in reversed(rows)]
    return {
        "ts_code": ts_code,
        "name": stock["name"] if stock else "",
        "items": items,
    }
```

- [ ] **Step 2: 验证方法存在**

```bash
cd backend && source venv/bin/activate && python -c "from app.services.stock_service import StockService; print('get_kline' in dir(StockService))"
```

Expected: `True`

---

### Task 2: 后端 — stocks.py 新增 kline 路由

**Files:**
- Modify: `backend/app/api/stocks.py`

- [ ] **Step 1: 添加 GET /kline 端点**

```python
@router.get("/kline")
def get_kline(
    ts_code: str = Query(..., min_length=1, description="股票代码"),
    days: int = Query(365, ge=1, le=730, description="数据天数"),
    current_user: User = Depends(get_current_user),
):
    """获取股票 K 线数据"""
    result = StockService.get_kline(ts_code, days)
    return {"code": 0, "message": "ok", "data": result}
```

用 query parameter 传 `ts_code` 避免 path parameter 中 `.` 的解析问题。

- [ ] **Step 2: 启动后端并测试接口**

```bash
cd backend && source venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 2

# 需要先登录获取 token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

# 测试 K 线接口
curl -s "http://localhost:8000/api/v1/stocks/kline?ts_code=000001.SZ&days=30" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -30
```

Expected: 返回 30 条 OHLCV 数据，`code: 0`

---

### Task 3: 前端 — 添加类型定义

**Files:**
- Modify: `frontend/src/types/stock.ts`

- [ ] **Step 1: 添加 KLineItem 和 KLineData 接口**

在文件末尾追加：

```ts
export interface KLineItem {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  vol: number;
  amount: number;
}

export interface KLineData {
  ts_code: string;
  name: string;
  items: KLineItem[];
}
```

- [ ] **Step 2: 类型检查**

```bash
cd frontend && npx tsc --noEmit src/types/stock.ts
```

Expected: 无报错

---

### Task 4: 前端 — stockService 新增 getKLine 方法

**Files:**
- Modify: `frontend/src/services/stockService.ts`

- [ ] **Step 1: 添加 getKLine 方法**

```ts
import api from './api';
import type { StockSearchResponse, KLineData } from '@/types/stock';

export const stockService = {
  async search(q: string, limit = 10) {
    const response = await api.get<{ code: number; data: StockSearchResponse }>('/stocks/search', {
      params: { q, limit },
    });
    return response.data.data.items;
  },

  async getKLine(tsCode: string, days: number = 365): Promise<KLineData> {
    const response = await api.get<{ code: number; data: KLineData }>('/stocks/kline', {
      params: { ts_code: tsCode, days },
    });
    return response.data.data;
  },
};

export default stockService;
```

- [ ] **Step 2: 类型检查**

```bash
cd frontend && npx tsc --noEmit src/services/stockService.ts
```

Expected: 无报错

---

### Task 5: 前端 — 新增 useKLineData hook

**Files:**
- Create: `frontend/src/hooks/useKLineData.ts`

- [ ] **Step 1: 创建 hook 文件**

```ts
import { useState, useEffect, useRef } from 'react';
import stockService from '@/services/stockService';
import type { KLineItem } from '@/types/stock';

const cache = new Map<string, { name: string; items: KLineItem[] }>();

interface KLineDataState {
  name: string;
  items: KLineItem[];
}

export function useKLineData(tsCode: string | null, days: number = 365) {
  const [data, setData] = useState<KLineDataState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cacheKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!tsCode) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }

    const key = `${tsCode}:${days}`;
    cacheKeyRef.current = key;

    const cached = cache.get(key);
    if (cached) {
      setData(cached);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    stockService
      .getKLine(tsCode, days)
      .then((result) => {
        if (cancelled) return;
        const value = { name: result.name, items: result.items };
        cache.set(key, value);
        setData(value);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.response?.data?.message || '获取 K 线数据失败');
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [tsCode, days]);

  return { data, loading, error };
}
```

- [ ] **Step 2: 类型检查**

```bash
cd frontend && npx tsc --noEmit src/hooks/useKLineData.ts
```

Expected: 无报错

---

### Task 6: 前端 — 新增 KLineChart 组件

**Files:**
- Create: `frontend/src/components/charts/KLineChart.tsx`

- [ ] **Step 1: 创建 KLineChart 组件**

```tsx
import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChartsWrapper from '@/components/charts/EChartsWrapper';
import type { KLineItem } from '@/types/stock';

interface KLineChartProps {
  data: KLineItem[];
  loading?: boolean;
  height?: number;
}

function calcMA(data: number[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    sum += data[i];
    if (i >= period) {
      sum -= data[i - period];
    }
    result.push(i >= period - 1 ? sum / period : null);
  }
  return result;
}

const MA_LINES = [
  { period: 5, name: 'MA5', color: '#757575' },
  { period: 10, name: 'MA10', color: '#f5a623' },
  { period: 20, name: 'MA20', color: '#e040fb' },
  { period: 60, name: 'MA60', color: '#1e88e5' },
] as const;

export default function KLineChart({ data, loading, height = 500 }: KLineChartProps) {
  const option: EChartsOption = useMemo(() => {
    if (!data.length) return {};

    const dates = data.map((d) => d.trade_date.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3'));
    const ohlc = data.map((d) => [d.open, d.close, d.low, d.high]);
    const volumes = data.map((d) => d.vol);
    const closes = data.map((d) => d.close);

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        valueFormatter: (value: unknown) => (typeof value === 'number' ? value.toFixed(2) : String(value)),
      },
      legend: {
        data: ['K 线', ...MA_LINES.map((m) => m.name)],
        top: 0,
      },
      grid: [
        { left: '8%', right: '2%', top: '8%', height: '62%' },
        { left: '8%', right: '2%', top: '76%', height: '16%' },
      ],
      xAxis: [
        {
          type: 'category',
          data: dates,
          gridIndex: 0,
          axisLabel: { show: false },
          axisLine: { onZero: false },
        },
        {
          type: 'category',
          data: dates,
          gridIndex: 1,
          axisLabel: { rotate: 0, formatter: (v: string) => v.slice(5) },
        },
      ],
      yAxis: [
        {
          scale: true,
          gridIndex: 0,
          splitArea: { show: true },
          axisLabel: { formatter: (v: number) => v.toFixed(1) },
        },
        {
          scale: true,
          gridIndex: 1,
          splitNumber: 2,
          axisLabel: {
            formatter: (v: number) => {
              if (v >= 1e8) return `${(v / 1e8).toFixed(1)}亿`;
              if (v >= 1e4) return `${(v / 1e4).toFixed(0)}万`;
              return String(v);
            },
          },
        },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
        { type: 'slider', xAxisIndex: [0, 1], start: 0, end: 100, height: 20, bottom: 0 },
      ],
      series: [
        {
          name: 'K 线',
          type: 'candlestick',
          data: ohlc,
          xAxisIndex: 0,
          yAxisIndex: 0,
          itemStyle: {
            color: '#ef5350',
            color0: '#26a69a',
            borderColor: '#ef5350',
            borderColor0: '#26a69a',
          },
        },
        ...MA_LINES.map((m) => ({
          name: m.name,
          type: 'line' as const,
          data: calcMA(closes, m.period),
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: true,
          lineStyle: { color: m.color, width: 1 },
          symbol: 'none' as const,
        })),
        {
          name: '成交量',
          type: 'bar',
          data: volumes,
          xAxisIndex: 1,
          yAxisIndex: 1,
          itemStyle: {
            color: (params: { dataIndex: number }) => {
              const d = data[params.dataIndex];
              return d.close >= d.open ? '#ef5350' : '#26a69a';
            },
          },
        },
      ],
    };
  }, [data]);

  return <EChartsWrapper options={option} loading={loading} height={height} empty={!data.length} />;
}
```

- [ ] **Step 2: 类型检查**

```bash
cd frontend && npx tsc --noEmit src/components/charts/KLineChart.tsx
```

Expected: 无报错

---

### Task 7: 前端 — 新增 StockKLineModal 组件

**Files:**
- Create: `frontend/src/components/shared/StockKLineModal.tsx`

- [ ] **Step 1: 创建 StockKLineModal 组件**

```tsx
import { Modal, Alert } from 'antd';
import { useKLineData } from '@/hooks/useKLineData';
import KLineChart from '@/components/charts/KLineChart';

interface StockKLineModalProps {
  ts_code: string;
  name?: string;
  open: boolean;
  onClose: () => void;
  days?: number;
}

export default function StockKLineModal({
  ts_code,
  name,
  open,
  onClose,
  days = 365,
}: StockKLineModalProps) {
  const { data, loading, error } = useKLineData(open ? ts_code : null, days);

  const title = name
    ? `${name}（${ts_code}）— 近一年 K 线图`
    : `${ts_code} — 近一年 K 线图`;

  return (
    <Modal
      title={title}
      open={open}
      onCancel={onClose}
      width={960}
      footer={null}
      destroyOnClose
    >
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
      <KLineChart data={data?.items ?? []} loading={loading} height={520} />
    </Modal>
  );
}
```

- [ ] **Step 2: 类型检查**

```bash
cd frontend && npx tsc --noEmit src/components/shared/StockKLineModal.tsx
```

Expected: 无报错

---

### Task 8: 前端 — BacktestDetail 接入

**Files:**
- Modify: `frontend/src/pages/BacktestDetail.tsx`

- [ ] **Step 1: 添加 import 和 state**

在文件顶部 import 区域添加：

```tsx
import StockKLineModal from '@/components/shared/StockKLineModal';
```

在组件函数内部，`const [executeResult, setExecuteResult] = ...` 行之后（实际上 BacktestDetail 没有这行，在 `const isFailed = ...` 之后）添加：

```tsx
const [selectedStock, setSelectedStock] = useState<RecommendationItem | null>(null);
```

- [ ] **Step 2: 修改 ts_code 列的 render**

将第 56 行：

```tsx
{ title: '股票代码', dataIndex: 'ts_code', key: 'ts_code', width: 110 },
```

替换为：

```tsx
{
  title: '股票代码',
  dataIndex: 'ts_code',
  key: 'ts_code',
  width: 110,
  render: (code: string, record: RecommendationItem) => (
    <a onClick={() => setSelectedStock(record)}>{code}</a>
  ),
},
```

需要从 `@/types/backtest` 导入 `RecommendationItem`（目前尚未导入，需在文件顶部添加）：

```tsx
import type { RecommendationItem } from '@/types/backtest';
```

- [ ] **Step 3: 在页面底部添加 Modal**

在 `</>` 返回的 Fragment 结束前（最后一个 `</>` 之前），添加：

```tsx
<StockKLineModal
  ts_code={selectedStock?.ts_code ?? ''}
  name={selectedStock?.name}
  open={!!selectedStock}
  onClose={() => setSelectedStock(null)}
/>
```

- [ ] **Step 4: 类型检查**

```bash
cd frontend && npx tsc --noEmit src/pages/BacktestDetail.tsx
```

Expected: 无报错

---

### Task 9: 前端 — BatchBacktestDetail 接入

**Files:**
- Modify: `frontend/src/pages/BatchBacktestDetail.tsx`

- [ ] **Step 1: 添加 import 和 state**

在文件顶部 import 区域添加：

```tsx
import { useState } from 'react';
import StockKLineModal from '@/components/shared/StockKLineModal';
```

注意：该文件已经 `import { useState } from 'react'`（第 1 行），只需添加 `StockKLineModal` 的 import。

- [ ] **Step 2: 修改 recColumns 中 ts_code 列的 render**

`recColumns` 是模块级常量（第 13-22 行），不能在其中使用 hook。需要将 `ts_code` 列的 render 改为接收一个回调。最简单的方式是：将 `recColumns` 改为函数，接收 `setSelectedStock` 参数。

删除第 13-22 行的 `const recColumns = [...]`，改为：

```tsx
function getRecColumns(onStockClick: (record: RecommendationItem) => void) {
  return [
    { title: '排名', key: 'index', width: 60, render: (_: unknown, __: unknown, i: number) => i + 1 },
    {
      title: '代码',
      dataIndex: 'ts_code',
      key: 'ts_code',
      width: 110,
      render: (code: string, record: RecommendationItem) => (
        <a onClick={() => onStockClick(record)}>{code}</a>
      ),
    },
    { title: '名称', dataIndex: 'name', key: 'name', width: 100 },
    { title: '得分', dataIndex: 'score', key: 'score', width: 70 },
    { title: '当日', dataIndex: 'return_0d', key: 'return_0d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
    { title: '3天', dataIndex: 'return_3d', key: 'return_3d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
    { title: '7天', dataIndex: 'return_7d', key: 'return_7d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
    { title: '15天', dataIndex: 'return_15d', key: 'return_15d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
  ];
}
```

- [ ] **Step 3: 修改 DailyPanel 组件，接收 onStockClick prop 并使用 getRecColumns**

修改 `DailyPanel` 函数签名：

```tsx
function DailyPanel({ result, onStockClick }: { result: DailyResultItem; onStockClick: (record: RecommendationItem) => void }) {
```

将其中的 `columns={recColumns}` 改为 `columns={getRecColumns(onStockClick)}`。

- [ ] **Step 4: 在 BatchBacktestDetail 中添加 state 和 Modal**

在组件函数内部，状态声明区域添加：

```tsx
const [selectedStock, setSelectedStock] = useState<RecommendationItem | null>(null);
```

`collapseItems` 中 `children: <DailyPanel result={result} />` 改为：

```tsx
children: <DailyPanel result={result} onStockClick={setSelectedStock} />,
```

在组件返回的 `</>` 结束前添加：

```tsx
<StockKLineModal
  ts_code={selectedStock?.ts_code ?? ''}
  name={selectedStock?.name}
  open={!!selectedStock}
  onClose={() => setSelectedStock(null)}
/>
```

- [ ] **Step 5: 类型检查**

```bash
cd frontend && npx tsc --noEmit src/pages/BatchBacktestDetail.tsx
```

Expected: 无报错

---

### Task 10: 前端 — StrategyDetail 接入

**Files:**
- Modify: `frontend/src/pages/StrategyDetail.tsx`

- [ ] **Step 1: 添加 import 和 state**

在文件顶部 import 区域添加：

```tsx
import StockKLineModal from '@/components/shared/StockKLineModal';
```

在 `executeResult` state 之后添加：

```tsx
const [selectedStock, setSelectedStock] = useState<RecommendationItem | null>(null);
```

- [ ] **Step 2: 修改执行结果表格的 ts_code 列**

在第 212 行，将：

```tsx
{ title: '股票代码', dataIndex: 'ts_code', width: 110 },
```

替换为：

```tsx
{
  title: '股票代码',
  dataIndex: 'ts_code',
  width: 110,
  render: (code: string, record: RecommendationItem) => (
    <a onClick={() => setSelectedStock(record)}>{code}</a>
  ),
},
```

- [ ] **Step 3: 在页面底部添加 Modal**

在组件返回的 `</>` 结束前（第 283 行 `</>` 之前），添加：

```tsx
<StockKLineModal
  ts_code={selectedStock?.ts_code ?? ''}
  name={selectedStock?.name}
  open={!!selectedStock}
  onClose={() => setSelectedStock(null)}
/>
```

- [ ] **Step 4: 类型检查**

```bash
cd frontend && npx tsc --noEmit src/pages/StrategyDetail.tsx
```

Expected: 无报错

---

### Task 11: 端到端验证

- [ ] **Step 1: 确保后端运行**

```bash
cd backend && source venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
```

- [ ] **Step 2: 确保前端运行**

```bash
cd frontend && npm run dev &
```

- [ ] **Step 3: 打开浏览器，验证功能**

1. 登录 `http://localhost:5173/login`
2. 进入一个已完成回测的报告页 `/backtests/:id`
3. 点击推荐清单中的股票代码（蓝色链接）
4. 验证：
   - Modal 弹出，标题显示股票名称和代码
   - K 线图正确渲染（红涨绿跌）
   - MA5/10/20/60 四条均线叠加在主图上
   - 成交量柱状图在下方，颜色跟随涨跌
   - 鼠标悬停显示十字光标 + tooltip
   - 底部 slider 可缩放时间范围
   - 关闭 Modal 后再次点击同一股票，数据从缓存读取（不重复请求）
5. 在批量回测详情页 `/backtests/batch/:id` 展开某一天，重复上述验证
6. 在策略详情页 `/strategies/:id` 的执行结果 Tab，重复上述验证

- [ ] **Step 4: 完整类型检查 + 构建**

```bash
cd frontend && npm run build
```

Expected: TypeScript 检查通过，Vite 构建成功

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/stock_service.py backend/app/api/stocks.py
git add frontend/src/types/stock.ts frontend/src/services/stockService.ts
git add frontend/src/hooks/useKLineData.ts frontend/src/components/charts/KLineChart.tsx frontend/src/components/shared/StockKLineModal.tsx
git add frontend/src/pages/BacktestDetail.tsx frontend/src/pages/BatchBacktestDetail.tsx frontend/src/pages/StrategyDetail.tsx
git commit -m "feat: add stock K-line chart modal on backtest recommendation pages"
```
