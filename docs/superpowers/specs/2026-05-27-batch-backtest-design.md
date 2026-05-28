# Batch Backtest Design

## Overview

Extend backtesting from single-day to multi-day period execution. User selects a date range, backend runs the strategy for every trading day in that range, stores daily results in a single batch report. No aggregation needed.

## Data Model

New `BatchBacktestReport` table (separate from existing `BacktestReport`):

| Column | Type | Notes |
|--------|------|-------|
| `id` | int PK | auto-increment |
| `strategy_id` | FK → strategies | |
| `user_id` | int | |
| `name` | varchar(100) | optional, user-defined label |
| `start_date` | varchar(8) | YYYYMMDD |
| `end_date` | varchar(8) | YYYYMMDD |
| `track_days` | JSON | e.g. `[3, 7, 15]` |
| `config` | JSON | strategy config (e.g. `{"ts_code": null}`) |
| `total_days` | int | total trading days in range |
| `completed_days` | int | days processed so far |
| `daily_results` | JSON | array of daily results (see below) |
| `status` | enum | pending / running / completed / failed |
| `error_message` | text | top-level error if entire batch fails |
| `created_at` | datetime | |
| `updated_at` | datetime | |
| `completed_at` | datetime | |

**daily_results JSON structure — each entry stores only metadata, not raw market data:**

```json
[
  {
    "cutoff_date": "20260515",
    "status": "completed",
    "input": {
      "cutoff_date": "20260515",
      "config": {}
    },
    "recommendations": [
      {
        "ts_code": "000001.SZ",
        "name": "平安银行",
        "reason": "...",
        "return_0d": 0.012,
        "return_3d": 0.035,
        "return_7d": null,
        "return_15d": null
      }
    ],
    "summary": {
      "avg_return_3d": 0.028,
      "win_rate_3d": 0.6,
      "avg_return_7d": null,
      "win_rate_7d": null,
      "avg_return_15d": null,
      "win_rate_15d": null,
      "best_return_15d": null,
      "worst_return_15d": null
    }
  }
]
```

- `input` stores only `cutoff_date` + `config`, not raw market data (can be re-queried from source DB)
- `return_*d` is `null` when tracking data not yet available
- Failed days set `status: "failed"` with an `error` field, don't block remaining days

## Engine Design

### Core change: load once, slice per day

Instead of loading data per-cutoff-date, load the full range once then filter per day:

```
_load_data(earliest_date = start_date - 180 days, latest_date = end_date)
  → all stocks, daily, sector_flow in memory

for each trading_day in distinct trade_dates between start_date..end_date:
    daily_slice = filter(daily, trade_date <= trading_day)
    input = { cutoff_date: trading_day, stocks, daily: daily_slice, sector_flow, config }
    recommendations = strategy_func(input)
    _track_performance(recommendations, trading_day)
    append daily_result
```

### New method on BacktestEngine

`run_batch(start_date, end_date, track_days)` — iterates trading days, calls strategy, tracks performance per day. Returns list of daily results.

### Trading day list

Derived from `daily` table: `SELECT DISTINCT trade_date FROM daily WHERE trade_date BETWEEN start_date AND end_date ORDER BY trade_date`. No external calendar dependency.

### Error handling

Single-day failure records `status: "failed"` + `error` in that day's result, then continues to next day. Only set top-level status to `failed` if _every_ day fails or an unrecoverable error occurs (e.g. DB connection lost).

## API Design

Base path: `/api/v1/backtests/batch`

| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/batch` | Create batch backtest, returns 202 |
| `GET` | `/batch` | List batch reports (paginated, filterable by strategy_id) |
| `GET` | `/batch/{id}` | Get single batch report with daily_results |
| `DELETE` | `/batch/{id}` | Delete batch report, returns 204 |

### POST /batch body

```json
{
  "strategy_id": 1,
  "start_date": "20260401",
  "end_date": "20260501",
  "track_days": [3, 7, 15],
  "name": "4月回测",
  "config": {}
}
```

### GET /batch response (list)

Returns batch reports without `daily_results` (too large for list view). Each item includes: id, strategy_id, name, start_date, end_date, status, total_days, completed_days, created_at.

### GET /batch/{id} response

Full report including `daily_results` array.

### Execution model

Same as single-day: POST creates DB record with `status=pending`, `asyncio.create_task` runs `BacktestService._run_batch_backtest()`. After each trading day, update `completed_days` and append to `daily_results`. On completion set `status=completed`.

## Frontend Design

### BacktestForm.tsx — add batch mode

Add a mode toggle (single / batch) at the top of the form:

- **Batch mode**: Date picker becomes `RangePicker` (Ant Design). Optional `name` text input. Track_days and config fields unchanged.
- **Single mode**: Existing behavior unchanged.

On submit, batch mode POSTs to `/batch`, single mode POSTs to `/`.

### BatchBacktestList.tsx — new page

Table of batch reports:

| Column | Content |
|--------|---------|
| Name | user-defined name or auto-generated |
| Strategy | strategy name |
| Date Range | start_date ~ end_date |
| Status | status tag |
| Progress | completed_days / total_days |
| Created | created_at |
| Actions | view / delete |

Filter: by strategy. Pagination: yes.

Route: `/backtests/batch`

### BatchBacktestDetail.tsx — new page

Top section: strategy name, date range, status, progress bar.

Main section: `Collapse` (Ant Design) of daily results, newest first. Each panel:
- Header: date, status tag, recommendation count, avg_return_3d
- Body: recommendations table + summary (reuse existing chart components like `ReturnComparisonChart`, `WinRateDonutChart`)

Default: newest day expanded, rest collapsed.

Polling: refresh every 3s while `status in ['pending', 'running']`.

Null returns displayed as `—`.

Route: `/backtests/batch/:id`

### Sidebar navigation

Add "批量回测" entry under the backtesting section.

## Data Source

External SQLite database at hardcoded path (`STOCK_DB_PATH` in `backtest_engine.py`). The same source database as single-day backtesting — stocks, daily, sector_flow tables.

No new data sources. No changes to data loading logic except the date range extension.
