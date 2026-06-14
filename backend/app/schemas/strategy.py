"""策略相关的 Pydantic schemas"""

from pydantic import BaseModel, Field, field_validator, model_validator
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


class ConditionItem(BaseModel):
    """单个选股条件/评分修正配置"""
    condition_id: str = Field(..., description="条件ID")
    params: Dict[str, Any] = Field(default_factory=dict, description="条件参数")


class SelectionGroup(BaseModel):
    """选股条件组"""
    logic: str = Field("AND", description="条件组合逻辑: AND / OR")
    conditions: List[ConditionItem] = Field(default_factory=list, description="条件列表")


class FactorConfig(BaseModel):
    """因子组合配置"""
    selection_conditions: SelectionGroup = Field(default_factory=lambda: SelectionGroup())
    scoring_modifiers: List[ConditionItem] = Field(default_factory=list, description="评分修正列表")
    buy_signals: SignalGroup = Field(default_factory=lambda: SignalGroup())
    sell_signals: SignalGroup = Field(default_factory=lambda: SignalGroup())
    risk_factors: List[FactorItem] = Field(default_factory=list, description="风控因子列表")

    @staticmethod
    def _has_any_factor(config: "FactorConfig") -> bool:
        """检查是否有任何因子/条件被配置"""
        return bool(
            config.selection_conditions.conditions
            or config.scoring_modifiers
            or config.buy_signals.factors
            or config.sell_signals.factors
            or config.risk_factors
        )


# ------- 策略相关 -------

class StrategyBase(BaseModel):
    """策略基础 schema"""
    name: str = Field(..., min_length=1, max_length=255, description="策略名称")
    description: Optional[str] = Field(None, description="策略描述")
    tags: Optional[List[str]] = Field(None, description="标签列表")


class StrategyCreate(StrategyBase):
    """创建策略请求 schema（因子模式）"""
    factor_config: FactorConfig = Field(..., description="因子组合配置")

    @model_validator(mode='after')
    def check_has_any_factor(self):
        if not FactorConfig._has_any_factor(self.factor_config):
            raise ValueError('请至少添加一个因子（买入信号、卖出信号、风控因子、选股条件或评分修正）')
        return self


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

    @model_validator(mode='after')
    def check_factor_config_not_empty(self):
        if self.factor_config is not None and not FactorConfig._has_any_factor(self.factor_config):
            raise ValueError('请至少添加一个因子（买入信号、卖出信号、风控因子、选股条件或评分修正）')
        return self


class StrategyResponse(StrategyBase):
    """策略响应 schema"""
    id: int
    user_id: Optional[int] = None
    owner_name: Optional[str] = None
    status: str = "active"
    version: int = 1
    is_published: bool = False
    file_path: Optional[str] = None
    params_schema: Optional[str] = None
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
