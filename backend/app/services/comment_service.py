"""评论业务逻辑层"""

from typing import List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from ..models.strategy_comment import StrategyComment
from ..models.strategy import Strategy


class CommentService:
    """评论服务类"""

    @staticmethod
    async def create_comment(
        db: AsyncSession,
        strategy_id: int,
        user_id: int,
        content: str,
    ) -> StrategyComment:
        """发表评论"""
        strategy = await db.get(Strategy, strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="策略不存在")

        comment = StrategyComment(
            strategy_id=strategy_id,
            user_id=user_id,
            content=content,
        )
        db.add(comment)
        await db.commit()
        # 重新加载以获取 user 关系
        result = await db.execute(
            select(StrategyComment)
            .options(selectinload(StrategyComment.user))
            .where(StrategyComment.id == comment.id)
        )
        return result.scalar_one()

    @staticmethod
    async def get_comments(
        db: AsyncSession,
        strategy_id: int,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[StrategyComment], int]:
        """获取评论列表（按时间倒序）"""
        # 总数
        count_result = await db.execute(
            select(func.count()).select_from(StrategyComment)
            .where(StrategyComment.strategy_id == strategy_id)
        )
        total = count_result.scalar()

        # 分页
        offset = (page - 1) * limit
        result = await db.execute(
            select(StrategyComment)
            .options(selectinload(StrategyComment.user))
            .where(StrategyComment.strategy_id == strategy_id)
            .order_by(StrategyComment.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        comments = result.scalars().all()

        return comments, total

    @staticmethod
    async def delete_comment(
        db: AsyncSession,
        comment_id: int,
        user_id: int,
    ) -> None:
        """删除评论（评论作者或策略创建者）"""
        comment = await db.get(StrategyComment, comment_id)
        if not comment:
            raise HTTPException(status_code=404, detail="评论不存在")

        # 检查权限：评论作者或策略创建者
        strategy = await db.get(Strategy, comment.strategy_id)
        is_comment_author = comment.user_id == user_id
        is_strategy_owner = strategy and strategy.user_id == user_id

        if not is_comment_author and not is_strategy_owner:
            raise HTTPException(
                status_code=403,
                detail="无权删除此评论"
            )

        await db.delete(comment)
        await db.commit()
