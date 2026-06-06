# 板块涨跌幅分布图设计

## 需求

市场热度 → 涨跌比弹窗 → 涨跌幅分布图上方新增板块标签（全部/上证/深圳/科创/创业），切换后显示对应板块的个股涨跌幅分布。

## 后端

### API：`GET /market-heat/change-distribution`

新增可选参数 `board`（`Optional[str]`）：

| board 值 | 含义 | ts_code 正则 |
|----------|------|-------------|
| 不传 | 全市场 | 无过滤 |
| `sh_main` | 上证主板 | `^[56]0[0-5]` |
| `sz_main` | 深证主板 | `^00[0-3]` |
| `sh_star` | 科创板 | `^688` |
| `sz_chi` | 创业板 | `^30[01]` |

Service 层：在现有 8 区间 COUNT 查询的 WHERE 子句中，当 `board` 不为空时追加 `Daily.ts_code ~ '<pattern>'` 条件。复用已有 `BOARD_DEFINITIONS`。

## 前端

### `marketHeatService.ts`

`getChangeDistribution(tradeDate?, board?)` — 增加可选 `board` 参数，以 query param 传递。

### `KpiDetailModal.tsx`

- 分布图上方新增 `Segmented` 组件（Ant Design）：`全部 | 上证 | 深圳 | 科创 | 创业`
- 默认选中"全部"，切换时重新调用 API
- 前端 `board` → 后端参数映射：

```ts
const BOARD_MAP: Record<string, string | undefined> = {
  '全部': undefined,
  '上证': 'sh_main',
  '深圳': 'sz_main',
  '科创': 'sh_star',
  '创业': 'sz_chi',
};
```

- 新增 `board` state，`useEffect` 中依赖 `board` 变化触发请求
- 切换板块时显示 loading 状态

## 不涉及

- TemperatureCard 涨跌比 KPI 不变
- 其他页面无影响
