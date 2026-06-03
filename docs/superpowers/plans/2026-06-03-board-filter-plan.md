# Board Filter & 入选率展示 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 回测表单增加板块筛选复选框，回测报告展示入选总数/基础总股数/入选率指标，批量回测过滤 0 入选日并支持股票每日追踪展开。

**Architecture:** 后端在 BacktestEngine 的 run/run_batch 中，策略返回后截断前统计 total_qualifying；加载 stocks 后按 config.board_filter 前缀过滤并计 base_stock_count。前端 BacktestForm 加复选框写入 config，BacktestDetail/BatchBacktestDetail 展示新 StatCard，BatchBacktestDetail 增加 StockKLineModal + expandable 每日追踪行。

**Tech Stack:** Python/FastAPI/SQLAlchemy (后端) + React/TypeScript/Ant Design/ECharts (前端)

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `backend/app/schemas/backtest.py` | BacktestSummary +3 字段 |
| 修改 | `backend/app/services/backtest_engine.py` | 板块过滤 + 入选计数 + 空日过滤 |
| 修改 | `backend/app/services/trade_sim_engine.py` | _get_stock_candidates 中应用板块过滤 |
| 修改 | `frontend/src/types/backtest.ts` | BacktestSummary 接口 +3 字段 |
| 修改 | `frontend/src/pages/BacktestForm.tsx` | 板块复选框 + config.board_filter |
| 修改 | `frontend/src/pages/BacktestDetail.tsx` | 汇总卡片 +3 StatCard |
| 修改 | `frontend/src/pages/BatchBacktestDetail.tsx` | 过滤 + 每日统计 + StockKLineModal + 展开行 |

---

### Task 1: 后端 Schema — BacktestSummary 新增 3 字段

**Files:**
- Modify: `backend/app/schemas/backtest.py`

- [ ] **Step 1: 在 BacktestSummary 末尾添加 3 个新字段**

在 `BacktestSummary` 类的 `worst_return_15d` 字段后添加：

```python
    total_qualifying: int = Field(0, description="满足策略条件的股票总数（topN 截断前）")
    base_stock_count: int = Field(0, description="选中板块的股票总数（池子大小）")
    pick_rate: float = Field(0.0, description="入选率 = total_qualifying / base_stock_count")
```

- [ ] **Step 2: 验证 Schema 导入正常**

```bash
cd backend && source venv/bin/activate && python -c "from app.schemas.backtest import BacktestSummary; s = BacktestSummary(total_recommendations=5, avg_return_3d=0.01, avg_return_7d=0.02, avg_return_15d=0.03, win_rate_3d=0.6, win_rate_7d=0.5, win_rate_15d=0.4, best_return_15d=0.15, worst_return_15d=-0.10, total_qualifying=20, base_stock_count=500, pick_rate=0.04); print(s.model_dump())"
```

Expected: 输出包含 `total_qualifying`, `base_stock_count`, `pick_rate`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/backtest.py
git commit -m "feat: BacktestSummary 新增 total_qualifying/base_stock_count/pick_rate 字段"
```

---

### Task 2: 后端引擎 — 板块过滤辅助方法 + _empty_summary 更新

**Files:**
- Modify: `backend/app/services/backtest_engine.py`

- [ ] **Step 1: 添加 `_filter_by_board` 静态/实例方法**

在 `BacktestEngine` 类中 `_validate_strategy` 方法之后添加：

```python
    def _apply_board_filter(
        self,
        stocks_data: List[Dict],
        daily_data: Dict[str, List[Dict]],
    ) -> Tuple[List[Dict], Dict[str, List[Dict]], int]:
        """按 config.board_filter 过滤 stocks 和 daily，返回 (filtered_stocks, filtered_daily, base_count)"""
        board_filter = (self.config or {}).get("board_filter")
        if not board_filter or not isinstance(board_filter, list) or len(board_filter) == 0:
            # 未设置板块过滤，默认全板块
            board_filter = ["60", "00", "688", "689", "300", "301"]

        def _matches_board(ts_code: str) -> bool:
            return any(ts_code.startswith(prefix) for prefix in board_filter)

        filtered_stocks = [s for s in stocks_data if _matches_board(s["ts_code"])]
        filtered_codes = {s["ts_code"] for s in filtered_stocks}
        filtered_daily = {
            code: rows for code, rows in daily_data.items()
            if code in filtered_codes
        }

        return filtered_stocks, filtered_daily, len(filtered_stocks)
