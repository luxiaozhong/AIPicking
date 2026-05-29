"""策略相关 API 路由"""

import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.strategy_service import StrategyService
from ..schemas.strategy import (
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    StrategyListResponse,
    StrategyUploadResponse,
    FactorConfig
)
from ..middleware.auth import get_current_user
from ..models.user import User


router = APIRouter()


@router.get("", response_model=StrategyListResponse)
async def list_strategies(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    status: Optional[str] = Query(None, description="状态筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取策略列表"""
    if not status:
        status = "active"

    strategies, total = await StrategyService.get_strategies(
        db, page, limit, search, status,
        user_id=current_user.id, user_role=current_user.role
    )

    return {
        "items": strategies,
        "total": total,
        "page": page,
        "limit": limit
    }


@router.post("/upload", response_model=StrategyUploadResponse)
async def upload_strategy(
    file: UploadFile = File(..., description="策略脚本文件（.py）"),
    name: Optional[str] = Form(None, description="策略名称（可选，默认使用文件名）"),
    description: Optional[str] = Form(None, description="策略描述（可选）"),
    tags: Optional[str] = Form(None, description="标签（逗号分隔，可选）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传策略脚本"""
    return await StrategyService.upload_strategy(
        db, file, name, description, tags, user_id=current_user.id
    )


# ========== 注意：/code 路由必须放在 /{strategy_id} 之前，否则会被错误匹配 ==========
@router.get("/{strategy_id}/code")
async def get_strategy_generated_code(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查看策略自动生成的代码"""
    return await StrategyService.get_generated_code(db, strategy_id)


@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个策略详情"""
    strategy = await StrategyService.get_strategy(
        db, strategy_id, user_id=current_user.id, user_role=current_user.role
    )

    # 获取策略代码
    code_content = ""
    if strategy.file_path and os.path.exists(strategy.file_path):
        try:
            code_content = await StrategyService.get_strategy_code(strategy.file_path)
        except Exception:
            pass
    if not code_content:
        code_content = strategy.generated_code or ""

    # 使用 Pydantic 模型序列化策略对象
    from ..schemas.strategy import StrategyResponse
    strategy_data = StrategyResponse.model_validate(strategy).model_dump()

    # 返回策略信息和代码内容
    return {
        "code": 0,
        "data": strategy_data,
        "code_content": code_content
    }


@router.get("/{strategy_id}/download")
async def download_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载策略脚本"""
    strategy = await StrategyService.get_strategy(
        db, strategy_id, user_id=current_user.id, user_role=current_user.role
    )
    file_path = StrategyService.get_strategy_file_path(strategy.file_path)

    return FileResponse(
        path=file_path,
        filename=f"{strategy.name}.py",
        media_type="application/octet-stream"
    )


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    strategy: StrategyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新策略元数据（名称、描述、标签等）"""
    return await StrategyService.update_strategy(
        db, strategy_id, strategy,
        user_id=current_user.id, user_role=current_user.role
    )


@router.put("/{strategy_id}/code", response_model=StrategyUploadResponse)
async def update_strategy_code(
    strategy_id: int,
    file: Optional[UploadFile] = File(None, description="新的策略脚本文件（.py）（可选）"),
    code: Optional[str] = Form(None, description="策略代码文本（可选，与 file 二选一）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新策略代码（上传新文件或在线编辑）"""
    return await StrategyService.update_strategy_code(
        db, strategy_id, file, code
    )


@router.delete("/{strategy_id}/permanent", status_code=204)
async def permanent_delete_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """彻底删除策略（同时删除关联的回测报告）"""
    await StrategyService.permanent_delete_strategy(
        db, strategy_id, user_id=current_user.id, user_role=current_user.role
    )


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除策略（软删除）"""
    await StrategyService.delete_strategy(
        db, strategy_id, user_id=current_user.id, user_role=current_user.role
    )


# ========== 新增：因子策略 API ==========

@router.post("", response_model=StrategyUploadResponse)
async def create_strategy_with_factors(
    strategy: StrategyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """通过因子配置创建策略（新方式）"""
    return await StrategyService.create_with_factors(
        db,
        name=strategy.name,
        description=strategy.description,
        tags=strategy.tags,
        factor_config=strategy.factor_config.model_dump(),
        user_id=current_user.id,
    )


@router.put("/{strategy_id}/factors")
async def update_strategy_factors(
    strategy_id: int,
    factor_config: FactorConfig,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新策略的因子配置（重新生成代码）"""
    return await StrategyService.update_factor_config(
        db, strategy_id, factor_config.model_dump()
    )
