"""交易模拟业务逻辑层"""

import json
import asyncio
import os
from datetime import datetime
import numpy as np
from typing import List, Optional, Tuple
from ..models.base import beijing_now
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from ..models.trade_sim import TradeSimReport
from ..models.strategy import Strategy
from ..schemas.trade_sim import TradeSimCreate


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


class TradeSimService:

    @staticmethod
    async def create(
        db: AsyncSession,
        data: TradeSimCreate,
        user_id: int,
    ) -> TradeSimReport:
        """提交交易模拟回测"""
        # 检查策略存在
        strategy_result = await db.execute(
            select(Strategy).where(Strategy.id == data.strategy_id)
        )
        strategy = strategy_result.scalar_one_or_none()
        if not strategy:
            raise HTTPException(status_code=404, detail="策略不存在")

        # 至少启用一个止损止盈条件
        enabled = [sf for sf in data.stop_factors if sf.enabled]
        if not enabled:
            raise HTTPException(status_code=400, detail="请至少启用一个止损止盈条件")

        config = {
            "total_amount": data.total_amount,
            "top_n": data.top_n,
            "max_hold_days": data.max_hold_days,
            "stop_factors": [
                {"id": sf.id, "enabled": sf.enabled, "params": sf.params}
                for sf in data.stop_factors
            ],
        }

        report = TradeSimReport(
            strategy_id=data.strategy_id,
            user_id=user_id,
            cutoff_date=datetime.strptime(data.cutoff_date, "%Y-%m-%d").date(),
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
            TradeSimService._run,
            report.id,
            data.cutoff_date,
        )

        return report

    @staticmethod
    def _run(report_id: int, cutoff_date: str):
        """执行交易模拟（线程池中）"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from ..config import settings
        from .trade_sim_engine import TradeSimEngine

        engine = create_engine(settings.SYNC_DATABASE_URL)
        Session = sessionmaker(bind=engine)

        with Session() as db:
            try:
                report = db.query(TradeSimReport).filter(TradeSimReport.id == report_id).first()
                if not report:
                    return

                report.status = "running"
                report.started_at = beijing_now()
                db.commit()

                strategy = db.query(Strategy).filter(Strategy.id == report.strategy_id).first()
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
                # 转换 cutoff_date: "YYYY-MM-DD" → "YYYYMMDD"
                cutoff_date_fmt = cutoff_date.replace("-", "")

                engine_obj = TradeSimEngine(
                    strategy_code=strategy_code,
                    strategy_params={},
                    config=config,
                )

                result = engine_obj.run(cutoff_date_fmt)

                report.trades = json.dumps(result["trades"], ensure_ascii=False, cls=NumpyEncoder)
                report.summary = json.dumps(result["summary"], ensure_ascii=False, cls=NumpyEncoder)
                report.status = "completed"
                report.completed_at = beijing_now()
                db.commit()

            except Exception as e:
                db.rollback()
                report = db.query(TradeSimReport).filter(TradeSimReport.id == report_id).first()
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
    ) -> Tuple[List[TradeSimReport], int]:
        """获取交易模拟列表"""
        query = select(TradeSimReport).options(selectinload(TradeSimReport.strategy))

        if strategy_id:
            query = query.where(TradeSimReport.strategy_id == strategy_id)
        if status_filter:
            query = query.where(TradeSimReport.status == status_filter)
        if user_role != "admin":
            query = query.where(TradeSimReport.user_id == user_id)

        count_query = select(func.count()).select_from(TradeSimReport)
        if strategy_id:
            count_query = count_query.where(TradeSimReport.strategy_id == strategy_id)
        if status_filter:
            count_query = count_query.where(TradeSimReport.status == status_filter)
        if user_role != "admin":
            count_query = count_query.where(TradeSimReport.user_id == user_id)

        total = (await db.execute(count_query)).scalar()
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit).order_by(TradeSimReport.created_at.desc())

        result = await db.execute(query)
        return result.scalars().all(), total

    @staticmethod
    async def get_detail(
        db: AsyncSession,
        report_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> TradeSimReport:
        """获取交易模拟详情"""
        result = await db.execute(
            select(TradeSimReport)
            .options(selectinload(TradeSimReport.strategy))
            .where(TradeSimReport.id == report_id)
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
        """删除交易模拟报告"""
        report = await TradeSimService.get_detail(db, report_id, user_id, user_role)
        await db.delete(report)
        await db.commit()

    @staticmethod
    async def create_batch(
        db: AsyncSession,
        data,  # BatchTradeSimCreate
        user_id: int,
    ):
        """提交批量交易模拟回测"""
        from ..models.trade_sim import BatchTradeSimReport

        strategy_result = await db.execute(
            select(Strategy).where(Strategy.id == data.strategy_id)
        )
        strategy = strategy_result.scalar_one_or_none()
        if not strategy:
            raise HTTPException(status_code=404, detail="策略不存在")

        enabled = [sf for sf in data.stop_factors if sf.enabled]
        if not enabled:
            raise HTTPException(status_code=400, detail="请至少启用一个止损止盈条件")

        config = {
            "total_amount": data.total_amount,
            "top_n": data.top_n,
            "max_hold_days": data.max_hold_days,
            "stop_factors": [
                {"id": sf.id, "enabled": sf.enabled, "params": sf.params}
                for sf in data.stop_factors
            ],
        }

        report = BatchTradeSimReport(
            strategy_id=data.strategy_id,
            user_id=user_id,
            name=data.name or f"{strategy.name}_{data.start_date}_{data.end_date}",
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
            None, TradeSimService._run_batch, report.id, data.start_date, data.end_date
        )
        return report

    @staticmethod
    def _run_batch(report_id: int, start_date: str, end_date: str):
        """执行批量交易模拟（线程池中）"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from ..config import settings
        from ..models.trade_sim import BatchTradeSimReport
        from .trade_sim_engine import TradeSimEngine

        engine = create_engine(settings.SYNC_DATABASE_URL)
        Session = sessionmaker(bind=engine)

        with Session() as db:
            try:
                report = db.query(BatchTradeSimReport).filter(BatchTradeSimReport.id == report_id).first()
                if not report:
                    return

                report.status = "running"
                report.started_at = beijing_now()
                db.commit()

                strategy = db.query(Strategy).filter(Strategy.id == report.strategy_id).first()
                if not strategy:
                    raise ValueError(f"策略 {report.strategy_id} 不存在")

                if strategy.generated_code:
                    strategy_code = strategy.generated_code
                elif strategy.file_path and os.path.exists(strategy.file_path):
                    with open(strategy.file_path, "r", encoding="utf-8") as f:
                        strategy_code = f.read()
                else:
                    raise FileNotFoundError("策略代码不存在")

                config = json.loads(report.config) if report.config else {}

                engine_obj = TradeSimEngine(
                    strategy_code=strategy_code,
                    strategy_params={},
                    config=config,
                )

                # 进度回调：每个交易日完成后立即更新 DB，前端轮询可见实时进度
                def update_progress(completed_count, total_count):
                    report.total_days = total_count
                    report.completed_days = completed_count
                    db.commit()

                daily_results = engine_obj.run_batch(
                    start_date, end_date,
                    progress_callback=update_progress,
                )

                # 最终写入完整结果
                report.daily_results = json.dumps(daily_results, ensure_ascii=False, cls=NumpyEncoder)

                if report.completed_days == 0 and report.total_days > 0:
                    report.status = "failed"
                    report.error_message = "所有交易日执行均失败"
                else:
                    report.status = "completed"

                report.completed_at = beijing_now()
                db.commit()

            except Exception as e:
                db.rollback()
                report = db.query(BatchTradeSimReport).filter(BatchTradeSimReport.id == report_id).first()
                if report:
                    report.status = "failed"
                    report.error_message = str(e)
                    report.completed_at = beijing_now()
                    db.commit()

    @staticmethod
    async def get_batch_list(
        db: AsyncSession,
        page: int = 1,
        limit: int = 20,
        strategy_id: Optional[int] = None,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ):
        """获取批量交易模拟列表"""
        from ..models.trade_sim import BatchTradeSimReport

        query = select(BatchTradeSimReport).options(selectinload(BatchTradeSimReport.strategy))
        if strategy_id:
            query = query.where(BatchTradeSimReport.strategy_id == strategy_id)
        if user_role != "admin":
            query = query.where(BatchTradeSimReport.user_id == user_id)

        count_query = select(func.count()).select_from(BatchTradeSimReport)
        if strategy_id:
            count_query = count_query.where(BatchTradeSimReport.strategy_id == strategy_id)
        if user_role != "admin":
            count_query = count_query.where(BatchTradeSimReport.user_id == user_id)

        total = (await db.execute(count_query)).scalar()
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit).order_by(BatchTradeSimReport.created_at.desc())

        result = await db.execute(query)
        return result.scalars().all(), total

    @staticmethod
    async def get_batch_detail(
        db: AsyncSession,
        report_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ):
        """获取批量交易模拟详情"""
        from ..models.trade_sim import BatchTradeSimReport

        result = await db.execute(
            select(BatchTradeSimReport)
            .options(selectinload(BatchTradeSimReport.strategy))
            .where(BatchTradeSimReport.id == report_id)
        )
        report = result.scalar_one_or_none()
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")
        if user_role != "admin" and report.user_id != user_id:
            raise HTTPException(status_code=403, detail="无权访问")
        return report

    @staticmethod
    async def delete_batch(
        db: AsyncSession,
        report_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> None:
        """删除批量交易模拟报告"""
        report = await TradeSimService.get_batch_detail(db, report_id, user_id, user_role)
        await db.delete(report)
        await db.commit()
