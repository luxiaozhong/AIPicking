"""回测相关的 Pydantic schemas（新逻辑）"""

from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, Any, List
import json


class BacktestSummary(BaseModel):
    """回测汇总指标 schema"""
    total_recommendations: int = Field(..., description="推荐股票总数")
    avg_return_3d: float = Field(..., description="3天平均收益")
    avg_return_7d: float = Field(..., description="7天平均收益")
    avg_return_15d: float = Field(..., description="15天平均收益")
    win_rate_3d: float = Field(..., description="3天胜率")
    win_rate_7d: float = Field(..., description="7天胜率")
    win_rate_15d: float = Field(..., description="15天胜率")
    best_return_15d: float = Field(..., description="15天最高涨幅")
    worst_return_15d: float = Field(..., description="15天最大跌幅")
    total_qualifying: int = Field(0, description="满足策略条件的股票总数（topN 截断前）")
    base_stock_count: int = Field(0, description="选中板块的股票总数（池子大小）")
    pick_rate: float = Field(0.0, description="入选率 = total_qualifying / base_stock_count")


class RecommendationItem(BaseModel):
    """推荐股票项 schema"""
    ts_code: str
    name: str
    score: float
    signal: str
    return_0d: Optional[float] = None
    return_3d: Optional[float] = None
    return_7d: Optional[float] = None
    return_15d: Optional[float] = None
    breakdown: Optional[dict] = None
    details: Optional[dict] = None


class BacktestCreate(BaseModel):
    """提交回测请求 schema"""
    strategy_id: int = Field(..., description="策略 ID")
    cutoff_date: str = Field(..., description="截止日，格式 YYYYMMDD")
    track_days: List[int] = Field([3, 7, 15], description="追踪天数")
    config: Optional[dict] = Field(None, description="策略自定义配置（如目标股票代码 ts_code）")


class BacktestResponse(BaseModel):
    """回测报告响应 schema"""
    id: int
    strategy_id: int
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    strategy_name: Optional[str] = None
    name: Optional[str] = None
    status: str = "pending"
    cutoff_date: str
    config: Optional[dict] = None
    recommendations: Optional[List[RecommendationItem]] = None
    summary: Optional[BacktestSummary] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @field_validator('config', 'recommendations', 'summary', mode='before')
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


class BacktestListResponse(BaseModel):
    """回测报告列表响应 schema"""
    items: list[BacktestResponse]
    total: int
    page: int = 1
    limit: int = 20


class StrategyExecuteResponse(BaseModel):
    """策略执行响应 schema（同步返回）"""
    strategy_id: int
    strategy_name: str
    cutoff_date: str
    recommendations: list[RecommendationItem]
    total: int


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
    cutoff_date: str = Field(..., description="截止日，格式 YYYYMMDD")
    status: str = Field("pending", description="状态：completed / failed")
    input: Optional[dict] = Field(None, description="策略输入（cutoff_date + config）")
    recommendations: Optional[List[RecommendationItem]] = Field(None, description="推荐股票列表")
    summary: Optional[BacktestSummary] = Field(None, description="当日汇总指标")
    error_message: Optional[str] = Field(None, description="错误信息")


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
        """解析 JSON 字符串字段"""
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
