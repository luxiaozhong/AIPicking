# Stock Search & Auto-Complete Spec

> Status: Draft (2026-05-28)
> Target: Replace manual ts_code input with search-based stock lookup across all backtest forms

---

## 1. Overview

Currently, users must input exact `ts_code` with exchange suffix (e.g., `300328.SZ`) in all backtest forms. This is unfriendly — users think in terms of stock codes without suffixes (`300328`) or stock names (`平安银行`), not internal `ts_code` identifiers.

This feature adds a **stock search API** that queries the external `stocks` table, and **replaces all plain text inputs with auto-complete fields** so users can type a code or name and pick from matching results. The resolved `ts_code` is then passed to existing backtest APIs — no changes to those APIs.

### Flow

```
User types "300328" or "平安"
  → AutoComplete calls GET /api/v1/stocks/search?q=...
  → Dropdown shows matching stocks (code + name + market)
  → User selects one
  → Form stores the resolved ts_code (e.g. "300328.SZ")
  → Existing backtest APIs receive ts_code as before
```

---

## 2. Stock Search API

### 2.1 New endpoint

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/stocks/search` | Yes | Search stocks by code or name |

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | string | required | Search keyword (stock code or name) |
| `limit` | int | 10 | Max results (1–50) |

**Response format** (follows app envelope convention):

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "ts_code": "000001.SZ",
        "symbol": "sz000001",
        "name": "平安银行",
        "market": "SZ"
      }
    ],
    "total": 1
  }
}
```

### 2.2 Search logic

Search is performed against the external SQLite database (`STOCK_DB_PATH`) `stocks` table.

```
SELECT ts_code, symbol, name, market
FROM stocks
WHERE ts_code LIKE ? OR name LIKE ?
ORDER BY
  CASE
    WHEN ts_code = ? THEN 0           -- exact ts_code match
    WHEN name = ? THEN 1              -- exact name match
    WHEN ts_code LIKE ? THEN 2        -- prefix match (e.g. "000001" matches "000001.SZ")
    ELSE 3
  END,
  ts_code
LIMIT ?
```

Parameter bindings:
- `%{q}%` for LIKE clauses
- Raw `q` for exact match clauses (for ranking)
- `{q}%` for ts_code prefix match (e.g. typing "000" matches "000001.SZ", "000002.SZ", etc.)

All matching is **case-insensitive** (SQLite `LIKE` is already case-insensitive for ASCII).

### 2.3 Connection management

The external SQLite database is read-only for this use case. The service opens a short-lived connection per request using `sqlite3.connect(STOCK_DB_PATH)` with `check_same_thread=False`. No connection pooling needed — the query is a simple indexed lookup.

An index on `stocks(name)` should be verified; if missing, create one.

---

## 3. Backend Implementation

### 3.1 New files

| File | Purpose |
|------|---------|
| `backend/app/services/stock_service.py` | `StockService.search(q, limit)` — queries external DB |
| `backend/app/api/stocks.py` | `GET /api/v1/stocks/search` router |
| `backend/app/schemas/stock.py` | `StockItem`, `StockSearchResponse` Pydantic models |

### 3.2 Modified files

| File | Change |
|------|--------|
| `backend/app/main.py` | Register `stocks` router |
| `backend/app/config.py` | Ensure `STOCK_DB_PATH` is accessible from the stock service (already defined, verify import) |

### 3.3 StockService pseudocode

```python
import sqlite3
from app.config import settings

class StockService:
    @staticmethod
    def search(q: str, limit: int = 10) -> dict:
        conn = sqlite3.connect(settings.STOCK_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT ts_code, symbol, name, market
            FROM stocks
            WHERE ts_code LIKE ? OR name LIKE ?
            ORDER BY
              CASE
                WHEN ts_code = ? THEN 0
                WHEN name = ? THEN 1
                WHEN ts_code LIKE ? THEN 2
                ELSE 3
              END,
              ts_code
            LIMIT ?
            """,
            (f"%{q}%", f"%{q}%", q, q, f"{q}%", limit)
        )
        rows = cursor.fetchall()
        conn.close()
        return {
            "items": [dict(r) for r in rows],
            "total": len(rows)
        }
```

---

## 4. Frontend Changes

### 4.1 New components / services

| File | Purpose |
|------|---------|
| `frontend/src/services/stockService.ts` | `searchStocks(q)` → calls `GET /api/v1/stocks/search` |
| `frontend/src/types/stock.ts` | `StockItem` interface |

### 4.2 Modified pages

**All places where users currently type a ts_code:**

| Page | Current Component | Change |
|------|------------------|--------|
| `BacktestForm.tsx` | `<Input>` (line 195) | Replace with `<AutoComplete>` |
| `StrategyDetail.tsx` | `<Input>` (line 155) | Replace with `<AutoComplete>` |

### 4.3 AutoComplete behavior

