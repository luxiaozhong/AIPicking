"""教育内容 API"""

import yaml
from pathlib import Path
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


CASES_DIR = Path(__file__).resolve().parent.parent.parent / "content" / "education" / "macd-interactive"


@router.get("/macd-interactive/cases")
async def get_macd_cases(
    current_user: User = Depends(get_current_user),
):
    """获取 MACD 交互学习案例配置"""
    cases_file = CASES_DIR / "cases.yaml"
    if not cases_file.exists():
        return {"code": 1, "message": "案例配置不存在", "data": None}
    try:
        data = yaml.safe_load(cases_file.read_text(encoding="utf-8"))
    except Exception:
        return {"code": 1, "message": "案例配置解析失败", "data": None}

    # 为每个步骤加载内容
    for case in data.get("cases", []):
        for step in case.get("steps", []):
            content_file = step.get("content_file", "")
            filepath = CASES_DIR / "steps" / content_file
            if filepath.exists():
                try:
                    step["content"] = filepath.read_text(encoding="utf-8")
                except Exception:
                    step["content"] = ""
            else:
                step["content"] = ""
    return {"code": 0, "message": "ok", "data": data}

RSI_CASES_DIR = Path(__file__).resolve().parent.parent.parent / "content" / "education" / "rsi-interactive"


@router.get("/rsi-interactive/cases")
async def get_rsi_cases(
    current_user: User = Depends(get_current_user),
):
    """获取 RSI 交互学习案例配置"""
    cases_file = RSI_CASES_DIR / "cases.yaml"
    if not cases_file.exists():
        return {"code": 1, "message": "案例配置不存在", "data": None}
    try:
        data = yaml.safe_load(cases_file.read_text(encoding="utf-8"))
    except Exception:
        return {"code": 1, "message": "案例配置解析失败", "data": None}
    for case in data.get("cases", []):
        for step in case.get("steps", []):
            content_file = step.get("content_file", "")
            filepath = RSI_CASES_DIR / "steps" / content_file
            if filepath.exists():
                try:
                    step["content"] = filepath.read_text(encoding="utf-8")
                except Exception:
                    step["content"] = ""
            else:
                step["content"] = ""
    return {"code": 0, "message": "ok", "data": data}

KDJ_CASES_DIR = Path(__file__).resolve().parent.parent.parent / "content" / "education" / "kdj-interactive"


@router.get("/kdj-interactive/cases")
async def get_kdj_cases(current_user: User = Depends(get_current_user)):
    """获取 KDJ 交互学习案例配置"""
    cases_file = KDJ_CASES_DIR / "cases.yaml"
    if not cases_file.exists():
        return {"code": 1, "message": "案例配置不存在", "data": None}
    try:
        data = yaml.safe_load(cases_file.read_text(encoding="utf-8"))
    except Exception:
        return {"code": 1, "message": "案例配置解析失败", "data": None}
    for case in data.get("cases", []):
        for step in case.get("steps", []):
            content_file = step.get("content_file", "")
            filepath = KDJ_CASES_DIR / "steps" / content_file
            if filepath.exists():
                try:
                    step["content"] = filepath.read_text(encoding="utf-8")
                except Exception:
                    step["content"] = ""
            else:
                step["content"] = ""
    return {"code": 0, "message": "ok", "data": data}

BOLLINGER_CASES_DIR = Path(__file__).resolve().parent.parent.parent / "content" / "education" / "bollinger-interactive"


@router.get("/bollinger-interactive/cases")
async def get_bollinger_cases(current_user: User = Depends(get_current_user)):
    """获取布林带交互学习案例配置"""
    cases_file = BOLLINGER_CASES_DIR / "cases.yaml"
    if not cases_file.exists():
        return {"code": 1, "message": "案例配置不存在", "data": None}
    try:
        data = yaml.safe_load(cases_file.read_text(encoding="utf-8"))
    except Exception:
        return {"code": 1, "message": "案例配置解析失败", "data": None}
    for case in data.get("cases", []):
        for step in case.get("steps", []):
            content_file = step.get("content_file", "")
            filepath = BOLLINGER_CASES_DIR / "steps" / content_file
            if filepath.exists():
                try: step["content"] = filepath.read_text(encoding="utf-8")
                except Exception: step["content"] = ""
            else: step["content"] = ""
    return {"code": 0, "message": "ok", "data": data}
