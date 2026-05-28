# Batch Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend backtesting from single-day to multi-day period execution with a dedicated batch report model and UI.

**Architecture:** New `BatchBacktestReport` model with embedded `daily_results` JSON. Engine loads data once for the full date range, slices per trading day. Separate API routes under `/api/v1/backtests/batch`. New frontend pages for batch list and detail.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + TypeScript + Ant Design + Zustand (frontend)

---

### Task 1: Add BatchBacktestReport model

**Files:**
- Modify: `backend/app/models/backtest.py` (append new model)
- Modify: `backend/app/models/__init__.py` (export new model)

- [ ] **Step 1: Add BatchBacktestReport model class**

```python
class BatchBacktestReport(BaseModel):
    """批量回测报告模型

    一次批量回测覆盖多个交易日，每天独立运行策略并追踪表现。
    daily_results 存储每日结果数组。
    """

    __tablename__ = "batch_backtest_reports"

    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255))
    status = Column(String(50), default="pending", index=True)
    start_date = Column(String(8), nullable=False)
    end_date = Column(String(8), nullable=False)
    config = Column(Text)  # JSON: track_days, strategy config
    total_days = Column(Integer, default=0)
    completed_days = Column(Integer, default=0)
    daily_results = Column(Text)  # JSON 数组，每条一个交易日的结果
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    strategy = relationship("Strategy", back_populates="batch_backtest_reports")
    owner = relationship("User", back_populates="batch_backtest_reports")

    @property
    def strategy_name(self) -> str:
        return self.strategy.name if self.strategy else None
```

Open `backend/app/models/backtest.py` and append the above class after the existing `StrategyRun` class. Also add the `batch_backtest_reports` relationship to `Strategy` and `User` models:

In `backend/app/models/strategy.py`, add to the `Strategy` class:
```python
batch_backtest_reports = relationship("BatchBacktestReport", back_populates="strategy")
```

In `backend/app/models/user.py`, add to the `User` class:
```python
batch_backtest_reports = relationship("BatchBacktestReport", back_populates="owner")
```

- [ ] **Step 2: Export BatchBacktestReport from models __init__**

Open `backend/app/models/__init__.py`, add `BatchBacktestReport` to the imports.

- [ ] **Step 3: Run migration**

The app uses `init_db()` on startup which creates tables. If there's an explicit migration step, run it. Otherwise the table will be created on next startup.

- [ ] **Step 4: Run tests to verify model loads**

```bash
cd backend && python -c "from app.models import BatchBacktestReport; print('OK')"
```

Expected: `OK` printed, no import error.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/backtest.py backend/app/models/__init__.py backend/app/models/strategy.py backend/app/models/user.py
git commit -m "feat: add BatchBacktestReport model"
```

---

### Task 2: Add batch backtest Pydantic schemas

**Files:**
- Modify: `backend/app/schemas/backtest.py` (append batch schemas)

- [ ] **Step 1: Add batch schemas to backtest.py**

```python
class BatchBacktestCreate(BaseModel):
    """批量回测创建请求"""
    strategy_id: int = Field(..., description="策略 ID")
    start_date: str = Field(..., description="起始日期，格式 YYYYMMDD")
    end_date: str = Field(..., description="结束日期，格式 YYYYMMDD")
    track_days: List[int] = Field([3, 7, 15], description="追踪天数")
    name: Optional[str] = Field(None, description="批量回测名称")
    config: Optional[dict] = Field(None, description="策略自定义配置")


class DailyResultItem(BaseModel):
    """单日回测结果"""
    cutoff_date: str
    status: str
    input: Optional[dict] = None
    recommendations: Optional[List[RecommendationItem]] = None
    summary: Optional[BacktestSummary] = None
    error: Optional[str] = None


