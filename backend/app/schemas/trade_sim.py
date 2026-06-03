"""交易模拟回测 Pydantic Schema"""

from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
import json


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
    total_pnl: float = 0.0
    total_qualifying: int = 0
    base_stock_count: int = 0
    pick_rate: float = 0.0
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

    @field_validator('config', 'trades', 'summary', mode='before')
    @classmethod
    def parse_json_fields(cls, v):
        """解析 JSON 字符串字段"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v

    class Config:
        from_attributes = True


class TradeSimListResponse(BaseModel):
    items: List[TradeSimResponse]
    total: int
    page: int
    limit: int


# --- 批量请求 ---

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

    @field_validator('config', 'daily_results', mode='before')
    @classmethod
    def parse_json_fields(cls, v):
        """解析 JSON 字符串字段"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v

    class Config:
        from_attributes = True


class BatchTradeSimListResponse(BaseModel):
    items: List[BatchTradeSimResponse]
    total: int
    page: int
    limit: int
