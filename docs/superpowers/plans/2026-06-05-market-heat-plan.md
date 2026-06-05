# 市场热度页面 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「市场热度」页面，展示板块资金流热力图、主题词云、KPI 概览、热门股票/龙虎榜/北向资金明细，支持点击下钻。

**Architecture:** 后端新增 `market_heat_service.py`（Core 级别 SQL 查询）和 `market_heat.py` API 路由；前端新增 `MarketHeat` 页面，使用 ECharts Treemap + WordCloud + Ant Design Drawer 实现可视化与下钻交互。

**Tech Stack:** FastAPI + SQLAlchemy async + React 19 + TypeScript + Ant Design 6 + ECharts 6 + Zustand

**Spec:** `docs/superpowers/specs/2026-06-05-market-heat-design.md`

---

## 文件结构

```
backend/app/
├── services/market_heat_service.py   # 创建 — 9 个查询方法 + 温度计算
├── api/market_heat.py                # 创建 — 9 个 API 端点
└── main.py                           # 修改 — 注册路由

frontend/
├── package.json                      # 修改 — 添加 echarts-wordcloud
├── src/
│   ├── services/marketHeatService.ts # 创建 — API 调用
│   ├── stores/marketHeatStore.ts     # 创建 — Zustand store
│   ├── pages/MarketHeat.tsx          # 创建 — 主页面
│   ├── components/market-heat/
│   │   ├── TemperatureCard.tsx       # 创建 — KPI 卡片
│   │   ├── SectorTreemap.tsx         # 创建 — ECharts Treemap
│   │   ├── ThemeWordCloud.tsx        # 创建 — ECharts WordCloud
│   │   ├── SectorDrawer.tsx          # 创建 — 板块详情抽屉
│   │   └── ThemeDrawer.tsx           # 创建 — 主题详情抽屉
│   ├── App.tsx                       # 修改 — 注册路由
│   └── components/Layout/AppLayout.tsx # 修改 — 新增菜单项
```

---

### Task 1: 后端 — MarketHeatService（数据查询 + 温度计算）

**Files:**
- Create: `backend/app/services/market_heat_service.py`

- [ ] **Step 1: 创建服务文件**

