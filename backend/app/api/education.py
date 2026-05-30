"""教育内容 API"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException

from ..middleware.auth import get_current_user
from ..models.user import User
from ..services.education_service import EducationService

router = APIRouter()


@router.get("/categories")
async def get_categories(
    current_user: User = Depends(get_current_user),
):
    """获取所有分类"""
    svc = EducationService.instance()
    return {"code": 0, "message": "ok", "data": svc.get_categories()}


@router.get("/articles")
async def get_articles(
    category: Optional[str] = Query(None, description="按分类筛选"),
    current_user: User = Depends(get_current_user),
):
    """获取文章列表（不含正文）"""
    svc = EducationService.instance()
    articles = svc.get_articles(category=category)
    # 列表不返回 body
    articles_preview = [
        {k: v for k, v in a.items() if k != "body"}
        for a in articles
    ]
    return {"code": 0, "message": "ok", "data": articles_preview}


@router.get("/articles/{slug}")
async def get_article(
    slug: str,
    current_user: User = Depends(get_current_user),
):
    """获取单篇文章完整内容"""
    svc = EducationService.instance()
    article = svc.get_article(slug)
    if article is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    return {"code": 0, "message": "ok", "data": article}
