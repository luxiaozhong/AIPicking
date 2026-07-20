"""实时报价服务 — 腾讯财经 qt.gtimg.cn（免费、免鉴权，A 股稳定）

接口：
    http://qt.gtimg.cn/q=sh600519,sz000001
返回（GBK 编码）：
    v_sh600519="1~贵州茅台~600519~1480.50~1450.10~...~...";

按 ~ 切分后的关键字段（0 起）：
    1  名称
    3  当前价
    4  昨收
    31 涨跌额
    32 涨跌幅(%)
    30 时间（YYYY-MM-DD HH:MM:SS）
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import httpx

_TENCENT_QUOTE_URL = "http://qt.gtimg.cn/q="
_TIMEOUT = 5.0
_MAX_BATCH = 100


@dataclass
class Quote:
    ts_code: str          # 完整代码，如 600519.SH
    name: str             # 名称
    price: float          # 当前价
    pre_close: float      # 昨收
    change: float         # 涨跌额
    pct: float            # 涨跌幅(%)
    time: str             # 行情时间


def _to_tencent_code(ts_code: str) -> str:
    """600519.SH -> sh600519 ; 000001.SZ -> sz000001"""
    code, _, exch = ts_code.partition(".")
    exch = exch.upper()
    prefix = "sh" if exch in ("SH", "SS") else "sz"
    return f"{prefix}{code}"


def _parse_one(raw: str, ts_code: str) -> Quote | None:
    """解析单行 v_xxx="..." 报价文本，失败时返回 None"""
    m = re.search(r'="(.*)"', raw)
    if not m:
        return None
    fields = m.group(1).split("~")
    if len(fields) < 33:
        return None
    try:
        name = fields[1]
        price = float(fields[3])
        pre_close = float(fields[4])
        change = float(fields[31])
        pct = float(fields[32])
        time = fields[30] if len(fields) > 30 else ""
    except (ValueError, IndexError):
        return None
    return Quote(
        ts_code=ts_code,
        name=name,
        price=price,
        pre_close=pre_close,
        change=change,
        pct=pct,
        time=time,
    )


async def fetch_quotes(ts_codes: list[str]) -> list[Quote]:
    """批量获取实时报价。

    Args:
        ts_codes: 完整 ts_code 列表，如 ["600519.SH", "000001.SZ"]

    Returns:
        成功解析的 Quote 列表（失败的代码被跳过，保持顺序）
    """
    if not ts_codes:
        return []

    quotes: list[Quote] = []
    # 分批，避免 URL 过长
    for i in range(0, len(ts_codes), _MAX_BATCH):
        batch = ts_codes[i : i + _MAX_BATCH]
        tencent_codes = [_to_tencent_code(c) for c in batch]
        url = _TENCENT_QUOTE_URL + ",".join(tencent_codes)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url)
            text = resp.content.decode("gbk", errors="ignore")
        except (httpx.HTTPError, UnicodeError):
            continue

        # 每行一个 v_xxx="..."
        lines = text.strip().split(";")
        # 建立 tencent_code -> ts_code 映射
        code_map = dict(zip(tencent_codes, batch))
        for line in lines:
            line = line.strip()
            if not line or "v_" not in line:
                continue
            tc = line.split("=")[0].replace("v_", "").strip()
            ts_code = code_map.get(tc, tc)
            q = _parse_one(line, ts_code)
            if q is not None:
                quotes.append(q)

    return quotes


async def fetch_quotes_map(ts_codes: list[str]) -> dict[str, Quote]:
    """同 fetch_quotes，但返回 {ts_code: Quote} 便于按股票索引"""
    quotes = await fetch_quotes(ts_codes)
    return {q.ts_code: q for q in quotes}


def build_broadcast_text(quotes: list[Quote]) -> str:
    """把报价拼成口语化播报文本。

    示例：「您关注的股票：贵州茅台，1480.50 元，上涨 2.10%；平安银行，12.30 元，下跌 0.80%。」
    无股票时返回提示语。
    """
    if not quotes:
        return "您当前没有关注任何股票，请先添加。"

    parts = []
    for q in quotes:
        direction = "上涨" if q.change >= 0 else "下跌"
        parts.append(
            f"{q.name}，{q.price:.2f} 元，{direction} {abs(q.pct):.2f}%"
        )
    return "您关注的股票：" + "；".join(parts) + "。"


if __name__ == "__main__":
    async def _main():
        res = await fetch_quotes(["600519.SH", "000001.SZ"])
        for q in res:
            print(q)
        print(build_broadcast_text(res))

    asyncio.run(_main())
