"""因子相关 API 路由"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..factors import list_factors, get_factor_meta, get_all_categories

router = APIRouter()


@router.get("/factors")
async def list_all_factors(
    category: Optional[str] = Query(None, description="按分类筛选"),
    db: AsyncSession = Depends(get_db)
):
    """获取因子列表（按分类）"""
    factors = list_factors(category)
    categories = get_all_categories()
    return {
        "code": 0,
        "data": {
            "factors": factors,
            "categories": categories,
        }
    }


@router.get("/factors/{factor_id}")
async def get_factor_detail(
    factor_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取单个因子详情（含参数定义）"""
    meta = get_factor_meta(factor_id)
    if meta is None:
        return {"code": 404, "message": f"因子不存在: {factor_id}", "data": None}
    return {"code": 0, "data": meta}
