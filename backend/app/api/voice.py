"""语音播报 API — 老人微信链接入口

路由（均无 JWT，靠 token 校验）：
    GET /voice/{token}                 返回 H5 大字播报页
    GET /api/v1/voice/announce?token=  返回关注股实时报价 + 预生成音频 URL
    GET /api/v1/voice/tts?text=&voice= 生成（命中缓存则返回）mp3 音频
    GET /api/v1/voice/audio/{key}.mp3  返回缓存的 mp3（供 <audio> 播放）
    GET /api/v1/voice/watchlist?token=&action=&codes=  管理关注列表（token 简单验证）
"""

from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..services import tts_service
from ..services.quote_service import fetch_quotes, build_broadcast_text
from ..services.watchlist_service import (
    ensure_index_info,
    add_stocks,
    remove_stock,
    get_stocks,
)

router = APIRouter()

from ..services import voice_token_service


async def _resolve_token(db, token: str):
    """校验 token（DB 查询），返回 VoiceToken 行；无效/未启用抛 403。

    一 token 一列表：token 绑定的 index_code 即该链接独立的关注列表。
    """
    vt = await voice_token_service.get_token(db, token)
    if vt is None or not vt.active:
        raise HTTPException(status_code=403, detail="无效的播报链接")
    return vt


def _check_admin(admin: str | None) -> None:
    """管理员校验：配置了 VOICE_ADMIN_TOKEN 时必须匹配；未配置则放开（任一有效 token 即可）。"""
    if settings.VOICE_ADMIN_TOKEN:
        if admin != settings.VOICE_ADMIN_TOKEN:
            raise HTTPException(status_code=403, detail="需要管理员 token")


def _voice_cache_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
        "voice_cache",
    )


@router.get("/voice/{token}", response_class=HTMLResponse)
async def voice_page(token: str, db: AsyncSession = Depends(get_db)):
    """H5 大字播报页（注入 token 与配置）"""
    vt = await _resolve_token(db, token)  # 校验
    html_path = os.path.join(os.path.dirname(__file__), "..", "static", "voice.html")
    html_path = os.path.abspath(html_path)
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="页面未找到")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    # 注入运行时配置（token / 刷新间隔 / 标题）
    html = html.replace("__VOICE_TOKEN__", token)
    html = html.replace("__VOICE_REFRESH__", str(settings.VOICE_REFRESH_SECONDS))
    html = html.replace("__VOICE_TITLE__", vt.index_name)
    return HTMLResponse(content=html)


@router.get("/api/v1/voice/announce")
async def announce(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """返回关注股实时报价 + 口语化播报文本 + 预生成音频 URL"""
    vt = await _resolve_token(db, token)

    # 读取该 token 独立的关注列表
    result = await get_stocks(db, index_code=vt.index_code)
    stocks = result.get("stocks", [])
    ts_codes = [s["ts_code"] for s in stocks if s.get("ts_code")]

    quotes = await fetch_quotes(ts_codes)

    # 按关注列表顺序归并报价（无报价的保留名称、价格为空）
    quote_map = {q.ts_code: q for q in quotes}
    items = []
    for s in stocks:
        q = quote_map.get(s["ts_code"])
        if q is not None:
            items.append(
                {
                    "ts_code": q.ts_code,
                    "name": q.name or s.get("stock_name", ""),
                    "price": q.price,
                    "change": q.change,
                    "pct": q.pct,
                    "time": q.time,
                }
            )
        else:
            items.append(
                {
                    "ts_code": s["ts_code"],
                    "name": s.get("stock_name", s["ts_code"]),
                    "price": None,
                    "change": None,
                    "pct": None,
                    "time": "",
                }
            )

    text = build_broadcast_text(
        [q for q in quotes] if quotes else []
    )
    # 当关注列表有股票但报价全空时，给语音一个温和提示
    if not quotes and stocks:
        text = "暂时获取不到行情数据，请稍后再试。"

    # 为每只股票单独生成播报文本与音频（轮询播报：逐只朗读）
    stocks_out = []
    for s in items:
        if s["price"] is None:
            btext = f"{s['name']}，暂无行情。"
        else:
            pct = s["pct"] or 0
            direction = "上涨" if pct > 0 else ("下跌" if pct < 0 else "持平")
            btext = f"{s['name']}，{s['price']:.2f} 元，{direction} {abs(pct):.2f}%。"
        # 预生成音频（命中缓存直接返回），确保 H5 的 audio_url 可播放
        await tts_service.synthesize(btext)
        audio_url = tts_service.get_audio_url(btext)
        stocks_out.append({**s, "broadcast_text": btext, "audio_url": audio_url})

    # 预生成整段音频（兼容旧用法 / 单条播报兜底）
    await tts_service.synthesize(text)
    summary_audio_url = tts_service.get_audio_url(text)
    return {
        "code": 0,
        "data": {
            "title": vt.index_name,
            "refresh_seconds": settings.VOICE_REFRESH_SECONDS,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stocks": stocks_out,
            "summary_text": text,
            "audio_url": summary_audio_url,
        },
    }


@router.get("/api/v1/voice/tts")
async def tts(
    text: str = Query(..., min_length=1, max_length=500),
    voice: str = Query(default=settings.VOICE_TTS_VOICE),
):
    """合成语音，返回 mp3 文件。命中缓存直接返回。"""
    if len(text) > 500:
        raise HTTPException(status_code=400, detail="文本过长")
    path = await tts_service.synthesize(text, voice)
    return FileResponse(path, media_type="audio/mpeg", filename="voice.mp3")


@router.get("/api/v1/voice/audio/{key}.mp3")
async def audio(key: str):
    """返回缓存的 mp3 音频文件（key 为 sha256 哈希，防遍历）"""
    # 仅允许十六进制哈希
    if not all(c in "0123456789abcdef" for c in key):
        raise HTTPException(status_code=400, detail="非法请求")
    path = os.path.join(_voice_cache_dir(), f"{key}.mp3")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="音频未生成")
    return FileResponse(path, media_type="audio/mpeg")


