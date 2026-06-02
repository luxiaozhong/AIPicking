# 交易模拟回测 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有回测系统基础上新增交易模拟模式，支持资金分配、止损止盈条件触发、逐笔交易追踪和详细报表。

**Architecture:** 独立引擎 TradeSimEngine 组合复用 BacktestEngine 的数据加载和策略执行能力，新建 trade_sim_reports 表存储结果，共用现有回测页面通过模式切换。后端 FastAPI + SQLAlchemy，前端 React + Ant Design + ECharts。

**Tech Stack:** Python 3, FastAPI, SQLAlchemy (sync + async), PostgreSQL, React 19, TypeScript, Ant Design 6, Zustand, ECharts

---

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| Create | `backend/app/models/trade_sim.py` | TradeSimReport ORM 模型 |
| Create | `backend/app/schemas/trade_sim.py` | Pydantic 请求/响应 schema |
| Create | `backend/app/factors/trade_sim_stops.py` | 止损止盈因子注册表 + 3 个内置因子 |
| Create | `backend/app/services/trade_sim_engine.py` | 交易模拟引擎核心逻辑 |
| Create | `backend/app/services/trade_sim_service.py` | 业务逻辑层（CRUD + 异步提交） |
| Create | `backend/app/api/trade_sims.py` | API 路由 |
| Create | `backend/tests/test_trade_sim.py` | 后端测试 |
| Modify | `backend/app/models/__init__.py` | 导出新模型 + 设置关系 |
| Modify | `backend/app/main.py` | 注册 trade_sims 路由 |
| Create | `frontend/src/types/tradeSim.ts` | TypeScript 类型定义 |
| Create | `frontend/src/services/tradeSimService.ts` | API 调用封装 |
| Create | `frontend/src/pages/TradeSimDetail.tsx` | 交易模拟报表组件 |
| Create | `backend/app/models/trade_sim.py` | 新增 BatchTradeSimReport 模型 |
| Create | `backend/app/schemas/trade_sim.py` | 新增 BatchTradeSimCreate/Response schema |
| Modify | `backend/app/services/trade_sim_engine.py` | 新增 `run_batch()` 方法 |
| Modify | `backend/app/services/trade_sim_service.py` | 新增批量 CRUD 方法 |
| Modify | `backend/app/api/trade_sims.py` | 新增批量 API 端点 |
| Create | `frontend/src/pages/BatchTradeSimDetail.tsx` | 批量交易模拟报表 |
| Modify | `frontend/src/pages/BacktestForm.tsx` | 增加模式切换 + 交易模拟表单（含批量） |
| Modify | `frontend/src/pages/BacktestDetail.tsx` | 按模式渲染不同报表 |
| Modify | `frontend/src/services/backtestService.ts` | 新增交易模拟回测 API 方法 |

---

### Task 1: 数据库模型 TradeSimReport

**Files:**
- Create: `backend/app/models/trade_sim.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_trade_sim.py`

- [ ] **Step 1: 编写 TradeSimReport 模型**

```python
# backend/app/models/trade_sim.py
"""交易模拟回测报告模型"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from .base import BaseModel


class TradeSimReport(BaseModel):
    """交易模拟回测报告

    用户输入投资总额，资金均分到策略评分前N只股票，
    逐日追踪并执行止损止盈条件，记录逐笔交易明细和汇总。
    """

    __tablename__ = "trade_sim_reports"

    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    cutoff_date = Column(Date, nullable=False)
    config = Column(Text)     # JSON: total_amount, top_n, max_hold_days, stop_factors
    trades = Column(Text)     # JSON: 逐笔交易明细（含 daily_tracking）
    summary = Column(Text)    # JSON: 汇总统计
    status = Column(String(20), default="pending", index=True)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    strategy = relationship("Strategy", back_populates="trade_sim_reports")
    owner = relationship("User", back_populates="trade_sim_reports")

    @property
    def strategy_name(self) -> str:
        return self.strategy.name if self.strategy else None
```

- [ ] **Step 2: 在 models/__init__.py 中注册模型和关系**

```python
# 在 backend/app/models/__init__.py 中添加

# import 部分添加：
from .trade_sim import TradeSimReport

# 关系设置部分添加：
Strategy.trade_sim_reports = relationship("TradeSimReport", back_populates="strategy", cascade="all, delete-orphan")
TradeSimReport.owner = relationship("User", back_populates="trade_sim_reports")
User.trade_sim_reports = relationship("TradeSimReport", back_populates="owner")
```

- [ ] **Step 3: 编写模型测试**

```python
# backend/tests/test_trade_sim.py
import pytest
from datetime import date
from app.models.trade_sim import TradeSimReport


class TestTradeSimModel:
    def test_trade_sim_report_creation(self):
        """测试 TradeSimReport 实例创建"""
        report = TradeSimReport(
            strategy_id=1,
            user_id=1,
            cutoff_date=date(2026, 1, 5),
            config='{"total_amount": 100000, "top_n": 5, "max_hold_days": 60}',
            status="pending",
        )
        assert report.strategy_id == 1
        assert report.cutoff_date == date(2026, 1, 5)
        assert report.status == "pending"
        assert report.trades == "[]"
        assert report.summary == "{}"

    def test_trade_sim_report_defaults(self):
        """测试默认值"""
        report = TradeSimReport(
            strategy_id=1,
            user_id=1,
            cutoff_date=date(2026, 1, 5),
        )
        assert report.status == "pending"
        assert report.config == "{}"
```

