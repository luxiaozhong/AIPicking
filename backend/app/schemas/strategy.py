"""策略相关的 Pydantic schemas"""

from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List, Dict, Any
import json


# ------- 因子配置相关 -------

class FactorItem(BaseModel):
    """单个因子配置"""
    factor_id: str = Field(..., description="因子ID")
    params: Dict[str, Any] = Field(default_factory=dict, description="因子参数")


class SignalGroup(BaseModel):
    """信号组（买入/卖出）"""
    logic: str = Field("AND", description="因子组合逻辑: AND / OR")
    factors: List[FactorItem] = Field(default_factory=list, description="因子列表")


class FactorConfig(BaseModel):
    """因子组合配置"""
    buy_signals: SignalGroup = Field(default_factory=lambda: SignalGroup())
    sell_signals: SignalGroup = Field(default_factory=lambda: SignalGroup())
    risk_factors: List[FactorItem] = Field(default_factory=list, description="风控因子列表")


# ------- 策略相关 -------

class StrategyBase(BaseModel):
    """策略基础 schema"""
    name: str = Field(..., min_length=1, max_length=255, description="策略名称")
    description: Optional[str] = Field(None, description="策略描述")
    tags: Optional[List[str]] = Field(None, description="标签列表")


class StrategyCreate(StrategyBase):
    """创建策略请求 schema（因子模式）"""
    factor_config: FactorConfig = Field(..., description="因子组合配置")


class StrategyCreateUpload(StrategyBase):
    """创建策略请求 schema（上传模式，兼容旧版）"""
    file: Optional[str] = Field(None, description="策略代码（文本）")


class StrategyUpdate(BaseModel):
    """更新策略请求 schema"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    factor_config: Optional[FactorConfig] = None


class StrategyResponse(StrategyBase):
    """策略响应 schema"""
    id: int
    user_id: Optional[int] = None
    owner_name: Optional[str] = None
    status: str = "active"
    version: int = 1
    is_published: bool = False
    file_path: Optional[str] = None
    factor_config: Optional[Dict[str, Any]] = None
    generated_code: Optional[str] = None
    avg_score: Optional[float] = None
    rating_count: int = 0
    created_at: datetime
    updated_at: datetime

    @field_validator('tags', mode='before')
    @classmethod
    def parse_tags(cls, v):
        """解析 tags，如果是逗号分隔的字符串则转换为列表"""
        if isinstance(v, str):
            return [t.strip() for t in v.split(',') if t.strip()]
        return v

    @field_validator('factor_config', mode='before')
    @classmethod
    def parse_factor_config(cls, v):
        """解析 factor_config，如果是字符串则解析为字典"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    class Config:
        from_attributes = True


class StrategyListResponse(BaseModel):
    """策略列表响应 schema"""
    items: List[StrategyResponse]
    total: int
    page: int = 1
    limit: int = 20


class StrategyUploadResponse(BaseModel):
    """策略上传/创建响应 schema"""
    code: int = 0
    message: str
    data: Optional[StrategyResponse] = None
    errors: Optional[List[str]] = None


class PublishResponse(BaseModel):
    """发布/取消发布响应"""
    code: int = 0
    message: str
    is_published: bool