```

- [ ] **Step 2: 更新 `_empty_summary` 方法**

将 `_empty_summary` 方法更新为包含新字段：

```python
    def _empty_summary(self) -> Dict[str, Any]:
        return {
            "total_recommendations": 0,
            "total_qualifying": 0,
            "base_stock_count": 0,
            "pick_rate": 0.0,
            "avg_return_3d": 0.0, "win_rate_3d": 0.0,
            "best_return_3d": 0.0, "worst_return_3d": 0.0,
            "avg_return_7d": 0.0, "win_rate_7d": 0.0,
            "best_return_7d": 0.0, "worst_return_7d": 0.0,
            "avg_return_15d": 0.0, "win_rate_15d": 0.0,
            "best_return_15d": 0.0, "worst_return_15d": 0.0,
        }
```

- [ ] **Step 3: 验证导入**

```bash
cd backend && source venv/bin/activate && python -c "from app.services.backtest_engine import BacktestEngine; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/backtest_engine.py
git commit -m "feat: 添加 _apply_board_filter 辅助方法，更新 _empty_summary 含新字段"
```

---

### Task 3: 后端引擎 — `run()` 方法集成板块过滤 & 计数

**Files:**
- Modify: `backend/app/services/backtest_engine.py` ( `run()` 方法，约第 198-233 行)

- [ ] **Step 1: 修改 `run()` 方法**

将现有 `run()` 方法中加载数据后、调用策略前的逻辑替换为：

```python
    def run(
        self,
        cutoff_date: str,
        track_days: List[int] = [3, 7, 15]
    ) -> Dict[str, Any]:
        loaded = self._load_data(cutoff_date)
        stocks_data = loaded["stocks"]
        daily_data = loaded["daily"]

        ts_code = (self.config or {}).get("ts_code", "").strip()

        # 单股诊断模式：不应用板块过滤
        if ts_code:
            if ts_code in daily_data:
                daily_data = {ts_code: daily_data[ts_code]}
            else:
                return {"recommendations": [], "summary": self._empty_summary()}
            base_stock_count = 1
        else:
            # 应用板块过滤
            stocks_data, daily_data, base_stock_count = self._apply_board_filter(
                stocks_data, daily_data
            )

        strategy_input = {
            "cutoff_date": cutoff_date,
            **loaded,
            "stocks": stocks_data,
            "daily": daily_data,
            "config": self.config or {},
        }

        try:
            recommendations = self.strategy_func(strategy_input)
        except Exception as e:
            raise RuntimeError(f"策略执行失败: {e}")

        if not recommendations or not isinstance(recommendations, list):
            return {"recommendations": [], "summary": self._empty_summary()}

        # 截断前统计
        total_qualifying = len(recommendations)
        recommendations = recommendations[:MAX_RECOMMENDATIONS]
        recommendations = self._track_performance(recommendations, cutoff_date, track_days)
        summary = self._calculate_summary(recommendations, track_days)

        # 写入板块统计
        summary["total_qualifying"] = total_qualifying
        summary["base_stock_count"] = base_stock_count
        summary["pick_rate"] = round(
            total_qualifying / base_stock_count, 6
        ) if base_stock_count > 0 else 0.0

        return {"recommendations": recommendations, "summary": summary}
