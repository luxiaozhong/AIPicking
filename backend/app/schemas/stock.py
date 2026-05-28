"""股票搜索相关 Pydantic 模型"""

from pydantic import BaseModel


class StockItem(BaseModel):
    ts_code: str
    symbol: str
    name: str
    market: str


class StockSearchResponse(BaseModel):
    items: list[StockItem]
    total: int