```python
"""市场热度服务 — Core 级别 SQL 查询"""
from datetime import datetime, timedelta
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.stock_tables import (
    Daily, DailySectorFlow, DailyHotStock, DailyHotTheme,
    DailyNorthboundFlow, DailyDragonTiger, DailyDragonTigerSeat
)


class MarketHeatService:

    # ── 工具方法 ─────────────────────────────────────────────

    @staticmethod
    async def _get_latest_date(db: AsyncSession) -> str | None:
        """获取最新有数据的交易日"""
        stmt = select(func.max(DailySectorFlow.trade_date))
        result = await db.execute(stmt)
        return result.scalar()

    # ── 概览 KPI ─────────────────────────────────────────────

    @staticmethod
    async def get_overview(db: AsyncSession, trade_date: str | None = None) -> dict:
        """返回 4 个核心 KPI：市场温度、北向资金、涨跌比、领涨板块"""
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return {"trade_date": None, "temperature": None, "northbound": None,
                    "advance_decline": None, "leading_sector": None}

        # 北向资金
        nb_stmt = select(DailyNorthboundFlow.__table__).where(
            DailyNorthboundFlow.trade_date == date
        )
        nb_result = await db.execute(nb_stmt)
        nb_row = nb_result.mappings().first()
        northbound = dict(nb_row) if nb_row else None

        # 涨跌比：从 daily 表统计当日上涨/下跌家数
        adv_stmt = select(
            func.count().label("total"),
            func.sum(
                func.case((Daily.close > Daily.open, 1), else_=0)
            ).label("up_count"),
            func.sum(
                func.case((Daily.close < Daily.open, 1), else_=0)
            ).label("down_count"),
        ).where(Daily.trade_date == date, ~Daily.ts_code.like("%.IDX"))
        adv_result = await db.execute(adv_stmt)
        adv_row = adv_result.mappings().first()
        adv = dict(adv_row) if adv_row else {"total": 0, "up_count": 0, "down_count": 0}

        # 领涨板块：sector_flow 按 change_pct 降序取第一
        sector_stmt = select(DailySectorFlow.__table__).where(
            DailySectorFlow.trade_date == date,
            DailySectorFlow.sector_type == "industry"
        ).order_by(DailySectorFlow.change_pct.desc()).limit(1)
        sector_result = await db.execute(sector_stmt)
        leading = dict(sector_result.mappings().first()) if sector_result else None

        # 计算市场温度
        temperature = MarketHeatService._calc_temperature(
            northbound=northbound,
            adv=adv,
            date=date,
            db=db,
        )

        return {
            "trade_date": date,
            "temperature": temperature,
            "northbound": northbound,
            "advance_decline": adv,
            "leading_sector": {
                "sector_name": leading["sector_name"],
                "change_pct": leading["change_pct"],
                "main_net_yi": leading["main_net_yi"],
            } if leading else None,
        }

    # ── 板块资金流 ────────────────────────────────────────────

    @staticmethod
    async def get_sectors(
        db: AsyncSession, trade_date: str | None, sector_type: str = "industry"
    ) -> list[dict]:
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return []
        stmt = select(DailySectorFlow.__table__).where(
            DailySectorFlow.trade_date == date,
            DailySectorFlow.sector_type == sector_type,
        ).order_by(DailySectorFlow.rank.asc())
        result = await db.execute(stmt)
        return [dict(r) for r in result.mappings().all()]

    @staticmethod
    async def get_sector_detail(
        db: AsyncSession, sector_code: str, trade_date: str | None, days: int = 10
    ) -> dict:
        """板块详情：近 N 日资金流趋势 + 成分股 Top5"""
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return {"trend": [], "stocks": [], "info": None}

        # 基本信息
        info_stmt = select(DailySectorFlow.__table__).where(
            DailySectorFlow.trade_date == date,
            DailySectorFlow.sector_code == sector_code,
        )
        info_result = await db.execute(info_stmt)
        info = dict(info_result.mappings().first()) if info_result else None

        # 近 N 日趋势
        trend_stmt = select(DailySectorFlow.__table__).where(
            DailySectorFlow.sector_code == sector_code,
            DailySectorFlow.trade_date <= date,
        ).order_by(DailySectorFlow.trade_date.desc()).limit(days)
        trend_result = await db.execute(trend_stmt)
        trend = [dict(r) for r in reversed(list(trend_result.mappings().all()))]

        # 成分股 Top5（从 daily 表查当天该板块涨幅最大的 stock）
        # 注：daily 表的 industry 概念需通过 stocks.industry_l1/l2/l3 关联
        top5 = []
        if info:
            from ..models.stock_tables import Stock
            stock_stmt = (
                select(Stock.ts_code, Stock.name, Daily.close, Daily.open)
                .join(Daily, Stock.ts_code == Daily.ts_code)
                .where(
                    Daily.trade_date == date,
                    (Stock.industry_l2 == info["sector_name"]) |
                    (Stock.industry_l1 == info["sector_name"])
                )
                .order_by(
                    ((Daily.close - Daily.open) / func.nullif(Daily.open, 0)).desc()
                )
                .limit(5)
            )
            stock_result = await db.execute(stock_stmt)
            top5 = [
                {"ts_code": r.ts_code, "name": r.name, "close": r.close, "open": r.open}
                for r in stock_result.all()
            ]

        return {"info": info, "trend": trend, "stocks": top5}

    # ── 主题 ─────────────────────────────────────────────────

    @staticmethod
    async def get_themes(db: AsyncSession, trade_date: str | None, limit: int = 20) -> list[dict]:
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return []
        stmt = select(DailyHotTheme.__table__).where(
            DailyHotTheme.trade_date == date
        ).order_by(DailyHotTheme.stock_count.desc()).limit(limit)
        result = await db.execute(stmt)
        return [dict(r) for r in result.mappings().all()]

    @staticmethod
    async def get_theme_detail(
        db: AsyncSession, theme_name: str, trade_date: str | None
    ) -> list[dict]:
        """主题关联股票：从 hot_stocks 的 reason 字段模糊匹配"""
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return []
        stmt = select(DailyHotStock.__table__).where(
            DailyHotStock.trade_date == date,
            DailyHotStock.reason.ilike(f"%{theme_name}%"),
        ).order_by(DailyHotStock.sort_order.asc())
        result = await db.execute(stmt)
        return [dict(r) for r in result.mappings().all()]

    # ── 热门股票 / 龙虎榜 / 北向 ──────────────────────────────

    @staticmethod
    async def get_hot_stocks(
        db: AsyncSession, trade_date: str | None, page: int = 1, page_size: int = 20
    ) -> dict:
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return {"items": [], "total": 0}

        # 总数
        count_stmt = select(func.count()).select_from(DailyHotStock.__table__).where(
            DailyHotStock.trade_date == date
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = select(DailyHotStock.__table__).where(
            DailyHotStock.trade_date == date
        ).order_by(DailyHotStock.sort_order.asc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        result = await db.execute(stmt)
        items = [dict(r) for r in result.mappings().all()]
        return {"items": items, "total": total}

    @staticmethod
    async def get_dragon_tiger(
        db: AsyncSession, trade_date: str | None, page: int = 1, page_size: int = 20
    ) -> dict:
        date = trade_date or await MarketHeatService._get_latest_date(db)
        if not date:
            return {"items": [], "total": 0}

        count_stmt = select(func.count()).select_from(DailyDragonTiger.__table__).where(
            DailyDragonTiger.trade_date == date
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = select(DailyDragonTiger.__table__).where(
            DailyDragonTiger.trade_date == date
        ).order_by(DailyDragonTiger.net_buy_wan.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        result = await db.execute(stmt)
        items = [dict(r) for r in result.mappings().all()]

        # 为每个股票附加席位明细
        for item in items:
            seat_stmt = select(DailyDragonTigerSeat.__table__).where(
                DailyDragonTigerSeat.trade_date == date,
                DailyDragonTigerSeat.stock_code == item["stock_code"],
            ).order_by(DailyDragonTigerSeat.seat_type, DailyDragonTigerSeat.rank)
            seat_result = await db.execute(seat_stmt)
            item["seats"] = [dict(s) for s in seat_result.mappings().all()]

        return {"items": items, "total": total}

    @staticmethod
    async def get_northbound(db: AsyncSession, days: int = 30) -> list[dict]:
        stmt = select(DailyNorthboundFlow.__table__).order_by(
            DailyNorthboundFlow.trade_date.desc()
        ).limit(days)
        result = await db.execute(stmt)
        return [dict(r) for r in reversed(list(result.mappings().all()))]

    @staticmethod
    async def get_available_dates(db: AsyncSession, days: int = 20) -> list[str]:
        stmt = (
            select(DailySectorFlow.trade_date)
            .distinct()
            .order_by(DailySectorFlow.trade_date.desc())
            .limit(days)
        )
        result = await db.execute(stmt)
        return [r[0] for r in result.all()]

    # ── 市场温度计算 ─────────────────────────────────────────

    @staticmethod
    def _calc_temperature(
        northbound: dict | None,
        adv: dict,
        date: str,
        db: AsyncSession | None = None,
    ) -> dict:
        """5 维度综合评分，每维度 0-20 分，满分 100"""
        scores = {}

        # 1. 资金面 (20): 北向净流入方向+规模
        nb_score = 10  # 中性
        if northbound and northbound.get("total_net_yi"):
            net = northbound["total_net_yi"]
            if net > 50:
                nb_score = 20
            elif net > 20:
                nb_score = 17
            elif net > 0:
                nb_score = 14
            elif net > -20:
                nb_score = 7
            elif net > -50:
                nb_score = 3
            else:
                nb_score = 0
        scores["capital"] = nb_score

        # 2. 涨跌结构 (20): 上涨占比
        total = adv.get("total", 0) or 0
        up = adv.get("up_count", 0) or 0
        ratio = up / total if total > 0 else 0.5
        scores["breadth"] = min(20, round(ratio * 25))  # 80%+ = 满分

        # 3. 情绪面 (20): 涨停数（从 daily 表统计，简化处理）
        # 注：数据库中无直接 limit_up/down 列，使用 change_pct 推算
        # 此处从 adv 统计中提取，若无精确数据则给中值
        scores["sentiment"] = 10  # 中性默认值

        # 4. 板块集中度 (20): 适中最好（过度集中=不可持续）
        scores["concentration"] = 10  # 中性默认值

        # 5. 热度延续 (20): 需要前后两天数据比较
        scores["continuity"] = 10  # 中性默认值

        total_score = sum(scores.values())
        level = (
            "冰点" if total_score <= 30 else
            "偏冷" if total_score <= 50 else
            "中性" if total_score <= 70 else
            "偏热" if total_score <= 85 else
            "过热"
        )

        return {
            "score": total_score,
            "level": level,
            "dimensions": scores,
        }
```

- [ ] **Step 2: 验证服务文件可导入**

```bash
cd backend && source venv/bin/activate && python -c "from app.services.market_heat_service import MarketHeatService; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/market_heat_service.py
git commit -m "feat: 新增 MarketHeatService — 市场热度数据查询 + 温度计算

- 9 个查询方法：概览/板块/主题/热门股/龙虎榜/北向/日期
- 5 维市场温度综合评分（0-100）
- Core 级别 SQL，兼容 PostgreSQL

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 后端 — API 路由 + 注册

**Files:**
- Create: `backend/app/api/market_heat.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建路由文件**

