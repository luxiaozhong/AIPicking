"""语音合成服务 — Edge-TTS（免费、免 API key，中文音质好）

- 默认音色 zh-CN-XiaoxiaoNeural（自然女声）
- 按 hash(text + voice) 缓存 mp3 到 backend/data/voice_cache/，命中直接返回
- 提供 synthesize() 返回文件路径，及 get_audio_url() 返回可播放的相对 URL
"""

from __future__ import annotations

import hashlib
import os
import tempfile

import edge_tts

from ..config import settings

# 缓存目录（相对 backend 运行目录）
_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "voice_cache",
)


def _cache_key(text: str, voice: str) -> str:
    return hashlib.sha256(f"{voice}::{text}".encode("utf-8")).hexdigest()


def _cache_path(key: str) -> str:
    return os.path.join(_CACHE_DIR, f"{key}.mp3")


def cache_exists(text: str, voice: str | None = None) -> bool:
    voice = voice or settings.VOICE_TTS_VOICE
    return os.path.exists(_cache_path(_cache_key(text, voice)))


async def synthesize(text: str, voice: str | None = None) -> str:
    """合成语音，返回 mp3 文件绝对路径（命中缓存直接返回）。

    Args:
        text: 要朗读的中文文本
        voice: 音色，默认 settings.VOICE_TTS_VOICE
    """
    voice = voice or settings.VOICE_TTS_VOICE
    key = _cache_key(text, voice)
    path = _cache_path(key)

    if os.path.exists(path):
        return path

    os.makedirs(_CACHE_DIR, exist_ok=True)

    # 先写临时文件再原子替换，避免并发写入半截文件
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3", dir=_CACHE_DIR)
    os.close(tmp_fd)
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(tmp_path)
        os.replace(tmp_path, path)
    except Exception:
        # 清理失败临时文件
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise

    return path


def get_audio_url(text: str, voice: str | None = None) -> str:
    """返回音频文件的相对 URL（供 <audio src> 播放）。"""
    voice = voice or settings.VOICE_TTS_VOICE
    key = _cache_key(text, voice)
    return f"/api/v1/voice/audio/{key}.mp3"