- **Debounce**: 300ms after last keystroke before calling search API
- **Min input length**: 1 character (single char triggers search)
- **Loading state**: Show `<Spin>` indicator in dropdown while fetching
- **Empty state**: Show "未找到匹配的股票" when results are empty
- **Option format**: Each dropdown item shows `{ts_code}  {name}` (e.g., `000001.SZ  平安银行`)
- **On select**: Store the selected `ts_code` in form state; display the selected label in the input
- **On clear**: Reset to empty (full market scan mode unchanged)
- **Value persistence**: The selected label is displayed in the input, but the `ts_code` value is what gets submitted in the form payload

### 4.4 AutoComplete implementation sketch (BacktestForm.tsx)

```tsx
import { AutoComplete, Spin } from 'antd';
import { useState, useCallback, useRef } from 'react';
import stockService from '@/services/stockService';
import type { StockItem } from '@/types/stock';

// Inside component:
const [stockOptions, setStockOptions] = useState<{value: string; label: ReactNode}[]>([]);
const [stockSearching, setStockSearching] = useState(false);
const debounceRef = useRef<ReturnType<typeof setTimeout>>();

const handleStockSearch = useCallback((keyword: string) => {
  if (!keyword) {
    setStockOptions([]);
    return;
  }
  if (debounceRef.current) clearTimeout(debounceRef.current);
  debounceRef.current = setTimeout(async () => {
    setStockSearching(true);
    try {
      const items = await stockService.search(keyword);
      setStockOptions(items.map((s: StockItem) => ({
        value: s.ts_code,
        label: <span>{s.ts_code}  <Text type="secondary">{s.name}</Text></span>,
      })));
    } catch {
      setStockOptions([]);
    } finally {
      setStockSearching(false);
    }
  }, 300);
}, []);

// Replace <Input> with:
<AutoComplete
  value={stockCode}
  options={stockOptions}
  onSearch={handleStockSearch}
  onSelect={(value: string) => setStockCode(value)}
  onChange={(value: string) => setStockCode(value)}  // allow free typing
  placeholder="输入股票代码或名称搜索（留空则全市场选股）"
  allowClear
  notFoundContent={stockSearching ? <Spin size="small" /> : null}
  style={{ width: '100%' }}
/>
```

Key behaviors:
- `onSelect` fires when user clicks a dropdown option → sets `ts_code`
- `onChange` allows free typing (user can still type a raw `ts_code` if they want)
- `allowClear` resets to empty for full-market scan mode
- User can still manually type a complete `ts_code` (e.g., `300328.SZ`) and submit without selecting from dropdown — the existing APIs accept it directly

### 4.5 No changes to existing APIs

All backtest APIs (`POST /backtests`, `POST /backtests/execute/{id}`, `POST /backtests/batch`) continue to accept `ts_code` in their current format. The resolved `ts_code` flows through the same `config.ts_code` path as before.

---

## 5. Implementation File Map

### Backend (new)
- `backend/app/schemas/stock.py` — `StockItem`, `StockSearchResponse`
- `backend/app/services/stock_service.py` — `StockService.search()`
- `backend/app/api/stocks.py` — `GET /api/v1/stocks/search`

### Backend (modified)
- `backend/app/main.py` — Register `stocks` router (2 lines)

### Frontend (new)
- `frontend/src/types/stock.ts` — `StockItem` interface
- `frontend/src/services/stockService.ts` — `searchStocks(q)` API call

### Frontend (modified)
- `frontend/src/pages/BacktestForm.tsx` — Replace `<Input>` with `<AutoComplete>`, add `handleStockSearch`
- `frontend/src/pages/StrategyDetail.tsx` — Same `<AutoComplete>` replacement

### Optional / verification
- Verify `stocks(name)` index exists in external SQLite DB for query performance
- If STOCK_DB_PATH is not currently reachable from the FastAPI process (different from BacktestEngine's direct usage), confirm the env var is set

---

## 6. Edge Cases & Behavior

| Scenario | Behavior |
|----------|----------|
| User types "000001" | Dropdown shows "000001.SZ  平安银行" and any other ts_codes containing "000001" |
| User types "平安" | Dropdown shows all stocks with "平安" in name, top match first |
| User types "000001.SZ" directly | Dropdown still works; user can select or just tab away (the raw value is already a valid ts_code) |
| User types gibberish | Dropdown shows "未找到匹配的股票" (or empty). User can still submit — the engine will simply return empty results (existing behavior) |
| User clears input | Full market scan mode (same as existing behavior when field is empty) |
| External DB unavailable | API returns 500; frontend catches error and shows empty dropdown. Existing backtest APIs unaffected. |
| Multiple stocks with same name prefix | Both appear in dropdown, ranked by match quality. User picks the correct one. |

---

## 7. Known Limitations & Future Work

- Search is limited to `stocks` table — does not cover funds, bonds, or other security types
- No recent/frequent stock suggestions (no user preference tracking)
- The external SQLite DB is opened per-request (simple, no connection pooling). If search becomes high-frequency, consider a shared read-only connection or in-memory cache
- No paging on search results (limit=10 is sufficient for auto-complete)
- Stock name index on external DB should be verified; without it, `LIKE %name%` does a full table scan on ~5000 rows (acceptable for now)