```

- [ ] **Step 2: 验证语法正确**

```bash
cd backend && source venv/bin/activate && python -c "from app.services.backtest_engine import BacktestEngine; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/backtest_engine.py
git commit -m "feat: run() 集成板块过滤，截断前统计入选总数及入选率"
```

---

### Task 4: 后端引擎 — `run_batch()` 集成板块过滤 & 空日跳过

**Files:**
- Modify: `backend/app/services/backtest_engine.py` ( `run_batch()` 方法，约第 235-303 行)

- [ ] **Step 1: 修改 `run_batch()` 方法**

修改 `run_batch()` 中的循环体。定位到 `for cutoff_date in trading_days:` 循环内部（约第 253 行），修改为：

```python
        for cutoff_date in trading_days:
            cutoff_date_fmt = datetime.strptime(cutoff_date, "%Y%m%d").strftime("%Y-%m-%d")
            daily_result = {
                "cutoff_date": cutoff_date,
                "input": {"cutoff_date": cutoff_date, "config": self.config or {}},
            }
            try:
                sliced_daily = {}
                for code, rows in daily_data.items():
                    sliced_rows = [r for r in rows if r["trade_date"] <= cutoff_date]
                    if sliced_rows:
                        sliced_daily[code] = sliced_rows

                if ts_code:
                    sliced_daily = {ts_code: sliced_daily[ts_code]} if ts_code in sliced_daily else {}
                    base_stock_count = 1
                    filtered_stocks = stocks_data  # 单股模式不应用板块过滤
                else:
                    # 应用板块过滤（stocks_data 在循环外已全量加载）
                    filtered_stocks, sliced_daily, base_stock_count = self._apply_board_filter(
                        stocks_data, sliced_daily
                    )

                # 切片横截面数据到当日
                sliced_hot_stocks = [r for r in loaded["hot_stocks"] if r.get("trade_date") == cutoff_date_fmt]
                sliced_hot_themes = [r for r in loaded["hot_themes"] if r.get("trade_date") == cutoff_date_fmt]

                strategy_input = {
                    "cutoff_date": cutoff_date,
                    "stocks": filtered_stocks,
                    "daily": sliced_daily,
                    "daily_sector_flow": loaded["daily_sector_flow"],
                    "hot_stocks": sliced_hot_stocks,
                    "hot_themes": sliced_hot_themes,
                    "dragon_tiger": loaded["dragon_tiger"],
                    "dragon_tiger_seats": loaded["dragon_tiger_seats"],
                    "financials": loaded["financials"],
                    "config": self.config or {},
                }

                recommendations = self.strategy_func(strategy_input)
                if not recommendations or not isinstance(recommendations, list):
                    recommendations = []

                # 0 入选日跳过
                if len(recommendations) == 0:
                    continue

                # 截断前统计
                total_qualifying = len(recommendations)
                recommendations = recommendations[:MAX_RECOMMENDATIONS]
                recommendations = self._track_performance(recommendations, cutoff_date, track_days)
                summary = self._calculate_summary(recommendations, track_days)

                summary["total_qualifying"] = total_qualifying
                summary["base_stock_count"] = base_stock_count
                summary["pick_rate"] = round(
                    total_qualifying / base_stock_count, 6
                ) if base_stock_count > 0 else 0.0

                daily_result["status"] = "completed"
                daily_result["recommendations"] = recommendations
                daily_result["summary"] = summary
            except Exception as e:
                daily_result["status"] = "failed"
                daily_result["error_message"] = str(e)

            results.append(daily_result)
```

> 注意：需要把循环外 `stocks_data` 的引用改为 `filtered_stocks`。注意 `ts_code` 单股模式不应用板块过滤。

- [ ] **Step 2: 验证语法正确**

```bash
cd backend && source venv/bin/activate && python -c "from app.services.backtest_engine import BacktestEngine; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/backtest_engine.py
git commit -m "feat: run_batch() 集成板块过滤，0 入选日跳过，每日统计入选率"
```

---

### Task 5: 后端 — trade_sim_engine 应用板块过滤

**Files:**
- Modify: `backend/app/services/trade_sim_engine.py`

- [ ] **Step 1: 修改 `_get_stock_candidates` 方法**

在 `_get_stock_candidates` 中加载数据后、传给策略前应用板块过滤（约第 101-126 行）：

```python
    def _get_stock_candidates(self, cutoff_date: str) -> List[dict]:
        """运行策略选股，按 score 降序取前 N 只"""
        loaded = self._backtest_engine._load_data(cutoff_date)

        stocks_data = loaded["stocks"]
        daily_data = loaded["daily"]

        # 应用板块过滤
        filtered_stocks, filtered_daily, _ = self._backtest_engine._apply_board_filter(
            stocks_data, daily_data
        )

        strategy_input = {
            "cutoff_date": cutoff_date,
            **loaded,
            "stocks": filtered_stocks,
            "daily": filtered_daily,
            "config": self.config,
        }

        try:
            recommendations = self._backtest_engine.strategy_func(strategy_input)
        except Exception as e:
            raise RuntimeError(f"策略执行失败: {e}")

        if not recommendations or not isinstance(recommendations, list):
            return []

        # 按 score 降序排序，无 score 按名称排序
        recommendations.sort(
            key=lambda x: (x.get("score") is not None, x.get("score", 0), x.get("name", "")),
            reverse=True,
        )

        top_n = self.config.get("top_n", 5)
        return recommendations[:top_n]
