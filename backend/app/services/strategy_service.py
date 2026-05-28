"""策略业务逻辑层"""

import os
import json
import shutil
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status, UploadFile, Form
from pathlib import Path

from ..models import Strategy
from ..schemas.strategy import (
    StrategyCreate, StrategyUpdate, StrategyUploadResponse,
    FactorConfig
)
from ..utils.validator import StrategyValidator
from .code_generator import generate_strategy_code


class StrategyService:
    """策略服务类"""

    STRATEGY_DIR = "app/strategies/examples"  # 策略脚本存储目录
    
    @staticmethod
    async def get_strategies(
        db: AsyncSession,
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
        status: Optional[str] = None,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> Tuple[List[Strategy], int]:
        """获取策略列表"""
        query = select(Strategy).options(selectinload(Strategy.owner))

        # 筛选条件
        if search:
            query = query.where(Strategy.name.like(f"%{search}%"))
        if status:
            query = query.where(Strategy.status == status)
        # 普通用户只看自己的数据
        if user_role != "admin":
            query = query.where(Strategy.user_id == user_id)

        # 计算总数
        count_query = select(func.count()).select_from(Strategy)
        if search:
            count_query = count_query.where(Strategy.name.like(f"%{search}%"))
        if status:
            count_query = count_query.where(Strategy.status == status)
        if user_role != "admin":
            count_query = count_query.where(Strategy.user_id == user_id)
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # 分页
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit).order_by(Strategy.created_at.desc())

        result = await db.execute(query)
        strategies = result.scalars().all()

        return strategies, total
    
    @staticmethod
    async def get_strategy(
        db: AsyncSession,
        strategy_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> Optional[Strategy]:
        """获取单个策略"""
        query = select(Strategy).where(Strategy.id == strategy_id)
        result = await db.execute(query)
        strategy = result.scalar_one_or_none()

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy with id {strategy_id} not found"
            )

        # 普通用户只能访问自己的策略
        if user_role != "admin" and strategy.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此策略"
            )

        return strategy
    
    @staticmethod
    async def upload_strategy(
        db: AsyncSession,
        file: UploadFile,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> dict:
        """上传策略脚本"""
        # 1. 检查文件类型
        if not file.filename.endswith('.py'):
            return {
                "code": 40001,
                "message": "策略脚本必须是 .py 文件",
                "errors": ["文件类型错误"]
            }
        
        # 2. 读取文件内容
        content = await file.read()
        code = content.decode('utf-8')
        
        # 3. 验证策略代码
        # 3.1 语法检查
        is_valid, error_msg = StrategyValidator.validate(code)
        if not is_valid:
            return {
                "code": 40002,
                "message": "策略脚本验证失败（语法错误）",
                "errors": [error_msg]
            }
        
        # 3.2 必需函数检查
        has_required, missing_funcs = StrategyValidator.check_required_functions(code)
        if not has_required:
            return {
                "code": 40003,
                "message": "策略脚本缺少必需函数",
                "errors": [f"缺少必需函数: {func}" for func in missing_funcs]
            }
        
        # 4. 检查名称是否已存在
        strategy_name = name if name else file.filename.replace('.py', '')
        result = await db.execute(
            select(Strategy).where(Strategy.name == strategy_name)
        )
        if result.scalar_one_or_none():
            return {
                "code": 40004,
                "message": f"Strategy with name '{strategy_name}' already exists"
            }
        
        # 5. 保存策略脚本文件
        # 确保目录存在
        os.makedirs(StrategyService.STRATEGY_DIR, exist_ok=True)
        
        # 生成文件名（ID 未知，先保存到临时文件）
        temp_file_path = os.path.join(StrategyService.STRATEGY_DIR, f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py")
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            f.write(code)
        
        # 6. 创建策略记录
        db_strategy = Strategy(
            name=strategy_name,
            description=description,
            file_path=temp_file_path,  # 临时路径，稍后更新
            params_schema=None,  # 可选，从代码中提取
            tags=tags if tags else None,
            status="active",
            version=1,
            user_id=user_id,
        )
        
        db.add(db_strategy)
        await db.commit()
        await db.refresh(db_strategy)
        
        # 7. 更新文件路径（使用策略 ID）
        final_file_path = os.path.join(
            StrategyService.STRATEGY_DIR,
            f"{db_strategy.id}_{strategy_name}.py"
        )
        os.rename(temp_file_path, final_file_path)
        db_strategy.file_path = final_file_path
        
        await db.commit()
        await db.refresh(db_strategy)
        
        return {
            "code": 0,
            "message": "策略上传成功",
            "data": {
                "id": db_strategy.id,
                "name": db_strategy.name,
                "description": db_strategy.description,
                "file_path": db_strategy.file_path,
                "status": db_strategy.status,
                "created_at": db_strategy.created_at,
                "updated_at": db_strategy.updated_at,
                "version": db_strategy.version
            }
        }
    
    @staticmethod
    async def get_strategy_code(file_path: str) -> str:
        """获取策略代码内容"""
        full_path = StrategyService.get_strategy_file_path(file_path)
        
        if not os.path.exists(full_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy file not found: {full_path}"
            )
        
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    @staticmethod
    def get_strategy_file_path(file_path: str) -> str:
        """获取策略文件的完整路径"""
        # 如果 file_path 是相对路径，转换为绝对路径
        if not os.path.isabs(file_path):
            # 假设 file_path 是相对于项目根目录的
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            return os.path.join(base_dir, file_path)
        return file_path
    
    @staticmethod
    async def update_strategy_code(
        db: AsyncSession,
        strategy_id: int,
        file: Optional[UploadFile] = None,
        code: Optional[str] = None
    ) -> dict:
        """更新策略代码（上传新文件或在线编辑）"""
        db_strategy = await StrategyService.get_strategy(db, strategy_id)
        
        # 1. 获取新代码
        if file:
            # 从文件上传
            if not file.filename.endswith('.py'):
                return {
                    "code": 40001,
                    "message": "策略脚本必须是 .py 文件",
                    "errors": ["文件类型错误"]
                }
            
            content = await file.read()
            new_code = content.decode('utf-8')
        elif code:
            # 从文本编辑
            new_code = code
        else:
            return {
                "code": 40005,
                "message": "必须提供文件或代码文本"
            }
        
        # 2. 验证策略代码
        # 2.1 语法检查
        is_valid, error_msg = StrategyValidator.validate(new_code)
        if not is_valid:
            return {
                "code": 40002,
                "message": "策略脚本验证失败（语法错误）",
                "errors": [error_msg]
            }
        
        # 2.2 必需函数检查
        has_required, missing_funcs = StrategyValidator.check_required_functions(new_code)
        if not has_required:
            return {
                "code": 40003,
                "message": "策略脚本缺少必需函数",
                "errors": [f"缺少必需函数: {func}" for func in missing_funcs]
            }
        
        # 3. 保存策略代码
        full_path = StrategyService.get_strategy_file_path(db_strategy.file_path)
        
        # 如果文件不存在，创建新文件
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(new_code)
        
        # 4. 更新版本号
        db_strategy.version += 1
        
        await db.commit()
        await db.refresh(db_strategy)
        
        return {
            "code": 0,
            "message": "策略代码更新成功",
            "data": {
                "id": db_strategy.id,
                "name": db_strategy.name,
                "file_path": db_strategy.file_path,
                "status": db_strategy.status,
                "created_at": db_strategy.created_at,
                "updated_at": db_strategy.updated_at,
                "version": db_strategy.version
            }
        }
    
    @staticmethod
    async def update_strategy(
        db: AsyncSession,
        strategy_id: int,
        strategy: StrategyUpdate
    ) -> Strategy:
        """更新策略元数据（名称、描述、标签等，不含代码）"""
        db_strategy = await StrategyService.get_strategy(db, strategy_id)
        
        # 更新字段
        update_data = strategy.model_dump(exclude_unset=True)
        if 'tags' in update_data and update_data['tags']:
            update_data['tags'] = ",".join(update_data['tags'])
        
        for field, value in update_data.items():
            setattr(db_strategy, field, value)
        
        db_strategy.version += 1
        
        await db.commit()
        await db.refresh(db_strategy)
        
        return db_strategy
    
    @staticmethod
    async def delete_strategy(
        db: AsyncSession,
        strategy_id: int,
        user_id: Optional[int] = None,
        user_role: str = "user",
    ) -> None:
        """删除策略（软删除）"""
        db_strategy = await StrategyService.get_strategy(
            db, strategy_id, user_id=user_id, user_role=user_role
        )
        db_strategy.status = "deleted"
        await db.commit()

    @staticmethod
    async def create_with_factors(
        db: AsyncSession,
        name: str,
        description: Optional[str],
        tags: Optional[List[str]],
        factor_config: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> dict:
        """通过因子配置创建策略（新方式）"""
        # 1. 检查名称是否已存在
        result = await db.execute(
            select(Strategy).where(Strategy.name == name)
        )
        if result.scalar_one_or_none():
            return {
                "code": 40004,
                "message": f"策略名称已存在: {name}"
            }

        # 2. 生成策略代码
        generated_code = generate_strategy_code(name, factor_config)

        # 3. 创建策略记录
        db_strategy = Strategy(
            name=name,
            description=description,
            file_path="",  # 因子策略不需要上传文件
            factor_config=json.dumps(factor_config, ensure_ascii=False),
            generated_code=generated_code,
            tags=",".join(tags) if tags else None,
            status="active",
            version=1,
            user_id=user_id,
        )

        db.add(db_strategy)
        await db.commit()
        await db.refresh(db_strategy)

        # 4. 保存生成的代码到文件（可选，便于调试）
        try:
            os.makedirs(StrategyService.STRATEGY_DIR, exist_ok=True)
            code_file_path = os.path.join(
                StrategyService.STRATEGY_DIR,
                f"auto_{db_strategy.id}_{name}.py"
            )
            with open(code_file_path, 'w', encoding='utf-8') as f:
                f.write(generated_code)
            db_strategy.file_path = code_file_path
            await db.commit()
            await db.refresh(db_strategy)  # 重新加载对象，避免 async session 过期
        except Exception as e:
            # 文件写入失败不影响策略创建，只记录警告
            print(f"Warning: Failed to save code to file: {e}")

        return {
            "code": 0,
            "message": "策略创建成功",
            "data": {
                "id": db_strategy.id,
                "name": db_strategy.name,
                "description": db_strategy.description,
                "factor_config": factor_config,
                "generated_code": generated_code,
                "status": db_strategy.status,
                "created_at": db_strategy.created_at,
                "updated_at": db_strategy.updated_at,
                "version": db_strategy.version
            }
        }

    @staticmethod
    async def update_factor_config(
        db: AsyncSession,
        strategy_id: int,
        factor_config: Dict[str, Any]
    ) -> dict:
        """更新策略的因子配置（重新生成代码）"""
        db_strategy = await StrategyService.get_strategy(db, strategy_id)

        # 重新生成代码
        generated_code = generate_strategy_code(db_strategy.name, factor_config)

        db_strategy.factor_config = json.dumps(factor_config, ensure_ascii=False)
        db_strategy.generated_code = generated_code
        db_strategy.version += 1

        # 更新代码文件
        if db_strategy.file_path and os.path.exists(db_strategy.file_path):
            with open(db_strategy.file_path, 'w', encoding='utf-8') as f:
                f.write(generated_code)

        await db.commit()
        await db.refresh(db_strategy)

        return {
            "code": 0,
            "message": "因子配置更新成功",
            "data": {
                "id": db_strategy.id,
                "name": db_strategy.name,
                "factor_config": factor_config,
                "generated_code": generated_code,
            }
        }

    @staticmethod
    async def get_generated_code(db: AsyncSession, strategy_id: int) -> dict:
        """获取策略生成的代码"""
        db_strategy = await StrategyService.get_strategy(db, strategy_id)
        return {
            "code": 0,
            "data": {
                "generated_code": db_strategy.generated_code,
                "factor_config": json.loads(db_strategy.factor_config) if db_strategy.factor_config else None
            }
        }