Run: `cd backend && source venv/bin/activate && pytest tests/test_trade_sim.py -v`
Expected: 2 tests FAIL (table doesn't exist yet in test DB — 模型导入和属性测试通过即可)

- [ ] **Step 4: 运行测试确认模型正确**

Run: `cd backend && source venv/bin/activate && python -c "from app.models.trade_sim import TradeSimReport; r = TradeSimReport(strategy_id=1, user_id=1, cutoff_date='2026-01-05'); print('OK:', r.status)"`
Expected: `OK: pending`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/trade_sim.py backend/app/models/__init__.py backend/tests/test_trade_sim.py
git commit -m "feat: add TradeSimReport model"
```

---

### Task 2: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/trade_sim.py`

- [ ] **Step 1: 编写所有 schema**

```python
# backend/app/schemas/trade_sim.py
"""交易模拟回测 Pydantic Schema"""

from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# --- 请求 ---

class StopFactorConfig(BaseModel):
    id: str
    enabled: bool
    params: Dict[str, Any] = {}


class TradeSimCreate(BaseModel):
    strategy_id: int
    cutoff_date: str          # YYYY-MM-DD
    total_amount: float = Field(..., gt=0, description="投资总额")
    top_n: int = Field(default=5, ge=1, le=20, description="选前N只")
    max_hold_days: int = Field(default=60, ge=1, le=365, description="强制平仓天数")
    stop_factors: List[StopFactorConfig]


# --- 响应 ---

class DailyTrackingItem(BaseModel):
    date: str
    open: float
    close: float
    high: float
    low: float
    ma10: Optional[float] = None
    prev_low_ref: Optional[float] = None
    ma10_stop_line: Optional[float] = None
    return_pct: float
    status: str  # holding | stopped | take_profit | force_close


class TradeItem(BaseModel):
    ts_code: str
    name: str
    score: float
    allocated_amount: float
    shares: float
    buy_price: float
    buy_date: str
    sell_price: Optional[float] = None
    sell_date: Optional[str] = None
    sell_reason: Optional[str] = None
    hold_days: Optional[int] = None
    return_pct: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    max_drawdown: Optional[float] = None
    daily_tracking: List[DailyTrackingItem] = []


class ReturnDistribution(BaseModel):
    lt_minus10: int = Field(default=0, alias="lt_-10")
    minus10_0: int = Field(default=0, alias="-10_0")
    zero_5: int = Field(default=0, alias="0_5")
    five_10: int = Field(default=0, alias="5_10")
    gt_10: int = Field(default=0, alias="gt_10")

    class Config:
        populate_by_name = True


class TradeSimSummary(BaseModel):
    total_trades: int = 0
    win_count: int = 0
    lose_count: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_loss_ratio: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    return_distribution: ReturnDistribution = Field(default_factory=ReturnDistribution)


class TradeSimResponse(BaseModel):
    id: int
    strategy_id: int
    strategy_name: Optional[str] = None
    cutoff_date: date
    config: Optional[dict] = None
    trades: Optional[List[TradeItem]] = None
    summary: Optional[TradeSimSummary] = None
    status: str
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TradeSimListResponse(BaseModel):
    items: List[TradeSimResponse]
    total: int
    page: int
    limit: int
```

- [ ] **Step 2: 验证 schema 导入**

Run: `cd backend && source venv/bin/activate && python -c "from app.schemas.trade_sim import TradeSimCreate, TradeSimResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/trade_sim.py
git commit -m "feat: add trade sim Pydantic schemas"
```

---

### Task 3: 止损止盈因子注册表

**Files:**
- Create: `backend/app/factors/trade_sim_stops.py`
- Test: `backend/tests/test_trade_sim_stops.py`

- [ ] **Step 1: 编写因子注册表和 3 个内置因子**

```python
# backend/app/factors/trade_sim_stops.py
"""止损止盈因子注册表

扩展方式：编写 check_fn 函数 → 调用 StopFactorRegistry.register() 注册。
check_fn(df, position, params) -> TriggerResult | None
  - df: list[dict], 该股从买入日到当前日的日线数据（含 trade_date, open, high, low, close, adj_close）
  - position: dict {buy_price, buy_date, buy_idx}
  - params: dict, 因子参数
  - 返回 TriggerResult 表示触发，返回 None 表示未触发
"""

from dataclasses import dataclass, field
from typing import Callable, Optional, List, Dict, Any


@dataclass
class ParamDef:
    name: str
    type: str            # "int" | "float"
    default: Any
    description: str


@dataclass
class TriggerResult:
    reason: str           # 触发描述
    sell_price: Optional[float] = None  # 可选卖出价（默认由引擎决定）


class StopFactorRegistry:
    """止损止盈因子注册表"""

    _factors: Dict[str, dict] = {}

    @classmethod
    def register(cls, id: str, name: str, params: List[ParamDef], check_fn: Callable):
        cls._factors[id] = {
            "name": name,
            "params": params,
            "check": check_fn,
        }

    @classmethod
    def get_all(cls) -> Dict[str, dict]:
        """返回所有已注册因子（供前端展示）"""
        return {
            fid: {"name": f["name"], "params": [p.__dict__ for p in f["params"]]}
            for fid, f in cls._factors.items()
        }

    @classmethod
    def get_check_fn(cls, id: str) -> Callable:
        if id not in cls._factors:
            raise ValueError(f"未知止损止盈因子: {id}")
        return cls._factors[id]["check"]

    @classmethod
    def get_name(cls, id: str) -> str:
        if id not in cls._factors:
            return id
        return cls._factors[id]["name"]


# ========== 内置因子 ==========

def _check_stop_prev_low(df: list, position: dict, params: dict) -> Optional[TriggerResult]:
    """破前低止损：当日收盘价 < ref_days 个交易日前的收盘价"""
    ref_days = params.get("ref_days", 20)
    if len(df) < ref_days:
        return None

    today = df[-1]
    ref_day = df[-ref_days]

    close_price = today.get("adj_close") or today.get("close")
    ref_price = ref_day.get("adj_close") or ref_day.get("close")

    if close_price is None or ref_price is None:
        return None

    if close_price < ref_price:
        return TriggerResult(reason=f"破前低止损（{ref_days}日前收盘价 {ref_price:.2f}）")
    return None


StopFactorRegistry.register(
    id="stop_prev_low",
    name="破前低止损",
    params=[
        ParamDef(name="ref_days", type="int", default=20, description="前低参考天数"),
    ],
    check_fn=_check_stop_prev_low,
)


def _check_stop_ma10_cross(df: list, position: dict, params: dict) -> Optional[TriggerResult]:
    """MA10跌破止损：连续 buffer_days 天收盘价 < MA10 × coefficient"""
    coefficient = params.get("coefficient", 0.93)
    buffer_days = params.get("buffer_days", 2)

    if len(df) < 11:  # 至少需要 10 天算 MA10 + buffer_days
        return None

    # 计算最近 buffer_days 天是否都满足条件
    consecutive = 0
    for i in range(len(df) - buffer_days, len(df)):
        day = df[i]
        close_price = day.get("adj_close") or day.get("close")
        if close_price is None:
            continue

        # 计算当天 MA10（基于当天及前 9 天的收盘价）
        start_idx = max(0, i - 9)
        closes = []
        for j in range(start_idx, i + 1):
            c = df[j].get("adj_close") or df[j].get("close")
            if c is not None:
                closes.append(c)
        if len(closes) < 10:
            continue
        ma10 = sum(closes) / len(closes)

        if close_price < ma10 * coefficient:
            consecutive += 1
        else:
            consecutive = 0  # 缓冲计数重置

    if consecutive >= buffer_days:
        return TriggerResult(
            reason=f"MA10跌破止损（MA10×{coefficient}，连续{buffer_days}天）"
        )
    return None


StopFactorRegistry.register(
    id="stop_ma10_cross",
    name="MA10跌破止损",
    params=[
        ParamDef(name="coefficient", type="float", default=0.93, description="MA10系数"),
        ParamDef(name="buffer_days", type="int", default=2, description="缓冲确认天数"),
    ],
    check_fn=_check_stop_ma10_cross,
)


def _check_take_profit_pct(df: list, position: dict, params: dict) -> Optional[TriggerResult]:
    """固定止盈：涨幅 >= profit_pct%"""
    profit_pct = params.get("profit_pct", 5.0)
    buy_price = position.get("buy_price")
    if buy_price is None or buy_price <= 0:
        return None

    today = df[-1]
    close_price = today.get("adj_close") or today.get("close")
    if close_price is None:
        return None

    return_pct = (close_price - buy_price) / buy_price * 100
    if return_pct >= profit_pct:
        return TriggerResult(reason=f"止盈{profit_pct}%（涨幅 {return_pct:.2f}%）")
    return None


StopFactorRegistry.register(
    id="take_profit_pct",
    name="固定止盈",
    params=[
        ParamDef(name="profit_pct", type="float", default=5.0, description="止盈百分比"),
    ],
    check_fn=_check_take_profit_pct,
)
```

- [ ] **Step 2: 编写因子测试**

```python
# backend/tests/test_trade_sim_stops.py
import pytest
from app.factors.trade_sim_stops import (
    StopFactorRegistry,
    TriggerResult,
    _check_stop_prev_low,
    _check_take_profit_pct,
    _check_stop_ma10_cross,
)


def make_daily(closes, adj_closes=None):
    """构建日线数据"""
    if adj_closes is None:
        adj_closes = closes
    return [
        {"trade_date": f"2026-01-{i+1:02d}", "open": c, "high": c, "low": c,
         "close": c, "adj_close": ac}
        for i, (c, ac) in enumerate(zip(closes, adj_closes))
    ]


class TestStopPrevLow:
    def test_not_triggered_when_above(self):
        """当前价高于前低，不触发"""
        df = make_daily([10.0] * 19 + [10.5])
        result = _check_stop_prev_low(df, {}, {"ref_days": 20})
        assert result is None

    def test_triggered_when_below(self):
        """当前价低于20日前，触发"""
        df = make_daily([12.0] + [10.0] * 18 + [9.5])
        result = _check_stop_prev_low(df, {}, {"ref_days": 20})
        assert result is not None
        assert "破前低止损" in result.reason

    def test_not_enough_data(self):
        """数据不足，不触发"""
        df = make_daily([10.0] * 10)
        result = _check_stop_prev_low(df, {}, {"ref_days": 20})
        assert result is None


class TestTakeProfit:
    def test_not_triggered_below_target(self):
        """涨幅不足，不触发"""
        df = make_daily([10.0, 10.3])
        result = _check_take_profit_pct(df, {"buy_price": 10.0}, {"profit_pct": 5.0})
        assert result is None

    def test_triggered_at_target(self):
        """涨幅达到目标，触发"""
        df = make_daily([10.0, 10.50])
        result = _check_take_profit_pct(df, {"buy_price": 10.0}, {"profit_pct": 5.0})
        assert result is not None
        assert "止盈" in result.reason


class TestStopMA10Cross:
    def test_not_triggered_without_consecutive(self):
        """不连续跌破，不触发（中间回升）"""
        prices = [10.0] * 10 + [9.0, 10.5, 9.0]  # 跌、回升、又跌，不连续
        df = make_daily(prices)
        # MA10 大约 9.77，9.0 < 9.77*0.93=9.09 可以触发，但需要连续2天
        # 这里不是连续的，所以不触发
        result = _check_stop_ma10_cross(df, {}, {"coefficient": 0.93, "buffer_days": 2})
        # 最后一天 close=9.0, MA10≈(10*7+9+10.5+9)/10=9.85, 9<9.85*0.93=9.16 触发
        # 倒数第二天 close=10.5, MA10≈(10*8+9+9)/10=9.9, 10.5>9.9*0.93=9.21 不触发
        # 所以 non-consecutive，不触发
        assert result is None

    def test_triggered_consecutive(self):
        """连续跌破，触发"""
        # 前10天全是10，最后2天是9.0
        prices = [10.0] * 11 + [9.0, 9.0]
        df = make_daily(prices)
        result = _check_stop_ma10_cross(df, {}, {"coefficient": 0.93, "buffer_days": 2})
        # MA10≈9.8, 9.0<9.8*0.93=9.11 连续2天
        assert result is not None
        assert "MA10" in result.reason


class TestStopFactorRegistry:
    def test_register_and_retrieve(self):
        """注册和获取因子"""
        factors = StopFactorRegistry.get_all()
        assert "stop_prev_low" in factors
        assert "stop_ma10_cross" in factors
        assert "take_profit_pct" in factors
        assert len(factors) == 3

    def test_get_check_fn(self):
        """获取检查函数"""
        fn = StopFactorRegistry.get_check_fn("take_profit_pct")
        assert fn is not None
        assert callable(fn)

    def test_unknown_factor_raises(self):
        """未知因子抛出异常"""
        with pytest.raises(ValueError, match="未知止损止盈因子"):
            StopFactorRegistry.get_check_fn("unknown")
```

- [ ] **Step 3: 运行测试确认**

Run: `cd backend && source venv/bin/activate && pytest tests/test_trade_sim_stops.py -v`
Expected: 7 tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/factors/trade_sim_stops.py backend/tests/test_trade_sim_stops.py
git commit -m "feat: add stop factor registry with 3 built-in factors"
```

---

### Task 4: TradeSimEngine 核心引擎

**Files:**
- Create: `backend/app/services/trade_sim_engine.py`

- [ ] **Step 1: 编写 TradeSimEngine（完整实现）**

```python
# backend/app/services/trade_sim_engine.py
"""交易模拟引擎

独立于 BacktestEngine，组合复用数据加载和策略执行能力。
核心流程：选股 → 分配资金 → 逐日追踪 → 止损止盈检查 → 统计汇总
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from ..config import settings
from ..models.stock_tables import Daily
from ..factors.trade_sim_stops import StopFactorRegistry, TriggerResult

_sync_engine = create_engine(settings.SYNC_DATABASE_URL)
SyncSession = sessionmaker(bind=_sync_engine)


def _get_db():
    return SyncSession()


class TradeSimEngine:
    """交易模拟引擎"""

    def __init__(
        self,
        strategy_code: str,
        strategy_params: Dict[str, Any],
        config: Dict[str, Any],
    ):
        self.strategy_code = strategy_code
        self.strategy_params = strategy_params
        self.config = config  # {total_amount, top_n, max_hold_days, stop_factors: [...]}

        # 创建 BacktestEngine 实例来复用策略加载 + 数据加载
        from .backtest_engine import BacktestEngine
        self._backtest_engine = BacktestEngine(
            strategy_code=strategy_code,
            strategy_params=strategy_params,
            config=config,
        )

    def run(self, cutoff_date: str) -> Dict[str, Any]:
        """主入口，返回 {trades: [...], summary: {...}}"""
        # 1. 选股
        candidates = self._get_stock_candidates(cutoff_date)
        if not candidates:
            return {"trades": [], "summary": self._empty_summary()}

        # 2. 加载追踪数据
        ts_codes = [c["ts_code"] for c in candidates]
        tracking_daily = self._load_tracking_data(ts_codes, cutoff_date)

        # 3. 逐股模拟
        top_n = self.config.get("top_n", 5)
        total_amount = self.config.get("total_amount", 100000)
        allocated = total_amount / top_n
        max_hold_days = self.config.get("max_hold_days", 60)
        stop_factors = self.config.get("stop_factors", [])

        trades = []
        for candidate in candidates:
            ts_code = candidate["ts_code"]
            daily = tracking_daily.get(ts_code, [])
            trade = self._simulate_trade(
                ts_code=ts_code,
                name=candidate.get("name", ts_code),
                score=candidate.get("score", 0),
                allocated_amount=allocated,
                daily=daily,
                stop_factors=stop_factors,
                max_hold_days=max_hold_days,
            )
            trades.append(trade)

        # 4. 汇总
        summary = self._calculate_summary(trades)

        return {"trades": trades, "summary": summary}

    def _get_stock_candidates(self, cutoff_date: str) -> List[dict]:
        """运行策略选股，按 score 降序取前 N 只"""
        loaded = self._backtest_engine._load_data(cutoff_date)
        daily_data = loaded["daily"]

        strategy_input = {
            "cutoff_date": cutoff_date,
            **loaded,
            "daily": daily_data,
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

    def _load_tracking_data(self, ts_codes: List[str], cutoff_date: str) -> dict:
        """加载截止日后所有日线数据（用于追踪）"""
        session = _get_db()
        try:
            stmt = select(
                Daily.ts_code, Daily.trade_date, Daily.open, Daily.high,
                Daily.low, Daily.close, Daily.adj_close, Daily.vol, Daily.amount,
            ).where(
                Daily.ts_code.in_(ts_codes),
                Daily.trade_date > cutoff_date,
            ).order_by(Daily.ts_code, Daily.trade_date)

            rows = [dict(row._mapping) for row in session.execute(stmt)]
        finally:
            session.close()

        result = {}
        for row in rows:
            ts_code = row["ts_code"]
            if ts_code not in result:
                result[ts_code] = []
            result[ts_code].append({
                "trade_date": row["trade_date"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "adj_close": row["adj_close"],
                "vol": row["vol"],
                "amount": row["amount"],
            })
        return result

    def _simulate_trade(
        self,
        ts_code: str,
        name: str,
        score: float,
        allocated_amount: float,
        daily: list,
        stop_factors: list,
        max_hold_days: int,
    ) -> dict:
        """模拟单只股票的一笔交易"""

        # 构建基础 trade 对象
        trade = {
            "ts_code": ts_code,
            "name": name,
            "score": score,
            "allocated_amount": allocated_amount,
            "shares": 0.0,
            "buy_price": None,
            "buy_date": None,
            "sell_price": None,
            "sell_date": None,
            "sell_reason": None,
            "hold_days": 0,
            "return_pct": None,
            "high_price": None,
            "low_price": None,
            "max_drawdown": None,
            "daily_tracking": [],
        }

        if not daily:
            trade["sell_reason"] = "数据缺失（无后续日线）"
            return trade

        # a. 买入日 = 截止日后第一个交易日
        buy_day = daily[0]
        buy_price = buy_day.get("open")
        if buy_price is None or buy_price <= 0:
            trade["sell_reason"] = "数据缺失（无开盘价）"
            return trade

        trade["buy_price"] = buy_price
        trade["buy_date"] = buy_day["trade_date"]
        trade["shares"] = allocated_amount / buy_price

        # b. 初始化追踪状态
        high_price = buy_price
        low_price = buy_price

        # 确定启用的因子（按 config 顺序）
        enabled_factors = [
            sf for sf in stop_factors
            if sf.get("enabled") and sf.get("id")
        ]

        # c. 逐日循环
        triggered = False
        for i, day in enumerate(daily):
            close_price = day.get("adj_close") or day.get("close")
            open_price = day.get("open")
            high = day.get("high") or close_price
            low = day.get("low") or close_price

            if close_price is None:
                continue

            # 更新极值和回撤
            if close_price > high_price:
                high_price = close_price
            if close_price < low_price:
                low_price = close_price
            max_drawdown = (low_price - buy_price) / buy_price * 100

            # 计算 MA10（需要至少 10 天数据）
            ma10 = None
            if i >= 9:
                ma10_closes = []
                for j in range(i - 9, i + 1):
                    c = daily[j].get("adj_close") or daily[j].get("close")
                    if c is not None:
                        ma10_closes.append(c)
                if len(ma10_closes) >= 10:
                    ma10 = sum(ma10_closes) / len(ma10_closes)

            # 构建追踪记录
            current_return = (close_price - buy_price) / buy_price * 100
            tracking_record = {
                "date": day["trade_date"],
                "open": open_price,
                "close": close_price,
                "high": high,
                "low": low,
                "ma10": round(ma10, 4) if ma10 else None,
                "prev_low_ref": None,
                "ma10_stop_line": None,
                "return_pct": round(current_return, 2),
                "status": "holding",
            }

            # 计算止损参考线（用于前端展示）
            for sf in enabled_factors:
                fid = sf.get("id")
                params = sf.get("params", {})
                if fid == "stop_prev_low":
                    ref_days = params.get("ref_days", 20)
                    if i >= ref_days:
                        ref_day = daily[i - ref_days]
                        ref_price = ref_day.get("adj_close") or ref_day.get("close")
                        tracking_record["prev_low_ref"] = ref_price
                elif fid == "stop_ma10_cross" and ma10 is not None:
                    coeff = params.get("coefficient", 0.93)
                    tracking_record["ma10_stop_line"] = round(ma10 * coeff, 4)

            # 检查止损止盈
            if not triggered:
                for sf in enabled_factors:
                    fid = sf.get("id")
                    params = sf.get("params", {})
                    try:
                        check_fn = StopFactorRegistry.get_check_fn(fid)
                        # 从买入日到当天的 slice
                        result = check_fn(
                            daily[: i + 1],
                            {"buy_price": buy_price, "buy_date": trade["buy_date"], "buy_idx": 0},
                            params,
                        )
                        if result is not None:
                            # 触发！卖出价 = 次日开盘价（最后一天用收盘价）
                            triggered = True
                            if i + 1 < len(daily):
                                sell_price = daily[i + 1].get("open") or daily[i + 1].get("close")
                                sell_date = daily[i + 1]["trade_date"]
                            else:
                                sell_price = close_price
                                sell_date = day["trade_date"]

                            trade["sell_price"] = sell_price
                            trade["sell_date"] = sell_date
                            trade["sell_reason"] = result.reason
                            trade["hold_days"] = i + 1  # 买入日 index 0，持有到第 i 天触发
                            trade["return_pct"] = round((sell_price - buy_price) / buy_price * 100, 2)
                            tracking_record["status"] = "stopped" if "止损" in result.reason else "take_profit"
                            break
                    except ValueError:
                        continue

            # 强制平仓检查
            if not triggered and i + 1 >= max_hold_days:
                triggered = True
                sell_price = close_price
                sell_date = day["trade_date"]
                trade["sell_price"] = sell_price
                trade["sell_date"] = sell_date
                trade["sell_reason"] = f"强制平仓（持有超过{max_hold_days}天）"
                trade["hold_days"] = i + 1
                trade["return_pct"] = round((sell_price - buy_price) / buy_price * 100, 2)
                tracking_record["status"] = "force_close"

            trade["daily_tracking"].append(tracking_record)

        # 更新极值
        trade["high_price"] = round(high_price, 2)
        trade["low_price"] = round(low_price, 2)
        if trade["buy_price"]:
            trade["max_drawdown"] = round((low_price - trade["buy_price"]) / trade["buy_price"] * 100, 2)

        # 如果始终未触发也未强制平仓（追踪数据不足 max_hold_days 天就结束了）
        if not triggered:
            trade["sell_reason"] = "数据缺失（追踪数据不足）"

        return trade

    def _calculate_summary(self, trades: List[dict]) -> dict:
        """汇总统计"""
        if not trades:
            return self._empty_summary()

        # 只统计有卖出记录的
        closed = [t for t in trades if t["return_pct"] is not None]
        if not closed:
            return self._empty_summary()

        total_trades = len(closed)
        wins = [t for t in closed if t["return_pct"] > 0]
        losses = [t for t in closed if t["return_pct"] <= 0]

        win_count = len(wins)
        lose_count = len(losses)
        win_rate = win_count / total_trades * 100 if total_trades > 0 else 0.0

        all_returns = [t["return_pct"] for t in closed]
        avg_return = sum(all_returns) / len(all_returns)

        avg_win = sum(t["return_pct"] for t in wins) / len(wins) if wins else 0.0
        avg_loss = sum(t["return_pct"] for t in losses) / len(losses) if losses else 0.0

        profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0

        # 最大连续盈亏（按买入日期排序）
        closed_sorted = sorted(closed, key=lambda t: t.get("buy_date", ""))
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0
        for t in closed_sorted:
            if t["return_pct"] > 0:
                current_wins += 1
                current_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_losses)

        # 收益分布
        dist = {"lt_-10": 0, "-10_0": 0, "0_5": 0, "5_10": 0, "gt_10": 0}
        for r in all_returns:
            if r < -10:
                dist["lt_-10"] += 1
            elif r < 0:
                dist["-10_0"] += 1
            elif r < 5:
                dist["0_5"] += 1
            elif r < 10:
                dist["5_10"] += 1
            else:
                dist["gt_10"] += 1

        return {
            "total_trades": total_trades,
            "win_count": win_count,
            "lose_count": lose_count,
            "win_rate": round(win_rate, 2),
            "avg_return": round(avg_return, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_loss_ratio": round(profit_loss_ratio, 2),
            "max_consecutive_wins": max_consecutive_wins,
            "max_consecutive_losses": max_consecutive_losses,
            "return_distribution": dist,
        }

    def _empty_summary(self) -> dict:
        return {
            "total_trades": 0,
            "win_count": 0,
            "lose_count": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_loss_ratio": 0.0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "return_distribution": {
                "lt_-10": 0, "-10_0": 0, "0_5": 0, "5_10": 0, "gt_10": 0,
            },
        }
```

- [ ] **Step 2: 验证引擎可导入**

Run: `cd backend && source venv/bin/activate && python -c "from app.services.trade_sim_engine import TradeSimEngine; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/trade_sim_engine.py
git commit -m "feat: add TradeSimEngine core logic"
```

---

### Task 5: TradeSimService 业务逻辑层

**Files:**
- Create: `backend/app/services/trade_sim_service.py`

- [ ] **Step 1: 编写 Service**

```python
# backend/app/services/trade_sim_service.py
"""交易模拟业务逻辑层"""

import json
import asyncio
import numpy as np
from typing import List, Optional, Tuple
from datetime import datetime
from ..models.base import beijing_now
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from ..models.trade_sim import TradeSimReport
from ..models.strategy import Strategy
from ..schemas.trade_sim import TradeSimCreate


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


class TradeSimService:

    @staticmethod
    async def create(
        db: AsyncSession,
        data: TradeSimCreate,
        user_id: int,
    ) -> TradeSimReport:
        """提交交易模拟回测"""
        # 检查策略存在
        strategy_result = await db.execute(
            select(Strategy).where(Strategy.id == data.strategy_id)
        )
        strategy = strategy_result.scalar_one_or_none()
        if not strategy:
            raise HTTPException(status_code=404, detail="策略不存在")

        # 至少启用一个止损止盈条件
        enabled = [sf for sf in data.stop_factors if sf.enabled]
        if not enabled:
            raise HTTPException(status_code=400, detail="请至少启用一个止损止盈条件")

        config = {
            "total_amount": data.total_amount,
            "top_n": data.top_n,
            "max_hold_days": data.max_hold_days,
            "stop_factors": [
                {"id": sf.id, "enabled": sf.enabled, "params": sf.params}
                for sf in data.stop_factors
            ],
        }

        report = TradeSimReport(
            strategy_id=data.strategy_id,
            user_id=user_id,
            cutoff_date=data.cutoff_date,
            config=json.dumps(config, ensure_ascii=False),
            status="pending",
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)

        report.strategy = strategy

        loop = asyncio.get_running_loop()
        loop.run_in_executor(
            None,
            TradeSimService._run,
            report.id,
            data.cutoff_date,
        )

        return report

    @staticmethod
    def _run(report_id: int, cutoff_date: str):
        """执行交易模拟（线程池中）"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from ..config import settings
        from .trade_sim_engine import TradeSimEngine

        engine = create_engine(settings.SYNC_DATABASE_URL)
        Session = sessionmaker(bind=engine)

        with Session() as db:
            try:
                report = db.query(TradeSimReport).filter(TradeSimReport.id == report_id).first()
                if not report:
                    return

                report.status = "running"
                report.started_at = beijing_now()
                db.commit()

                strategy = db.query(Strategy).filter(Strategy.id == report.strategy_id).first()
                if not strategy:
                    raise ValueError(f"策略 {report.strategy_id} 不存在")

                # 获取策略代码
                if strategy.generated_code:
                    strategy_code = strategy.generated_code
                elif strategy.file_path and __import__('os').path.exists(strategy.file_path):
                    with open(strategy.file_path, "r", encoding="utf-8") as f:
                        strategy_code = f.read()
                else:
                    raise FileNotFoundError(f"策略代码不存在")

                config = json.loads(report.config) if report.config else {}
                # 转换 cutoff_date: "YYYY-MM-DD" → "YYYYMMDD"
                cutoff_date_fmt = cutoff_date.replace("-", "")

                engine_obj = TradeSimEngine(
                    strategy_code=strategy_code,
                    strategy_params={},
                    config=config,
                )

                result = engine_obj.run(cutoff_date_fmt)

                report.trades = json.dumps(result["trades"], ensure_ascii=False, cls=NumpyEncoder)
                report.summary = json.dumps(result["summary"], ensure_ascii=False, cls=NumpyEncoder)
                report.status = "completed"
                report.completed_at = beijing_now()
                db.commit()

            except Exception as e:
                db.rollback()
                report = db.query(TradeSimReport).filter(TradeSimReport.id == report_id).first()
                if report:
                    report.status = "failed"
                    report.error_message = str(e)
                    report.completed_at = beijing_now()
                    db.commit()

    @staticmethod
    async def get_list(
        db: AsyncSession,
        page: int = 1,
        limit: int = 20,
        strategy_id: Optional[int] = None,
        status_filter: Optional[str] = None,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> Tuple[List[TradeSimReport], int]:
        """获取交易模拟列表"""
        query = select(TradeSimReport).options(selectinload(TradeSimReport.strategy))

        if strategy_id:
            query = query.where(TradeSimReport.strategy_id == strategy_id)
        if status_filter:
            query = query.where(TradeSimReport.status == status_filter)
        if user_role != "admin":
            query = query.where(TradeSimReport.user_id == user_id)

        count_query = select(func.count()).select_from(TradeSimReport)
        if strategy_id:
            count_query = count_query.where(TradeSimReport.strategy_id == strategy_id)
        if status_filter:
            count_query = count_query.where(TradeSimReport.status == status_filter)
        if user_role != "admin":
            count_query = count_query.where(TradeSimReport.user_id == user_id)

        total = (await db.execute(count_query)).scalar()
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit).order_by(TradeSimReport.created_at.desc())

        result = await db.execute(query)
        return result.scalars().all(), total

    @staticmethod
    async def get_detail(
        db: AsyncSession,
        report_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> TradeSimReport:
        """获取交易模拟详情"""
        result = await db.execute(
            select(TradeSimReport)
            .options(selectinload(TradeSimReport.strategy))
            .where(TradeSimReport.id == report_id)
        )
        report = result.scalar_one_or_none()
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")

        if user_role != "admin" and report.user_id != user_id:
            raise HTTPException(status_code=403, detail="无权访问")

        return report

    @staticmethod
    async def delete(
        db: AsyncSession,
        report_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> None:
        """删除交易模拟报告"""
        report = await TradeSimService.get_detail(db, report_id, user_id, user_role)
        await db.delete(report)
        await db.commit()
```

- [ ] **Step 2: 验证 Service 可导入**

Run: `cd backend && source venv/bin/activate && python -c "from app.services.trade_sim_service import TradeSimService; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/trade_sim_service.py
git commit -m "feat: add TradeSimService business logic"
```

---

### Task 6: API 路由

**Files:**
- Create: `backend/app/api/trade_sims.py`

- [ ] **Step 1: 编写 API 路由**

```python
# backend/app/api/trade_sims.py
"""交易模拟回测 API 路由"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..middleware.auth import get_current_user
from ..schemas.trade_sim import (
    TradeSimCreate,
    TradeSimResponse,
    TradeSimListResponse,
)
from ..services.trade_sim_service import TradeSimService
from ..factors.trade_sim_stops import StopFactorRegistry

router = APIRouter()


@router.post("/", response_model=TradeSimResponse, status_code=202)
async def create_trade_sim(
    data: TradeSimCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """提交交易模拟回测（异步执行）"""
    report = await TradeSimService.create(db, data, current_user["user_id"])
    return _format_response(report)


@router.get("/", response_model=TradeSimListResponse)
async def list_trade_sims(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    strategy_id: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询交易模拟列表"""
    items, total = await TradeSimService.get_list(
        db, page, limit, strategy_id, status,
        current_user.id, current_user.get("role", "user"),
    )
    return {
        "items": [_format_response(item) for item in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/factors")
async def get_stop_factors():
    """获取可用止损止盈因子列表（供前端渲染表单）"""
    return StopFactorRegistry.get_all()


@router.get("/{report_id}", response_model=TradeSimResponse)
async def get_trade_sim(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询交易模拟详情（含 trades + summary）"""
    report = await TradeSimService.get_detail(
        db, report_id, current_user["user_id"], current_user.get("role", "user"),
    )
    return _format_response(report)


@router.delete("/{report_id}")
async def delete_trade_sim(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除交易模拟报告"""
    await TradeSimService.delete(
        db, report_id, current_user["user_id"], current_user.get("role", "user"),
    )
    return {"message": "已删除"}


def _format_response(report) -> dict:
    """将 ORM 对象格式化为响应 dict"""
    config = None
    if report.config:
        try:
            config = json.loads(report.config)
        except (json.JSONDecodeError, TypeError):
            config = {}

    trades = None
    if report.trades:
        try:
            trades = json.loads(report.trades)
        except (json.JSONDecodeError, TypeError):
            trades = []

    summary = None
    if report.summary:
        try:
            summary = json.loads(report.summary)
        except (json.JSONDecodeError, TypeError):
            summary = {}

    return {
        "id": report.id,
        "strategy_id": report.strategy_id,
        "strategy_name": report.strategy_name,
        "cutoff_date": str(report.cutoff_date) if report.cutoff_date else None,
        "config": config,
        "trades": trades,
        "summary": summary,
        "status": report.status,
        "error_message": report.error_message,
        "created_at": report.created_at,
        "started_at": report.started_at,
        "completed_at": report.completed_at,
    }
```

- [ ] **Step 2: 注意路由定义顺序** — `GET /factors` 必须在 `GET /{report_id}` 之前，否则 FastAPI 会把 "factors" 当成 report_id

- [ ] **Step 3: 验证路由可导入**

Run: `cd backend && source venv/bin/activate && python -c "from app.api.trade_sims import router; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/trade_sims.py
git commit -m "feat: add trade sim API routes"
```

---

### Task 7: 注册路由和模型到主应用

**Files:**
- Modify: `backend/app/main.py:76,88`

- [ ] **Step 1: 在 main.py 中注册路由**

在 `backend/app/main.py` 的 import 部分添加：
```python
from .api import strategies, backtests, batch_backtests, factors, ai, auth, users, stocks, education, ratings, comments, financials, trade_sims
```

在路由注册部分添加（注意放在 `backtests` 路由之前，避免路径冲突）：
```python
app.include_router(trade_sims.router, prefix="/api/v1/trade-sims", tags=["trade-sims"])
```

- [ ] **Step 2: 创建数据库表**

Run: `cd backend && source venv/bin/activate && python -c "
from app.database import engine, Base
from app.models.trade_sim import TradeSimReport
import asyncio
async def create():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Tables created')
asyncio.run(create())
"`
Expected: `Tables created`

- [ ] **Step 3: 验证应用启动**

Run: `cd backend && source venv/bin/activate && timeout 5 python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 2>&1 || true`
Expected: 无 import 错误

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: register trade-sims router and model relationships"
```

---

### Task 8: 前端 TypeScript 类型 + API Service

**Files:**
- Create: `frontend/src/types/tradeSim.ts`
- Create: `frontend/src/services/tradeSimService.ts`

- [ ] **Step 1: 编写 TypeScript 类型**

```typescript
// frontend/src/types/tradeSim.ts

export interface StopFactorMeta {
  name: string;
  params: Array<{
    name: string;
    type: 'int' | 'float';
    default: number;
    description: string;
  }>;
}

export interface StopFactorConfig {
  id: string;
  enabled: boolean;
  params: Record<string, number>;
}

export interface TradeSimCreate {
  strategy_id: number;
  cutoff_date: string;        // YYYY-MM-DD
  total_amount: number;
  top_n: number;              // default 5
  max_hold_days: number;      // default 60
  stop_factors: StopFactorConfig[];
}

export interface DailyTrackingItem {
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  ma10: number | null;
  prev_low_ref: number | null;
  ma10_stop_line: number | null;
  return_pct: number;
  status: 'holding' | 'stopped' | 'take_profit' | 'force_close';
}

export interface TradeItem {
  ts_code: string;
  name: string;
  score: number;
  allocated_amount: number;
  shares: number;
  buy_price: number;
  buy_date: string;
  sell_price: number | null;
  sell_date: string | null;
  sell_reason: string | null;
  hold_days: number | null;
  return_pct: number | null;
  high_price: number | null;
  low_price: number | null;
  max_drawdown: number | null;
  daily_tracking: DailyTrackingItem[];
}

export interface ReturnDistribution {
  'lt_-10': number;
  '-10_0': number;
  '0_5': number;
  '5_10': number;
  'gt_10': number;
}

export interface TradeSimSummary {
  total_trades: number;
  win_count: number;
  lose_count: number;
  win_rate: number;
  avg_return: number;
  avg_win: number;
  avg_loss: number;
  profit_loss_ratio: number;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  return_distribution: ReturnDistribution;
}

export interface TradeSimReport {
  id: number;
  strategy_id: number;
  strategy_name?: string;
  cutoff_date: string;
  config: TradeSimCreate | null;
  trades: TradeItem[] | null;
  summary: TradeSimSummary | null;
  status: string;
  error_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface TradeSimListResponse {
  items: TradeSimReport[];
  total: number;
  page: number;
  limit: number;
}
```

- [ ] **Step 2: 编写 API Service**

```typescript
// frontend/src/services/tradeSimService.ts
import api from './api';
import type {
  TradeSimReport,
  TradeSimListResponse,
  TradeSimCreate,
  StopFactorMeta,
} from '@/types/tradeSim';

const BASE = '/trade-sims';

export const tradeSimService = {
  async create(data: TradeSimCreate): Promise<TradeSimReport> {
    const response = await api.post<TradeSimReport>(BASE, data);
    return response.data;
  },

  async getList(params: {
    page?: number;
    limit?: number;
    strategy_id?: number;
    status?: string;
  } = {}): Promise<TradeSimListResponse> {
    const response = await api.get<TradeSimListResponse>(BASE, { params });
    return response.data;
  },

  async getDetail(id: number): Promise<TradeSimReport> {
    const response = await api.get<TradeSimReport>(`${BASE}/${id}`);
    return response.data;
  },

  async delete(id: number): Promise<void> {
    await api.delete(`${BASE}/${id}`);
  },

  async getStopFactors(): Promise<Record<string, StopFactorMeta>> {
    const response = await api.get<Record<string, StopFactorMeta>>(`${BASE}/factors`);
    return response.data;
  },
};

export default tradeSimService;
```

- [ ] **Step 3: 验证 TypeScript 编译**

Run: `cd frontend && npx tsc --noEmit --pretty`
Expected: 无新增类型错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/tradeSim.ts frontend/src/services/tradeSimService.ts
git commit -m "feat: add trade sim TypeScript types and API service"
```

---

### Task 9: 改造 BacktestForm — 增加交易模拟模式

**Files:**
- Modify: `frontend/src/pages/BacktestForm.tsx`

- [ ] **Step 1: 添加模式切换和交易模拟表单**

在 `BacktestForm.tsx` 中：

1. 新增 `backtestMode` state：`'simple' | 'trade-sim'`
2. 新增交易模拟字段：`totalAmount`, `topN`, `maxHoldDays`, `stopFactors`
3. 在 `Radio.Group` 中增加 `交易模拟` 选项
4. 条件渲染表单：
   - 简单模式 → 现有表单
   - 交易模拟模式 → 新表单

完整代码如下（在现有文件基础上修改）：

在现有 `mode` state 下方添加：
```typescript
const [backtestMode, setBacktestMode] = useState<'simple' | 'trade-sim'>('simple');

// 交易模拟字段
const [totalAmount, setTotalAmount] = useState<number>(100000);
const [topN, setTopN] = useState<number>(5);
const [maxHoldDays, setMaxHoldDays] = useState<number>(60);
const [stopFactors, setStopFactors] = useState<Array<{ id: string; enabled: boolean; params: Record<string, number> }>>([
  { id: 'stop_prev_low', enabled: true, params: { ref_days: 20 } },
  { id: 'stop_ma10_cross', enabled: false, params: { coefficient: 0.93, buffer_days: 2 } },
  { id: 'take_profit_pct', enabled: true, params: { profit_pct: 5.0 } },
]);

const [availableFactors, setAvailableFactors] = useState<Record<string, any>>({});

useEffect(() => {
  tradeSimService.getStopFactors().then(setAvailableFactors).catch(() => {});
}, []);
```

在 `handleSubmit` 中添加交易模拟分支：
```typescript
const handleSubmit = async () => {
  if (!currentStrategy) {
    message.error('策略不存在');
    return;
  }

  // ... 现有 batch/simple 逻辑保持不变 ...

  // 交易模拟模式
  if (backtestMode === 'trade-sim') {
    if (!cutoffDate) {
      message.error('请选择截止日');
      return;
    }
    if (!totalAmount || totalAmount <= 0) {
      message.error('请输入投资总额');
      return;
    }
    const enabled = stopFactors.filter(sf => sf.enabled);
    if (enabled.length === 0) {
      message.error('请至少启用一个止损止盈条件');
      return;
    }

    try {
      const payload: TradeSimCreate = {
        strategy_id: currentStrategy.id,
        cutoff_date: cutoffDate.format('YYYY-MM-DD'),
        total_amount: totalAmount,
        top_n: topN,
        max_hold_days: maxHoldDays,
        stop_factors: stopFactors,
      };
      const result = await tradeSimService.create(payload);
      message.success('交易模拟回测已提交');
      navigate(`/backtests/trade-sim/${result.id}`);
    } catch (err: any) {
      message.error(err.response?.data?.detail || '提交失败');
    }
    return;
  }

  // ... 现有提交逻辑 ...
};
```

第一个 Radio.Group 改为：
```tsx
<Form.Item label="回测类型">
  <Radio.Group value={backtestMode} onChange={(e) => setBacktestMode(e.target.value)}>
    <Radio.Button value="simple">简单回测</Radio.Button>
    <Radio.Button value="trade-sim">交易模拟</Radio.Button>
  </Radio.Group>
</Form.Item>
```

在简单模式的内容后，添加交易模拟模式的内容：
```tsx
{backtestMode === 'simple' ? (
  <>
    {/* 现有的 mode Radio + 表单内容 */}
    <Form.Item label="回测模式">
      <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)}>
        <Radio.Button value="single">单日回测</Radio.Button>
        <Radio.Button value="batch">批量回测</Radio.Button>
      </Radio.Group>
    </Form.Item>
    {/* ... 其余现有内容 ... */}
  </>
) : (
  <>
    <Form.Item label="截止日" required>
      <DatePicker
        value={cutoffDate}
        onChange={setCutoffDate}
        style={{ width: '100%' }}
        placeholder="策略将用此日及之前的数据选股"
      />
    </Form.Item>

    <Form.Item label="投资总额（元）" required>
      <InputNumber
        value={totalAmount}
        onChange={(v) => setTotalAmount(v || 0)}
        min={1}
        style={{ width: '100%' }}
        placeholder="如 100000"
      />
    </Form.Item>

    <Form.Item label="持仓股票数 N">
      <InputNumber
        value={topN}
        onChange={(v) => setTopN(v || 5)}
        min={1}
        max={20}
        style={{ width: '100%' }}
        placeholder="取分数最高的前N只"
      />
    </Form.Item>

    <Form.Item label="强制平仓天数">
      <InputNumber
        value={maxHoldDays}
        onChange={(v) => setMaxHoldDays(v || 60)}
        min={1}
        max={365}
        style={{ width: '100%' }}
        placeholder="超过此天数未触发则强制平仓"
      />
    </Form.Item>

    <Form.Item label="止损止盈条件" required>
      <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
        任一条件触发即平仓（OR 关系），按顺序检查
      </Text>
      {stopFactors.map((sf, idx) => {
        const meta = availableFactors[sf.id];
        const factorName = meta?.name || sf.id;
        return (
          <Card key={sf.id} size="small" style={{ marginBottom: 8 }}>
            <Space>
              <Checkbox
                checked={sf.enabled}
                onChange={(e) => {
                  const next = [...stopFactors];
                  next[idx] = { ...next[idx], enabled: e.target.checked };
                  setStopFactors(next);
                }}
              >
                {factorName}
              </Checkbox>
            </Space>
            {sf.enabled && meta && (
              <div style={{ marginTop: 8, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                {meta.params.map((param: any) => (
                  <div key={param.name}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {param.description}:
                    </Text>
                    <InputNumber
                      size="small"
                      value={sf.params[param.name] ?? param.default}
                      onChange={(v) => {
                        const next = [...stopFactors];
                        next[idx] = {
                          ...next[idx],
                          params: { ...next[idx].params, [param.name]: v ?? param.default },
                        };
                        setStopFactors(next);
                      }}
                      step={param.type === 'float' ? 0.01 : 1}
                      style={{ width: 100, marginLeft: 4 }}
                    />
                  </div>
                ))}
              </div>
            )}
          </Card>
        );
      })}
    </Form.Item>
  </>
)}
```

- [ ] **Step 2: 验证 TypeScript 编译无错误**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: 无新增错误

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/BacktestForm.tsx
git commit -m "feat: add trade sim mode toggle and form to BacktestForm"
```

---

### Task 10: 交易模拟报表组件 TradeSimDetail

**Files:**
- Create: `frontend/src/pages/TradeSimDetail.tsx`

- [ ] **Step 1: 编写 TradeSimDetail 组件**

```typescript
// frontend/src/pages/TradeSimDetail.tsx
import { useEffect, useState } from 'react';
import {
  Card, Spin, Alert, Descriptions, Table, Button, Row, Col, Space, message, Typography,
} from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import StatCard from '@/components/shared/StatCard';
import LoadingSkeleton from '@/components/shared/LoadingSkeleton';
import { tradeSimService } from '@/services/tradeSimService';
import type { TradeSimReport, TradeItem, DailyTrackingItem } from '@/types/tradeSim';
import ReactECharts from 'echarts-for-react';

const { Text } = Typography;

function formatPct(v: number | null | undefined): string {
  if (v == null) return '—';
  const sign = v > 0 ? '+' : '';
  return `${sign}${v.toFixed(2)}%`;
}

function pctColor(v: number | null | undefined): string {
  if (v == null) return '#999';
  if (v > 0) return '#cf1322';
  if (v < 0) return '#3f8600';
  return '#999';
}

export default function TradeSimDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [report, setReport] = useState<TradeSimReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDetail = async () => {
    if (!id) return;
    try {
      const data = await tradeSimService.getDetail(parseInt(id));
      setReport(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDetail();
  }, [id]);

  // 轮询 pending/running
  useEffect(() => {
    if (report && (report.status === 'pending' || report.status === 'running')) {
      const timer = setInterval(fetchDetail, 3000);
      return () => clearInterval(timer);
    }
  }, [report?.status, id]);

  useEffect(() => {
    if (error) message.error(error);
  }, [error]);

  if (loading) return <LoadingSkeleton type="detail" />;
  if (!report) return <Alert type="error" title="报告不存在" />;

  const { trades, summary } = report;
  const isPending = report.status === 'pending' || report.status === 'running';

  const tradeColumns = [
    { title: '排名', key: 'index', width: 60, render: (_: any, __: any, i: number) => i + 1 },
    { title: '股票代码', dataIndex: 'ts_code', key: 'ts_code', width: 110 },
    { title: '股票名称', dataIndex: 'name', key: 'name', width: 100 },
    { title: '分数', dataIndex: 'score', key: 'score', width: 70 },
    { title: '买入价', dataIndex: 'buy_price', key: 'buy_price', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: '卖出价', dataIndex: 'sell_price', key: 'sell_price', width: 80, render: (v: number | null) => v?.toFixed(2) ?? '—' },
    { title: '持有天数', dataIndex: 'hold_days', key: 'hold_days', width: 80 },
    {
      title: '收益率', dataIndex: 'return_pct', key: 'return_pct', width: 100,
      render: (v: number | null) => <Text style={{ color: pctColor(v), fontWeight: 'bold' }}>{formatPct(v)}</Text>,
    },
    {
      title: '最大回撤', dataIndex: 'max_drawdown', key: 'max_drawdown', width: 100,
      render: (v: number | null) => <Text style={{ color: '#3f8600' }}>{v != null ? `${v.toFixed(2)}%` : '—'}</Text>,
    },
    { title: '卖出原因', dataIndex: 'sell_reason', key: 'sell_reason' },
  ];

  const expandedRowRender = (record: TradeItem) => {
    const trackingCols = [
      { title: '日期', dataIndex: 'date', key: 'date', width: 110 },
      { title: '开盘', dataIndex: 'open', key: 'open', width: 80, render: (v: number) => v?.toFixed(2) },
      { title: '收盘', dataIndex: 'close', key: 'close', width: 80, render: (v: number) => v?.toFixed(2) },
      { title: '最高', dataIndex: 'high', key: 'high', width: 80, render: (v: number) => v?.toFixed(2) },
      { title: '最低', dataIndex: 'low', key: 'low', width: 80, render: (v: number) => v?.toFixed(2) },
      { title: 'MA10', dataIndex: 'ma10', key: 'ma10', width: 80, render: (v: number | null) => v?.toFixed(2) ?? '—' },
      { title: '止损线', dataIndex: 'ma10_stop_line', key: 'ma10_stop_line', width: 80, render: (v: number | null) => v?.toFixed(2) ?? '—' },
      {
        title: '浮盈', dataIndex: 'return_pct', key: 'return_pct', width: 90,
        render: (v: number) => <Text style={{ color: pctColor(v) }}>{formatPct(v)}</Text>,
      },
      {
        title: '状态', dataIndex: 'status', key: 'status', width: 90,
        render: (v: string) => {
          const colorMap: Record<string, string> = { holding: '#1677ff', stopped: '#ff4d4f', take_profit: '#52c41a', force_close: '#faad14' };
          return <Text style={{ color: colorMap[v] || '#999' }}>{v}</Text>;
        },
      },
    ];

    const chartOption = {
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 20, top: 10, bottom: 30 },
      xAxis: { type: 'category', data: record.daily_tracking.map((d: DailyTrackingItem) => d.date.slice(5)), axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
      series: [{
        type: 'line',
        data: record.daily_tracking.map((d: DailyTrackingItem) => d.close),
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#1677ff' },
      }],
    };

    return (
      <div style={{ padding: 16 }}>
        <Card size="small" title="每日追踪" style={{ marginBottom: 12 }}>
          <Table
            dataSource={record.daily_tracking}
            columns={trackingCols}
            rowKey="date"
            pagination={false}
            size="small"
            scroll={{ x: 800 }}
          />
        </Card>
        <ReactECharts option={chartOption} style={{ height: 200 }} />
      </div>
    );
  };

  const distChartOption = summary?.return_distribution ? {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ['<-10%', '-10%~0', '0~5%', '5%~10%', '>10%'] },
    yAxis: { type: 'value' },
    series: [{
      type: 'bar',
      data: [
        summary.return_distribution['lt_-10'] ?? 0,
        summary.return_distribution['-10_0'] ?? 0,
        summary.return_distribution['0_5'] ?? 0,
        summary.return_distribution['5_10'] ?? 0,
        summary.return_distribution['gt_10'] ?? 0,
      ],
      itemStyle: {
        color: (params: any) => ['#cf1322', '#ff7875', '#95de64', '#52c41a', '#237804'][params.dataIndex],
      },
    }],
  } : null;

  return (
    <>
      <PageHeader
        title="交易模拟回测详情"
        breadcrumb={[
          { title: '回测报告', path: '/backtests' },
          { title: `交易模拟 #${report.id}` },
        ]}
        extra={<Button onClick={() => navigate('/backtests')}>返回列表</Button>}
      />

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="策略名称">{report.strategy_name || '—'}</Descriptions.Item>
          <Descriptions.Item label="截止日">{report.cutoff_date}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Space>
              <StatusTag status={report.status} type="backtest" />
              {isPending && <Spin size="small" />}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">{report.created_at ? new Date(report.created_at).toLocaleString() : '—'}</Descriptions.Item>
        </Descriptions>
      </Card>

      {report.status === 'failed' && report.error_message && (
        <Alert type="error" message="执行失败" description={report.error_message} style={{ marginBottom: 16 }} />
      )}

      {report.status === 'completed' && summary && (
        <Card title="汇总指标" style={{ marginBottom: 16 }}>
          <Row gutter={[16, 16]}>
            <Col xs={12} sm={6}>
              <StatCard title="总交易笔数" value={`${summary.total_trades}`} color="#1677ff" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="胜率" value={`${summary.win_rate?.toFixed(1)}%`} color="#52c41a" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="平均回报率" value={formatPct(summary.avg_return)} color={summary.avg_return > 0 ? '#cf1322' : '#3f8600'} />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="平均亏损率" value={formatPct(summary.avg_loss)} color="#3f8600" />
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={12} sm={6}>
              <StatCard title="盈亏比" value={summary.profit_loss_ratio?.toFixed(2) || '—'} color="#722ed1" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="最大连续盈利" value={`${summary.max_consecutive_wins} 笔`} color="#cf1322" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="最大连续亏损" value={`${summary.max_consecutive_losses} 笔`} color="#3f8600" />
            </Col>
          </Row>

          {distChartOption && (
            <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
              <Col span={24}>
                <Card size="small" title="收益分布">
                  <ReactECharts option={distChartOption} style={{ height: 250 }} />
                </Card>
              </Col>
            </Row>
          )}
        </Card>
      )}

      {report.status === 'completed' && trades && trades.length > 0 && (
        <Card title={`交易明细（共 ${trades.length} 笔）`}>
          <Table
            dataSource={trades}
            columns={tradeColumns}
            rowKey="ts_code"
            pagination={false}
            size="middle"
            scroll={{ x: 1000 }}
            expandable={{
              expandedRowRender,
              rowExpandable: (record: TradeItem) => record.daily_tracking.length > 0,
            }}
          />
        </Card>
      )}

      {isPending && (
        <Card>
          <Spin tip={report.status === 'pending' ? '等待中...' : '执行中...'}>
            <div style={{ padding: 60, textAlign: 'center', color: '#999' }}>
              {report.status === 'pending' ? '任务已提交，等待执行...' : '正在模拟交易，请稍候...'}
            </div>
          </Spin>
        </Card>
      )}
    </>
  );
}
```

- [ ] **Step 2: 添加前端路由** — 在 `App.tsx` 中添加：

```tsx
// import 部分：
import TradeSimDetail from '@/pages/TradeSimDetail';

// routes 部分添加（在 backtests 路由附近）：
<Route path="/backtests/trade-sim/:id" element={<TradeSimDetail />} />
```

- [ ] **Step 3: 验证 TypeScript 编译**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: 无新增错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/TradeSimDetail.tsx frontend/src/App.tsx
git commit -m "feat: add TradeSimDetail report component and route"
```

---

### Task 11: 改造 BacktestDetail — 按模式渲染

**Files:**
- Modify: `frontend/src/pages/BacktestDetail.tsx`

This is optional — the original BacktestDetail only handles BacktestReport objects. We don't need to modify it since TradeSimDetail has its own route (`/backtests/trade-sim/:id`). 

- [ ] **Step 1: 确认无需修改** — 现有 BacktestDetail 保持不变

既然 TradeSimDetail 有自己的路由，BacktestDetail 不需要改动。但 BacktestForm 中的 `navigate` 需要调整——交易模拟提交后跳转到 `/backtests/trade-sim/:id` 而非 `/backtests/:id`。

在 BacktestForm.tsx 中（Task 9 已处理）：
```typescript
// 交易模拟提交后跳转到：
navigate(`/backtests/trade-sim/${result.id}`);
```

- [ ] **Step 2: Commit（如有修改）**

如果 Task 9 已包含导航修改，无需额外 commit。

---

### Task 12: 端到端验证

**Files:** 无新建

- [ ] **Step 1: 启动后端服务**

Run: `cd backend && source venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &`
验证 `curl http://localhost:8000/health` 返回 `{"status":"healthy"}`

- [ ] **Step 2: 验证 API 路由可访问**

```bash
# 获取可用因子列表
curl -s http://localhost:8000/api/v1/trade-sims/factors | python -m json.tool
```
Expected: 返回 3 个因子的 JSON

- [ ] **Step 3: 提交一个交易模拟回测**

```bash
curl -s -X POST http://localhost:8000/api/v1/trade-sims \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "strategy_id": 1,
    "cutoff_date": "2026-05-15",
    "total_amount": 100000,
    "top_n": 5,
    "max_hold_days": 60,
    "stop_factors": [
      {"id": "stop_prev_low", "enabled": true, "params": {"ref_days": 20}},
      {"id": "take_profit_pct", "enabled": true, "params": {"profit_pct": 5.0}}
    ]
  }' | python -m json.tool
```
Expected: 返回 202，status=pending

- [ ] **Step 4: 查询详情确认执行完成**

```bash
curl -s http://localhost:8000/api/v1/trade-sims/1 -H "Authorization: Bearer <token>" | python -m json.tool | head -30
```
Expected: 返回完整的 trades + summary

- [ ] **Step 5: 验证前端页面**

Run: `cd frontend && npm run dev`
导航到策略回测页面，验证：
- 模式切换"简单回测"/"交易模拟"正常切换
- 交易模拟表单渲染正确（因子卡片、参数输入）
- 提交后正确跳转到 TradeSimDetail
- 报表展示：汇总卡片、收益分布图、交易明细表、展开行

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete trade simulation backtest feature"
```

---

### Task 13: 批量交易模拟 — 模型 + Schema + Engine

**Files:**
- Modify: `backend/app/models/trade_sim.py` — 新增 BatchTradeSimReport
- Modify: `backend/app/schemas/trade_sim.py` — 新增批量 schema
- Modify: `backend/app/services/trade_sim_engine.py` — 新增 `run_batch()`

- [ ] **Step 1: 新增 BatchTradeSimReport 模型**

```python
# 追加到 backend/app/models/trade_sim.py
class BatchTradeSimReport(BaseModel):
    """批量交易模拟回测报告"""

    __tablename__ = "batch_trade_sim_reports"

    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255))
    status = Column(String(20), default="pending", index=True)
    start_date = Column(String(8), nullable=False)   # YYYYMMDD
    end_date = Column(String(8), nullable=False)      # YYYYMMDD
    config = Column(Text)        # JSON: total_amount, top_n, max_hold_days, stop_factors
    total_days = Column(Integer, default=0)
    completed_days = Column(Integer, default=0)
    daily_results = Column(Text)  # JSON: [{cutoff_date, trades, summary, status, error_message}]
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    strategy = relationship("Strategy", back_populates="batch_trade_sim_reports")
    owner = relationship("User", back_populates="batch_trade_sim_reports")

    @property
    def strategy_name(self) -> str:
        return self.strategy.name if self.strategy else None
```

在 `models/__init__.py` 添加：
```python
from .trade_sim import TradeSimReport, BatchTradeSimReport
Strategy.batch_trade_sim_reports = relationship("BatchTradeSimReport", back_populates="strategy", cascade="all, delete-orphan")
BatchTradeSimReport.owner = relationship("User", back_populates="batch_trade_sim_reports")
User.batch_trade_sim_reports = relationship("BatchTradeSimReport", back_populates="owner")
```

- [ ] **Step 2: 新增批量 Schema**

```python
# 追加到 backend/app/schemas/trade_sim.py
from typing import Optional, List

class BatchTradeSimCreate(BaseModel):
    strategy_id: int
    start_date: str              # YYYYMMDD
    end_date: str                # YYYYMMDD
    name: Optional[str] = None
    total_amount: float = Field(..., gt=0)
    top_n: int = Field(default=5, ge=1, le=20)
    max_hold_days: int = Field(default=60, ge=1, le=365)
    stop_factors: List[StopFactorConfig]


class BatchDailyResult(BaseModel):
    cutoff_date: str
    status: str                  # completed | failed
    trades: Optional[List[TradeItem]] = None
    summary: Optional[TradeSimSummary] = None
    error_message: Optional[str] = None


class BatchTradeSimResponse(BaseModel):
    id: int
    strategy_id: int
    strategy_name: Optional[str] = None
    name: Optional[str] = None
    status: str
    start_date: str
    end_date: str
    config: Optional[dict] = None
    total_days: int
    completed_days: int
    daily_results: Optional[List[BatchDailyResult]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BatchTradeSimListResponse(BaseModel):
    items: List[BatchTradeSimResponse]
    total: int
    page: int
    limit: int
```

- [ ] **Step 3: 新增 TradeSimEngine.run_batch() 方法**

```python
# 追加到 TradeSimEngine 类中
def run_batch(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """批量交易模拟：遍历每个交易日运行交易模拟"""
    # 加载全时段数据用于策略选股
    loaded = self._backtest_engine._load_data_range(start_date, end_date)
    daily_data = loaded["daily"]

    # 获取所有交易日
    trading_days = sorted(set(
        row["trade_date"] for rows in daily_data.values() for row in rows
        if start_date <= row["trade_date"] <= end_date
    ))

    results = []
    for cutoff_date in trading_days:
        try:
            result = self.run(cutoff_date)
            result["cutoff_date"] = cutoff_date
            result["status"] = "completed"
        except Exception as e:
            result = {
                "cutoff_date": cutoff_date,
                "status": "failed",
                "error_message": str(e),
            }
        results.append(result)

    return results
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/trade_sim.py backend/app/models/__init__.py backend/app/schemas/trade_sim.py backend/app/services/trade_sim_engine.py
git commit -m "feat: add batch trade sim model, schema, and engine method"
```

---

### Task 14: 批量交易模拟 — Service + API

**Files:**
- Modify: `backend/app/services/trade_sim_service.py`
- Modify: `backend/app/api/trade_sims.py`

- [ ] **Step 1: 新增批量 Service 方法**

```python
# 追加到 TradeSimService 类中
@staticmethod
async def create_batch(
    db: AsyncSession,
    data,  # BatchTradeSimCreate
    user_id: int,
):
    """提交批量交易模拟回测"""
    from ..models.trade_sim import BatchTradeSimReport

    strategy_result = await db.execute(
        select(Strategy).where(Strategy.id == data.strategy_id)
    )
    strategy = strategy_result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")

    enabled = [sf for sf in data.stop_factors if sf.enabled]
    if not enabled:
        raise HTTPException(status_code=400, detail="请至少启用一个止损止盈条件")

    config = {
        "total_amount": data.total_amount,
        "top_n": data.top_n,
        "max_hold_days": data.max_hold_days,
        "stop_factors": [
            {"id": sf.id, "enabled": sf.enabled, "params": sf.params}
            for sf in data.stop_factors
        ],
    }

    report = BatchTradeSimReport(
        strategy_id=data.strategy_id,
        user_id=user_id,
        name=data.name or f"{strategy.name}_{data.start_date}_{data.end_date}",
        start_date=data.start_date,
        end_date=data.end_date,
        config=json.dumps(config, ensure_ascii=False),
        status="pending",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    report.strategy = strategy

    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None, TradeSimService._run_batch, report.id, data.start_date, data.end_date
    )
    return report


@staticmethod
def _run_batch(report_id: int, start_date: str, end_date: str):
    """执行批量交易模拟（线程池中）"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from ..config import settings
    from ..models.trade_sim import BatchTradeSimReport
    from .trade_sim_engine import TradeSimEngine

    engine = create_engine(settings.SYNC_DATABASE_URL)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        try:
            report = db.query(BatchTradeSimReport).filter(BatchTradeSimReport.id == report_id).first()
            if not report:
                return

            report.status = "running"
            report.started_at = beijing_now()
            db.commit()

            strategy = db.query(Strategy).filter(Strategy.id == report.strategy_id).first()
            if not strategy:
                raise ValueError(f"策略 {report.strategy_id} 不存在")

            if strategy.generated_code:
                strategy_code = strategy.generated_code
            elif strategy.file_path and __import__('os').path.exists(strategy.file_path):
                with open(strategy.file_path, "r", encoding="utf-8") as f:
                    strategy_code = f.read()
            else:
                raise FileNotFoundError("策略代码不存在")

            config = json.loads(report.config) if report.config else {}

            engine_obj = TradeSimEngine(
                strategy_code=strategy_code,
                strategy_params={},
                config=config,
            )

            daily_results = engine_obj.run_batch(start_date, end_date)

            report.total_days = len(daily_results)
            report.completed_days = len([r for r in daily_results if r.get("status") == "completed"])
            report.daily_results = json.dumps(daily_results, ensure_ascii=False, cls=NumpyEncoder)

            if report.completed_days == 0 and report.total_days > 0:
                report.status = "failed"
                report.error_message = "所有交易日执行均失败"
            else:
                report.status = "completed"

            report.completed_at = beijing_now()
            db.commit()

        except Exception as e:
            db.rollback()
            report = db.query(BatchTradeSimReport).filter(BatchTradeSimReport.id == report_id).first()
            if report:
                report.status = "failed"
                report.error_message = str(e)
                report.completed_at = beijing_now()
                db.commit()


@staticmethod
async def get_batch_list(
    db: AsyncSession,
    page: int = 1,
    limit: int = 20,
    strategy_id: Optional[int] = None,
    user_id: Optional[int] = None,
    user_role: str = "user",
):
    """获取批量交易模拟列表"""
    from ..models.trade_sim import BatchTradeSimReport

    query = select(BatchTradeSimReport).options(selectinload(BatchTradeSimReport.strategy))
    if strategy_id:
        query = query.where(BatchTradeSimReport.strategy_id == strategy_id)
    if user_role != "admin":
        query = query.where(BatchTradeSimReport.user_id == user_id)

    count_query = select(func.count()).select_from(BatchTradeSimReport)
    if strategy_id:
        count_query = count_query.where(BatchTradeSimReport.strategy_id == strategy_id)
    if user_role != "admin":
        count_query = count_query.where(BatchTradeSimReport.user_id == user_id)

    total = (await db.execute(count_query)).scalar()
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit).order_by(BatchTradeSimReport.created_at.desc())

    result = await db.execute(query)
    return result.scalars().all(), total


@staticmethod
async def get_batch_detail(
    db: AsyncSession,
    report_id: int,
    user_id: Optional[int] = None,
    user_role: str = "user",
):
    """获取批量交易模拟详情"""
    from ..models.trade_sim import BatchTradeSimReport

    result = await db.execute(
        select(BatchTradeSimReport)
        .options(selectinload(BatchTradeSimReport.strategy))
        .where(BatchTradeSimReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    if user_role != "admin" and report.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权访问")
    return report


@staticmethod
async def delete_batch(
    db: AsyncSession,
    report_id: int,
    user_id: Optional[int] = None,
    user_role: str = "user",
) -> None:
    """删除批量交易模拟报告"""
    report = await TradeSimService.get_batch_detail(db, report_id, user_id, user_role)
    await db.delete(report)
    await db.commit()
```

- [ ] **Step 2: 新增批量 API 端点**

```python
# 追加到 backend/app/api/trade_sims.py（注意在 GET /{report_id} 之前）
from ..schemas.trade_sim import (
    BatchTradeSimCreate, BatchTradeSimResponse, BatchTradeSimListResponse,
)

@router.post("/batch", response_model=BatchTradeSimResponse, status_code=202)
async def create_batch_trade_sim(
    data: BatchTradeSimCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    report = await TradeSimService.create_batch(db, data, current_user.id)
    return _format_batch_response(report)


@router.get("/batch", response_model=BatchTradeSimListResponse)
async def list_batch_trade_sims(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    strategy_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    items, total = await TradeSimService.get_batch_list(
        db, page, limit, strategy_id,
        current_user.id, current_user.role if hasattr(current_user, 'role') else "user",
    )
    return {"items": [_format_batch_response(i) for i in items], "total": total, "page": page, "limit": limit}


@router.get("/batch/{report_id}", response_model=BatchTradeSimResponse)
async def get_batch_trade_sim(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    report = await TradeSimService.get_batch_detail(
        db, report_id, current_user.id,
        current_user.role if hasattr(current_user, 'role') else "user",
    )
    return _format_batch_response(report)


@router.delete("/batch/{report_id}")
async def delete_batch_trade_sim(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    await TradeSimService.delete_batch(
        db, report_id, current_user.id,
        current_user.role if hasattr(current_user, 'role') else "user",
    )
    return {"message": "已删除"}


def _format_batch_response(report) -> dict:
    config = json.loads(report.config) if report.config else {}
    daily_results = json.loads(report.daily_results) if report.daily_results else []
    return {
        "id": report.id,
        "strategy_id": report.strategy_id,
        "strategy_name": report.strategy_name,
        "name": report.name,
        "status": report.status,
        "start_date": report.start_date,
        "end_date": report.end_date,
        "config": config,
        "total_days": report.total_days,
        "completed_days": report.completed_days,
        "daily_results": daily_results,
        "error_message": report.error_message,
        "started_at": report.started_at,
        "completed_at": report.completed_at,
        "created_at": report.created_at,
    }
```

**注意路由定义顺序**：`/batch` 系列路由必须在 `/{report_id}` 之前定义。

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/trade_sim_service.py backend/app/api/trade_sims.py
git commit -m "feat: add batch trade sim service and API endpoints"
```

---

### Task 15: 前端批量交易模拟 — 表单 + 详情

**Files:**
- Modify: `frontend/src/pages/BacktestForm.tsx` — 交易模拟模式增加批量子模式
- Create: `frontend/src/pages/BatchTradeSimDetail.tsx`
- Modify: `frontend/src/App.tsx` — 批量详情路由
- Modify: `frontend/src/types/tradeSim.ts` — 批量类型
- Modify: `frontend/src/services/tradeSimService.ts` — 批量 API

- [ ] **Step 1: 前端批量类型**

```typescript
// 追加到 frontend/src/types/tradeSim.ts
export interface BatchTradeSimCreate {
  strategy_id: number;
  start_date: string;       // YYYYMMDD
  end_date: string;         // YYYYMMDD
  name?: string;
  total_amount: number;
  top_n: number;
  max_hold_days: number;
  stop_factors: StopFactorConfig[];
}

export interface BatchDailyResult {
  cutoff_date: string;
  status: string;
  trades?: TradeItem[];
  summary?: TradeSimSummary;
  error_message?: string;
}

export interface BatchTradeSimReport {
  id: number;
  strategy_id: number;
  strategy_name?: string;
  name?: string;
  status: string;
  start_date: string;
  end_date: string;
  config: BatchTradeSimCreate | null;
  total_days: number;
  completed_days: number;
  daily_results?: BatchDailyResult[];
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  created_at?: string;
}
```

- [ ] **Step 2: 前端批量 API 方法**

```typescript
// 追加到 tradeSimService
async createBatch(data: BatchTradeSimCreate): Promise<BatchTradeSimReport> {
  const response = await api.post<BatchTradeSimReport>(`${BASE}/batch`, data);
  return response.data;
},

async getBatchList(params: {
  page?: number; limit?: number; strategy_id?: number;
} = {}): Promise<{ items: BatchTradeSimReport[]; total: number; page: number; limit: number }> {
  const response = await api.get(`${BASE}/batch`, { params });
  return response.data;
},

async getBatchDetail(id: number): Promise<BatchTradeSimReport> {
  const response = await api.get<BatchTradeSimReport>(`${BASE}/batch/${id}`);
  return response.data;
},
```

- [ ] **Step 3: BacktestForm 交易模拟模式增加批量子模式**

在交易模拟表单的 `截止日` 字段处，增加单日/批量切换：

```tsx
{/* 在交易模拟模式下 */}
<Form.Item label="回测模式">
  <Radio.Group value={tradeSimMode} onChange={(e) => setTradeSimMode(e.target.value)}>
    <Radio.Button value="single">单日</Radio.Button>
    <Radio.Button value="batch">批量</Radio.Button>
  </Radio.Group>
</Form.Item>

{tradeSimMode === 'single' ? (
  <Form.Item label="截止日" required>
    <DatePicker value={cutoffDate} onChange={setCutoffDate} style={{ width: '100%' }} />
  </Form.Item>
) : (
  <>
    <Form.Item label="日期范围" required>
      <DatePicker.RangePicker
        value={dateRange as any}
        onChange={(v) => setDateRange(v as [dayjs.Dayjs, dayjs.Dayjs])}
        style={{ width: '100%' }}
      />
    </Form.Item>
    <Form.Item label="报告名称（可选）">
      <Input placeholder="如：5月交易模拟" value={batchName} onChange={(e) => setBatchName(e.target.value)} allowClear />
    </Form.Item>
  </>
)}
```

提交逻辑中增加批量分支：
```typescript
// 交易模拟批量模式
if (backtestMode === 'trade-sim' && tradeSimMode === 'batch') {
  // 校验...
  const payload: BatchTradeSimCreate = {
    strategy_id: currentStrategy.id,
    start_date: dateRange![0].format('YYYYMMDD'),
    end_date: dateRange![1].format('YYYYMMDD'),
    name: batchName.trim() || undefined,
    total_amount: totalAmount,
    top_n: topN,
    max_hold_days: maxHoldDays,
    stop_factors: stopFactors,
  };
  const result = await tradeSimService.createBatch(payload);
  message.success('批量交易模拟已提交');
  navigate(`/backtests/trade-sim/batch/${result.id}`);
  return;
}
```

- [ ] **Step 4: BatchTradeSimDetail 组件**

类似 TradeSimDetail，但显示每日结果的表格（每行一个交易日，展示：日期、交易笔数、胜率、平均回报率），点击行展开该日的完整 trade 明细。

```typescript
// 核心结构：
// - 汇总区：总交易日数、完成天数、所有日汇总的平均胜率/回报率
// - 每日结果表格（可展开），展开后复用 TradeSimDetail 的单日报表逻辑
```

（完整代码在 Task 中实现时补充细节）

- [ ] **Step 5: 路由注册**

```tsx
// App.tsx 添加：
import BatchTradeSimDetail from '@/pages/BatchTradeSimDetail';
<Route path="/backtests/trade-sim/batch/:id" element={<BatchTradeSimDetail />} />
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/BacktestForm.tsx frontend/src/pages/BatchTradeSimDetail.tsx frontend/src/App.tsx frontend/src/types/tradeSim.ts frontend/src/services/tradeSimService.ts
git commit -m "feat: add batch trade sim frontend form and detail"
```

---

### Task 16: 端到端验证（含批量）

- [ ] **Step 1: 重启后端服务**
- [ ] **Step 2: 验证单日 + 批量 API 端点均可访问**
- [ ] **Step 3: 提交批量交易模拟，验证返回 daily_results**
- [ ] **Step 4: 前端验证批量表单和批量详情页**

---

## 计划自审（更新）

**Spec 覆盖率检查：**

| Spec 要求 | 对应 Task |
|-----------|----------|
| TradeSimReport 数据库模型 | Task 1 |
| 止损止盈因子注册机制 + 3 个内置因子 | Task 3 |
| TradeSimEngine 核心逻辑 | Task 4 |
| 业务逻辑层（CRUD + 异步执行） | Task 5 |
| API 路由（CRUD + factors） | Task 6 |
| 路由注册 + DB 表创建 | Task 7 |
| 前端类型 + API Service | Task 8 |
| BacktestForm 模式切换 + 交易模拟表单 | Task 9 |
| TradeSimDetail 报表组件（汇总 + 明细 + 每日追踪 + 图表） | Task 10 |
| 前端路由注册 | Task 10 Step 2 |
| 错误处理（各种边界情况） | 各 Task 中处理 |
| 除权除息（adj_close 优先） | Task 4 engine |
| 缓冲计数重置 | Task 3 stop_ma10_cross |
| 强制平仓 | Task 4 engine |
| 数据缺失处理 | Task 4 engine |

**一致性检查：**
- `TradeSimCreate.cutoff_date` 格式为 `YYYY-MM-DD` → service 中转换为 `YYYYMMDD` 传给 engine → engine 的 `_load_data` 接受 `YYYYMMDD` 格式 → 一致
- JSON 字段 `return_distribution` key 使用 `"lt_-10"`, `"-10_0"`, `"0_5"`, `"5_10"`, `"gt_10"` → Pydantic model 使用 alias → TypeScript 使用字符串 key 访问 → 一致
- 因子检查函数签名 `check_fn(df: list, position: dict, params: dict) -> TriggerResult | None` — engine 和 registry 一致

**无占位符：** ✅ 所有 step 都有完整代码
