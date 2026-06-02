"""
内置策略数据种子脚本。
每次启动时调用，确保数据库中存在预置策略。
若策略 name 已存在则跳过。
"""
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.strategy import Strategy

BUILTIN_STRATEGIES = [
    {
        "name": "Trend Upstart",
        "description": "趋势启动捕捉策略：基于大阳线信号+量能确认+均线多头排列+MACD/RSI辅助，捕捉中大盘趋势启动点",
        "file_path": "app/strategies/examples/22_Trend_Upstart.py",
        "tags": "趋势,动量,量能,技术面",
    },
    {
        "name": "Trend Upstart Flow",
        "description": "基于 Trend Upstart + 板块资金流向增强打分",
        "file_path": "app/strategies/examples/23_Trend_Upstart_Flow.py",
        "tags": None,
    },
    {
        "name": "Bottom Divergence",
        "description": "日线MACD底背离反弹策略：股价新低+DIF未新低+缩量+阳线确认",
        "file_path": "app/strategies/examples/24_Bottom_Divergence.py",
        "tags": None,
    },
    {
        "name": "Stock Checkup",
        "description": "个股综合诊断：从趋势、动量、量能、形态、资金流五维度打分",
        "file_path": "app/strategies/examples/25_Stock_Checkup.py",
        "tags": "个股诊断,技术分析,资金流",
    },
    {
        "name": "Oversold Bounce",
        "description": "科技股超跌反弹策略：三阶段信号链捕捉放量急跌后的止跌反弹。仅限创业板+科创板。",
        "file_path": "app/strategies/examples/oversold_bounce.py",
        "tags": "超跌反弹,量价,创业板,科创板,技术面",
    },
    {
        "name": "动量",
        "description": "",
        "file_path": "app/strategies/examples/auto_20_动量.py",
        "tags": None,
        "factor_config": json.dumps({
            "buy_signals": {
                "logic": "AND",
                "factors": [
                    {"factor_id": "momentum_kdj", "params": {"n": 9, "m1": 3, "m2": 3}},
                    {"factor_id": "momentum_macd", "params": {"fast_period": 12, "slow_period": 26, "signal_period": 9}},
                ],
            },
            "sell_signals": {"logic": "OR", "factors": []},
            "risk_factors": [],
        }),
    },
    {
        "name": "daydayup1",
        "description": "",
        "file_path": "app/strategies/examples/auto_23_daydayup1.py",
        "tags": None,
        "factor_config": json.dumps({
            "buy_signals": {
                "logic": "AND",
                "factors": [
                    {"factor_id": "volume_turnover", "params": {"min_turnover": 2, "max_turnover": 20, "require_price_up": True}},
                    {"factor_id": "momentum_macd", "params": {"fast_period": 12, "slow_period": 26, "signal_period": 9}},
                    {"factor_id": "pattern_morning_star", "params": {"body_ratio": 50}},
                ],
            },
            "sell_signals": {"logic": "OR", "factors": []},
            "risk_factors": [],
        }),
    },
]


async def seed_strategies(db: AsyncSession, admin_user_id: int = 1) -> int:
    """预置策略（按 name 去重，已存在则跳过）。返回新创建的策略数。"""
    created = 0
    for s in BUILTIN_STRATEGIES:
        result = await db.execute(select(Strategy).where(Strategy.name == s["name"]))
        if result.scalar_one_or_none():
            continue

        strategy = Strategy(
            name=s["name"],
            description=s["description"],
            file_path=s["file_path"],
            tags=s.get("tags"),
            status="active",
            version=1,
            factor_config=s.get("factor_config"),
            user_id=admin_user_id,
        )
        db.add(strategy)
        created += 1

    if created:
        await db.flush()
        print(f"已预置 {created} 个策略")
    return created
