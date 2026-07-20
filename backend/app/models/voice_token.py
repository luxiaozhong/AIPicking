"""语音播报 token 表 — 一 token 一列表

每个 voice token 绑定一个独立指数（index_code），其关注列表即该指数的成分股。
"""

from sqlalchemy import Column, String, Boolean

from .base import BaseModel


class VoiceToken(BaseModel):
    __tablename__ = "voice_tokens"

    token = Column(String(64), unique=True, nullable=False, index=True,
                   comment="访问钥匙，放在 URL 中")
    label = Column(String(50), nullable=False, default="elder",
                   comment="备注，如 elder")
    index_code = Column(String(20), nullable=False, index=True,
                        comment="该 token 专属的指数代码（独立列表载体）")
    index_name = Column(String(50), nullable=False, default="语音播报关注",
                        comment="列表标题，注入 H5 页")
    active = Column(Boolean, nullable=False, default=True,
                    comment="是否启用")
