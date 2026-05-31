"""评分业务逻辑层"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from ..models.strategy_rating import StrategyRating
from ..models.strategy import Strategy


class RatingService:
    """评分服务类"""

    @staticmethod
    async def upsert_rating(
        db: AsyncSession,
        strategy_id: int,
        user_id: int,
        score: int,
    ) -> StrategyRating:
        """提交或更新评分"""
        # 检查策略是否存在且可访问
        strategy = await db.get(Strategy, strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="策略不存在")

        # 查找已有评分
        result = await db.execute(
            select(StrategyRating).where(
                StrategyRating.strategy_id == strategy_id,
                StrategyRating.user_id == user_id,
            )
        )
        rating = result.scalar_one_or_none()

        if rating:
            rating.score = score
        else:
            rating = StrategyRating(
                strategy_id=strategy_id,
                user_id=user_id,
                score=score,
            )
            db.add(rating)

        await db.commit()
        await db.refresh(rating)
        return rating

    @staticmethod
    async def get_rating_stats(
        db: AsyncSession,
        strategy_id: int,
        current_user_id: Optional[int] = None,
    ) -> dict:
        """获取评分统计"""
        # 均分 & 总数
        result = await db.execute(
            select(
                func.avg(StrategyRating.score).label("avg"),
                func.count(StrategyRating.id).label("cnt"),
            ).where(StrategyRating.strategy_id == strategy_id)
        )
        row = result.one()
        avg = float(row[0]) if row[0] else None
        cnt = row[1] or 0

        # 分布
        dist_result = await db.execute(
            select(
                StrategyRating.score,
                func.count(StrategyRating.id),
            ).where(StrategyRating.strategy_id == strategy_id)
            .group_by(StrategyRating.score)
        )
        distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for score, count in dist_result.all():
            distribution[score] = count

        # 当前用户评分
        current_user_score = None
        if current_user_id:
            u_result = await db.execute(
                select(StrategyRating.score).where(
                    StrategyRating.strategy_id == strategy_id,
                    StrategyRating.user_id == current_user_id,
                )
            )
            score_row = u_result.scalar_one_or_none()
            current_user_score = score_row

        return {
            "average": avg,
            "count": cnt,
            "distribution": distribution,
            "current_user_score": current_user_score,
        }