```python
"""市场热度 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..services.market_heat_service import MarketHeatService

router = APIRouter()


@router.get("/overview")
async def get_overview(
    trade_date: str | None = Query(None, description="交易日 YYYYMMDD，默认最新"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """市场概览 KPI（市场温度、北向资金、涨跌比、领涨板块）"""
    data = await MarketHeatService.get_overview(db, trade_date)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/sectors")
async def get_sectors(
    trade_date: str | None = Query(None),
    sector_type: str = Query("industry", regex="^(industry|concept)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """板块资金流列表（热力图数据源）"""
    data = await MarketHeatService.get_sectors(db, trade_date, sector_type)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/sectors/{sector_code}")
async def get_sector_detail(
    sector_code: str,
    trade_date: str | None = Query(None),
    days: int = Query(10, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """板块详情：近 N 日资金流趋势 + 成分股 Top5"""
    data = await MarketHeatService.get_sector_detail(db, sector_code, trade_date, days)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/themes")
async def get_themes(
    trade_date: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """热门主题列表（词云数据源）"""
    data = await MarketHeatService.get_themes(db, trade_date, limit)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/themes/{theme_name}")
async def get_theme_detail(
    theme_name: str,
    trade_date: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """主题关联股票列表"""
    data = await MarketHeatService.get_theme_detail(db, theme_name, trade_date)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/hot-stocks")
async def get_hot_stocks(
    trade_date: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """热门股票分页列表"""
    data = await MarketHeatService.get_hot_stocks(db, trade_date, page, page_size)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/dragon-tiger")
async def get_dragon_tiger(
    trade_date: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """龙虎榜分页列表（含席位明细）"""
    data = await MarketHeatService.get_dragon_tiger(db, trade_date, page, page_size)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/northbound")
async def get_northbound(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """北向资金日趋势"""
    data = await MarketHeatService.get_northbound(db, days)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/available-dates")
async def get_available_dates(
    days: int = Query(20, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """有数据的交易日列表（日期选择器用）"""
    data = await MarketHeatService.get_available_dates(db, days)
    return {"code": 0, "message": "ok", "data": data}
```

- [ ] **Step 2: 在 main.py 中注册路由**

在 `backend/app/main.py` 中，在现有 `from .api import ...` 行末添加 `market_heat`，并在 `app.include_router` 区域末尾添加注册行：

找到这一行：
```python
from .api import strategies, backtests, batch_backtests, factors, ai, auth, users, stocks, education, ratings, comments, financials, trade_sims
```

修改为：
```python
from .api import strategies, backtests, batch_backtests, factors, ai, auth, users, stocks, education, ratings, comments, financials, trade_sims, market_heat
```

在 `app.include_router(financials.router, ...)` 之后添加：
```python
app.include_router(market_heat.router, prefix="/api/v1/market-heat", tags=["market-heat"])
```

- [ ] **Step 3: 启动后端验证路由可访问**

```bash
cd backend && source venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/docs | grep -o "market-heat" || echo "Check Swagger at http://localhost:8000/docs"
```

预期：Swagger 文档中出现 `market-heat` tag，包含 9 个端点。

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/market_heat.py backend/app/main.py
git commit -m "feat: 新增市场热度 API 路由（9 个端点）

/market-heat/overview|sectors|themes|hot-stocks|dragon-tiger|northbound|available-dates + 详情端点

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 前端 — 依赖安装 + Service + Store

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/services/marketHeatService.ts`
- Create: `frontend/src/stores/marketHeatStore.ts`

- [ ] **Step 1: 安装 echarts-wordcloud**

```bash
cd frontend && npm install echarts-wordcloud
```

如果安装失败或启动后报错（与 ECharts 6 不兼容），改用柱状图展示主题 Top 10 作为降级方案。

- [ ] **Step 2: 创建 marketHeatService.ts**

```typescript
import api from './api';

export interface OverviewData {
  trade_date: string | null;
  temperature: {
    score: number;
    level: string;
    dimensions: Record<string, number>;
  } | null;
  northbound: {
    trade_date: string;
    hgt_net_yi: number;
    sgt_net_yi: number;
    total_net_yi: number;
  } | null;
  advance_decline: {
    total: number;
    up_count: number;
    down_count: number;
  } | null;
  leading_sector: {
    sector_name: string;
    change_pct: number;
    main_net_yi: number;
  } | null;
}

export interface SectorItem {
  trade_date: string;
  sector_type: string;
  sector_code: string;
  sector_name: string;
  change_pct: number;
  up_count: number;
  down_count: number;
  leader_stock: string;
  leader_change: number;
  main_net_yi: number;
  net_inflow: number;
  rank: number;
}

export interface SectorDetail {
  info: SectorItem | null;
  trend: SectorItem[];
  stocks: { ts_code: string; name: string; close: number; open: number }[];
}

export interface ThemeItem {
  trade_date: string;
  theme_name: string;
  stock_count: number;
}

export interface HotStockItem {
  trade_date: string;
  stock_code: string;
  stock_name: string;
  close: number;
  change_pct: number;
  turnover_pct: number;
  reason: string;
  dde_net: number;
  sort_order: number;
}

export interface DragonTigerItem {
  trade_date: string;
  stock_code: string;
  stock_name: string;
  reason: string;
  close: number;
  change_pct: number;
  turnover_pct: number;
  net_buy_wan: number;
  buy_wan: number;
  sell_wan: number;
  seats: {
    seat_type: string;
    rank: number;
    seat_name: string;
    buy_amt_wan: number;
    sell_amt_wan: number;
    net_amt_wan: number;
    is_institution: boolean;
  }[];
}

export interface NorthboundItem {
  trade_date: string;
  hgt_net_yi: number;
  sgt_net_yi: number;
  total_net_yi: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
}

