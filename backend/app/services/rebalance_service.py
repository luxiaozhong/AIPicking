"""每日调仓回测业务逻辑层"""

import json
import asyncio
import os
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from ..models.rebalance import RebalanceReport
from ..models.strategy import Strategy
from ..schemas.rebalance import RebalanceCreate


class RebalanceService:

    @staticmethod
    async def create(
        db: AsyncSession,
        data: RebalanceCreate,
        user_id: int,
    ) -> RebalanceReport:
        """提交调仓回测"""
        # 检查策略存在
        strategy_result = await db.execute(
            select(Strategy).where(Strategy.id == data.strategy_id)
        )
        strategy = strategy_result.scalar_one_or_none()
        if not strategy:
            raise HTTPException(status_code=404, detail="策略不存在")

        # 构建 config
        config = {
            "N": data.config.get("N", 5) if data.config else 5,
            "M": data.config.get("M", 20) if data.config else 20,
            "index_code": data.config.get("index_code", "980080") if data.config else "980080",
            "initial_capital": data.initial_capital,
        }
        # 合并用户传入的其他参数
        if data.config:
            for k, v in data.config.items():
                if k not in config:
                    config[k] = v

        report = RebalanceReport(
            strategy_id=data.strategy_id,
            user_id=user_id,
            name=data.name,
            start_date=data.start_date,
            end_date=data.end_date,
            config=json.dumps(config, ensure_ascii=False),
            status="pending",
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)

        report.strategy = strategy

        loop = asyncio.get_running_loop()
        loop.run_in_executor(
            None,
            RebalanceService._run,
            report.id,
            data.start_date,
            data.end_date,
        )

        return report

    @staticmethod
    def _run(report_id: int, start_date: str, end_date: str):
        """执行调仓回测（线程池中）"""
        from sqlalchemy import create_engine, update as sql_update
        from sqlalchemy.orm import sessionmaker
        from ..config import settings
        from .rebalance_engine import RebalanceEngine
        from ..models.base import beijing_now

        engine = create_engine(settings.SYNC_DATABASE_URL)
        Session = sessionmaker(bind=engine)

        with Session() as db:
            try:
                report = db.query(RebalanceReport).filter(
                    RebalanceReport.id == report_id
                ).first()
                if not report:
                    return

                report.status = "running"
                report.started_at = beijing_now()
                db.commit()

                strategy = db.query(Strategy).filter(
                    Strategy.id == report.strategy_id
                ).first()
                if not strategy:
                    raise ValueError(f"策略 {report.strategy_id} 不存在")

                # 获取策略代码
                if strategy.generated_code:
                    strategy_code = strategy.generated_code
                elif strategy.file_path and os.path.exists(strategy.file_path):
                    with open(strategy.file_path, "r", encoding="utf-8") as f:
                        strategy_code = f.read()
                else:
                    raise FileNotFoundError("策略代码不存在")

                config = json.loads(report.config) if report.config else {}

                engine_obj = RebalanceEngine(
                    strategy_code=strategy_code,
                    strategy_params={},
                    config=config,
                )

                # 进度回调（每 5 天写一次 DB，减少 IO）
                def update_progress(completed: int, total: int):
                    if completed % 5 == 0 or completed == total:
                        try:
                            db.execute(
                                sql_update(RebalanceReport)
                                .where(RebalanceReport.id == report_id)
                                .values(total_days=total, completed_days=completed)
                            )
                            db.commit()
                        except Exception:
                            pass

                result = engine_obj.run(
                    start_date, end_date,
                    progress_callback=update_progress,
                )

                # 写入结果
                report = db.query(RebalanceReport).filter(
                    RebalanceReport.id == report_id
                ).first()
                if not report:
                    return

                report.daily_snapshots = json.dumps(
                    result["daily_snapshots"], ensure_ascii=False
                )
                report.trades = json.dumps(
                    result["trades"], ensure_ascii=False
                )
                report.summary = json.dumps(
                    result["summary"], ensure_ascii=False
                )
                report.status = "completed"
                report.completed_at = beijing_now()
                db.commit()

            except Exception as e:
                db.rollback()
                report = db.query(RebalanceReport).filter(
                    RebalanceReport.id == report_id
                ).first()
                if report:
                    report.status = "failed"
                    report.error_message = str(e)
                    report.completed_at = beijing_now()
                    db.commit()

    @staticmethod
    async def get_list(
        db: AsyncSession,
        page: int = 1,
        limit: int = 20,
        strategy_id: Optional[int] = None,
        status_filter: Optional[str] = None,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> Tuple[List[RebalanceReport], int]:
        """获取调仓回测列表"""
        query = select(RebalanceReport).options(
            selectinload(RebalanceReport.strategy)
        )

        if strategy_id:
            query = query.where(RebalanceReport.strategy_id == strategy_id)
        if status_filter:
            query = query.where(RebalanceReport.status == status_filter)
        if user_role != "admin":
            query = query.where(RebalanceReport.user_id == user_id)

        count_query = select(func.count()).select_from(RebalanceReport)
        if strategy_id:
            count_query = count_query.where(RebalanceReport.strategy_id == strategy_id)
        if status_filter:
            count_query = count_query.where(RebalanceReport.status == status_filter)
        if user_role != "admin":
            count_query = count_query.where(RebalanceReport.user_id == user_id)

        total = (await db.execute(count_query)).scalar()
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit).order_by(
            RebalanceReport.created_at.desc()
        )

        result = await db.execute(query)
        return result.scalars().all(), total

    @staticmethod
    async def get_detail(
        db: AsyncSession,
        report_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> RebalanceReport:
        """获取调仓回测详情"""
        result = await db.execute(
            select(RebalanceReport)
            .options(selectinload(RebalanceReport.strategy))
            .where(RebalanceReport.id == report_id)
        )
        report = result.scalar_one_or_none()
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")

        if user_role != "admin" and report.user_id != user_id:
            raise HTTPException(status_code=403, detail="无权访问")

        return report

    @staticmethod
    async def delete(
        db: AsyncSession,
        report_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> None:
        """删除调仓回测报告"""
        report = await RebalanceService.get_detail(db, report_id, user_id, user_role)
        await db.delete(report)
        await db.commit()
