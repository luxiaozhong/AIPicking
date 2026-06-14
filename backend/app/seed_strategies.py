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
        "name": "Oversold Bounce SS",
        "description": "主板超跌反弹策略：三阶段信号链捕捉放量急跌后的止跌反弹。仅限上证主板(600/601/603/605)+深证主板(000/001/002/003)。",
        "file_path": "app/strategies/examples/oversold_bounce_ss.py",
        "tags": "超跌反弹,量价,上证,深证,主板,技术面",
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
    {
        "name": "laoyatou",
        "description": "老鸭头形态策略：经典技术形态选股 — 上升趋势中回调不破MA60后金叉再启动。五阶段检测：鸭颈多头确认→鸭头顶回调→MA60支撑→鸭嘴放量金叉→鸭眼MACD确认",
        "file_path": "app/strategies/examples/laoyatou.py",
        "tags": "老鸭头,形态,均线,MACD,量能,技术面",
    },
    {
        "name": "grow_with_money",
        "description": "成长100 + 资金流选股：以国证成长100成分股为股票池，按过去M日主力资金净流入排序，推荐前N只",
        "file_path": "app/strategies/examples/grow_with_money.py",
        "tags": "指数成分股,资金流,成长100,主力净流入",
    },
    {
        "name": "grow_with_money_v1",
        "description": "成长100 + 资金流/市值选股：以国证成长100成分股为股票池，按过去M日主力资金净流入/总市值比率排序，推荐前N只",
        "file_path": "app/strategies/examples/grow_with_money_v1.py",
        "tags": "指数成分股,资金流,成长100,资金效率,市值比率",
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