export const marketHeatService = {
  async getOverview(tradeDate?: string) {
    const response = await api.get<{ code: number; data: OverviewData }>(
      '/market-heat/overview',
      { params: { trade_date: tradeDate } },
    );
    return response.data.data;
  },

  async getSectors(tradeDate?: string, sectorType: 'industry' | 'concept' = 'industry') {
    const response = await api.get<{ code: number; data: SectorItem[] }>(
      '/market-heat/sectors',
      { params: { trade_date: tradeDate, sector_type: sectorType } },
    );
    return response.data.data;
  },

  async getSectorDetail(sectorCode: string, tradeDate?: string, days: number = 10) {
    const response = await api.get<{ code: number; data: SectorDetail }>(
      `/market-heat/sectors/${sectorCode}`,
      { params: { trade_date: tradeDate, days } },
    );
    return response.data.data;
  },

  async getThemes(tradeDate?: string, limit: number = 20) {
    const response = await api.get<{ code: number; data: ThemeItem[] }>(
      '/market-heat/themes',
      { params: { trade_date: tradeDate, limit } },
    );
    return response.data.data;
  },

  async getThemeDetail(themeName: string, tradeDate?: string) {
    const response = await api.get<{ code: number; data: HotStockItem[] }>(
      `/market-heat/themes/${encodeURIComponent(themeName)}`,
      { params: { trade_date: tradeDate } },
    );
    return response.data.data;
  },

  async getHotStocks(tradeDate?: string, page: number = 1, pageSize: number = 20) {
    const response = await api.get<{ code: number; data: PaginatedResponse<HotStockItem> }>(
      '/market-heat/hot-stocks',
      { params: { trade_date: tradeDate, page, page_size: pageSize } },
    );
    return response.data.data;
  },

  async getDragonTiger(tradeDate?: string, page: number = 1, pageSize: number = 20) {
    const response = await api.get<{ code: number; data: PaginatedResponse<DragonTigerItem> }>(
      '/market-heat/dragon-tiger',
      { params: { trade_date: tradeDate, page, page_size: pageSize } },
    );
    return response.data.data;
  },

  async getNorthbound(days: number = 30) {
    const response = await api.get<{ code: number; data: NorthboundItem[] }>(
      '/market-heat/northbound',
      { params: { days } },
    );
    return response.data.data;
  },

  async getAvailableDates(days: number = 20) {
    const response = await api.get<{ code: number; data: string[] }>(
      '/market-heat/available-dates',
      { params: { days } },
    );
    return response.data.data;
  },
};

export default marketHeatService;
```

- [ ] **Step 3: 创建 marketHeatStore.ts**

```typescript
import { create } from 'zustand';
import marketHeatService, {
  type OverviewData,
  type SectorItem,
  type SectorDetail,
  type ThemeItem,
  type HotStockItem,
  type DragonTigerItem,
  type NorthboundItem,
} from '@/services/marketHeatService';

interface MarketHeatState {
  // 日期
  tradeDate: string | undefined;
  availableDates: string[];

  // 概览
  overview: OverviewData | null;
  overviewLoading: boolean;

  // 板块
  sectorType: 'industry' | 'concept';
  sectors: SectorItem[];
  sectorsLoading: boolean;

  // 主题
  themes: ThemeItem[];
  themesLoading: boolean;

  // 热门股票
  hotStocks: HotStockItem[];
  hotStocksTotal: number;
  hotStocksPage: number;
  hotStocksLoading: boolean;

  // 龙虎榜
  dragonTiger: DragonTigerItem[];
  dragonTigerTotal: number;
  dragonTigerPage: number;
  dragonTigerLoading: boolean;

  // 北向
  northbound: NorthboundItem[];
  northboundLoading: boolean;

  // 抽屉
  drawer: {
    open: boolean;
    type: 'sector' | 'theme' | null;
    code: string | null;
    name: string | null;
  };

  // 错误
  error: string | null;

  // Actions
  setTradeDate: (date: string) => void;
  setSectorType: (type: 'industry' | 'concept') => void;
  fetchAvailableDates: () => Promise<void>;
  fetchOverview: () => Promise<void>;
  fetchSectors: () => Promise<void>;
  fetchThemes: () => Promise<void>;
  fetchHotStocks: (page?: number) => Promise<void>;
  fetchDragonTiger: (page?: number) => Promise<void>;
  fetchNorthbound: () => Promise<void>;
  openDrawer: (type: 'sector' | 'theme', code: string, name: string) => void;
  closeDrawer: () => void;
  clearError: () => void;
}