class BatchBacktestResponse(BaseModel):
    """批量回测响应"""
    id: int
    strategy_id: int
    strategy_name: Optional[str] = None
    name: Optional[str] = None
    status: str = "pending"
    start_date: str
    end_date: str
    config: Optional[dict] = None
    total_days: int = 0
    completed_days: int = 0
    daily_results: Optional[List[DailyResultItem]] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @field_validator('config', 'daily_results', mode='before')
    @classmethod
    def parse_json_fields(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v

    class Config:
        from_attributes = True


class BatchBacktestListResponse(BaseModel):
    """批量回测列表响应（不含 daily_results）"""
    items: list[BatchBacktestResponse]
    total: int
    page: int = 1
    limit: int = 20
```

Append these classes after the existing `StrategyExecuteResponse` class in `backend/app/schemas/backtest.py`.

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/backtest.py
git commit -m "feat: add batch backtest Pydantic schemas"
```

---

### Task 3: Add run_batch() to BacktestEngine

**Files:**
- Modify: `backend/app/services/backtest_engine.py`

- [ ] **Step 1: Add `run_batch()` method to `BacktestEngine`**

After the existing `run()` method (after line 255), add:

```python
    def run_batch(
        self,
        start_date: str,
        end_date: str,
        track_days: List[int] = [3, 7, 15]
    ) -> List[Dict[str, Any]]:
        """
        执行批量回测

        参数:
            start_date: 起始日期，格式 YYYYMMDD
            end_date: 结束日期，格式 YYYYMMDD
            track_days: 追踪天数列表

        返回:
            list[dict]，每天一条结果：
            {
                "cutoff_date": "20260515",
                "status": "completed",
                "input": {...},
                "recommendations": [...],
                "summary": {...}
            }
        """
        # 1. 加载全时段数据
        stocks_data, daily_data, sector_flow_data = self._load_data_range(start_date, end_date)

        # 2. 获取日期范围内的所有交易日
        trading_days = sorted(set(
            row["trade_date"] for rows in daily_data.values() for row in rows
            if start_date <= row["trade_date"] <= end_date
        ))

        ts_code = (self.config or {}).get("ts_code", "").strip()
        results = []

        for cutoff_date in trading_days:
            daily_result = {
                "cutoff_date": cutoff_date,
                "input": {"cutoff_date": cutoff_date, "config": self.config or {}},
            }

            try:
                # 裁剪 daily 到 cutoff_date 及之前
                sliced_daily = {}
                for code, rows in daily_data.items():
                    sliced_rows = [r for r in rows if r["trade_date"] <= cutoff_date]
                    if sliced_rows:
                        sliced_daily[code] = sliced_rows

                # 如果指定了 ts_code，只保留该股票
                if ts_code:
                    sliced_daily = {ts_code: sliced_daily[ts_code]} if ts_code in sliced_daily else {}

                strategy_input = {
                    "cutoff_date": cutoff_date,
                    "stocks": stocks_data,
                    "daily": sliced_daily,
                    "sector_flow": sector_flow_data,
                    "config": self.config or {},
                }

                recommendations = self.strategy_func(strategy_input)
                if not recommendations or not isinstance(recommendations, list):
                    recommendations = []

                recommendations = recommendations[:MAX_RECOMMENDATIONS]
                recommendations = self._track_performance(recommendations, cutoff_date, track_days)
                summary = self._calculate_summary(recommendations, track_days)

                daily_result["status"] = "completed"
                daily_result["recommendations"] = recommendations
                daily_result["summary"] = summary

            except Exception as e:
                daily_result["status"] = "failed"
                daily_result["error"] = str(e)

            results.append(daily_result)

        return results
```

- [ ] **Step 2: Add `_load_data_range()` helper to `BacktestEngine`**

After the `_load_data()` method (after line 334), add:

```python
    def _load_data_range(self, start_date: str, end_date: str) -> Tuple[List[Dict], Dict[str, List[Dict]], List[Dict]]:
        """
        加载全时段历史数据（用于批量回测）

        加载 start_date - 180 天到 end_date 的完整数据，后续按天切片。

        返回:
            (stocks_data, daily_data, sector_flow_data)
        """
        conn = sqlite3.connect(STOCK_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1. 加载股票基础信息
        cur.execute("""
            SELECT ts_code, symbol, name, market,
                   industry_l1, industry_l2, industry_l3,
                   concepts, total_shares, float_shares
            FROM stocks
            WHERE ts_code IS NOT NULL AND ts_code != ''
        """)
        stocks_data = [dict(row) for row in cur.fetchall()]

        # 2. 计算数据起始日
        start_dt = datetime.strptime(start_date, "%Y%m%d")
        earliest_dt = start_dt - timedelta(days=180)
        earliest_date = earliest_dt.strftime("%Y%m%d")

        flow_start_dt = datetime.strptime(start_date, "%Y%m%d")
        flow_earliest_dt = flow_start_dt - timedelta(days=30)
        flow_earliest_date = flow_earliest_dt.strftime("%Y%m%d")

        # 3. 加载日线数据（从 earliest 到 end_date）
        cur.execute(f"""
            SELECT ts_code, trade_date, open, high, low, close,
                   vol, amount, adj_close, market_cap, circ_market_cap
            FROM daily
            WHERE trade_date BETWEEN '{earliest_date}' AND '{end_date}'
            ORDER BY ts_code, trade_date
        """)
        daily_rows = cur.fetchall()

        # 4. 加载板块资金流向
        cur.execute(f"""
            SELECT trade_date, sector_code, sector_name, sector_type,
                   change_pct, main_inflow, main_inflow_pct,
                   retail_inflow, retail_inflow_pct,
                   net_inflow, big_order_inflow, big_order_inflow_pct,
                   mid_order_inflow, mid_order_inflow_pct
            FROM sector_flow
            WHERE trade_date BETWEEN '{flow_earliest_date}' AND '{end_date}'
            ORDER BY trade_date, sector_type, sector_name
        """)
        sector_flow_data = [dict(row) for row in cur.fetchall()]

        conn.close()

        # 5. 按 ts_code 分组
        daily_data = {}
        for row in daily_rows:
            ts_code = row['ts_code']
            if ts_code not in daily_data:
                daily_data[ts_code] = []
            daily_data[ts_code].append({
                "trade_date": row['trade_date'],
                "open": row['open'],
                "high": row['high'],
                "low": row['low'],
                "close": row['close'],
                "vol": row['vol'],
                "amount": row['amount'],
                "adj_close": row['adj_close'],
                "market_cap": row['market_cap'],
                "circ_market_cap": row['circ_market_cap'],
            })

        return stocks_data, daily_data, sector_flow_data
```

- [ ] **Step 3: Verify method exists**

```bash
cd backend && python -c "from app.services.backtest_engine import BacktestEngine; e = BacktestEngine('def run(data): return []', {}); print(hasattr(e, 'run_batch'))"
```

Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/backtest_engine.py
git commit -m "feat: add run_batch and _load_data_range to BacktestEngine"
```

---

### Task 4: Add batch methods to BacktestService

**Files:**
- Modify: `backend/app/services/backtest_service.py`

- [ ] **Step 1: Add `create_batch_backtest` method**

Append to `BacktestService` class:

```python
    @staticmethod
    async def create_batch_backtest(
        db: AsyncSession,
        backtest: "BatchBacktestCreate",
        user_id: Optional[int] = None,
    ) -> "BatchBacktestReport":
        from ..schemas.backtest import BatchBacktestCreate
        from ..models.backtest import BatchBacktestReport

        strategy_result = await db.execute(
            select(Strategy).where(Strategy.id == backtest.strategy_id)
        )
        strategy = strategy_result.scalar_one_or_none()

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy with id {backtest.strategy_id} not found"
            )

        config_dict = backtest.config or {}
        config_dict["track_days"] = backtest.track_days

        db_backtest = BatchBacktestReport(
            strategy_id=backtest.strategy_id,
            user_id=user_id,
            name=backtest.name or f"{strategy.name}_{backtest.start_date}_{backtest.end_date}",
            status="pending",
            start_date=backtest.start_date,
            end_date=backtest.end_date,
            config=json.dumps(config_dict, ensure_ascii=False),
        )

        db.add(db_backtest)
        await db.commit()
        await db.refresh(db_backtest)

        db_backtest.strategy = strategy

        asyncio.create_task(
            BacktestService._run_batch_backtest(
                db_backtest.id,
                backtest.start_date,
                backtest.end_date,
                backtest.track_days,
            )
        )

        return db_backtest