```

- [ ] **Step 2: 验证语法正确**

```bash
cd backend && source venv/bin/activate && python -c "from app.services.trade_sim_engine import TradeSimEngine; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/trade_sim_engine.py
git commit -m "feat: trade_sim_engine 应用板块过滤"
```

---

### Task 6: 前端类型 — BacktestSummary 接口新增字段

**Files:**
- Modify: `frontend/src/types/backtest.ts`

- [ ] **Step 1: 在 BacktestSummary 接口末尾添加 3 个字段**

在 `worst_return_15d` 后添加：

```typescript
export interface BacktestSummary {
  total_recommendations: number;
  avg_return_3d: number;
  avg_return_7d: number;
  avg_return_15d: number;
  win_rate_3d: number;
  win_rate_7d: number;
  win_rate_15d: number;
  best_return_15d: number;
  worst_return_15d: number;
  total_qualifying: number;
  base_stock_count: number;
  pick_rate: number;
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20
```

Expected: 无新增类型错误

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/backtest.ts
git commit -m "feat: BacktestSummary 类型新增 total_qualifying/base_stock_count/pick_rate"
```

---

### Task 7: 前端 BacktestForm — 板块复选框

**Files:**
- Modify: `frontend/src/pages/BacktestForm.tsx`

- [ ] **Step 1: 添加板块选择状态和默认值**

在现有状态声明区域（约第 43 行 `stopFactors` 之后）添加：

```typescript
  const BOARD_OPTIONS = [
    { label: '上证', value: '60' },
    { label: '深圳', value: '00' },
    { label: '科创', value: '688/689' },
    { label: '创业', value: '300/301' },
  ];

  const [boardFilter, setBoardFilter] = useState<string[]>(['60', '00', '688/689', '300/301']);
```

- [ ] **Step 2: 添加板块选中值转前缀数组的辅助函数**

在组件顶部（import 之后，组件定义之前）添加：

```typescript
function boardFilterToPrefixes(selected: string[]): string[] {
  const map: Record<string, string[]> = {
    '60': ['60'],
    '00': ['00'],
    '688/689': ['688', '689'],
    '300/301': ['300', '301'],
  };
  return selected.flatMap(k => map[k] || []);
}
```

- [ ] **Step 3: 在简单回测和交易模拟表单中添加板块复选框 UI**

在「目标股票」Form.Item 之后（约第 303 行，`</>` 之前），简单回测区域添加：

```tsx
              <Form.Item label="基础板块" required>
                <CheckboxGroup
                  options={BOARD_OPTIONS}
                  value={boardFilter}
                  onChange={(values) => {
                    if (values.length > 0) {
                      setBoardFilter(values as string[]);
                    }
                  }}
                />
                <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
                  用于计算入选率的分母，至少选一个
                </Text>
              </Form.Item>
```

同样在交易模拟区域（约第 423 行 `</>` 之前）也添加相同的板块选择 UI。

- [ ] **Step 4: 修改提交流程，将 board_filter 写入 config**

**简单回测单日**（约第 191-198 行），修改 payload 构建：

```typescript
      if (stockCode.trim()) {
        payload.config = { ts_code: stockCode.trim(), board_filter: boardFilterToPrefixes(boardFilter) };
      } else {
        payload.config = { board_filter: boardFilterToPrefixes(boardFilter) };
      }
```

**简单回测批量**（约第 159-174 行），同样修改：

```typescript
        if (stockCode.trim()) {
          payload.config = { ts_code: stockCode.trim(), board_filter: boardFilterToPrefixes(boardFilter) };
        } else {
          payload.config = { board_filter: boardFilterToPrefixes(boardFilter) };
        }
```

**交易模拟单日**（约第 133-140 行），修改 payload：

```typescript
        const payload: TradeSimCreate = {
          strategy_id: currentStrategy.id,
          cutoff_date: cutoffDate.format('YYYY-MM-DD'),
          total_amount: totalAmount,
          top_n: topN,
          max_hold_days: maxHoldDays,
          stop_factors: stopFactors,
          config: { board_filter: boardFilterToPrefixes(boardFilter) },
        };
```

**交易模拟批量**（约第 98-107 行），同样添加 config。

- [ ] **Step 5: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/BacktestForm.tsx
git commit -m "feat: BacktestForm 新增基础板块复选框，写入 config.board_filter"
```

---

### Task 8: 前端 BacktestDetail — 新增 3 个 StatCard

**Files:**
- Modify: `frontend/src/pages/BacktestDetail.tsx`

- [ ] **Step 1: 在汇总指标卡片中添加第二行**

在现有 4 个 StatCard 的 `</Row>` 之后（第 136 行后），图表之前，添加：

```tsx
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={12} sm={8}>
              <StatCard
                title="入选总数"
                value={`${summary.total_qualifying ?? '—'}`}
                color="#1677ff"
              />
            </Col>
            <Col xs={12} sm={8}>
              <StatCard
                title="基础总股数"
                value={`${summary.base_stock_count ?? '—'}`}
                color="#722ed1"
              />
            </Col>
            <Col xs={12} sm={8}>
              <StatCard
                title="入选率"
                value={summary.pick_rate != null ? `${(summary.pick_rate * 100).toFixed(2)}%` : '—'}
                color="#52c41a"
              />
            </Col>
          </Row>
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/BacktestDetail.tsx
git commit -m "feat: BacktestDetail 汇总卡片新增入选总数/基础总股数/入选率"
```

---

### Task 9: 前端 BatchBacktestDetail — 过滤 + 每日统计 + 展开行 + K 线弹窗

**Files:**
- Modify: `frontend/src/pages/BatchBacktestDetail.tsx`

这是最复杂的任务，分多个步骤。

- [ ] **Step 1: 添加 import**

在文件顶部 import 区域添加：

```tsx
import ReactECharts from 'echarts-for-react';
import type { KLineItem } from '@/types/stock';
import { useKLineData } from '@/hooks/useKLineData';
```

- [ ] **Step 2: 创建 `DailyTrackingPanel` 组件**

在 `DailyPanel` 组件之前添加：

```tsx
function DailyTrackingPanel({ ts_code, cutoffDate }: { ts_code: string; cutoffDate: string }) {
  const { data, loading } = useKLineData(ts_code, 180);
  
  if (loading || !data) {
    return <Spin tip="加载中..." style={{ display: 'block', padding: 24 }} />;
  }

  const cutoffDateStr = `${cutoffDate.slice(0, 4)}-${cutoffDate.slice(4, 6)}-${cutoffDate.slice(6, 8)}`;
  const trackedItems = data.items.filter(
    (item: KLineItem) => item.trade_date > cutoffDateStr
  );

  if (trackedItems.length === 0) {
    return <div style={{ color: '#999', padding: 16 }}>暂无后续交易日数据</div>;
  }

  const trackingCols = [
    { title: '日期', dataIndex: 'trade_date', key: 'trade_date', width: 110 },
    { title: '开盘', dataIndex: 'open', key: 'open', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: '收盘', dataIndex: 'close', key: 'close', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: '最高', dataIndex: 'high', key: 'high', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: '最低', dataIndex: 'low', key: 'low', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: '成交量', dataIndex: 'vol', key: 'vol', width: 100, render: (v: number) => (v / 10000).toFixed(0) + '万' },
  ];

  const chartOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 10, bottom: 30 },
    xAxis: {
      type: 'category',
      data: trackedItems.map((d: KLineItem) => d.trade_date.slice(5)),
      axisLabel: { fontSize: 10 },
    },
    yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
    series: [{
      type: 'line',
      data: trackedItems.map((d: KLineItem) => d.close),
      smooth: true,
      lineStyle: { width: 2 },
      itemStyle: { color: '#1677ff' },
    }],
  };

  return (
    <div style={{ padding: 16 }}>
      <Card size="small" title={`每日追踪 — 截止日 ${cutoffDateStr}`} style={{ marginBottom: 12 }}>
        <Table
          dataSource={trackedItems}
          columns={trackingCols}
          rowKey="trade_date"
          pagination={false}
          size="small"
          scroll={{ x: 600 }}
        />
      </Card>
      <ReactECharts option={chartOption} style={{ height: 200 }} />
    </div>
  );
}
```

- [ ] **Step 3: 修改 `DailyPanel` — 添加每日统计行和展开行 + K 线弹窗支持**

修改 `DailyPanel` 组件签名和内容：

```tsx
function DailyPanel({
  result,
  onStockClick,
  selectedStock,
  setSelectedStock,
}: {
  result: DailyResultItem;
  onStockClick: (record: RecommendationItem) => void;
  selectedStock: RecommendationItem | null;
  setSelectedStock: (s: RecommendationItem | null) => void;
}) {
  const isCompleted = result.status === 'completed';
  const isFailed = result.status === 'failed';
  const recs = result.recommendations || [];
  const summary = result.summary as BacktestSummary | null;

  // 每日统计列
  const panelRecColumns = [
    { title: '排名', key: 'index', width: 60, render: (_: unknown, __: unknown, i: number) => i + 1 },
    {
      title: '代码',
      dataIndex: 'ts_code',
      key: 'ts_code',
      width: 110,
      render: (code: string, record: RecommendationItem) => (
        <a onClick={(e) => { e.stopPropagation(); setSelectedStock(record); }}>{code}</a>
      ),
    },
    { title: '名称', dataIndex: 'name', key: 'name', width: 100 },
    { title: '得分', dataIndex: 'score', key: 'score', width: 70 },
    { title: '当日', dataIndex: 'return_0d', key: 'return_0d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
    { title: '3天', dataIndex: 'return_3d', key: 'return_3d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
    { title: '7天', dataIndex: 'return_7d', key: 'return_7d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
    { title: '15天', dataIndex: 'return_15d', key: 'return_15d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
  ];

  return (
    <>
      {isFailed && result.error_message && (
        <Alert type="error" message="执行失败" description={result.error_message} style={{ marginBottom: 12 }} showIcon />
      )}
      {isCompleted && summary && (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={6}>
              <StatCard title="3天平均收益" value={`${(summary.avg_return_3d * 100).toFixed(2)}%`} color="#52c41a" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="7天平均收益" value={`${(summary.avg_return_7d * 100).toFixed(2)}%`} color="#52c41a" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="15天平均收益" value={`${(summary.avg_return_15d * 100).toFixed(2)}%`} color="#52c41a" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="15天胜率" value={`${(summary.win_rate_15d * 100).toFixed(1)}%`} color="#1677ff" />
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={8}>
              <StatCard title="入选总数" value={`${summary.total_qualifying ?? '—'}`} color="#1677ff" />
            </Col>
            <Col xs={12} sm={8}>
              <StatCard title="基础总股数" value={`${summary.base_stock_count ?? '—'}`} color="#722ed1" />
            </Col>
            <Col xs={12} sm={8}>
              <StatCard
                title="入选率"
                value={summary.pick_rate != null ? `${(summary.pick_rate * 100).toFixed(2)}%` : '—'}
                color="#52c41a"
              />
            </Col>
          </Row>
        </>
      )}
      {isCompleted && recs.length > 0 && (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col span={24}>
              <Card size="small" title="持仓期收益对比">
                <ReturnComparisonChart recommendations={recs as RecommendationItem[]} />
              </Card>
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col span={24}>
              <Card size="small" title="胜率分布">
                <WinRateDonutChart summary={summary as BacktestSummary} />
              </Card>
            </Col>
          </Row>
          <Table
            dataSource={recs}
            columns={panelRecColumns}
            rowKey="ts_code"
            pagination={false}
            size="small"
            scroll={{ x: 760 }}
            expandable={{
              expandedRowRender: (record: RecommendationItem) => (
                <DailyTrackingPanel ts_code={record.ts_code} cutoffDate={result.cutoff_date} />
              ),
              rowExpandable: () => true,
            }}
          />
        </>
      )}
      {isCompleted && recs.length === 0 && (
        <div style={{ color: '#999', padding: 16 }}>当日无推荐标的</div>
      )}
    </>
  );
}
```

- [ ] **Step 4: 修改主组件 `BatchBacktestDetail`**

**a) 添加 `selectedStock` 状态**（已存在，约第 101 行，保持不变）

**b) 过滤 `collapseItems`**（约第 138 行），修改为过滤掉空推荐日期：

```tsx
  const collapseItems = dailyResults
    .filter((result: DailyResultItem) =>
      result.status === 'completed' && (result.recommendations?.length || 0) > 0
    )
    .map((result: DailyResultItem) => {
      const dateStr = `${result.cutoff_date.slice(0, 4)}-${result.cutoff_date.slice(4, 6)}-${result.cutoff_date.slice(6, 8)}`;
      const recCount = result.recommendations?.length || 0;
      const avg3d = result.summary && result.status === 'completed'
        ? `${((result.summary as BacktestSummary).avg_return_3d * 100).toFixed(2)}%`
        : null;

      return {
        key: result.cutoff_date,
        label: (
          <Space>
            <span>{dateStr}</span>
            <StatusTag status={result.status} type="backtest" />
            <span style={{ color: '#999' }}>{recCount} 只推荐</span>
            {avg3d !== null && <span style={{ color: parseFloat(avg3d) >= 0 ? '#52c41a' : '#ff4d4f' }}>3d avg: {avg3d}</span>}
          </Space>
        ),
        children: <DailyPanel result={result} onStockClick={setSelectedStock} selectedStock={selectedStock} setSelectedStock={setSelectedStock} />,
      };
    });
```

**c) 添加 `StockKLineModal`**（在 `</>` 结束标签之前，约第 220 行前）：

```tsx
      <StockKLineModal
        ts_code={selectedStock?.ts_code ?? ''}
        name={selectedStock?.name}
        open={!!selectedStock}
        onClose={() => setSelectedStock(null)}
      />
```

**d) 修改每日结果标题**：

```tsx
        <Card title={`每日结果（${collapseItems.length} 天有入选）`}>
```

**e) 修改 `defaultActiveKey`**：过滤空日后可能第一条变了，保留原逻辑：

```tsx
            defaultActiveKey={collapseItems.length > 0 ? [collapseItems[0].key] : []}
```

- [ ] **Step 5: 清理不再需要的 `getRecColumns` 函数**（约第 14 行，已移到 DailyPanel 内部）

删除文件顶部的 `getRecColumns` 函数。

- [ ] **Step 6: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/BatchBacktestDetail.tsx
git commit -m "feat: BatchBacktestDetail 过滤0入选日，新增每日入选统计，StockKLineModal + 展开行每日追踪"
```

---

### Task 10: 端到端验证

- [ ] **Step 1: 启动后端并验证 API**

```bash
cd backend && source venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
```

```bash
# 检查后端正常启动
curl -s http://localhost:8000/api/health 2>&1 || echo "check manually"
```

- [ ] **Step 2: 启动前端**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: 手动验证清单**

- [ ] 打开回测提交页面，确认 4 个板块复选框默认全选
- [ ] 取消所有复选框，确认无法取消最后一个（至少选一个）
- [ ] 提交一个简单回测，确认 config 中包含 `board_filter`
- [ ] 查看回测报告详情页，确认显示入选总数 / 基础总股数 / 入选率
- [ ] 提交一个批量回测，确认只展示有入选的日期
- [ ] 批量回测每日面板确认显示入选统计
- [ ] 点击股票代码，确认弹出 K 线弹窗
- [ ] 点击 `+` 展开行，确认显示每日追踪表 + 折线图

- [ ] **Step 4: 运行现有测试确保无回归**

```bash
cd backend && source venv/bin/activate && pytest tests/ -x -q 2>&1 | tail -20
cd frontend && npm run build 2>&1 | tail -5
```

---

## 实施顺序

```
Task 1 (Schema)  →  Task 2 (Helper)  →  Task 3 (run)  →  Task 4 (run_batch)
                                          ↘
                                            Task 5 (trade_sim)
Task 6 (Types)   →  Task 7 (Form)   →  Task 8 (Detail)  →  Task 9 (Batch)
                                                              ↓
                                                         Task 10 (验证)
```

Task 1-5（后端）和 Task 6（类型）可并行。Task 7-9（前端页面）依赖 Task 6。