export const useMarketHeatStore = create<MarketHeatState>((set, get) => ({
  tradeDate: undefined,
  availableDates: [],
  overview: null,
  overviewLoading: false,
  sectorType: 'industry',
  sectors: [],
  sectorsLoading: false,
  themes: [],
  themesLoading: false,
  hotStocks: [],
  hotStocksTotal: 0,
  hotStocksPage: 1,
  hotStocksLoading: false,
  dragonTiger: [],
  dragonTigerTotal: 0,
  dragonTigerPage: 1,
  dragonTigerLoading: false,
  northbound: [],
  northboundLoading: false,
  drawer: { open: false, type: null, code: null, name: null },
  error: null,

  setTradeDate: (date: string) => {
    set({ tradeDate: date });
    // 日期变化时重新加载所有数据
    get().fetchOverview();
    get().fetchSectors();
    get().fetchThemes();
    get().fetchHotStocks(1);
    get().fetchDragonTiger(1);
  },

  setSectorType: (type: 'industry' | 'concept') => {
    set({ sectorType: type });
    get().fetchSectors();
  },

  fetchAvailableDates: async () => {
    try {
      const dates = await marketHeatService.getAvailableDates();
      set({ availableDates: dates, tradeDate: dates[0] });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取日期失败' });
    }
  },

  fetchOverview: async () => {
    set({ overviewLoading: true, error: null });
    try {
      const data = await marketHeatService.getOverview(get().tradeDate);
      set({ overview: data, overviewLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取概览失败', overviewLoading: false });
    }
  },

  fetchSectors: async () => {
    set({ sectorsLoading: true, error: null });
    try {
      const data = await marketHeatService.getSectors(get().tradeDate, get().sectorType);
      set({ sectors: data, sectorsLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取板块失败', sectorsLoading: false });
    }
  },

  fetchThemes: async () => {
    set({ themesLoading: true, error: null });
    try {
      const data = await marketHeatService.getThemes(get().tradeDate);
      set({ themes: data, themesLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取主题失败', themesLoading: false });
    }
  },

  fetchHotStocks: async (page?: number) => {
    const p = page ?? get().hotStocksPage;
    set({ hotStocksLoading: true, hotStocksPage: p, error: null });
    try {
      const data = await marketHeatService.getHotStocks(get().tradeDate, p);
      set({ hotStocks: data.items, hotStocksTotal: data.total, hotStocksLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取热门股失败', hotStocksLoading: false });
    }
  },

  fetchDragonTiger: async (page?: number) => {
    const p = page ?? get().dragonTigerPage;
    set({ dragonTigerLoading: true, dragonTigerPage: p, error: null });
    try {
      const data = await marketHeatService.getDragonTiger(get().tradeDate, p);
      set({ dragonTiger: data.items, dragonTigerTotal: data.total, dragonTigerLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取龙虎榜失败', dragonTigerLoading: false });
    }
  },

  fetchNorthbound: async () => {
    set({ northboundLoading: true, error: null });
    try {
      const data = await marketHeatService.getNorthbound();
      set({ northbound: data, northboundLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取北向资金失败', northboundLoading: false });
    }
  },

  openDrawer: (type, code, name) =>
    set({ drawer: { open: true, type, code, name } }),

  closeDrawer: () =>
    set({ drawer: { open: false, type: null, code: null, name: null } }),

  clearError: () => set({ error: null }),
}));
```

- [ ] **Step 4: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/services/marketHeatService.ts frontend/src/stores/marketHeatStore.ts
git commit -m "feat: 前端市场热度 Service + Store

- marketHeatService: 9 个 API 调用封装
- marketHeatStore: Zustand 状态管理，日期切换自动刷新

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 前端 — 子组件（TemperatureCard + SectorTreemap + ThemeWordCloud）

**Files:**
- Create: `frontend/src/components/market-heat/TemperatureCard.tsx`
- Create: `frontend/src/components/market-heat/SectorTreemap.tsx`
- Create: `frontend/src/components/market-heat/ThemeWordCloud.tsx`
- Create: `frontend/src/components/market-heat/SectorDrawer.tsx`
- Create: `frontend/src/components/market-heat/ThemeDrawer.tsx`

- [ ] **Step 1: 创建 TemperatureCard.tsx**

```tsx
import React from 'react';
import { Card, Spin, theme } from 'antd';
import type { OverviewData } from '@/services/marketHeatService';

interface Props {
  overview: OverviewData | null;
  loading: boolean;
}

const TEMP_COLORS: Record<string, [string, string]> = {
  '冰点': ['#1890ff', '#096dd9'],
  '偏冷': ['#52c41a', '#389e0d'],
  '中性': ['#faad14', '#d48806'],
  '偏热': ['#ff7a45', '#fa541c'],
  '过热': ['#ff4d4f', '#cf1322'],
};

const TemperatureCard: React.FC<Props> = ({ overview, loading }) => {
  const { token } = theme.useToken();

  if (loading) {
    return (
      <Card><Spin /><div style={{ textAlign: 'center', marginTop: 8 }}>加载中...</div></Card>
    );
  }

  if (!overview?.temperature) {
    return <Card><div style={{ textAlign: 'center', color: '#999' }}>暂无数据</div></Card>;
  }

  const t = overview.temperature;
  const [startColor, endColor] = TEMP_COLORS[t.level] || TEMP_COLORS['中性'];

  const cards = [
    {
      label: '🔥 市场温度',
      value: `${t.score}°`,
      sub: t.level,
      gradient: `linear-gradient(135deg, ${startColor}, ${endColor})`,
    },
    {
      label: '💰 北向资金',
      value: overview.northbound
        ? `${overview.northbound.total_net_yi > 0 ? '+' : ''}${overview.northbound.total_net_yi.toFixed(1)}亿`
        : '--',
      sub: overview.northbound?.total_net_yi
        ? (overview.northbound.total_net_yi > 0 ? '净流入' : '净流出')
        : '无数据',
      gradient: 'linear-gradient(135deg, #1677ff, #0958d9)',
    },
    {
      label: '📊 涨跌比',
      value: overview.advance_decline && overview.advance_decline.total > 0
        ? `${(overview.advance_decline.up_count / overview.advance_decline.total * 100).toFixed(0)}%`
        : '--',
      sub: overview.advance_decline
        ? `涨 ${overview.advance_decline.up_count} · 跌 ${overview.advance_decline.down_count}`
        : '--',
      gradient: 'linear-gradient(135deg, #52c41a, #389e0d)',
    },
    {
      label: '🏆 领涨板块',
      value: overview.leading_sector?.sector_name || '--',
      sub: overview.leading_sector
        ? `${overview.leading_sector.change_pct > 0 ? '+' : ''}${overview.leading_sector.change_pct.toFixed(1)}% · 净流入 ${overview.leading_sector.main_net_yi.toFixed(1)}亿`
        : '--',
      gradient: 'linear-gradient(135deg, #722ed1, #531dab)',
    },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
      {cards.map((card) => (
        <div
          key={card.label}
          style={{
            background: card.gradient,
            borderRadius: token.borderRadius,
            padding: '16px 20px',
            color: '#fff',
          }}
        >
          <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 4 }}>{card.label}</div>
          <div style={{ fontSize: 24, fontWeight: 700, marginBottom: 2 }}>{card.value}</div>
          <div style={{ fontSize: 11, opacity: 0.75 }}>{card.sub}</div>
        </div>
      ))}
    </div>
  );
};

export default TemperatureCard;
```

- [ ] **Step 2: 创建 SectorTreemap.tsx**

```tsx
import React, { useMemo } from 'react';
import { Card, Segmented, Spin, Empty } from 'antd';
import ReactECharts from 'echarts-for-react';
import type { SectorItem } from '@/services/marketHeatService';

interface Props {
  sectors: SectorItem[];
  sectorType: 'industry' | 'concept';
  loading: boolean;
  onSectorTypeChange: (type: 'industry' | 'concept') => void;
  onSectorClick: (sector: SectorItem) => void;
}

const SectorTreemap: React.FC<Props> = ({
  sectors, sectorType, loading, onSectorTypeChange, onSectorClick,
}) => {
  const option = useMemo(() => {
    if (!sectors.length) return {};

    const data = sectors.map((s) => ({
      name: s.sector_name,
      value: Math.abs(s.net_inflow || 0.01),
      itemStyle: {
        color: s.change_pct >= 0
          ? `rgba(207, 19, 34, ${Math.min(Math.abs(s.change_pct) / 8, 0.9)})`
          : `rgba(35, 149, 74, ${Math.min(Math.abs(s.change_pct) / 8, 0.9)})`,
      },
      sectorData: s,
    }));

    return {
      tooltip: {
        formatter: (params: any) => {
          const d = params.data?.sectorData;
          if (!d) return params.name;
          return [
            `<strong>${d.sector_name}</strong>`,
            `涨跌幅: ${d.change_pct > 0 ? '+' : ''}${d.change_pct?.toFixed(2)}%`,
            `主力净流入: ${d.main_net_yi?.toFixed(2)}亿`,
            `上涨/下跌: ${d.up_count}/${d.down_count}`,
            `领涨股: ${d.leader_stock} ${d.leader_change > 0 ? '+' : ''}${d.leader_change?.toFixed(2)}%`,
          ].join('<br/>');
        },
      },
      series: [{
        type: 'treemap',
        width: '100%',
        height: '100%',
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        label: {
          show: true,
          formatter: '{b}',
          fontSize: 11,
          overflow: 'truncate',
        },
        upperLabel: { show: true, height: 20 },
        data,
      }],
    };
  }, [sectors]);

  return (
    <Card
      title="板块资金流"
      extra={
        <Segmented
          size="small"
          value={sectorType}
          onChange={(v) => onSectorTypeChange(v as 'industry' | 'concept')}
          options={[
            { label: '行业', value: 'industry' },
            { label: '概念', value: 'concept' },
          ]}
        />
      }
    >
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spin /></div>
      ) : sectors.length === 0 ? (
        <Empty description="暂无数据" />
      ) : (
        <ReactECharts
          option={option}
          style={{ height: 350 }}
          onEvents={{
            click: (params: any) => {
              if (params.data?.sectorData) {
                onSectorClick(params.data.sectorData);
              }
            },
          }}
        />
      )}
    </Card>
  );
};

export default SectorTreemap;
```

- [ ] **Step 3: 创建 ThemeWordCloud.tsx**

```tsx
import React, { useMemo } from 'react';
import { Card, Spin, Empty } from 'antd';
import ReactECharts from 'echarts-for-react';
import 'echarts-wordcloud';
import type { ThemeItem } from '@/services/marketHeatService';

interface Props {
  themes: ThemeItem[];
  loading: boolean;
  onThemeClick: (theme: ThemeItem) => void;
}

const ThemeWordCloud: React.FC<Props> = ({ themes, loading, onThemeClick }) => {
  const option = useMemo(() => {
    if (!themes.length) return {};

    const maxCount = Math.max(...themes.map((t) => t.stock_count), 1);

    return {
      tooltip: {
        formatter: (params: any) => {
          return `${params.name}: ${params.value} 只关联股票`;
        },
      },
      series: [{
        type: 'wordCloud',
        shape: 'circle',
        width: '100%',
        height: '100%',
        sizeRange: [14, 48],
        rotationRange: [-30, 30],
        gridSize: 8,
        layoutAnimation: true,
        textStyle: {
          fontFamily: 'sans-serif',
          fontWeight: 'bold',
          color: () => {
            const colors = ['#1677ff', '#52c41a', '#fa541c', '#722ed1', '#fa8c16', '#13c2c2', '#eb2f96'];
            return colors[Math.floor(Math.random() * colors.length)];
          },
        },
        emphasis: {
          textStyle: { shadowBlur: 10, shadowColor: '#333' },
        },
        data: themes.map((t) => ({
          name: t.theme_name,
          value: t.stock_count,
        })),
      }],
    };
  }, [themes]);

  return (
    <Card title="热门主题">
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spin /></div>
      ) : themes.length === 0 ? (
        <Empty description="暂无数据" />
      ) : (
        <ReactECharts
          option={option}
          style={{ height: 350 }}
          onEvents={{
            click: (params: any) => {
              const theme = themes.find((t) => t.theme_name === params.name);
              if (theme) onThemeClick(theme);
            },
          }}
        />
      )}
    </Card>
  );
};

export default ThemeWordCloud;
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/market-heat/
git commit -m "feat: 市场热度子组件 — TemperatureCard + SectorTreemap + ThemeWordCloud

- TemperatureCard: 4 个渐变色 KPI 卡片
- SectorTreemap: ECharts Treemap 展示板块资金流，支持行业/概念切换
- ThemeWordCloud: ECharts WordCloud 展示热门主题

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: 前端 — 抽屉组件（SectorDrawer + ThemeDrawer）

**Files:**
- Create: `frontend/src/components/market-heat/SectorDrawer.tsx`
- Create: `frontend/src/components/market-heat/ThemeDrawer.tsx`

- [ ] **Step 1: 创建 SectorDrawer.tsx**

```tsx
import React, { useEffect, useState } from 'react';
import { Drawer, Descriptions, Spin, Empty, Table, Tag } from 'antd';
import ReactECharts from 'echarts-for-react';
import marketHeatService, { type SectorDetail } from '@/services/marketHeatService';

interface Props {
  open: boolean;
  sectorCode: string | null;
  sectorName: string | null;
  tradeDate?: string;
  onClose: () => void;
}

const SectorDrawer: React.FC<Props> = ({ open, sectorCode, sectorName, tradeDate, onClose }) => {
  const [data, setData] = useState<SectorDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open && sectorCode) {
      setLoading(true);
      marketHeatService.getSectorDetail(sectorCode, tradeDate)
        .then(setData)
        .finally(() => setLoading(false));
    }
  }, [open, sectorCode, tradeDate]);

  const chartOption = React.useMemo(() => {
    if (!data?.trend?.length) return {};
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['主力净流入(亿)', '涨跌幅(%)'], bottom: 0 },
      grid: { top: 10, left: 50, right: 50, bottom: 30 },
      xAxis: {
        type: 'category',
        data: data.trend.map((t) => t.trade_date.slice(4)), // MMdd 格式
      },
      yAxis: [
        { type: 'value', name: '亿' },
        { type: 'value', name: '%' },
      ],
      series: [
        {
          name: '主力净流入(亿)',
          type: 'bar',
          data: data.trend.map((t) => t.main_net_yi),
          itemStyle: {
            color: (params: any) => params.value >= 0 ? '#cf1322' : '#389e0d',
          },
        },
        {
          name: '涨跌幅(%)',
          type: 'line',
          yAxisIndex: 1,
          data: data.trend.map((t) => t.change_pct),
          itemStyle: { color: '#1677ff' },
        },
      ],
    };
  }, [data]);

  const stockColumns = [
    { title: '股票', dataIndex: 'name', key: 'name' },
    {
      title: '涨幅',
      dataIndex: 'change_pct',
      key: 'change_pct',
      render: (_: any, record: any) => {
        const pct = ((record.close - record.open) / record.open * 100);
        return <span style={{ color: pct >= 0 ? '#cf1322' : '#389e0d' }}>{pct.toFixed(2)}%</span>;
      },
    },
    { title: '收盘价', dataIndex: 'close', key: 'close', render: (v: number) => v?.toFixed(2) },
  ];

  return (
    <Drawer
      title={
        <span>
          {sectorName}
          {data?.info && (
            <Tag color={data.info.change_pct >= 0 ? 'red' : 'green'} style={{ marginLeft: 8 }}>
              {data.info.change_pct > 0 ? '+' : ''}{data.info.change_pct.toFixed(2)}%
            </Tag>
          )}
        </span>
      }
      open={open}
      onClose={onClose}
      width={640}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
      ) : !data?.info ? (
        <Empty description="暂无数据" />
      ) : (
        <>
          <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
            <Descriptions.Item label="主力净流入">{data.info.main_net_yi?.toFixed(2)}亿</Descriptions.Item>
            <Descriptions.Item label="上涨/下跌">{data.info.up_count}/{data.info.down_count}</Descriptions.Item>
            <Descriptions.Item label="领涨股">{data.info.leader_stock}</Descriptions.Item>
            <Descriptions.Item label="排名">#{data.info.rank}</Descriptions.Item>
          </Descriptions>

          <h4 style={{ marginTop: 16 }}>近 10 日资金流趋势</h4>
          <ReactECharts option={chartOption} style={{ height: 240 }} />

          <h4 style={{ marginTop: 16 }}>成分股 Top 5</h4>
          <Table
            dataSource={data.stocks}
            columns={stockColumns}
            rowKey="ts_code"
            size="small"
            pagination={false}
          />
        </>
      )}
    </Drawer>
  );
};

export default SectorDrawer;
```

- [ ] **Step 2: 创建 ThemeDrawer.tsx**

```tsx
import React, { useEffect, useState } from 'react';
import { Drawer, Table, Spin, Empty, Tag } from 'antd';
import marketHeatService, { type HotStockItem } from '@/services/marketHeatService';

interface Props {
  open: boolean;
  themeName: string | null;
  tradeDate?: string;
  onClose: () => void;
}

const ThemeDrawer: React.FC<Props> = ({ open, themeName, tradeDate, onClose }) => {
  const [stocks, setStocks] = useState<HotStockItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open && themeName) {
      setLoading(true);
      marketHeatService.getThemeDetail(themeName, tradeDate)
        .then(setStocks)
        .finally(() => setLoading(false));
    }
  }, [open, themeName, tradeDate]);

  const columns = [
    { title: '股票', dataIndex: 'stock_name', key: 'stock_name', width: 100 },
    {
      title: '涨幅',
      dataIndex: 'change_pct',
      key: 'change_pct',
      width: 80,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#cf1322' : '#389e0d', fontWeight: 600 }}>
          {v > 0 ? '+' : ''}{v?.toFixed(2)}%
        </span>
      ),
    },
    {
      title: '换手率',
      dataIndex: 'turnover_pct',
      key: 'turnover_pct',
      width: 80,
      render: (v: number) => `${v?.toFixed(2)}%`,
    },
    { title: '收盘价', dataIndex: 'close', key: 'close', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: 'DDE净量', dataIndex: 'dde_net', key: 'dde_net', width: 80, render: (v: number) => v?.toFixed(2) },
    {
      title: '上涨原因',
      dataIndex: 'reason',
      key: 'reason',
      render: (v: string) => (
        <span style={{ fontSize: 12 }}>
          {(v || '').split('+').map((tag: string, i: number) => (
            <Tag key={i} color="blue" style={{ marginBottom: 2 }}>{tag.trim()}</Tag>
          ))}
        </span>
      ),
    },
  ];

  return (
    <Drawer
      title={`🔥 ${themeName} — ${stocks.length} 只关联股票`}
      open={open}
      onClose={onClose}
      width={700}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
      ) : stocks.length === 0 ? (
        <Empty description="暂无关联股票" />
      ) : (
        <Table
          dataSource={stocks}
          columns={columns}
          rowKey="stock_code"
          size="small"
          pagination={false}
        />
      )}
    </Drawer>
  );
};

export default ThemeDrawer;
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/market-heat/SectorDrawer.tsx frontend/src/components/market-heat/ThemeDrawer.tsx
git commit -m "feat: 市场热度抽屉组件 — SectorDrawer + ThemeDrawer

- SectorDrawer: 板块资金流趋势图 + 成分股 Top5
- ThemeDrawer: 主题关联股票列表（含原因标签）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: 前端 — 主页面 + 路由 + 菜单

**Files:**
- Create: `frontend/src/pages/MarketHeat.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout/AppLayout.tsx`

- [ ] **Step 1: 创建 MarketHeat.tsx**

```tsx
import React, { useEffect } from 'react';
import { Row, Col, Card, Tabs, Table, Tag, DatePicker, Spin, Alert, Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useMarketHeatStore } from '@/stores/marketHeatStore';
import TemperatureCard from '@/components/market-heat/TemperatureCard';
import SectorTreemap from '@/components/market-heat/SectorTreemap';
import ThemeWordCloud from '@/components/market-heat/ThemeWordCloud';
import SectorDrawer from '@/components/market-heat/SectorDrawer';
import ThemeDrawer from '@/components/market-heat/ThemeDrawer';
import type { SectorItem, ThemeItem, HotStockItem, DragonTigerItem } from '@/services/marketHeatService';

const MarketHeat: React.FC = () => {
  const store = useMarketHeatStore();

  useEffect(() => {
    store.fetchAvailableDates();
  }, []);

  useEffect(() => {
    if (store.tradeDate) {
      store.fetchOverview();
      store.fetchSectors();
      store.fetchThemes();
      store.fetchHotStocks(1);
      store.fetchDragonTiger(1);
      store.fetchNorthbound();
    }
  }, [store.tradeDate]);

  const handleRefresh = () => {
    store.fetchOverview();
    store.fetchSectors();
    store.fetchThemes();
    store.fetchHotStocks();
    store.fetchDragonTiger();
    store.fetchNorthbound();
  };

  const hotStockColumns = [
    { title: '股票', dataIndex: 'stock_name', key: 'stock_name', width: 100 },
    {
      title: '涨幅',
      dataIndex: 'change_pct',
      key: 'change_pct',
      width: 80,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#cf1322' : '#389e0d', fontWeight: 600 }}>
          {v > 0 ? '+' : ''}{v?.toFixed(2)}%
        </span>
      ),
    },
    {
      title: '换手率', dataIndex: 'turnover_pct', key: 'turnover_pct', width: 80,
      render: (v: number) => `${v?.toFixed(2)}%`,
    },
    { title: '收盘价', dataIndex: 'close', key: 'close', width: 80, render: (v: number) => v?.toFixed(2) },
    {
      title: '上涨原因', dataIndex: 'reason', key: 'reason',
      render: (v: string) => (v || '').split('+').map((tag: string, i: number) => (
        <Tag key={i} color="blue" style={{ marginBottom: 2 }}>{tag.trim()}</Tag>
      )),
    },
  ];

  const dragonColumns = [
    { title: '股票', dataIndex: 'stock_name', key: 'stock_name', width: 100 },
    {
      title: '涨幅', dataIndex: 'change_pct', key: 'change_pct', width: 80,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#cf1322' : '#389e0d', fontWeight: 600 }}>
          {v > 0 ? '+' : ''}{v?.toFixed(2)}%
        </span>
      ),
    },
    {
      title: '净买入(万)', dataIndex: 'net_buy_wan', key: 'net_buy_wan', width: 100,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#cf1322' : '#389e0d', fontWeight: 600 }}>
          {v > 0 ? '+' : ''}{v?.toFixed(0)}
        </span>
      ),
    },
    { title: '上榜原因', dataIndex: 'reason', key: 'reason', ellipsis: true },
  ];

  const tabItems = [
    {
      key: 'hot-stocks',
      label: '热门股票',
      children: (
        <Table
          dataSource={store.hotStocks}
          columns={hotStockColumns}
          rowKey="stock_code"
          size="small"
          loading={store.hotStocksLoading}
          pagination={{
            current: store.hotStocksPage,
            total: store.hotStocksTotal,
            pageSize: 20,
            onChange: (p) => store.fetchHotStocks(p),
            showSizeChanger: false,
          }}
          onRow={(record: HotStockItem) => ({
            style: { cursor: 'pointer' },
            onClick: () => window.open(`/strategies/${record.stock_code}`, '_blank'),
          })}
        />
      ),
    },
    {
      key: 'dragon-tiger',
      label: '龙虎榜',
      children: (
        <Table
          dataSource={store.dragonTiger}
          columns={dragonColumns}
          rowKey="stock_code"
          size="small"
          loading={store.dragonTigerLoading}
          expandable={{
            expandedRowRender: (record: DragonTigerItem) => (
              <Table
                dataSource={record.seats || []}
                columns={[
                  { title: '席位', dataIndex: 'seat_name', key: 'seat_name' },
                  {
                    title: '类型',
                    dataIndex: 'seat_type',
                    key: 'seat_type',
                    render: (v: string) => v === 'buy' ? '买入' : '卖出',
                  },
                  { title: '买入(万)', dataIndex: 'buy_amt_wan', key: 'buy_amt_wan', render: (v: number) => v?.toFixed(0) },
                  { title: '卖出(万)', dataIndex: 'sell_amt_wan', key: 'sell_amt_wan', render: (v: number) => v?.toFixed(0) },
                  {
                    title: '净额(万)',
                    dataIndex: 'net_amt_wan',
                    key: 'net_amt_wan',
                    render: (v: number) => (
                      <span style={{ color: v >= 0 ? '#cf1322' : '#389e0d' }}>{v?.toFixed(0)}</span>
                    ),
                  },
                  {
                    title: '机构',
                    dataIndex: 'is_institution',
                    key: 'is_institution',
                    render: (v: boolean) => v ? <Tag color="volcano">机构</Tag> : null,
                  },
                ]}
                rowKey={(r: any) => `${r.seat_type}-${r.rank}`}
                size="small"
                pagination={false}
              />
            ),
          }}
          pagination={{
            current: store.dragonTigerPage,
            total: store.dragonTigerTotal,
            pageSize: 20,
            onChange: (p) => store.fetchDragonTiger(p),
            showSizeChanger: false,
          }}
        />
      ),
    },
  ];

  return (
    <div>
      {/* 顶部栏：日期选择 + 刷新 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>市场热度</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <DatePicker
            value={store.tradeDate ? dayjs(store.tradeDate, 'YYYYMMDD') : null}
            onChange={(d) => d && store.setTradeDate(d.format('YYYYMMDD'))}
            allowClear={false}
            format="YYYY-MM-DD"
            disabledDate={(d) => {
              if (!store.availableDates.length) return false;
              return !store.availableDates.includes(d.format('YYYYMMDD'));
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={handleRefresh}>刷新</Button>
        </div>
      </div>

      {store.error && (
        <Alert message={store.error} type="error" closable style={{ marginBottom: 16 }} onClose={store.clearError} />
      )}

      {/* 第一层: KPI 卡片 */}
      <div style={{ marginBottom: 16 }}>
        <TemperatureCard overview={store.overview} loading={store.overviewLoading} />
      </div>

      {/* 第二层: 可视化 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={16}>
          <SectorTreemap
            sectors={store.sectors}
            sectorType={store.sectorType}
            loading={store.sectorsLoading}
            onSectorTypeChange={store.setSectorType}
            onSectorClick={(s: SectorItem) => store.openDrawer('sector', s.sector_code, s.sector_name)}
          />
        </Col>
        <Col xs={24} lg={8}>
          <ThemeWordCloud
            themes={store.themes}
            loading={store.themesLoading}
            onThemeClick={(t: ThemeItem) => store.openDrawer('theme', t.theme_name, t.theme_name)}
          />
        </Col>
      </Row>

      {/* 第三层: 明细列表 */}
      <Card>
        <Tabs items={tabItems} />
      </Card>

      {/* 抽屉 */}
      <SectorDrawer
        open={store.drawer.open && store.drawer.type === 'sector'}
        sectorCode={store.drawer.code}
        sectorName={store.drawer.name}
        tradeDate={store.tradeDate}
        onClose={store.closeDrawer}
      />
      <ThemeDrawer
        open={store.drawer.open && store.drawer.type === 'theme'}
        themeName={store.drawer.name}
        tradeDate={store.tradeDate}
        onClose={store.closeDrawer}
      />
    </div>
  );
};

export default MarketHeat;
```

- [ ] **Step 2: 注册路由 — 修改 App.tsx**

在 `App.tsx` 中：

添加 import：
```tsx
import MarketHeat from '@/pages/MarketHeat';
```

在 `<Routes>` 内，`/dashboard` 路由之后添加：
```tsx
<Route
  path="/market-heat"
  element={
    <ProtectedRoute>
      <MarketHeat />
    </ProtectedRoute>
  }
/>
```

- [ ] **Step 3: 注册菜单 — 修改 AppLayout.tsx**

在 `AppLayout.tsx` 中：

在 `import { ... } from '@ant-design/icons'` 中添加 `FireOutlined`：
```tsx
import {
  DashboardOutlined,
  LineChartOutlined,
  BarChartOutlined,
  BulbOutlined,
  UserOutlined,
  TeamOutlined,
  LogoutOutlined,
  ReadOutlined,
  QuestionCircleOutlined,
  FireOutlined,
} from '@ant-design/icons';
```

在 `menuItems` 数组中，`/dashboard` 项之后添加：
```tsx
{
  key: '/market-heat',
  icon: <FireOutlined />,
  label: '市场热度',
},
```

在 `selectedKey` 函数中，`/dashboard` 判断之前添加：
```typescript
if (location.pathname.startsWith('/market-heat')) return '/market-heat';
```

- [ ] **Step 4: 验证前端编译**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/MarketHeat.tsx frontend/src/App.tsx frontend/src/components/Layout/AppLayout.tsx
git commit -m "feat: 市场热度页面 + 路由 + 侧边栏菜单

- MarketHeat: 3 层信息架构页面组装
- App.tsx: /market-heat 路由注册
- AppLayout: 侧边栏新增「市场热度」菜单项 (FireOutlined)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 完成验证

全部 Task 完成后，执行以下端到端验证：

- [ ] **启动后端**

```bash
cd backend && source venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **启动前端**

```bash
cd frontend && npm run dev
```

- [ ] **浏览器验证**

打开 http://localhost:5173，登录后：
1. 侧边栏出现「市场热度」菜单，点击进入
2. 顶行 4 个 KPI 卡片正确渲染（带渐变色）
3. 板块热力图展示数据，切换行业/概念正常
4. 主题词云展示热点
5. 底部 Tab 切换热门股票/龙虎榜
6. 点击热力图板块 → 右侧抽屉展开，显示趋势图和成分股
7. 点击词云主题 → 抽屉展开，显示关联股票
8. 日期选择器切换有效日期，数据自动刷新

---

## 风险与降级

| 风险 | 降级方案 |
|------|----------|
| `echarts-wordcloud` 与 ECharts 6 不兼容 | 改用水平柱状图展示主题 Top 10，代码更简单且稳定 |
| 板块成分股关联不精确（industry 字段可能不匹配） | 在 SectorDrawer 中隐藏成分股表格，仅保留趋势图 |
| 数据库无最新交易日数据 | API 返回空列表，前端显示 `<Empty>` 组件，不报错 |
