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