@router.get("/api/v1/voice/watchlist")
async def watchlist_manager(
    token: str = Query(..., description="voice token，做简单验证"),
    action: str = Query(
        "list", pattern="^(list|add|remove|create_token|delete_token)$",
        description="list/add/remove/create_token/delete_token",
    ),
    codes: str = Query("", description="逗号分隔的 ts_code，如 600519.SH,000001.SZ"),
    index: str = Query(None, description="指数代码（高级覆盖，默认用该 token 自身的列表）"),
    admin: str = Query(None, description="管理员 token（create_token/delete_token 需要）"),
    name: str = Query(None, description="create_token 时的列表名称，如 朋友B"),
    target: str = Query(None, description="delete_token 时指定要删除的 token"),
    db: AsyncSession = Depends(get_db),
):
    """管理语音播报关注列表（无 UI，用 voice token 简单验证，便于直接以 URL 增删）。

    一 token 一列表：默认操作的是【传入 token 自身】的关注列表。
    - action=list（默认）：查看当前关注列表
    - action=add&codes=...：添加股票（幂等，只加不存在的）
    - action=remove&codes=...：删除股票
    - action=create_token：生成一份全新独立列表（新 token + 新指数 + 种子默认股票），
      需管理员校验，返回新 token 与 URL
    - action=delete_token&target=<token>：删除指定 token，需管理员校验
    增删只动 DB，下一次轮询即生效，无需重启。
    """
    vt = await _resolve_token(db, token)  # 基本 token 验证（无效返回 403）

    # 创建 / 删除 token 需要管理员权限
    if action in ("create_token", "delete_token"):
        _check_admin(admin)

    if action == "create_token":
        new_vt = await voice_token_service.create_token(db, label="elder", index_name=name)
        current = await get_stocks(db, index_code=new_vt.index_code)
        return {
            "code": 0,
            "data": {
                "action": "create_token",
                "token": new_vt.token,
                "index_code": new_vt.index_code,
                "index_name": new_vt.index_name,
                "url": f"/voice/{new_vt.token}",
                "stocks": [
                    {"ts_code": s["ts_code"], "stock_name": s["stock_name"]}
                    for s in current.get("stocks", [])
                ],
            },
        }

    if action == "delete_token":
        tgt = target or token
        ok = await voice_token_service.delete_token(db, tgt)
        return {
            "code": 0,
            "data": {
                "action": "delete_token",
                "deleted": tgt if ok else None,
                "found": ok,
            },
        }

    # list / add / remove：操作该 token 自身的列表
    index_code = index or vt.index_code
    result: dict = {"action": action, "index_code": index_code}

    if action == "add":
        code_list = [c.strip().upper() for c in codes.split(",") if c.strip()]
        if not code_list:
            raise HTTPException(status_code=400, detail="codes 不能为空")
        await ensure_index_info(
            db,
            index_code=index_code,
            index_name=vt.index_name,
            full_name=vt.index_name,
        )
        added = await add_stocks(db, code_list, index_code=index_code)
        result["added"] = added["ts_codes"]
    elif action == "remove":
        code_list = [c.strip().upper() for c in codes.split(",") if c.strip()]
        if not code_list:
            raise HTTPException(status_code=400, detail="codes 不能为空")
        removed = []
        for c in code_list:
            r = await remove_stock(db, c, index_code=index_code)
            if r.get("removed"):
                removed.append(c)
        result["removed"] = removed

    # 始终返回当前列表
    current = await get_stocks(db, index_code=index_code)
    result["index_name"] = vt.index_name
    result["stocks"] = [
        {"ts_code": s["ts_code"], "stock_name": s["stock_name"]}
        for s in current.get("stocks", [])
    ]
    return {"code": 0, "data": result}
