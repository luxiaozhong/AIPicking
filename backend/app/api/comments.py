"""评论相关 API 路由"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.comment_service import CommentService
from ..schemas.comment import CommentCreate, CommentListResponse
from ..middleware.auth import get_current_user
from ..models.user import User

router = APIRouter()


@router.post("/{strategy_id}/comments")
async def create_comment(
    strategy_id: int,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发表评论"""
    comment = await CommentService.create_comment(
        db, strategy_id, user_id=current_user.id, content=body.content
    )
    return {
        "code": 0,
        "message": "评论成功",
        "data": {
            "id": comment.id,
            "content": comment.content,
            "user_name": comment.user.username if comment.user else None,
            "created_at": comment.created_at.isoformat(),
        }
    }


@router.get("/{strategy_id}/comments", response_model=CommentListResponse)
async def get_comments(
    strategy_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取评论列表"""
    comments, total = await CommentService.get_comments(db, strategy_id, page, limit)
    return {
        "items": comments,
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.delete("/{strategy_id}/comments/{comment_id}")
async def delete_comment(
    strategy_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除评论（评论作者或策略创建者）"""
    await CommentService.delete_comment(db, comment_id, user_id=current_user.id)
    return {"code": 0, "message": "删除成功"}
