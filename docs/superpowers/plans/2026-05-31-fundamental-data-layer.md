# 基本面数据层 Phase 1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 AIpicking 平台建立基本面数据基础 — 新建 financial_reports / daily_valuation 两张表，拉取脚本（mootdx + 新浪 + 腾讯），基础查询 API 端点。

**Architecture:** 遵循现有三层模式：SQLAlchemy 模型 → Pydantic schema → Service → API Router。拉取脚本独立于 app，通过 psycopg2 直连 PG，与现有 `update_daily.py` / `sync_market_data.py` 模式对齐。

**Tech Stack:** Python 3.9+, SQLAlchemy 2.0 (async), FastAPI, psycopg2, mootdx, requests

**Spec:** `docs/superpowers/specs/2026-05-31-fundamental-data-layer-design.md`

---

## File Structure

```
Create:
  backend/app/models/financial.py           # FinancialReport + DailyValuation ORM models
  backend/app/schemas/financial.py          # Pydantic request/response schemas
  backend/app/services/financial_service.py # Query service (async SQLAlchemy)
  backend/app/api/financials.py             # API routes (/api/v1/financials, /api/v1/valuation)
  backend/migrate_add_financials.py         # CREATE TABLE migration script
  backend/scripts/sync_valuation.py         # Tencent valuation daily sync
  backend/scripts/sync_financials.py        # mootdx + Sina financial report sync

Modify:
  backend/app/models/__init__.py            # Register new models
  backend/app/main.py                       # Register financials router
```

---

### Task 1: 数据库模型

**Files:**
- Create: `backend/app/models/financial.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 创建 FinancialReport 和 DailyValuation 模型**

```python
"""基本面数据 ORM 模型"""
from sqlalchemy import (
    Column, String, Integer, Float, BigInteger, Text,
    UniqueConstraint, Index
)
from .base import BaseModel


class FinancialReport(BaseModel):
    """财报季报快照 — 每只股票每报告期一条记录"""
    __tablename__ = "financial_reports"
    __table_args__ = (
        UniqueConstraint("ts_code", "report_date", name="uq_fin_code_date"),
        Index("idx_fin_code", "ts_code"),
        Index("idx_fin_date", "report_date"),
        Index("idx_fin_type", "report_type"),
    )

    ts_code = Column(String(20), nullable=False, index=True)
    report_date = Column(String(10), nullable=False)   # YYYY-MM-DD
    report_type = Column(String(10), nullable=False)   # Q1/Q2/Q3/FY
    pub_date = Column(String(10))                      # 实际发布日期

    # 盈利质量
    eps = Column(Float)
    bvps = Column(Float)
    roe = Column(Float)
    roa = Column(Float)
    gross_margin = Column(Float)
    net_margin = Column(Float)

    # 成长性
    net_profit = Column(Float)          # 万元
    net_profit_yoy = Column(Float)      # %
    revenue = Column(Float)             # 万元
    revenue_yoy = Column(Float)         # %

    # 财务健康
    debt_to_assets = Column(Float)
    current_ratio = Column(Float)
    quick_ratio = Column(Float)

    # 现金流
    cf_operating = Column(Float)        # 万元
    cf_ratio = Column(Float)

    # 股本
    total_shares = Column(BigInteger)
    float_shares = Column(BigInteger)

    # 新浪补充
    total_assets = Column(Float)
    total_liabilities = Column(Float)
    shareholders_equity = Column(Float)

    # 元数据
    source = Column(String(20), default="mootdx")


class DailyValuation(BaseModel):
    """每日估值快照 — 每只股票每个交易日一条记录"""
    __tablename__ = "daily_valuation"
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uq_dv_code_date"),
        Index("idx_dv_code", "ts_code"),
        Index("idx_dv_date", "trade_date"),
    )

    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(String(8), nullable=False)  # YYYYMMDD

    # 腾讯财经估值
    pe_ttm = Column(Float)
    pe_static = Column(Float)
    pb = Column(Float)
    market_cap = Column(Float)          # 亿元
    circ_market_cap = Column(Float)     # 亿元
    dividend_yield = Column(Float)      # %

    source = Column(String(20), default="tencent")
```

- [ ] **Step 2: 在 models/__init__.py 注册新模型**

Read `backend/app/models/__init__.py` first, then edit it.

在 `from .stock_tables import (...)` 导入块中，将 `DailyDragonTigerSeat` 后的 `)` 替换为：

```python
    DailyDragonTigerSeat,
)
from .financial import FinancialReport, DailyValuation
```

同时在文件末尾添加 relationship（仅需导入，不需要额外 relationship，因为 financial 表不涉及外键关联到其他表）。

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/financial.py backend/app/models/__init__.py
git commit -m "feat: add FinancialReport and DailyValuation models

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 数据库迁移脚本

**Files:**
- Create: `backend/migrate_add_financials.py`

- [ ] **Step 1: 创建迁移脚本**

```python
"""
迁移脚本：创建 financial_reports 和 daily_valuation 表

用法：
    cd backend
    venv/bin/python migrate_add_financials.py
    venv/bin/python migrate_add_financials.py --pg-url postgresql://...
"""
import argparse
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

_ENV_DIR = Path(__file__).resolve().parent
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)

from app.config import settings


def get_conn(sync_url: str = None):
    """获取 PostgreSQL 连接"""
    url = sync_url or settings.SYNC_DATABASE_URL
    url = url.replace("+asyncpg", "").replace("+psycopg2", "")
    from urllib.parse import urlparse
    r = urlparse(url)
    return psycopg2.connect(
        host=r.hostname or "localhost",
        port=r.port or 5432,
        user=r.username or "aipicking",
        password=r.password or "",
        dbname=r.path.lstrip("/") or "aipicking",
    )


