"""语音播报 token 服务 — 一 token 一列表

管理 voice_tokens 表：创建/查询/删除 token，每个 token 绑定一个独立指数。
"""

from __future__ import annotations

import secrets

from sqlalchemy import select

from ..config import settings
from ..models.index_tables import IndexInfo
from ..models.voice_token import VoiceToken
from .watchlist_service import ensure_index_info, add_stocks, get_stocks

# 新建 token 时默认种子股票（贵州茅台、中国平安）
DEFAULT_SEED_STOCKS = ["600519.SH", "601318.SH"]


async def get_token(db, token: str) -> VoiceToken | None:
    """按 token 查询，不存在返回 None"""
    result = await db.execute(select(VoiceToken).where(VoiceToken.token == token))
    return result.scalar_one_or_none()


async def list_tokens(db) -> list[VoiceToken]:
    result = await db.execute(select(VoiceToken).order_by(VoiceToken.id))
    return list(result.scalars().all())


async def _gen_index_code(db) -> str:
    """生成一个不重复的 9 位数值指数代码（900000000~999999999 区间）"""
    for _ in range(20):
        code = "9" + f"{secrets.randbelow(10 ** 8):08d}"
        exists = await db.execute(
            select(IndexInfo.index_code).where(IndexInfo.index_code == code)
        )
        if exists.scalar() is None:
            return code
    raise RuntimeError("无法生成唯一指数代码")


async def create_token(
    db,
    label: str = "elder",
    index_name: str | None = None,
    seed_stocks: list[str] | None = None,
) -> VoiceToken:
    """创建新 token + 专属指数 + 种子股票，返回 VoiceToken 行"""
    token = secrets.token_urlsafe(16)
    index_code = await _gen_index_code(db)
    name = index_name or f"{label}的播报"

    # 注册指数元数据
    await ensure_index_info(
        db, index_code=index_code, index_name=name, full_name=name
    )
    # 种子股票（默认茅台/平安）
    stocks = seed_stocks if seed_stocks is not None else DEFAULT_SEED_STOCKS
    if stocks:
        await add_stocks(db, stocks, index_code=index_code)

    vt = VoiceToken(
        token=token,
        label=label,
        index_code=index_code,
        index_name=name,
        active=True,
    )
    db.add(vt)
    await db.commit()
    await db.refresh(vt)
    return vt


async def delete_token(db, token: str) -> bool:
    """删除 token，成功返回 True"""
    vt = await get_token(db, token)
    if vt is None:
        return False
    await db.delete(vt)
    await db.commit()
    return True


async def seed_voice_tokens(db, settings) -> None:
    """启动时种子：确保默认指数存在；若 voice_tokens 为空则从 env 种子（向后兼容）"""
    # 确保默认关注指数元数据存在（原行为）
    await ensure_index_info(
        db,
        index_code=settings.VOICE_WATCHLIST_INDEX,
        index_name=settings.VOICE_WATCHLIST_NAME,
        full_name=settings.VOICE_WATCHLIST_NAME,
    )

    # 若表为空且 env 配了 VOICE_TOKENS，则把现有 token 种子成行，绑定到默认指数
    # （保留现有 token 看到的仍是当前列表，保证向后兼容）
    existing = await db.execute(select(VoiceToken))
    if existing.scalars().first() is None and settings.VOICE_TOKENS.strip():
        for item in settings.VOICE_TOKENS.split(","):
            item = item.strip()
            if not item:
                continue
            if ":" in item:
                label, tok = item.split(":", 1)
                label, tok = label.strip(), tok.strip()
            else:
                label, tok = "elder", item
            db.add(
                VoiceToken(
                    token=tok,
                    label=label,
                    index_code=settings.VOICE_WATCHLIST_INDEX,
                    index_name=settings.VOICE_WATCHLIST_NAME,
                    active=True,
                )
            )
        await db.commit()
