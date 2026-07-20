"""语音播报 API — 老人微信链接入口

路由（均无 JWT，靠 token 校验）：
    GET /voice/{token}                 返回 H5 大字播报页
    GET /api/v1/voice/announce?token=  返回关注股实时报价 + 预生成音频 URL
    GET /api/v1/voice/tts?text=&voice= 生成（命中缓存则返回）mp3 音频
    GET /api/v1/voice/audio/{key}.mp3  返回缓存的 mp3（供 <audio> 播放）
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
from ..services.watchlist_service import get_stocks

router = APIRouter()

# token -> label 映射（启动时从配置加载）
_TOKEN_MAP: dict[str, str] = {}


def _load_tokens() -> None:
    """从 settings.VOICE_TOKENS 解析 token 映射（label:token, 逗号分隔）"""
    _TOKEN_MAP.clear()
    raw = (settings.VOICE_TOKENS or "").strip()
    if not raw:
        return
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            label, token = item.split(":", 1)
            _TOKEN_MAP[token.strip()] = label.strip()
        else:
            # 仅有 token，label 用 token 本身
            _TOKEN_MAP[item] = item


def _require_token(token: str) -> str:
    """校验 token，返回对应 label；失败抛 403"""
    if token not in _TOKEN_MAP:
        raise HTTPException(status_code=403, detail="无效的播报链接")
    return _TOKEN_MAP[token]


def _voice_cache_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
        "voice_cache",
    )


@router.get("/voice/{token}", response_class=HTMLResponse)
async def voice_page(token: str):
    """H5 大字播报页（注入 token 与配置）"""
    _require_token(token)  # 校验
    html_path = os.path.join(os.path.dirname(__file__), "..", "static", "voice.html")
    html_path = os.path.abspath(html_path)
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="页面未找到")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    # 注入运行时配置（token / 刷新间隔 / 标题）
    html = html.replace("__VOICE_TOKEN__", token)
    html = html.replace("__VOICE_REFRESH__", str(settings.VOICE_REFRESH_SECONDS))
    html = html.replace("__VOICE_TITLE__", settings.VOICE_WATCHLIST_NAME)
    return HTMLResponse(content=html)


@router.get("/api/v1/voice/announce")
async def announce(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """返回关注股实时报价 + 口语化播报文本 + 预生成音频 URL"""
    _require_token(token)

    # 读取老人关注列表（独立 index）
    result = await get_stocks(db, index_code=settings.VOICE_WATCHLIST_INDEX)
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
            "title": settings.VOICE_WATCHLIST_NAME,
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


def register_voice_tokens() -> None:
    """供应用启动时调用，加载 token 映射"""
    _load_tokens()