SQL_CREATE_FINANCIAL_REPORTS = """
CREATE TABLE IF NOT EXISTS financial_reports (
    id              SERIAL PRIMARY KEY,
    ts_code         VARCHAR(20) NOT NULL,
    report_date     VARCHAR(10) NOT NULL,
    report_type     VARCHAR(10) NOT NULL,
    pub_date        VARCHAR(10),
    eps             DOUBLE PRECISION,
    bvps            DOUBLE PRECISION,
    roe             DOUBLE PRECISION,
    roa             DOUBLE PRECISION,
    gross_margin    DOUBLE PRECISION,
    net_margin      DOUBLE PRECISION,
    net_profit      DOUBLE PRECISION,
    net_profit_yoy  DOUBLE PRECISION,
    revenue         DOUBLE PRECISION,
    revenue_yoy     DOUBLE PRECISION,
    debt_to_assets  DOUBLE PRECISION,
    current_ratio   DOUBLE PRECISION,
    quick_ratio     DOUBLE PRECISION,
    cf_operating    DOUBLE PRECISION,
    cf_ratio        DOUBLE PRECISION,
    total_shares    BIGINT,
    float_shares    BIGINT,
    total_assets         DOUBLE PRECISION,
    total_liabilities    DOUBLE PRECISION,
    shareholders_equity  DOUBLE PRECISION,
    source          VARCHAR(20) DEFAULT 'mootdx',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ts_code, report_date)
);

CREATE INDEX IF NOT EXISTS idx_fin_code ON financial_reports(ts_code);
CREATE INDEX IF NOT EXISTS idx_fin_date ON financial_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_fin_type ON financial_reports(report_type);
"""

SQL_CREATE_DAILY_VALUATION = """
CREATE TABLE IF NOT EXISTS daily_valuation (
    id              SERIAL PRIMARY KEY,
    ts_code         VARCHAR(20) NOT NULL,
    trade_date      VARCHAR(8) NOT NULL,
    pe_ttm          DOUBLE PRECISION,
    pe_static       DOUBLE PRECISION,
    pb              DOUBLE PRECISION,
    market_cap      DOUBLE PRECISION,
    circ_market_cap DOUBLE PRECISION,
    dividend_yield  DOUBLE PRECISION,
    source          VARCHAR(20) DEFAULT 'tencent',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ts_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_dv_code ON daily_valuation(ts_code);
CREATE INDEX IF NOT EXISTS idx_dv_date ON daily_valuation(trade_date);
"""


