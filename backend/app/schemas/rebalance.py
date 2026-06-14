"""每日调仓回测 schemas"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Any, Dict


class RebalanceCreate(BaseModel):
    """提交调仓回测请求"""
    strategy_id: int = Field(..., gt=0, description="策略 ID")
    start_date: str = Field(..., min_length=8, max_length=8, description="开始日期 YYYYMMDD")
    end_date: str = Field(..., min_length=8, max_length=8, description="结束日期 YYYYMMDD")
    name: Optional[str] = Field(None, max_length=255, description="报告名称")
    initial_capital: float = Field(100000, gt=0, description="初始资金")
    config: Optional[Dict[str, Any]] = Field(None, description="策略自定义参数 {N, M, index_code, ...}")


class RebalanceResponse(BaseModel):
    """调仓回测响应"""
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
    daily_snapshots: Optional[list] = None
    trades: Optional[list] = None
    summary: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RebalanceListResponse(BaseModel):
    """调仓回测列表响应"""
    items: List[RebalanceResponse]
    total: int
    page: int = 1
    limit: int = 20