```

Add the import at the top of the file:
```python
from ..models import BacktestReport, Strategy, BatchBacktestReport
```

- [ ] **Step 2: Add batch list, get, delete methods**

```python
    @staticmethod
    async def get_batch_backtests(
        db: AsyncSession,
        page: int = 1,
        limit: int = 20,
        strategy_id: Optional[int] = None,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> Tuple[List["BatchBacktestReport"], int]:
        query = select(BatchBacktestReport).options(selectinload(BatchBacktestReport.strategy))

        if strategy_id:
            query = query.where(BatchBacktestReport.strategy_id == strategy_id)
        if user_role != "admin":
            query = query.where(BatchBacktestReport.user_id == user_id)

        count_query = select(func.count()).select_from(BatchBacktestReport)
        if strategy_id:
            count_query = count_query.where(BatchBacktestReport.strategy_id == strategy_id)
        if user_role != "admin":
            count_query = count_query.where(BatchBacktestReport.user_id == user_id)
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit).order_by(BatchBacktestReport.created_at.desc())

        result = await db.execute(query)
        return result.scalars().all(), total

    @staticmethod
    async def get_batch_backtest(
        db: AsyncSession,
        backtest_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> "BatchBacktestReport":
        result = await db.execute(
            select(BatchBacktestReport)
            .options(selectinload(BatchBacktestReport.strategy))
            .where(BatchBacktestReport.id == backtest_id)
        )
        backtest = result.scalar_one_or_none()

        if not backtest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Batch backtest with id {backtest_id} not found"
            )

        if user_role != "admin" and backtest.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此回测报告"
            )

        return backtest

    @staticmethod
    async def delete_batch_backtest(
        db: AsyncSession,
        backtest_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> None:
        backtest = await BacktestService.get_batch_backtest(db, backtest_id, user_id, user_role)
        await db.delete(backtest)
        await db.commit()
```

- [ ] **Step 3: Add `_run_batch_backtest` async background task**

```python
    @staticmethod
    async def _run_batch_backtest(
        backtest_id: int,
        start_date: str,
        end_date: str,
        track_days: List[int],
    ):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from ..config import settings

        engine = create_engine(settings.DATABASE_URL.replace("+aiosqlite", ""))
        Session = sessionmaker(bind=engine)

        with Session() as db:
            try:
                backtest = db.query(BatchBacktestReport).filter(BatchBacktestReport.id == backtest_id).first()
                if not backtest:
                    return

                backtest.status = "running"
                backtest.started_at = beijing_now()
                db.commit()

                strategy = db.query(Strategy).filter(Strategy.id == backtest.strategy_id).first()
                if not strategy:
                    raise ValueError(f"Strategy {backtest.strategy_id} not found")

                strategy_code = BacktestService._get_strategy_code(strategy)

                config = json.loads(backtest.config) if backtest.config else {}
                strategy_config = {k: v for k, v in config.items() if k != "track_days"}
                engine_obj = BacktestEngine(
                    strategy_code=strategy_code,
                    strategy_params={},
                    config=strategy_config,
                )

                daily_results = engine_obj.run_batch(start_date, end_date, track_days)

                backtest.total_days = len(daily_results)
                backtest.completed_days = len([r for r in daily_results if r["status"] == "completed"])
                backtest.daily_results = json.dumps(daily_results, ensure_ascii=False, cls=NumpyEncoder)

                # If every day failed, mark batch as failed; otherwise completed
                if backtest.completed_days == 0 and backtest.total_days > 0:
                    backtest.status = "failed"
                    backtest.error_message = "所有交易日执行均失败"
                else:
                    backtest.status = "completed"

                backtest.completed_at = beijing_now()
                db.commit()

            except Exception as e:
                db.rollback()
                backtest = db.query(BatchBacktestReport).filter(BatchBacktestReport.id == backtest_id).first()
                if backtest:
                    backtest.status = "failed"
                    backtest.error_message = str(e)
                    backtest.completed_at = beijing_now()
                    db.commit()
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/backtest_service.py
git commit -m "feat: add batch backtest service methods"
```

---

### Task 5: Add batch API routes

**Files:**
- Create: `backend/app/api/batch_backtests.py`

- [ ] **Step 1: Create batch_backtests.py router**

```python
"""批量回测 API 路由"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.backtest_service import BacktestService
from ..schemas.backtest import (
    BatchBacktestCreate, BatchBacktestResponse, BatchBacktestListResponse,
)
from ..middleware.auth import get_current_user
from ..models.user import User

router = APIRouter()


@router.post("", response_model=BatchBacktestResponse, status_code=202)
async def create_batch_backtest(
    backtest: BatchBacktestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交批量回测任务（异步执行）"""
    return await BacktestService.create_batch_backtest(db, backtest, user_id=current_user.id)


@router.get("", response_model=BatchBacktestListResponse)
async def list_batch_backtests(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    strategy_id: Optional[int] = Query(None, description="策略 ID 筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取批量回测列表"""
    backtests, total = await BacktestService.get_batch_backtests(
        db, page, limit, strategy_id,
        user_id=current_user.id, user_role=current_user.role
    )

    return {
        "items": backtests,
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{backtest_id}", response_model=BatchBacktestResponse)
async def get_batch_backtest(
    backtest_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个批量回测详情（含 daily_results）"""
    return await BacktestService.get_batch_backtest(
        db, backtest_id, user_id=current_user.id, user_role=current_user.role
    )


@router.delete("/{backtest_id}", status_code=204)
async def delete_batch_backtest(
    backtest_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除批量回测报告"""
    await BacktestService.delete_batch_backtest(
        db, backtest_id, user_id=current_user.id, user_role=current_user.role
    )
```

- [ ] **Step 2: Register batch router in main.py**

In `backend/app/main.py`, add the import:
```python
from .api import strategies, backtests, batch_backtests, factors, ai, auth, users
```

Add the router registration after the backtests line:
```python
app.include_router(batch_backtests.router, prefix="/api/v1/backtests/batch", tags=["batch-backtests"])
```

- [ ] **Step 3: Start backend and verify routes**

```bash
curl http://localhost:8000/docs
```

Expected: `/api/v1/backtests/batch` endpoints visible in OpenAPI docs.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/batch_backtests.py backend/app/main.py
git commit -m "feat: add batch backtest API routes"
```

---

### Task 6: Add frontend types for batch backtest

**Files:**
- Modify: `frontend/src/types/backtest.ts`

- [ ] **Step 1: Append batch types**

```typescript
// 批量回测相关类型

export interface DailyResultItem {
  cutoff_date: string;
  status: string;
  input?: { cutoff_date: string; config: Record<string, any> };
  recommendations?: RecommendationItem[];
  summary?: BacktestSummary;
  error?: string;
}

export interface BatchBacktestReport {
  id: number;
  strategy_id: number;
  strategy_name?: string;
  name?: string;
  status: string;
  start_date: string;
  end_date: string;
  config?: Record<string, any>;
  total_days: number;
  completed_days: number;
  daily_results?: DailyResultItem[];
  error_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface BatchBacktestCreate {
  strategy_id: number;
  start_date: string;
  end_date: string;
  track_days?: number[];
  name?: string;
  config?: Record<string, any>;
}

export interface BatchBacktestListResponse {
  items: BatchBacktestReport[];
  total: number;
  page: number;
  limit: number;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/backtest.ts
git commit -m "feat: add batch backtest TypeScript types"
```

---

### Task 7: Add batch API methods to backtestService

**Files:**
- Modify: `frontend/src/services/backtestService.ts`

- [ ] **Step 1: Add batch service methods**

Add these import types:
```typescript
import type { BacktestReport, BacktestListResponse, BacktestCreate, StrategyExecuteResponse, BatchBacktestReport, BatchBacktestListResponse, BatchBacktestCreate } from '@/types/backtest';
```

Add these methods to the `backtestService` object:

```typescript
  // 批量回测
  async getBatchBacktests(params: {
    page?: number;
    limit?: number;
    strategy_id?: number;
  } = {}) {
    const response = await api.get<BatchBacktestListResponse>('/backtests/batch', { params });
    return response.data;
  },

  async getBatchBacktest(id: number) {
    const response = await api.get<BatchBacktestReport>(`/backtests/batch/${id}`);
    return response.data;
  },

  async createBatchBacktest(data: BatchBacktestCreate) {
    const response = await api.post<BatchBacktestReport>('/backtests/batch', data);
    return response.data;
  },

  async deleteBatchBacktest(id: number) {
    await api.delete(`/backtests/batch/${id}`);
  },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/backtestService.ts
git commit -m "feat: add batch backtest API service methods"
```

---

### Task 8: Update BacktestForm with batch mode

**Files:**
- Modify: `frontend/src/pages/BacktestForm.tsx`

- [ ] **Step 1: Add mode toggle and batch fields**

Add imports at the top:
```typescript
import { useState, useEffect } from 'react';
import { Card, Form, DatePicker, Checkbox, Button, message, Typography, Spin, Input, Radio, Space } from 'antd';
import dayjs from 'dayjs';
import { useParams, useNavigate } from 'react-router-dom';
import { useStrategyStore } from '@/stores/strategyStore';
import { useBacktestStore } from '@/stores/backtestStore';
import PageHeader from '@/components/shared/PageHeader';
import backtestService from '@/services/backtestService';
```

Add new state variables after existing ones:
```typescript
  const [mode, setMode] = useState<'single' | 'batch'>('single');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [batchName, setBatchName] = useState('');
```

Update `handleSubmit`:
```typescript
  const handleSubmit = async () => {
    if (!currentStrategy) {
      message.error('策略不存在');
      return;
    }

    if (mode === 'batch') {
      if (!dateRange || !dateRange[0] || !dateRange[1]) {
        message.error('请选择起始和结束日期');
        return;
      }
      if (trackDays.length === 0) {
        message.error('请至少选择一个追踪天数');
        return;
      }
      try {
        const payload: any = {
          strategy_id: currentStrategy.id,
          start_date: dateRange[0].format('YYYYMMDD'),
          end_date: dateRange[1].format('YYYYMMDD'),
          track_days: trackDays,
        };
        if (batchName.trim()) {
          payload.name = batchName.trim();
        }
        if (stockCode.trim()) {
          payload.config = { ts_code: stockCode.trim() };
        }
        const result = await backtestService.createBatchBacktest(payload);
        message.success('批量回测任务已提交');
        navigate(`/backtests/batch/${result.id}`);
      } catch (err: any) {
        message.error(err.response?.data?.detail || '提交批量回测失败');
      }
      return;
    }

    // single mode — existing logic
    if (!cutoffDate) {
      message.error('请选择截止日');
      return;
    }
    if (trackDays.length === 0) {
      message.error('请至少选择一个追踪天数');
      return;
    }

    try {
      const payload: any = {
        strategy_id: currentStrategy.id,
        cutoff_date: cutoffDate.format('YYYYMMDD'),
        track_days: trackDays,
      };
      if (stockCode.trim()) {
        payload.config = { ts_code: stockCode.trim() };
      }
      const result = await createBacktest(payload);
      message.success('回测任务已提交');
      navigate(`/backtests/${result.id}`);
    } catch {
      // error handled in store
    }
  };
```

Replace the Form content (after the strategy info card) to conditionally render single/batch fields:

```tsx
          <Form.Item label="回测模式">
            <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)}>
              <Radio.Button value="single">单日回测</Radio.Button>
              <Radio.Button value="batch">批量回测</Radio.Button>
            </Radio.Group>
          </Form.Item>

          {mode === 'single' ? (
            <Form.Item label="截止日" required>
              <DatePicker
                value={cutoffDate}
                onChange={setCutoffDate}
                style={{ width: '100%' }}
                placeholder="策略将用此日及之前的数据选股"
                presets={[
                  { label: '昨天', value: () => dayjs().subtract(1, 'day') },
                  { label: '上周五', value: () => dayjs().subtract(1, 'week').endOf('week').subtract(1, 'day') },
                  { label: '本月1日', value: () => dayjs().startOf('month') },
                ]}
              />
            </Form.Item>
          ) : (
            <>
              <Form.Item label="日期范围" required>
                <DatePicker.RangePicker
                  value={dateRange as any}
                  onChange={(v) => setDateRange(v as [dayjs.Dayjs, dayjs.Dayjs])}
                  style={{ width: '100%' }}
                  placeholder={['起始日期', '结束日期']}
                />
              </Form.Item>
              <Form.Item label="报告名称（可选）">
                <Input
                  placeholder="如：4月回测"
                  value={batchName}
                  onChange={(e) => setBatchName(e.target.value)}
                  allowClear
                />
              </Form.Item>
            </>
          )}

          <Form.Item label="追踪天数" required>
            <CheckboxGroup
              options={TRACK_DAY_OPTIONS}
              value={trackDays}
              onChange={(values) => setTrackDays(values as number[])}
            />
          </Form.Item>

          <Form.Item label="目标股票（可选）">
            <Input
              placeholder="留空则全市场选股，输入如 300328.SZ 则只看该股"
              value={stockCode}
              onChange={(e) => setStockCode(e.target.value)}
              allowClear
            />
          </Form.Item>
```

- [ ] **Step 2: Type check**

```bash
cd frontend && npm run build
```

Expected: no new TypeScript errors from BacktestForm.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/BacktestForm.tsx
git commit -m "feat: add batch mode toggle to BacktestForm"
```

---

### Task 9: Create BatchBacktestList page

**Files:**
- Create: `frontend/src/pages/BatchBacktestList.tsx`

- [ ] **Step 1: Create BatchBacktestList.tsx**

```tsx
import { useEffect, useState } from 'react';
import { Card, Table, Button, message, Popconfirm, Select } from 'antd';
import { useNavigate } from 'react-router-dom';
import backtestService from '@/services/backtestService';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import type { BatchBacktestReport } from '@/types/backtest';

export default function BatchBacktestList() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<BatchBacktestReport[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [strategyFilter, setStrategyFilter] = useState<number | undefined>();
  const [deleting, setDeleting] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await backtestService.getBatchBacktests({
        page,
        limit: 20,
        strategy_id: strategyFilter,
      });
      setData(res.items);
      setTotal(res.total);
    } catch {
      message.error('获取批量回测列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [page, strategyFilter]);

  // Poll when any task is running
  useEffect(() => {
    const hasActive = data.some((b) => b.status === 'pending' || b.status === 'running');
    if (!hasActive) return;
    const timer = setInterval(fetchData, 3000);
    return () => clearInterval(timer);
  }, [data]);

  const handleDelete = async (id: number) => {
    setDeleting(true);
    try {
      await backtestService.deleteBatchBacktest(id);
      message.success('已删除');
      fetchData();
    } catch {
      message.error('删除失败');
    } finally {
      setDeleting(false);
    }
  };

  const columns = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (text: string, record: BatchBacktestReport) => (
        <a onClick={() => navigate(`/backtests/batch/${record.id}`)}>{text || `批量回测 #${record.id}`}</a>
      ),
    },
    {
      title: '策略', dataIndex: 'strategy_name', key: 'strategy',
      render: (text: string) => text || '—',
    },
    {
      title: '日期范围', key: 'range',
      render: (_: unknown, r: BatchBacktestReport) =>
        `${r.start_date.slice(0, 4)}-${r.start_date.slice(4, 6)}-${r.start_date.slice(6, 8)} ~ ${r.end_date.slice(0, 4)}-${r.end_date.slice(4, 6)}-${r.end_date.slice(6, 8)}`,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 120,
      render: (status: string) => <StatusTag status={status} type="backtest" />,
    },
    {
      title: '进度', key: 'progress', width: 100,
      render: (_: unknown, r: BatchBacktestReport) =>
        r.status === 'completed' ? `${r.total_days}/${r.total_days}` : `${r.completed_days}/${r.total_days}`,
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180,
      render: (v: string) => v ? new Date(v).toLocaleString() : '—',
    },
    {
      title: '操作', key: 'actions', width: 120,
      render: (_: unknown, r: BatchBacktestReport) => (
        <Popconfirm title="确认删除？" onConfirm={() => handleDelete(r.id)}>
          <Button type="link" danger loading={deleting}>删除</Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="批量回测"
        breadcrumb={[{ title: '批量回测' }]}
      />

      <Card>
        <div style={{ marginBottom: 16 }}>
          <Select
            allowClear
            placeholder="按策略筛选"
            style={{ width: 200 }}
            value={strategyFilter}
            onChange={(v) => { setStrategyFilter(v); setPage(1); }}
          />
        </div>

        <Table
          dataSource={data}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: (p) => setPage(p),
            showTotal: (t) => `共 ${t} 条`,
          }}
        />
      </Card>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/BatchBacktestList.tsx
git commit -m "feat: add BatchBacktestList page"
```

---

### Task 10: Create BatchBacktestDetail page

**Files:**
- Create: `frontend/src/pages/BatchBacktestDetail.tsx`

- [ ] **Step 1: Create BatchBacktestDetail.tsx**

```tsx
import { useEffect, useState } from 'react';
import { Card, Spin, Alert, Descriptions, Table, Button, Row, Col, Space, message, Collapse, Progress } from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import backtestService from '@/services/backtestService';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import ReturnLabel from '@/components/shared/ReturnLabel';
import StatCard from '@/components/shared/StatCard';
import ReturnComparisonChart from '@/components/charts/ReturnComparisonChart';
import WinRateDonutChart from '@/components/charts/WinRateDonutChart';
import type { BatchBacktestReport, DailyResultItem, RecommendationItem, BacktestSummary } from '@/types/backtest';

const recColumns = [
  { title: '排名', key: 'index', width: 60, render: (_: unknown, __: unknown, i: number) => i + 1 },
  { title: '代码', dataIndex: 'ts_code', key: 'ts_code', width: 110 },
  { title: '名称', dataIndex: 'name', key: 'name', width: 100 },
  { title: '得分', dataIndex: 'score', key: 'score', width: 70 },
  { title: '当日', dataIndex: 'return_0d', key: 'return_0d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
  { title: '3天', dataIndex: 'return_3d', key: 'return_3d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
  { title: '7天', dataIndex: 'return_7d', key: 'return_7d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
  { title: '15天', dataIndex: 'return_15d', key: 'return_15d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
];

function DailyPanel({ result }: { result: DailyResultItem }) {
  const isCompleted = result.status === 'completed';
  const isFailed = result.status === 'failed';
  const recs = result.recommendations || [];
  const summary = result.summary as BacktestSummary | null;

  return (
    <>
      {isFailed && result.error && (
        <Alert type="error" message="执行失败" description={result.error} style={{ marginBottom: 12 }} showIcon />
      )}
      {isCompleted && summary && (
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
            columns={recColumns}
            rowKey="ts_code"
            pagination={false}
            size="small"
            scroll={{ x: 760 }}
          />
        </>
      )}
    </>
  );
}

export default function BatchBacktestDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [report, setReport] = useState<BatchBacktestReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    if (!id) return;
    try {
      const res = await backtestService.getBatchBacktest(parseInt(id));
      setReport(res);
    } catch (err: any) {
      setError(err.response?.data?.detail || '获取报告失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [id]);

  useEffect(() => {
    if (report && (report.status === 'pending' || report.status === 'running')) {
      const timer = setInterval(fetchData, 3000);
      return () => clearInterval(timer);
    }
  }, [report?.status, id]);

  useEffect(() => {
    if (error) message.error(error);
  }, [error]);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!report) return <Alert type="error" message="报告不存在" />;

  const isPending = report.status === 'pending' || report.status === 'running';
  const isFailed = report.status === 'failed';
  const dailyResults = report.daily_results || [];
  const progressPct = report.total_days > 0 ? Math.round((report.completed_days / report.total_days) * 100) : 0;

  const collapseItems = dailyResults.map((result: DailyResultItem) => {
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
          {recCount > 0 && <span style={{ color: '#999' }}>{recCount} 只推荐</span>}
          {avg3d !== null && <span style={{ color: parseFloat(avg3d) >= 0 ? '#52c41a' : '#ff4d4f' }}>3d avg: {avg3d}</span>}
        </Space>
      ),
      children: <DailyPanel result={result} />,
    };
  });

  return (
    <>
      <PageHeader
        title={report.name || `批量回测 #${report.id}`}
        breadcrumb={[
          { title: '批量回测', path: '/backtests/batch' },
          { title: report.name || `#${report.id}` },
        ]}
        extra={<Button onClick={() => navigate('/backtests/batch')}>返回列表</Button>}
      />

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="策略名称">{report.strategy_name || '—'}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Space>
              <StatusTag status={report.status} type="backtest" />
              {isPending && <Spin size="small" />}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="日期范围">
            {`${report.start_date.slice(0, 4)}-${report.start_date.slice(4, 6)}-${report.start_date.slice(6, 8)} ~ ${report.end_date.slice(0, 4)}-${report.end_date.slice(4, 6)}-${report.end_date.slice(6, 8)}`}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {report.created_at ? new Date(report.created_at).toLocaleString() : '—'}
          </Descriptions.Item>
        </Descriptions>
        {isPending && (
          <div style={{ marginTop: 16 }}>
            <Progress percent={progressPct} status="active" format={() => `${report.completed_days}/${report.total_days}`} />
          </div>
        )}
      </Card>

      {isFailed && report.error_message && (
        <Alert type="error" message="执行失败" description={report.error_message} style={{ marginBottom: 16 }} showIcon />
      )}

      {isPending && dailyResults.length === 0 && (
        <Card>
          <Spin tip="执行中...">
            <div style={{ padding: 60, textAlign: 'center', color: '#999' }}>
              批量回测正在执行中，请稍候...
            </div>
          </Spin>
        </Card>
      )}

      {dailyResults.length > 0 && (
        <Card title={`每日结果（${dailyResults.length} 天）`}>
          <Collapse
            defaultActiveKey={dailyResults.length > 0 ? [dailyResults[0].cutoff_date] : []}
            items={collapseItems}
          />
        </Card>
      )}
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/BatchBacktestDetail.tsx
git commit -m "feat: add BatchBacktestDetail page"
```

---

### Task 11: Register new routes and sidebar entry

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout/AppLayout.tsx`

- [ ] **Step 1: Add routes to App.tsx**

Add import:
```typescript
import BatchBacktestList from '@/pages/BatchBacktestList';
import BatchBacktestDetail from '@/pages/BatchBacktestDetail';
```

Add routes before the catch-all `*` route:
```tsx
        <Route
          path="/backtests/batch"
          element={
            <ProtectedRoute>
              <BatchBacktestList />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backtests/batch/:id"
          element={
            <ProtectedRoute>
              <BatchBacktestDetail />
            </ProtectedRoute>
          }
        />
```

- [ ] **Step 2: Add sidebar menu item in AppLayout.tsx**

Add to the `menuItems` array, after the "回测报告" entry:
```typescript
    {
      key: '/backtests/batch',
      icon: <BarChartOutlined />,
      label: '批量回测',
    },
```

Update `selectedKey` logic to handle the new path:
```typescript
  const selectedKey = (() => {
    if (location.pathname.startsWith('/users')) return '/users';
    if (location.pathname.startsWith('/backtests/batch')) return '/backtests/batch';
    if (location.pathname.startsWith('/backtests')) return '/backtests';
    if (location.pathname.startsWith('/strategies')) return '/strategies';
    if (location.pathname.startsWith('/dashboard')) return '/dashboard';
    return '/dashboard';
  })();
```

- [ ] **Step 3: Type check and build**

```bash
cd frontend && npm run build
```

Expected: clean build, no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Layout/AppLayout.tsx
git commit -m "feat: add batch backtest routes and sidebar entry"
```

---

### Task 12: End-to-end smoke test

**Files:** None (manual testing)

- [ ] **Step 1: Start backend and frontend**

```bash
cd backend && source venv/bin/activate && python -m uvicorn app.main:app --reload --port 8000 &
cd frontend && npm run dev &
```

- [ ] **Step 2: Test API directly**

```bash
# Create a batch backtest
curl -X POST http://localhost:8000/api/v1/backtests/batch \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"strategy_id": 1, "start_date": "20260401", "end_date": "20260410", "track_days": [3, 7, 15]}'
```

Expected: 202 with batch report JSON.

```bash
# List batch backtests
curl http://localhost:8000/api/v1/backtests/batch -H "Authorization: Bearer <token>"
```

Expected: 200 with items array.

- [ ] **Step 3: Test frontend UI**

1. Navigate to a strategy, click "运行回测"
2. Switch to "批量回测" mode
3. Select date range, submit
4. Verify redirect to batch detail page
5. Wait for results to populate (polling)
6. Expand daily result panels, verify charts render
7. Navigate to "批量回测" in sidebar, verify list page

- [ ] **Step 4: Commit**

```bash
git commit --allow-empty -m "chore: end-to-end smoke test passed"
```