def migrate(sync_url: str = None):
    conn = get_conn(sync_url)
    try:
        cur = conn.cursor()
        cur.execute(SQL_CREATE_FINANCIAL_REPORTS)
        cur.execute(SQL_CREATE_DAILY_VALUATION)
        conn.commit()
        print("✅ financial_reports 和 daily_valuation 表已创建")
    except Exception as e:
        conn.rollback()
        print(f"❌ 迁移失败: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="创建基本面数据表")
    parser.add_argument("--pg-url", type=str, default=None,
                        help="PostgreSQL 连接字符串")
    args = parser.parse_args()
    migrate(args.pg_url)
```

- [ ] **Step 2: 运行迁移**

```bash
cd backend && venv/bin/python migrate_add_financials.py
```

Expected: `✅ financial_reports 和 daily_valuation 表已创建`

- [ ] **Step 3: 验证表结构**

```bash
venv/bin/python -c "
from app.config import settings
import psycopg2
url = settings.SYNC_DATABASE_URL.replace('+asyncpg','').replace('+psycopg2','')
from urllib.parse import urlparse
r = urlparse(url)
conn = psycopg2.connect(host=r.hostname,port=r.port,user=r.username,password=r.password,dbname=r.path.lstrip('/'))
cur = conn.cursor()
cur.execute(\"SELECT table_name FROM information_schema.tables WHERE table_name IN ('financial_reports','daily_valuation')\")
print([r[0] for r in cur.fetchall()])
conn.close()
"
```

Expected: `['daily_valuation', 'financial_reports']`

- [ ] **Step 4: Commit**

```bash
git add backend/migrate_add_financials.py
git commit -m "feat: add migration script for financial data tables

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/financial.py`

- [ ] **Step 1: 创建请求/响应 schema**

```python
"""财务数据 Pydantic schemas"""
from typing import Optional
from pydantic import BaseModel


class FinancialReportOut(BaseModel):
    """单期财报响应"""
    ts_code: str
    report_date: str
    report_type: str
    pub_date: Optional[str] = None
    eps: Optional[float] = None
    bvps: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    gross_margin: Optional[float] = None
    net_margin: Optional[float] = None
    net_profit: Optional[float] = None
    net_profit_yoy: Optional[float] = None
    revenue: Optional[float] = None
    revenue_yoy: Optional[float] = None
    debt_to_assets: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    cf_operating: Optional[float] = None
    cf_ratio: Optional[float] = None
    total_shares: Optional[int] = None
    float_shares: Optional[int] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    shareholders_equity: Optional[float] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True


class ValuationOut(BaseModel):
    """单日估值响应"""
    ts_code: str
    trade_date: str
    pe_ttm: Optional[float] = None
    pe_static: Optional[float] = None
    pb: Optional[float] = None
    market_cap: Optional[float] = None
    circ_market_cap: Optional[float] = None
    dividend_yield: Optional[float] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True


class ScreenRequest(BaseModel):
    """筛选请求参数"""
    roe_min: Optional[float] = None
    roe_max: Optional[float] = None
    pe_max: Optional[float] = None
    pb_max: Optional[float] = None
    revenue_growth_min: Optional[float] = None
    net_profit_growth_min: Optional[float] = None
    debt_max: Optional[float] = None
    market_cap_min: Optional[float] = None
    limit: int = 50
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/financial.py
git commit -m "feat: add financial Pydantic schemas

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 查询服务

**Files:**
- Create: `backend/app/services/financial_service.py`

- [ ] **Step 1: 创建 FinancialService**

```python
"""财务数据查询服务"""
from typing import Optional
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.financial import FinancialReport, DailyValuation
from ..models.stock_tables import Stock


class FinancialService:
    """基本面数据查询"""

    @staticmethod
    async def get_reports(
        db: AsyncSession,
        ts_code: str,
        periods: int = 20,
    ) -> list[dict]:
        """获取单股最近 N 期财报"""
        stmt = (
            select(FinancialReport)
            .where(FinancialReport.ts_code == ts_code)
            .order_by(desc(FinancialReport.report_date))
            .limit(periods)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "ts_code": r.ts_code,
                "report_date": r.report_date,
                "report_type": r.report_type,
                "pub_date": r.pub_date,
                "eps": r.eps, "bvps": r.bvps,
                "roe": r.roe, "roa": r.roa,
                "gross_margin": r.gross_margin,
                "net_margin": r.net_margin,
                "net_profit": r.net_profit,
                "net_profit_yoy": r.net_profit_yoy,
                "revenue": r.revenue,
                "revenue_yoy": r.revenue_yoy,
                "debt_to_assets": r.debt_to_assets,
                "current_ratio": r.current_ratio,
                "quick_ratio": r.quick_ratio,
                "cf_operating": r.cf_operating,
                "cf_ratio": r.cf_ratio,
                "total_shares": r.total_shares,
                "float_shares": r.float_shares,
                "total_assets": r.total_assets,
                "total_liabilities": r.total_liabilities,
                "shareholders_equity": r.shareholders_equity,
                "source": r.source,
            }
            for r in rows
        ]

    @staticmethod
    async def get_latest_report(
        db: AsyncSession,
        ts_code: str,
    ) -> Optional[dict]:
        """获取最新一期财报"""
        stmt = (
            select(FinancialReport)
            .where(FinancialReport.ts_code == ts_code)
            .order_by(desc(FinancialReport.report_date))
            .limit(1)
        )
        result = await db.execute(stmt)
        r = result.scalars().first()
        if not r:
            return None
        return {
            "ts_code": r.ts_code,
            "report_date": r.report_date,
            "report_type": r.report_type,
            "pub_date": r.pub_date,
            "eps": r.eps, "bvps": r.bvps,
            "roe": r.roe, "roa": r.roa,
            "gross_margin": r.gross_margin,
            "net_margin": r.net_margin,
            "net_profit": r.net_profit,
            "net_profit_yoy": r.net_profit_yoy,
            "revenue": r.revenue,
            "revenue_yoy": r.revenue_yoy,
            "debt_to_assets": r.debt_to_assets,
            "current_ratio": r.current_ratio,
            "quick_ratio": r.quick_ratio,
            "cf_operating": r.cf_operating,
            "cf_ratio": r.cf_ratio,
            "total_shares": r.total_shares,
            "float_shares": r.float_shares,
            "total_assets": r.total_assets,
            "total_liabilities": r.total_liabilities,
            "shareholders_equity": r.shareholders_equity,
            "source": r.source,
        }

    @staticmethod
    async def get_valuation_history(
        db: AsyncSession,
        ts_code: str,
        days: int = 365,
    ) -> list[dict]:
        """获取单股估值历史"""
        stmt = (
            select(DailyValuation)
            .where(DailyValuation.ts_code == ts_code)
            .order_by(desc(DailyValuation.trade_date))
            .limit(days)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "ts_code": r.ts_code,
                "trade_date": r.trade_date,
                "pe_ttm": r.pe_ttm,
                "pe_static": r.pe_static,
                "pb": r.pb,
                "market_cap": r.market_cap,
                "circ_market_cap": r.circ_market_cap,
                "dividend_yield": r.dividend_yield,
                "source": r.source,
            }
            for r in reversed(rows)  # 升序返回
        ]

    @staticmethod
    async def get_latest_valuation_snapshot(
        db: AsyncSession,
        trade_date: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """获取全市场最新估值快照"""
        if trade_date:
            stmt = (
                select(DailyValuation)
                .where(DailyValuation.trade_date == trade_date)
                .limit(limit)
            )
        else:
            # 取最新交易日的数据
            subq = (
                select(DailyValuation.trade_date)
                .order_by(desc(DailyValuation.trade_date))
                .limit(1)
                .scalar_subquery()
            )
            stmt = (
                select(DailyValuation)
                .where(DailyValuation.trade_date == subq)
                .limit(limit)
            )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "ts_code": r.ts_code,
                "trade_date": r.trade_date,
                "pe_ttm": r.pe_ttm,
                "pe_static": r.pe_static,
                "pb": r.pb,
                "market_cap": r.market_cap,
                "circ_market_cap": r.circ_market_cap,
                "dividend_yield": r.dividend_yield,
                "source": r.source,
            }
            for r in rows
        ]

    @staticmethod
    async def screen(
        db: AsyncSession,
        roe_min: Optional[float] = None,
        pe_max: Optional[float] = None,
        pb_max: Optional[float] = None,
        revenue_growth_min: Optional[float] = None,
        net_profit_growth_min: Optional[float] = None,
        debt_max: Optional[float] = None,
        market_cap_min: Optional[float] = None,
        limit: int = 50,
    ) -> list[dict]:
        """简单筛选 — 最新财报 + 最新估值 联查"""
        # 每个股票取最新一期财报
        fin_subq = (
            select(
                FinancialReport.ts_code,
                FinancialReport.roe,
                FinancialReport.revenue_yoy,
                FinancialReport.net_profit_yoy,
                FinancialReport.debt_to_assets,
                FinancialReport.net_profit,
                FinancialReport.revenue,
                FinancialReport.report_date,
            )
            .distinct(FinancialReport.ts_code)
            .order_by(FinancialReport.ts_code, desc(FinancialReport.report_date))
            .subquery()
        )

        # 取最新估值
        val_subq = (
            select(
                DailyValuation.ts_code,
                DailyValuation.pe_ttm,
                DailyValuation.pb,
                DailyValuation.market_cap,
                DailyValuation.trade_date,
            )
            .distinct(DailyValuation.ts_code)
            .order_by(DailyValuation.ts_code, desc(DailyValuation.trade_date))
            .subquery()
        )

        stmt = (
            select(
                Stock.ts_code, Stock.name,
                fin_subq.c.roe, fin_subq.c.revenue_yoy,
                fin_subq.c.net_profit_yoy, fin_subq.c.debt_to_assets,
                fin_subq.c.net_profit, fin_subq.c.revenue,
                val_subq.c.pe_ttm, val_subq.c.pb, val_subq.c.market_cap,
            )
            .join(fin_subq, Stock.ts_code == fin_subq.c.ts_code)
            .join(val_subq, Stock.ts_code == val_subq.c.ts_code)
            .where(Stock.ts_code.isnot(None), Stock.ts_code != "")
        )

        if roe_min is not None:
            stmt = stmt.where(fin_subq.c.roe >= roe_min)
        if pe_max is not None:
            stmt = stmt.where(val_subq.c.pe_ttm <= pe_max)
        if pb_max is not None:
            stmt = stmt.where(val_subq.c.pb <= pb_max)
        if revenue_growth_min is not None:
            stmt = stmt.where(fin_subq.c.revenue_yoy >= revenue_growth_min)
        if net_profit_growth_min is not None:
            stmt = stmt.where(fin_subq.c.net_profit_yoy >= net_profit_growth_min)
        if debt_max is not None:
            stmt = stmt.where(fin_subq.c.debt_to_assets <= debt_max)
        if market_cap_min is not None:
            stmt = stmt.where(val_subq.c.market_cap >= market_cap_min)

        stmt = stmt.order_by(desc(fin_subq.c.roe)).limit(limit)
        result = await db.execute(stmt)
        rows = result.all()
        return [
            {
                "ts_code": r.ts_code,
                "name": r.name,
                "roe": r.roe,
                "revenue_yoy": r.revenue_yoy,
                "net_profit_yoy": r.net_profit_yoy,
                "debt_to_assets": r.debt_to_assets,
                "net_profit": r.net_profit,
                "revenue": r.revenue,
                "pe_ttm": r.pe_ttm,
                "pb": r.pb,
                "market_cap": r.market_cap,
            }
            for r in rows
        ]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/financial_service.py
git commit -m "feat: add FinancialService query layer

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: API 路由

**Files:**
- Create: `backend/app/api/financials.py`

- [ ] **Step 1: 创建 API 路由文件**

```python
"""基本面数据 API"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..services.financial_service import FinancialService

router = APIRouter()


@router.get("/financials/{ts_code}")
async def get_financial_reports(
    ts_code: str,
    periods: int = Query(20, ge=1, le=40, description="返回期数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单股财报历史"""
    result = await FinancialService.get_reports(db, ts_code, periods)
    return {"code": 0, "message": "ok", "data": result}


@router.get("/financials/{ts_code}/latest")
async def get_latest_financial_report(
    ts_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单股最新一期财报"""
    result = await FinancialService.get_latest_report(db, ts_code)
    return {"code": 0, "message": "ok", "data": result}


@router.get("/valuation/{ts_code}")
async def get_valuation_history(
    ts_code: str,
    days: int = Query(365, ge=1, le=730, description="数据天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单股估值历史"""
    result = await FinancialService.get_valuation_history(db, ts_code, days)
    return {"code": 0, "message": "ok", "data": result}


@router.get("/valuation/snapshot")
async def get_valuation_snapshot(
    trade_date: Optional[str] = Query(None, description="交易日 YYYYMMDD，默认最新"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取全市场最新估值快照"""
    result = await FinancialService.get_latest_valuation_snapshot(db, trade_date, limit)
    return {"code": 0, "message": "ok", "data": result}


@router.get("/financials/screen")
async def screen_stocks(
    roe_min: Optional[float] = Query(None, description="ROE 下限 (%)"),
    pe_max: Optional[float] = Query(None, description="PE 上限"),
    pb_max: Optional[float] = Query(None, description="PB 上限"),
    revenue_growth_min: Optional[float] = Query(None, description="营收增长率下限 (%)"),
    net_profit_growth_min: Optional[float] = Query(None, description="净利增长率下限 (%)"),
    debt_max: Optional[float] = Query(None, description="资产负债率上限 (%)"),
    market_cap_min: Optional[float] = Query(None, description="市值下限 (亿元)"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """基本面筛选"""
    result = await FinancialService.screen(
        db,
        roe_min=roe_min,
        pe_max=pe_max,
        pb_max=pb_max,
        revenue_growth_min=revenue_growth_min,
        net_profit_growth_min=net_profit_growth_min,
        debt_max=debt_max,
        market_cap_min=market_cap_min,
        limit=limit,
    )
    return {"code": 0, "message": "ok", "data": result}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/financials.py
git commit -m "feat: add financials API routes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: 注册路由

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: 在 main.py 注册 financials 路由**

Read `backend/app/main.py` first. 在 `from .api import ...` 导入行中添加 `financials`：

```python
from .api import strategies, backtests, batch_backtests, factors, ai, auth, users, stocks, education, ratings, comments, financials
```

在 `app.include_router` 块末尾添加：

```python
app.include_router(financials.router, prefix="/api/v1", tags=["financials"])
```

- [ ] **Step 2: 验证应用启动正常**

```bash
cd backend && venv/bin/python -c "
from app.main import app
routes = [r.path for r in app.routes if hasattr(r, 'path')]
print([r for r in routes if 'financial' in r or 'valuation' in r])
"
```

Expected: `['/api/v1/financials/{ts_code}', '/api/v1/financials/{ts_code}/latest', '/api/v1/valuation/{ts_code}', '/api/v1/valuation/snapshot', '/api/v1/financials/screen']`

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: register financials API router

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: 估值同步脚本

**Files:**
- Create: `backend/scripts/sync_valuation.py`

- [ ] **Step 1: 创建 sync_valuation.py**

```python
#!/usr/bin/env python3
"""
每日估值数据同步 — 通过腾讯财经 API 拉取 PE/PB/市值

用法：
    venv/bin/python scripts/sync_valuation.py          # 增量（昨天）
    venv/bin/python scripts/sync_valuation.py --init   # 全量最近365天
    venv/bin/python scripts/sync_valuation.py --date 2026-05-30

cron（每个交易日 17:30）:
    30 17 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_valuation.py
"""
import argparse
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ENV_DIR = Path(__file__).resolve().parent.parent
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)

# ── PG 连接 ──────────────────────────────────────────────────────────
def _parse_pg_url(url: str) -> dict:
    url = url.replace("+asyncpg", "").replace("+psycopg2", "")
    from urllib.parse import urlparse
    r = urlparse(url)
    return {
        "host": r.hostname or "localhost",
        "port": r.port or 5432,
        "user": r.username or "aipicking",
        "password": r.password or "",
        "dbname": r.path.lstrip("/") or "aipicking",
    }

_PG_PARAMS = _parse_pg_url(os.getenv(
    "DATABASE_URL",
    "postgresql://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:5432/<DB_NAME>"
))

TENCENT_QUOTE_URL = "http://qt.gtimg.cn/q="
BATCH_SIZE = 50   # 腾讯一次最多拉 50 只


def get_conn():
    return psycopg2.connect(**_PG_PARAMS)


def load_stocks():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT ts_code, symbol FROM stocks WHERE ts_code IS NOT NULL AND ts_code != ''")
    rows = cur.fetchall()
    conn.close()
    return [{"ts_code": r[0], "symbol": r[1]} for r in rows]


def tencent_stock_code(ts_code: str) -> str:
    """6位代码 → 腾讯前缀格式"""
    if ts_code.startswith(("6", "9")):
        return f"sh{ts_code}"
    elif ts_code.startswith("8"):
        return f"bj{ts_code}"
    else:
        return f"sz{ts_code}"


def fetch_valuations_batch(symbols: list[str]) -> list[dict]:
    """批量拉取腾讯估值数据"""
    url = TENCENT_QUOTE_URL + ",".join(symbols)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = resp.read().decode("gbk")
    except Exception as e:
        print(f"  ⚠️ 请求失败: {e}")
        return []

    results = []
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        try:
            key = line.split("=")[0].split("_")[-1]
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue
            code = key[2:]  # 去掉 sh/sz/bj 前缀
            pe_ttm = float(vals[39]) if vals[39] else None
            pe_static = float(vals[52]) if vals[52] else None
            pb = float(vals[46]) if vals[46] else None
            mcap = float(vals[44]) if vals[44] else None
            circ_mcap = float(vals[45]) if vals[45] else None
            # 股息率：腾讯字段索引 48 附近，需要验证
            div_yield = None

            if pe_ttm or pb or mcap:
                results.append({
                    "ts_code": code,
                    "pe_ttm": pe_ttm,
                    "pe_static": pe_static,
                    "pb": pb,
                    "market_cap": mcap,
                    "circ_market_cap": circ_mcap,
                    "dividend_yield": div_yield,
                })
        except (ValueError, IndexError):
            continue
    return results


def bulk_upsert(records: list[tuple], trade_date: str):
    """批量 upsert 估值数据"""
    conn = get_conn()
    cur = conn.cursor()
    psycopg2.extras.execute_batch(cur, """
        INSERT INTO daily_valuation
            (ts_code, trade_date, pe_ttm, pe_static, pb, market_cap, circ_market_cap, dividend_yield, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'tencent')
        ON CONFLICT (ts_code, trade_date) DO UPDATE SET
            pe_ttm = EXCLUDED.pe_ttm, pe_static = EXCLUDED.pe_static,
            pb = EXCLUDED.pb, market_cap = EXCLUDED.market_cap,
            circ_market_cap = EXCLUDED.circ_market_cap,
            dividend_yield = EXCLUDED.dividend_yield
    """, records)
    conn.commit()
    conn.close()


def sync_date(trade_date: str):
    """拉取指定日期的全市场估值"""
    stocks = load_stocks()
    print(f"📊 拉取 {trade_date} 估值数据，共 {len(stocks)} 只股票...")

    updated = 0
    records_batch = []
    prefix_symbols = []

    for i, s in enumerate(stocks):
        prefix_symbols.append(tencent_stock_code(s["ts_code"]))

        if len(prefix_symbols) >= BATCH_SIZE or i == len(stocks) - 1:
            results = fetch_valuations_batch(prefix_symbols)
            for r in results:
                records_batch.append((
                    r["ts_code"], trade_date,
                    r["pe_ttm"], r["pe_static"], r["pb"],
                    r["market_cap"], r["circ_market_cap"],
                    r["dividend_yield"],
                ))
                updated += 1

            if len(records_batch) >= 500:
                bulk_upsert(records_batch, trade_date)
                records_batch = []

            prefix_symbols = []
            time.sleep(0.1)  # 批次间短暂休息

        if (i + 1) % 500 == 0:
            print(f"  进度: {i+1}/{len(stocks)}, 已获取 {updated} 条")

    if records_batch:
        bulk_upsert(records_batch, trade_date)

    print(f"✅ 完成！{trade_date} 写入 {updated} 条估值数据")
    return updated


def is_trade_day(date_str: str) -> bool:
    """简单交易日判断（周末排除）"""
    d = datetime.strptime(date_str.replace("-", ""), "%Y%m%d")
    return d.weekday() < 5


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="每日估值数据同步")
    parser.add_argument("--init", action="store_true",
                        help="初始化最近365天估值数据")
    parser.add_argument("--date", type=str, default=None,
                        help="指定日期 YYYY-MM-DD（默认昨天）")
    parser.add_argument("--pg-url", type=str, default=None,
                        help="PG 连接字符串")
    args = parser.parse_args()

    if args.pg_url:
        _PG_PARAMS = _parse_pg_url(args.pg_url)

    if args.init:
        # 回溯 365 个自然日（约 250 个交易日）
        end = datetime.now()
        start = end - timedelta(days=365)
        d = start
        while d <= end:
            ds = d.strftime("%Y%m%d")
            if is_trade_day(ds):
                sync_date(ds)
            d += timedelta(days=1)
        print("🎉 初始化完成！")
    elif args.date:
        trade_date = args.date.replace("-", "")
        if not is_trade_day(trade_date):
            print(f"⚠️ {args.date} 不是交易日（周末），跳过")
            sys.exit(0)
        sync_date(trade_date)
    else:
        # 默认：昨天
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        if not is_trade_day(yesterday):
            print(f"⚠️ 昨天（{yesterday}）不是交易日，跳过")
            sys.exit(0)
        sync_date(yesterday)
```

- [ ] **Step 2: 测试脚本（拉取单日数据）**

```bash
cd backend && venv/bin/python scripts/sync_valuation.py --date 2026-05-30
```

Expected: 成功拉取约 5000+ 只股票的估值数据。

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/sync_valuation.py
git commit -m "feat: add daily valuation sync script (Tencent API)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: 财报同步脚本

**Files:**
- Create: `backend/scripts/sync_financials.py`

- [ ] **Step 1: 创建 sync_financials.py**

```python
#!/usr/bin/env python3
"""
财报数据同步 — mootdx finance (37字段) + 新浪三表补充

用法：
    venv/bin/python scripts/sync_financials.py --init   # 全量近5年
    venv/bin/python scripts/sync_financials.py          # 增量（最新一期）
    venv/bin/python scripts/sync_financials.py --code 600519  # 单票测试

cron（每季度财报季结束后第一周）:
    0 3 2 5,9,11 * * cd /opt/AIpicking/backend && venv/bin/python scripts/sync_financials.py
"""
import argparse
import os
import sys
import time
import requests
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ENV_DIR = Path(__file__).resolve().parent.parent
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)

# ── PG 连接 ──────────────────────────────────────────────────────────
def _parse_pg_url(url: str) -> dict:
    url = url.replace("+asyncpg", "").replace("+psycopg2", "")
    from urllib.parse import urlparse
    r = urlparse(url)
    return {
        "host": r.hostname or "localhost",
        "port": r.port or 5432,
        "user": r.username or "aipicking",
        "password": r.password or "",
        "dbname": r.path.lstrip("/") or "aipicking",
    }

_PG_PARAMS = _parse_pg_url(os.getenv(
    "DATABASE_URL",
    "postgresql://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:5432/<DB_NAME>"
))

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
SINA_FIN_URL = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"

# 报告期 → report_type 映射
# mootdx finance 返回的 report_date 是 YYYYMMDD 格式
# 例如 20260331 → Q1, 20260630 → Q2, 20260930 → Q3, 20261231 → FY
PERIOD_TYPE_MAP = {
    "0331": "Q1",
    "0630": "Q2",
    "0930": "Q3",
    "1231": "FY",
}


def get_conn():
    return psycopg2.connect(**_PG_PARAMS)


def load_stocks():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT ts_code, symbol FROM stocks WHERE ts_code IS NOT NULL AND ts_code != ''")
    rows = cur.fetchall()
    conn.close()
    return [{"ts_code": r[0], "symbol": r[1]} for r in rows]


def report_type_from_date(report_date: str) -> str:
    """从 YYYYMMDD 推断报告类型"""
    mmdd = report_date[4:]
    return PERIOD_TYPE_MAP.get(mmdd, "Q1")


def fetch_mootdx_finance(ts_code: str) -> dict | None:
    """
    从 mootdx 拉取单只股票财务快照（37 字段）
    返回 dict，key 为中文字段名
    """
    from mootdx.quotes import Quotes
    try:
        client = Quotes.factory(market="std")
        data = client.finance(symbol=ts_code)
        return data
    except Exception as e:
        print(f"  ⚠️ mootdx finance({ts_code}) 失败: {e}")
        return None


def fetch_sina_financials(ts_code: str, report_type: str) -> dict | None:
    """
    从新浪拉取三表数据（fzb=资产负债表, lrb=利润表, llb=现金流量表）
    返回合并后的 dict
    """
    prefix = "sh" if ts_code.startswith("6") else "sz"
    paper_code = f"{prefix}{ts_code}"

    result = {}
    for src in ("lrb", "fzb", "llb"):
        params = {
            "paperCode": paper_code,
            "source": src,
            "type": "0",
            "page": "1",
            "num": "1",  # 只取最新一期
        }
        try:
            r = requests.get(SINA_FIN_URL, params=params,
                             headers={"User-Agent": UA}, timeout=15)
            d = r.json()
            items = d.get("result", {}).get("data", {}).get(src, [])
            if items and isinstance(items, list) and len(items) > 0:
                result[src] = items[0]
        except Exception as e:
            pass
        time.sleep(0.3)
    return result if result else None


def parse_mootdx_row(row, ts_code: str) -> dict | None:
    """
    将 mootdx finance 单行数据解析为 financial_reports 记录

    mootdx finance 返回的字段名是中文，例如:
      - '每股收益' → eps
      - '每股净资产' → bvps
      - '净资产收益率' → roe
      - '净利润' → net_profit
      - '营业总收入' → revenue
      - '总股本' → total_shares
      - '流通股本' → float_shares
    """
    # 如果是 DataFrame row，转 dict
    if hasattr(row, "to_dict"):
        d = row.to_dict()
    elif hasattr(row, "_asdict"):
        d = row._asdict()
    else:
        d = dict(row)

    # 获取报告期
    report_date_raw = d.get("report_date") or d.get("报告期") or ""
    if not report_date_raw:
        return None

    report_date = str(report_date_raw).replace("-", "")
    if len(report_date) == 8:
        report_date_fmt = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:8]}"
    else:
        return None

    def _f(key_cn: str, fallback_en: str = None) -> float | None:
        """取字段值，先查中文 key，再查英文 fallback"""
        val = d.get(key_cn)
        if val is None and fallback_en:
            val = d.get(fallback_en)
        if val is None or val == "" or val == "None":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    eps = _f("每股收益", "eps")
    roe = _f("净资产收益率", "roe")
    net_profit = _f("净利润", "profit")
    revenue = _f("营业总收入", "income")
    total_shares = _f("总股本")
    float_shares = _f("流通股本")
    bvps = _f("每股净资产", "bvps")

    return {
        "ts_code": ts_code,
        "report_date": report_date_fmt,
        "report_type": report_type_from_date(report_date),
        "pub_date": None,
        "eps": eps,
        "bvps": bvps,
        "roe": roe,
        "roa": _f("总资产收益率"),
        "gross_margin": None,
        "net_margin": None,
        "net_profit": net_profit,
        "net_profit_yoy": _f("净利润同比增长率"),
        "revenue": revenue,
        "revenue_yoy": _f("营业收入同比增长率"),
        "debt_to_assets": _f("资产负债率"),
        "current_ratio": _f("流动比率"),
        "quick_ratio": _f("速动比率"),
        "cf_operating": _f("经营活动现金流量净额"),
        "cf_ratio": None,
        "total_shares": int(total_shares) if total_shares else None,
        "float_shares": int(float_shares) if float_shares else None,
        "total_assets": None,
        "total_liabilities": None,
        "shareholders_equity": None,
        "source": "mootdx",
    }


def merge_sina_data(record: dict, sina_data: dict):
    """将新浪三表数据合并到 record"""
    # 资产负债表
    fzb = sina_data.get("fzb", {})
    if fzb:
        record["total_assets"] = _safe_float(fzb.get("资产总计"))
        record["total_liabilities"] = _safe_float(fzb.get("负债合计"))
        record["shareholders_equity"] = _safe_float(fzb.get("归属母公司股东权益合计"))

    # 利润表
    lrb = sina_data.get("lrb", {})
    if lrb:
        if record["gross_margin"] is None:
            revenue = _safe_float(lrb.get("营业总收入"))
            cost = _safe_float(lrb.get("营业总成本"))
            if revenue and cost:
                record["gross_margin"] = round((revenue - cost) / revenue * 100, 2) if revenue else None
        if record["net_margin"] is None:
            net = record["net_profit"] or _safe_float(lrb.get("净利润"))
            rev = record["revenue"] or _safe_float(lrb.get("营业总收入"))
            if net and rev:
                record["net_margin"] = round(net / rev * 100, 2) if rev else None

    # 现金流量表
    llb = sina_data.get("llb", {})
    if llb:
        cf_op = _safe_float(llb.get("经营活动产生的现金流量净额"))
        if cf_op:
            if record["cf_operating"] is None:
                record["cf_operating"] = cf_op
            net = record["net_profit"] or _safe_float(lrb.get("净利润")) if lrb else None
            if net and net != 0:
                record["cf_ratio"] = round(cf_op / net, 4)


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def upsert_one(record: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO financial_reports
            (ts_code, report_date, report_type, pub_date,
             eps, bvps, roe, roa, gross_margin, net_margin,
             net_profit, net_profit_yoy, revenue, revenue_yoy,
             debt_to_assets, current_ratio, quick_ratio,
             cf_operating, cf_ratio, total_shares, float_shares,
             total_assets, total_liabilities, shareholders_equity, source)
        VALUES (%s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s)
        ON CONFLICT (ts_code, report_date) DO UPDATE SET
            eps = EXCLUDED.eps, bvps = EXCLUDED.bvps,
            roe = EXCLUDED.roe, roa = EXCLUDED.roa,
            gross_margin = EXCLUDED.gross_margin, net_margin = EXCLUDED.net_margin,
            net_profit = EXCLUDED.net_profit, net_profit_yoy = EXCLUDED.net_profit_yoy,
            revenue = EXCLUDED.revenue, revenue_yoy = EXCLUDED.revenue_yoy,
            debt_to_assets = EXCLUDED.debt_to_assets,
            current_ratio = EXCLUDED.current_ratio, quick_ratio = EXCLUDED.quick_ratio,
            cf_operating = EXCLUDED.cf_operating, cf_ratio = EXCLUDED.cf_ratio,
            total_shares = EXCLUDED.total_shares, float_shares = EXCLUDED.float_shares,
            total_assets = EXCLUDED.total_assets,
            total_liabilities = EXCLUDED.total_liabilities,
            shareholders_equity = EXCLUDED.shareholders_equity,
            source = EXCLUDED.source,
            updated_at = NOW()
    """, (
        record["ts_code"], record["report_date"], record["report_type"], record["pub_date"],
        record["eps"], record["bvps"], record["roe"], record["roa"],
        record["gross_margin"], record["net_margin"],
        record["net_profit"], record["net_profit_yoy"],
        record["revenue"], record["revenue_yoy"],
        record["debt_to_assets"], record["current_ratio"], record["quick_ratio"],
        record["cf_operating"], record["cf_ratio"],
        record["total_shares"], record["float_shares"],
        record["total_assets"], record["total_liabilities"],
        record["shareholders_equity"], record["source"],
    ))
    conn.commit()
    conn.close()


def sync_stock(ts_code: str, with_sina: bool = True):
    """同步单只股票的最新财报"""
    df = fetch_mootdx_finance(ts_code)
    if df is None or (hasattr(df, "empty") and df.empty):
        return 0

    # mootdx finance 可能返回多期数据
    rows = []
    if hasattr(df, "iterrows"):
        for _, row in df.iterrows():
            r = parse_mootdx_row(row, ts_code)
            if r:
                rows.append(r)
    elif hasattr(df, "to_dict"):
        # 也可能是单条记录
        r = parse_mootdx_row(df, ts_code)
        if r:
            rows.append(r)
    elif isinstance(df, list):
        for row in df:
            r = parse_mootdx_row(row, ts_code)
            if r:
                rows.append(r)

    # 只保留最近 20 期
    rows.sort(key=lambda x: x["report_date"], reverse=True)
    rows = rows[:20]

    # 用新浪数据补充最近 4 期
    if with_sina:
        for record in rows[:4]:
            try:
                sina = fetch_sina_financials(ts_code, record["report_type"])
                if sina:
                    merge_sina_data(record, sina)
            except Exception:
                pass

    for record in rows:
        upsert_one(record)

    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="财报数据同步")
    parser.add_argument("--init", action="store_true",
                        help="初始化全市场近5年财报数据")
    parser.add_argument("--code", type=str, default=None,
                        help="单只股票代码（测试用）")
    parser.add_argument("--pg-url", type=str, default=None,
                        help="PG 连接字符串")
    parser.add_argument("--no-sina", action="store_true",
                        help="跳过新浪数据补充")
    args = parser.parse_args()

    if args.pg_url:
        _PG_PARAMS = _parse_pg_url(args.pg_url)

    if args.code:
        # 单票测试
        print(f"🔍 测试拉取 {args.code} 财报...")
        n = sync_stock(args.code, with_sina=not args.no_sina)
        print(f"✅ {args.code}: 写入 {n} 期财报")
    elif args.init:
        stocks = load_stocks()
        print(f"📊 全量初始化财务数据，共 {len(stocks)} 只股票...")
        total = 0
        for i, s in enumerate(stocks):
            try:
                n = sync_stock(s["ts_code"], with_sina=(i < 20))
                total += n
                if (i + 1) % 100 == 0:
                    print(f"  进度: {i+1}/{len(stocks)}, 已写入 {total} 条")
                time.sleep(0.1)  # mootdx TCP 限速
            except Exception as e:
                print(f"  ⚠️ {s['ts_code']} 失败: {e}")
        print(f"🎉 全量初始化完成！共写入 {total} 条财报记录")
    else:
        # 增量模式：拉最新一期
        stocks = load_stocks()
        print(f"📊 增量更新财务数据，共 {len(stocks)} 只股票...")
        total = 0
        for i, s in enumerate(stocks):
            try:
                n = sync_stock(s["ts_code"], with_sina=(i < 20))
                total += n
                if (i + 1) % 200 == 0:
                    print(f"  进度: {i+1}/{len(stocks)}, 已写入 {total} 条")
                time.sleep(0.1)
            except Exception as e:
                print(f"  ⚠️ {s['ts_code']} 失败: {e}")
        print(f"✅ 增量更新完成！共写入 {total} 条")
```

- [ ] **Step 2: 测试脚本（单只股票）**

```bash
cd backend && venv/bin/python scripts/sync_financials.py --code 600519
```

Expected: 成功拉取贵州茅台最近 20 期财报数据。

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/sync_financials.py
git commit -m "feat: add financial report sync script (mootdx + Sina)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: 验证与收尾

- [ ] **Step 1: 运行全部现有测试确保无回归**

```bash
cd backend && venv/bin/python -m pytest tests/ -v
```

Expected: 38 passed（与基线一致）

- [ ] **Step 2: 验证 API 端点（启动服务后手动测试）**

```bash
# 启动服务
cd backend && venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# 测试端点（拉取前确保数据库有数据）
curl -s http://localhost:8000/api/v1/financials/600519?periods=5 | python -m json.tool
curl -s http://localhost:8000/api/v1/financials/600519/latest | python -m json.tool
curl -s http://localhost:8000/api/v1/valuation/600519?days=5 | python -m json.tool
curl -s "http://localhost:8000/api/v1/financials/screen?roe_min=15&pe_max=30&limit=10" | python -m json.tool
```

- [ ] **Step 3: 最终 commit**

```bash
git add -A
git commit -m "feat: Phase 1 fundamental data layer complete

- FinancialReport + DailyValuation SQLAlchemy models
- Database migration script (migrate_add_financials.py)
- Pydantic schemas for API responses
- FinancialService query layer (async SQLAlchemy)
- 5 API endpoints: reports, latest report, valuation history, snapshot, screen
- sync_valuation.py: Tencent API daily valuation sync
- sync_financials.py: mootdx finance + Sina 3-statement sync

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
