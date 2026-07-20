#!/usr/bin/env python
"""语音播报（老人微信链接入口）上云初始化脚本

功能：
  1. 幂等注册语音播报独立指数（默认 900099）到 index_info
  2. 批量添加关注股票到该指数（默认：贵州茅台、中国平安）
  3. （可选）生成访问 token，并打印可直接发给老人的 URL
  4. 打印需要写入 .env / .env.production 的 VOICE_* 配置片段

在云端 backend 目录下运行（需已激活 venv，且 .env.production 已存在）：
  ./venv/bin/python scripts/setup_voice.py --public-ip 1.2.3.4 --gen-token
  ./venv/bin/python scripts/setup_voice.py --stocks 600519.SH 601318.SH --name "关注的股票"
  ./venv/bin/python scripts/setup_voice.py --gen-token --public-ip 1.2.3.4 --port 80

注意：
  - 索引代码 / 名称默认读 settings.VOICE_WATCHLIST_INDEX、VOICE_WATCHLIST_NAME，
    也可用 --index / --name 覆盖。
  - --gen-token 仅生成 token 并打印配置片段；把该片段加进 .env.production 后
    需 `systemctl restart aipicking` 让后端加载新 token。
  - 本脚本只操作数据库，不依赖 Edge-TTS，因此无需先安装 edge-tts。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys

# 确保 backend 根目录在 sys.path，便于以 `python scripts/setup_voice.py` 直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import async_session
from app.config import settings
from app.services.watchlist_service import ensure_index_info, add_stocks, get_stocks


DEFAULT_STOCKS = ["600519.SH", "601318.SH"]  # 贵州茅台、中国平安


async def setup(
    index_code: str,
    index_name: str,
    stocks: list[str],
) -> None:
    db = await async_session()
    try:
        await ensure_index_info(
            db,
            index_code=index_code,
            index_name=index_name,
            full_name=index_name,
        )
        result = await add_stocks(db, stocks, index_code=index_code)
        current = await get_stocks(db, index_code=index_code)
        print(f"✓ 指数 {index_code}（{index_name}）已就绪")
        print(f"✓ 本次添加 {result['added']} 只：{', '.join(result['ts_codes'])}")
        print(
            "  当前关注列表："
            + ", ".join(f"{s['stock_name']}({s['ts_code']})" for s in current["stocks"])
        )
    finally:
        await db.close()


def gen_token() -> str:
    return secrets.token_urlsafe(16)


def main() -> None:
    parser = argparse.ArgumentParser(description="语音播报上云初始化")
    parser.add_argument(
        "--stocks", nargs="+", default=DEFAULT_STOCKS,
        help=f"关注股票 ts_code 列表（默认 {DEFAULT_STOCKS}）",
    )
    parser.add_argument(
        "--index", default=settings.VOICE_WATCHLIST_INDEX,
        help=f"语音播报指数代码（默认 {settings.VOICE_WATCHLIST_INDEX}）",
    )
    parser.add_argument(
        "--name", default=settings.VOICE_WATCHLIST_NAME,
        help=f"指数名称（默认 {settings.VOICE_WATCHLIST_NAME}）",
    )
    parser.add_argument(
        "--gen-token", action="store_true",
        help="生成一个访问 token（并打印 .env 配置片段与 URL）",
    )
    parser.add_argument(
        "--public-ip", default="",
        help="公网 IP 或域名；提供后生成可直接测试的完整 URL",
    )
    parser.add_argument(
        "--port", default="80",
        help="对外端口（nginx 默认 80；直连后端用 8000）",
    )
    args = parser.parse_args()

    asyncio.run(setup(args.index, args.name, args.stocks))

    if args.gen_token:
        token = gen_token()
        print("\n=== 请把以下配置追加到 .env / .env.production ===")
        print(f"VOICE_TOKENS=elder:{token}")
        print(f"VOICE_WATCHLIST_INDEX={args.index}")
        print(f"VOICE_WATCHLIST_NAME={args.name}")
        print("VOICE_TTS_VOICE=zh-CN-XiaoxiaoNeural")
        print("VOICE_QUOTE_SOURCE=tencent")
        print("VOICE_REFRESH_SECONDS=30")
        print("\n=== 然后重启后端使 token 生效 ===")
        print("  systemctl restart aipicking   # 或本地 ./restart.sh")

        if args.public_ip:
            url = f"http://{args.public_ip}:{args.port}/voice/{token}"
            print("\n=== 发给老人的链接 ===")
            print(url)


if __name__ == "__main__":
    main()
