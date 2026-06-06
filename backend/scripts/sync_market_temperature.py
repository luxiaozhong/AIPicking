"""
每日市场温度计算并持久化

在 sync_market_data.py 之后运行，依赖：
  - daily（日线行情）
  - daily_sector_flow（板块资金流）
  - daily_hot_themes（热门主题）
  - daily_northbound_flow（北向资金）

写入表：daily_market_temperature（幂等 upsert）

用法：
    cd backend
    venv/bin/python scripts/sync_market_temperature.py
    venv/bin/python scripts/sync_market_temperature.py --date 2026-06-05
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 确保 backend 目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import AsyncSessionLocal  # noqa: E402
from app.services.market_heat_service import MarketHeatService  # noqa: E402


async def main_async(trade_date: Optional[str] = None):
    """计算并保存指定日期的市场温度"""
    async with AsyncSessionLocal() as db:
        # 确定交易日
        if trade_date:
            date = trade_date
        else:
            # 默认取 daily 表最新日期
            from sqlalchemy import select, func
            from app.models.stock_tables import Daily
            stmt = select(func.max(Daily.__table__.c.trade_date))
            result = await db.execute(stmt)
            date = result.scalar()
            if not date:
                print("[温度] 无可用交易日数据，跳过")
                return

        print(f"[温度] 计算 {date} 全市场温度...")
        temp = await MarketHeatService.save_temperature(db, date)

        print(f"  得分: {temp['score']}° ({temp['level']})")
        dims = temp["dimensions"]
        print(f"  资金面: {dims['capital']}/20  涨跌结构: {dims['breadth']}/20  "
              f"情绪面: {dims['sentiment']}/20  集中度: {dims['concentration']}/20  "
              f"延续性: {dims['continuity']}/20")
        print("  ✓ 已保存到 daily_market_temperature")

        print(f"\n[温度] 计算 {date} 四大板块温度...")
        boards = await MarketHeatService.save_board_temperatures(db, date)
        for b in boards:
            dims = b["dimensions"]
            print(f"  {b['board_name']}: {b['score']}° ({b['level']})  "
                  f"结构:{dims['breadth']}/40 情绪:{dims['sentiment']}/30 量能:{dims['volume']}/30")
        print("  ✓ 已保存到 daily_board_temperature")


def main():
    parser = argparse.ArgumentParser(description="每日市场温度计算")
    parser.add_argument("--date", type=str, help="指定日期 YYYY-MM-DD，默认最新交易日")
    args = parser.parse_args()

    date_arg = args.date
    if date_arg and len(date_arg) == 8:
        date_arg = f"{date_arg[:4]}-{date_arg[4:6]}-{date_arg[6:]}"

    print(f"[温度] 开始 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    asyncio.run(main_async(date_arg))
    print(f"[温度] 结束 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
