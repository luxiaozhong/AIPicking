# StockSearchLookup Shared Component

**Date:** 2026-05-30
**Context:** Idea #16 — 四个页面复制了相同的股票搜索样板代码，抽成 shared 组件

## Problem

`BacktestForm`, `StrategyDetail`, `AIStrategyBuilder`, `BacktestList` 四个页面各自实现了相同的股票搜索逻辑（~25 行/页）：

- 3 个 state：`stockCode`, `stockOptions`, `stockSearching`
- 1 个 ref：`debounceRef`
- 1 个 callback：`handleStockSearch`（300ms 防抖 → `stockService.search()` → 映射 options）
- 1 个 AutoComplete JSX（value/options/onSearch/onSelect/onChange/placeholder/allowClear/notFoundContent）

## Design

### New Component: `StockSearchLookup`

**File:** `frontend/src/components/shared/StockSearchLookup.tsx`

**Props:**

| Prop | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `value` | `string` | Yes | — | Current stock code |
| `onChange` | `(code: string) => void` | Yes | — | Called on select or input change |
| `placeholder` | `string` | No | `"输入股票代码或名称搜索"` | Placeholder text |
| `style` | `React.CSSProperties` | No | `undefined` | Outer style |

**Internal behavior (encapsulated, not exposed to parent):**
- 300ms debounced search via `stockService.search(keyword)`
- Loading spinner in `notFoundContent` while searching
- Option format: `{value: s.ts_code, label: <ts_code + name>}`
- Cleanup debounce timer on unmount
- Empty keyword → clear options immediately

**Imports from parents (removed after refactor):**
- `stockService` — parents no longer import it for search
- `StockItem` type — parents no longer need it for search
- `useRef` — parents no longer need debounce ref

### Pages Changed

All four pages replace their inline stock search code with:

```tsx
<StockSearchLookup
  value={stockCode}
  onChange={setStockCode}
  placeholder="..."  // page-specific
/>
```

| Page | Lines Removed | Placeholder |
|------|---------------|-------------|
| `BacktestForm.tsx` | ~30 | `"输入股票代码或名称搜索（留空则全市场选股）"` |
| `StrategyDetail.tsx` | ~50 (two instances) | `"股票代码（可选）"` / `"输入股票代码或名称搜索（留空则全市场扫描）"` |
| `AIStrategyBuilder.tsx` | ~30 | `"输入股票代码或名称搜索"` |
| `BacktestList.tsx` | ~30 | `"搜索股票代码或名称"` |

### What Does NOT Change

- `stockService.search()` — stays as-is, called from within the component
- `StockItem` type — stays as-is, used by the component
- Page-level business logic — only the search UI is replaced
- `BacktestList` still has its own `doSearch` function; `onChange` sets `stockSearch` state, and the search button calls `doSearch(stockSearch)`

### Dependencies

- `antd` (`AutoComplete`, `Spin`)
- `@/services/stockService`
- `@/types/stock`

### Testing

- Manual verification: each page's stock search still works (type → debounce → dropdown → select)
- Existing Playwright E2E tests should continue to pass
