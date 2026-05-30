"""回测业务逻辑层（新逻辑：截止日推荐 + 后续表现追踪）"""

import json
import asyncio
import os
import numpy as np
from typing import List, Optional, Tuple
from datetime import datetime
from ..models.base import beijing_now
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from ..models import BacktestReport, Strategy, BatchBacktestReport
from ..schemas.backtest import BacktestCreate, BacktestResponse, StrategyExecuteResponse


class NumpyEncoder(json.JSONEncoder):
    """处理 numpy 类型的 JSON 编码器"""
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
from ..utils.validator import StrategyValidator
from .backtest_engine import BacktestEngine


class BacktestService:
    """回测服务类"""

    @staticmethod
    async def get_backtests(
        db: AsyncSession,
        page: int = 1,
        limit: int = 20,
        strategy_id: Optional[int] = None,
        status: Optional[str] = None,
        stock: Optional[str] = None,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> Tuple[List[BacktestReport], int]:
        """获取回测报告列表"""
        query = select(BacktestReport).options(selectinload(BacktestReport.strategy))

        if strategy_id:
            query = query.where(BacktestReport.strategy_id == strategy_id)
        if status:
            query = query.where(BacktestReport.status == status)
        if stock:
            query = query.where(BacktestReport.recommendations.like(f"%{stock}%"))
        if user_role != "admin":
            query = query.where(BacktestReport.user_id == user_id)

        # 计算总数
        count_query = select(func.count()).select_from(BacktestReport)
        if strategy_id:
            count_query = count_query.where(BacktestReport.strategy_id == strategy_id)
        if status:
            count_query = count_query.where(BacktestReport.status == status)
        if stock:
            count_query = count_query.where(BacktestReport.recommendations.like(f"%{stock}%"))
        if user_role != "admin":
            count_query = count_query.where(BacktestReport.user_id == user_id)
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # 分页
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit).order_by(BacktestReport.created_at.desc())

        result = await db.execute(query)
        backtests = result.scalars().all()

        return backtests, total

    @staticmethod
    async def get_backtest(
        db: AsyncSession,
        backtest_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> Optional[BacktestReport]:
        """获取单个回测报告"""
        result = await db.execute(
            select(BacktestReport).options(selectinload(BacktestReport.strategy)).where(BacktestReport.id == backtest_id)
        )
        backtest = result.scalar_one_or_none()

        if not backtest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Backtest with id {backtest_id} not found"
            )

        if user_role != "admin" and backtest.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此回测报告"
            )

        return backtest

    @staticmethod
    async def create_backtest(
        db: AsyncSession,
        backtest: BacktestCreate,
        user_id: Optional[int] = None,
    ) -> BacktestReport:
        """提交回测任务（异步执行）"""
        # 检查策略是否存在
        strategy_result = await db.execute(
            select(Strategy).where(Strategy.id == backtest.strategy_id)
        )
        strategy = strategy_result.scalar_one_or_none()

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy with id {backtest.strategy_id} not found"
            )

        # 创建回测报告（状态为 pending）
        config_dict = backtest.config or {}
        config_dict["track_days"] = backtest.track_days
        db_backtest = BacktestReport(
            strategy_id=backtest.strategy_id,
            user_id=user_id,
            name=f"{strategy.name}_{backtest.cutoff_date}",
            status="pending",
            cutoff_date=backtest.cutoff_date,
            config=json.dumps(config_dict, ensure_ascii=False),
        )

        db.add(db_backtest)
        await db.commit()
        await db.refresh(db_backtest)

        # Attach pre-loaded strategy to avoid lazy-load in async context
        db_backtest.strategy = strategy

        # 丢线程池执行（CPU密集，避免阻塞事件循环）
        loop = asyncio.get_running_loop()
        loop.run_in_executor(
            None,
            BacktestService._run_backtest,
            db_backtest.id,
            backtest.cutoff_date,
            backtest.track_days,
        )

        return db_backtest

    @staticmethod
    def _run_backtest(backtest_id: int, cutoff_date: str, track_days: List[int]):
        """执行回测（异步任务，使用独立的同步 Session）"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from ..config import settings

        # 创建同步 Session（异步任务中无法使用 AsyncSession）
        engine = create_engine(settings.SYNC_DATABASE_URL)
        Session = sessionmaker(bind=engine)

        with Session() as db:
            try:
                # 获取回测报告
                backtest = db.query(BacktestReport).filter(BacktestReport.id == backtest_id).first()
                if not backtest:
                    return

                # 更新状态为 running
                backtest.status = "running"
                backtest.started_at = beijing_now()
                db.commit()

                # 获取策略
                strategy = db.query(Strategy).filter(Strategy.id == backtest.strategy_id).first()
                if not strategy:
                    raise ValueError(f"Strategy {backtest.strategy_id} not found")

                # 获取策略代码（优先用 generated_code，其次读文件）
                strategy_code = BacktestService._get_strategy_code(strategy)

                # 创建回测引擎
                config = json.loads(backtest.config) if backtest.config else {}
                # 移除内部字段，剩下的传给策略
                strategy_config = {k: v for k, v in config.items() if k != "track_days"}
                engine = BacktestEngine(
                    strategy_code=strategy_code,
                    strategy_params={},
                    config=strategy_config,
                )

                # 执行回测
                result = engine.run(cutoff_date, track_days)

                # 更新回测报告
                backtest.status = "completed"
                backtest.recommendations = json.dumps(result["recommendations"], ensure_ascii=False, cls=NumpyEncoder)
                backtest.summary = json.dumps(result["summary"], ensure_ascii=False, cls=NumpyEncoder)
                backtest.completed_at = beijing_now()
                db.commit()

            except Exception as e:
                # 更新状态为 failed
                db.rollback()
                backtest = db.query(BacktestReport).filter(BacktestReport.id == backtest_id).first()
                if backtest:
                    backtest.status = "failed"
                    backtest.error_message = str(e)
                    backtest.completed_at = beijing_now()
                    db.commit()

    @staticmethod
    def _get_strategy_code(strategy: Strategy) -> str:
        """获取策略代码（优先用 generated_code，其次读文件）"""
        if strategy.generated_code:
            return strategy.generated_code

        # fallback：读文件
        if strategy.file_path and os.path.exists(strategy.file_path):
            with open(strategy.file_path, "r", encoding="utf-8") as f:
                return f.read()

        raise FileNotFoundError(f"策略 {strategy.id} 的代码不存在（generated_code 为空且 file_path 无效）")

    @staticmethod
    async def execute_strategy(
        db: AsyncSession,
        strategy_id: int,
        cutoff_date: Optional[str] = None,
        ts_code: Optional[str] = None,
    ) -> dict:
        """执行策略（同步，立即返回推荐结果）

        参数:
            db: 数据库 Session
            strategy_id: 策略 ID
            cutoff_date: 截止日（格式 YYYYMMDD），默认为今日
            ts_code: 可选，目标股票代码。传入时只分析该股票

        返回:
            {
                "strategy_id": 1,
                "strategy_name": "策略名",
                "cutoff_date": "20260525",
                "recommendations": [...],
                "total": 8
            }
        """
        # 1. 检查策略是否存在
        result = await db.execute(
            select(Strategy).where(Strategy.id == strategy_id)
        )
        strategy = result.scalar_one_or_none()

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy with id {strategy_id} not found"
            )

        # 2. 确定截止日（默认为今日，格式 YYYYMMDD）
        if not cutoff_date:
            from datetime import date
            cutoff_date = date.today().strftime("%Y%m%d")

        # 3. 获取策略代码（优先用 generated_code，其次读文件）
        try:
            strategy_code = BacktestService._get_strategy_code(strategy)
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )

        # 4. 创建引擎并执行
        engine = BacktestEngine(
            strategy_code=strategy_code,
            strategy_params={},
        )

        try:
            recommendations = engine.run_live(cutoff_date, ts_code=ts_code)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"策略执行失败: {str(e)}"
            )

        # 5. 保存执行记录（可选）
        # TODO: 保存到 StrategyRun 表

        return {
            "strategy_id": strategy.id,
            "strategy_name": strategy.name,
            "cutoff_date": cutoff_date,
            "recommendations": recommendations,
            "total": len(recommendations) if recommendations else 0
        }

    @staticmethod
    async def delete_backtest(
        db: AsyncSession,
        backtest_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> None:
        """删除回测报告"""
        backtest = await BacktestService.get_backtest(
            db, backtest_id, user_id=user_id, user_role=user_role
        )

        await db.delete(backtest)
        await db.commit()

    @staticmethod
    async def create_batch_backtest(
        db: AsyncSession,
        backtest,
        user_id: Optional[int] = None,
    ):
        """提交批量回测任务（异步执行）"""
        from ..models.backtest import BatchBacktestReport

        strategy_result = await db.execute(
            select(Strategy).where(Strategy.id == backtest.strategy_id)
        )
        strategy = strategy_result.scalar_one_or_none()

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy with id {backtest.strategy_id} not found"
            )

        config_dict = backtest.config or {}
        config_dict["track_days"] = backtest.track_days

        db_backtest = BatchBacktestReport(
            strategy_id=backtest.strategy_id,
            user_id=user_id,
            name=backtest.name or f"{strategy.name}_{backtest.start_date}_{backtest.end_date}",
            status="pending",
            start_date=backtest.start_date,
            end_date=backtest.end_date,
            config=json.dumps(config_dict, ensure_ascii=False),
        )

        db.add(db_backtest)
        await db.commit()
        await db.refresh(db_backtest)

        db_backtest.strategy = strategy

        loop = asyncio.get_running_loop()
        loop.run_in_executor(
            None,
            BacktestService._run_batch_backtest,
            db_backtest.id,
            backtest.start_date,
            backtest.end_date,
            backtest.track_days,
        )

        return db_backtest

    @staticmethod
    async def get_batch_backtests(
        db: AsyncSession,
        page: int = 1,
        limit: int = 20,
        strategy_id: Optional[int] = None,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ):
        """获取批量回测列表"""
        from ..models.backtest import BatchBacktestReport

        query = select(BatchBacktestReport).options(selectinload(BatchBacktestReport.strategy))

        if strategy_id:
            query = query.where(BatchBacktestReport.strategy_id == strategy_id)
        if user_role != "admin":
            query = query.where(BatchBacktestReport.user_id == user_id)

        count_query = select(func.count()).select_from(BatchBacktestReport)
        if strategy_id:
            count_query = count_query.where(BatchBacktestReport.strategy_id == strategy_id)
        if user_role != "admin":
            count_query = count_query.where(BatchBacktestReport.user_id == user_id)
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit).order_by(BatchBacktestReport.created_at.desc())

        result = await db.execute(query)
        return result.scalars().all(), total

    @staticmethod
    async def get_batch_backtest(
        db: AsyncSession,
        backtest_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ):
        """获取单个批量回测详情"""
        from ..models.backtest import BatchBacktestReport

        result = await db.execute(
            select(BatchBacktestReport)
            .options(selectinload(BatchBacktestReport.strategy))
            .where(BatchBacktestReport.id == backtest_id)
        )
        backtest = result.scalar_one_or_none()

        if not backtest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Batch backtest with id {backtest_id} not found"
            )

        if user_role != "admin" and backtest.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此回测报告"
            )

        return backtest

    @staticmethod
    async def delete_batch_backtest(
        db: AsyncSession,
        backtest_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> None:
        """删除批量回测报告"""
        backtest = await BacktestService.get_batch_backtest(db, backtest_id, user_id, user_role)
        await db.delete(backtest)
        await db.commit()

    @staticmethod
    def _run_batch_backtest(
        backtest_id: int,
        start_date: str,
        end_date: str,
        track_days: List[int],
    ):
        """执行批量回测（异步任务，使用独立的同步 Session）"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from ..config import settings
        from ..models.backtest import BatchBacktestReport

        engine = create_engine(settings.SYNC_DATABASE_URL)
        Session = sessionmaker(bind=engine)

        with Session() as db:
            try:
                backtest = db.query(BatchBacktestReport).filter(BatchBacktestReport.id == backtest_id).first()
                if not backtest:
                    return

                backtest.status = "running"
                backtest.started_at = beijing_now()
                db.commit()

                strategy = db.query(Strategy).filter(Strategy.id == backtest.strategy_id).first()
                if not strategy:
                    raise ValueError(f"Strategy {backtest.strategy_id} not found")

                strategy_code = BacktestService._get_strategy_code(strategy)

                config = json.loads(backtest.config) if backtest.config else {}
                strategy_config = {k: v for k, v in config.items() if k != "track_days"}
                engine_obj = BacktestEngine(
                    strategy_code=strategy_code,
                    strategy_params={},
                    config=strategy_config,
                )

                daily_results = engine_obj.run_batch(start_date, end_date, track_days)

                backtest.total_days = len(daily_results)
                backtest.completed_days = len([r for r in daily_results if r["status"] == "completed"])
                backtest.daily_results = json.dumps(daily_results, ensure_ascii=False, cls=NumpyEncoder)

                if backtest.completed_days == 0 and backtest.total_days > 0:
                    backtest.status = "failed"
                    backtest.error_message = "所有交易日执行均失败"
                else:
                    backtest.status = "completed"

                backtest.completed_at = beijing_now()
                db.commit()

            except Exception as e:
                db.rollback()
                backtest = db.query(BatchBacktestReport).filter(BatchBacktestReport.id == backtest_id).first()
                if backtest:
                    backtest.status = "failed"
                    backtest.error_message = str(e)
                    backtest.completed_at = beijing_now()
                    db.commit()
