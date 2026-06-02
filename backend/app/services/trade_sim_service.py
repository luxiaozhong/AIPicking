"""交易模拟业务逻辑层"""

import json
import asyncio
import os
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
            cutoff_date=data.cutoff_date,
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
