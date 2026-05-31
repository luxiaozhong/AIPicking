"""评分相关 API 路由"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.rating_service import RatingService
from ..schemas.rating import RatingCreate, RatingStats
from ..middleware.auth import get_current_user
from ..models.user import User

router = APIRouter()


@router.post("/{strategy_id}/ratings")
async def rate_strategy(
    strategy_id: int,
    body: RatingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交或更新评分"""
    rating = await RatingService.upsert_rating(
        db, strategy_id, user_id=current_user.id, score=body.score
    )
    return {
        "code": 0,
        "message": "评分成功",
        "data": {"id": rating.id, "score": rating.score}
    }


@router.get("/{strategy_id}/ratings", response_model=RatingStats)
async def get_ratings(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取评分统计（含当前用户评分）"""
    return await RatingService.get_rating_stats(
        db, strategy_id, current_user_id=current_user.id
    )
