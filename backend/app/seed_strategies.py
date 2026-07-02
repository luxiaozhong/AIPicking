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
        "params_schema": json.dumps({
            "index_code": {
                "type": "string",
                "default": "980080",
                "label": "指数代码",
                "description": "国证成长100=980080",
            },
            "N": {
                "type": "int",
                "default": 5,
                "label": "推荐数量 N",
                "description": "选取资金流前 N 名",
                "min": 1,
                "max": 20,
            },
            "M": {
                "type": "int",
                "default": 5,
                "label": "回顾天数 M",
                "description": "过去 M 个交易日的资金流累计",
                "min": 3,
                "max": 60,
            },
        }, ensure_ascii=False),
    },
    {
        "name": "grow_with_money_v1",
        "description": "成长100 + 资金流/市值选股：以国证成长100成分股为股票池，按过去M日主力资金净流入/总市值比率排序，推荐前N只",
        "file_path": "app/strategies/examples/grow_with_money_v1.py",
        "tags": "指数成分股,资金流,成长100,资金效率,市值比率",
        "params_schema": json.dumps({
            "index_code": {
                "type": "string",
                "default": "980080",
                "label": "指数代码",
                "description": "国证成长100=980080",
            },
            "N": {
                "type": "int",
                "default": 3,
                "label": "推荐数量 N",
                "description": "选取资金流/市值比率前 N 名",
                "min": 1,
                "max": 20,
            },
            "M": {
                "type": "int",
                "default": 5,
                "label": "回顾天数 M",
                "description": "过去 M 个交易日的资金流累计",
                "min": 3,
                "max": 60,
            },
        }, ensure_ascii=False),
    },
    {
        "name": "grow_with_money_sh",
        "description": "上证个股 + 资金流选股：以上证个股（600/601/603/605开头）为股票池，按过去M日主力资金净流入排序，推荐前N只",
        "file_path": "app/strategies/examples/grow_with_money_sh.py",
        "tags": "资金流,上证,主力净流入",
        "params_schema": json.dumps({
            "N": {
                "type": "int",
                "default": 5,
                "label": "推荐数量 N",
                "description": "选取资金流前 N 名",
                "min": 1,
                "max": 20,
            },
            "M": {
                "type": "int",
                "default": 5,
                "label": "回顾天数 M",
                "description": "过去 M 个交易日的资金流累计",
                "min": 3,
                "max": 60,
            },
        }, ensure_ascii=False),
    },
    {
        "name": "grow_with_money_hz",
        "description": "深证个股 + 资金流选股：以深证个股（000/001/002/003开头）为股票池，按过去M日主力资金净流入排序，推荐前N只",
        "file_path": "app/strategies/examples/grow_with_money_hz.py",
        "tags": "资金流,深证,主力净流入",
        "params_schema": json.dumps({
            "N": {
                "type": "int",
                "default": 5,
                "label": "推荐数量 N",
                "description": "选取资金流前 N 名",
                "min": 1,
                "max": 20,
            },
            "M": {
                "type": "int",
                "default": 5,
                "label": "回顾天数 M",
                "description": "过去 M 个交易日的资金流累计",
                "min": 3,
                "max": 60,
            },
        }, ensure_ascii=False),
    },
    {
        "name": "grow_with_money_cy",
        "description": "创业板个股 + 资金流选股：以创业板个股（300/301开头）为股票池，按过去M日主力资金净流入排序，推荐前N只",
        "file_path": "app/strategies/examples/grow_with_money_cy.py",
        "tags": "资金流,创业板,主力净流入",
        "params_schema": json.dumps({
            "N": {
                "type": "int",
                "default": 5,
                "label": "推荐数量 N",
                "description": "选取资金流前 N 名",
                "min": 1,
                "max": 20,
            },
            "M": {
                "type": "int",
                "default": 5,
                "label": "回顾天数 M",
                "description": "过去 M 个交易日的资金流累计",
                "min": 3,
                "max": 60,
            },
        }, ensure_ascii=False),
    },
    {
        "name": "grow_with_money_kc",
        "description": "科创板个股 + 资金流选股：以科创板个股（688开头）为股票池，按过去M日主力资金净流入排序，推荐前N只",
        "file_path": "app/strategies/examples/grow_with_money_kc.py",
        "tags": "资金流,科创板,主力净流入",
        "params_schema": json.dumps({
            "N": {
                "type": "int",
                "default": 5,
                "label": "推荐数量 N",
                "description": "选取资金流前 N 名",
                "min": 1,
                "max": 20,
            },
            "M": {
                "type": "int",
                "default": 5,
                "label": "回顾天数 M",
                "description": "过去 M 个交易日的资金流累计",
                "min": 3,
                "max": 60,
            },
        }, ensure_ascii=False),
    },
    {
        "name": "grow_with_money_all",
        "description": "全A股 + 资金流选股：以全部A股为股票池，按过去M日主力资金净流入排序，推荐前N只",
        "file_path": "app/strategies/examples/grow_with_money_all.py",
        "tags": "资金流,全A股,主力净流入",
        "params_schema": json.dumps({
            "N": {
                "type": "int",
                "default": 5,
                "label": "推荐数量 N",
                "description": "选取资金流前 N 名",
                "min": 1,
                "max": 20,
            },
            "M": {
                "type": "int",
                "default": 5,
                "label": "回顾天数 M",
                "description": "过去 M 个交易日的资金流累计",
                "min": 3,
                "max": 60,
            },
        }, ensure_ascii=False),
    },
    {
        "name": "动量轮动",
        "description": "量价动量轮动：多指数成分股池，按价格动量（多周期加权）+成交量（量比）横截面Z-score排名，选取top N",
        "file_path": "app/strategies/examples/momentum_rotation.py",
        "tags": "动量,量能,轮动,排名,指数成分股",
        "params_schema": json.dumps({
            "index_codes": {
                "type": "string",
                "default": "",
                "label": "指数代码",
                "description": "逗号分隔，如 399006,000300。留空则全市场选股",
            },
            "N": {
                "type": "int",
                "default": 10,
                "label": "推荐数量 N",
                "description": "选取 top N 只",
                "min": 1,
                "max": 50,
            },
            "mom_fast": {
                "type": "int",
                "default": 20,
                "label": "短周期动量窗口",
                "description": "短周期收益率窗口（交易日）",
                "min": 5,
                "max": 120,
            },
            "mom_slow": {
                "type": "int",
                "default": 60,
                "label": "长周期动量窗口",
                "description": "长周期收益率窗口（交易日）",
                "min": 10,
                "max": 250,
            },
            "mom_fast_weight": {
                "type": "float",
                "default": 0.6,
                "label": "短周期权重",
                "description": "短周期收益率权重，1-此值=长周期权重",
                "min": 0.1,
                "max": 0.9,
            },
            "vol_short": {
                "type": "int",
                "default": 5,
                "label": "短期均量窗口",
                "description": "短期均量窗口（交易日）",
                "min": 3,
                "max": 30,
            },
            "vol_long": {
                "type": "int",
                "default": 20,
                "label": "长期均量窗口",
                "description": "长期均量窗口（交易日）",
                "min": 5,
                "max": 60,
            },
            "volume_weight": {
                "type": "float",
                "default": 0.4,
                "label": "成交量权重",
                "description": "成交量在总分中的权重，1-此值=动量权重",
                "min": 0.1,
                "max": 0.9,
            },
        }, ensure_ascii=False),
    },
]


async def seed_strategies(db: AsyncSession, admin_user_id: int = 1) -> int:
    """预置策略（按 name 去重，已存在则更新 params_schema 等字段）。返回新创建的策略数。"""
    created = 0
    for s in BUILTIN_STRATEGIES:
        result = await db.execute(select(Strategy).where(Strategy.name == s["name"]))
        existing = result.scalar_one_or_none()

        if existing:
            # 更新已有策略的 params_schema、description 等字段
            updated = False
            if s.get("params_schema") and existing.params_schema != s["params_schema"]:
                existing.params_schema = s["params_schema"]
                updated = True
            if s.get("description") and existing.description != s["description"]:
                existing.description = s["description"]
                updated = True
            if s.get("file_path") and existing.file_path != s["file_path"]:
                existing.file_path = s["file_path"]
                updated = True
            if s.get("tags") and existing.tags != s["tags"]:
                existing.tags = s["tags"]
                updated = True
            if not existing.is_published:
                existing.is_published = True
                updated = True
            if updated:
                db.add(existing)
            continue

        strategy = Strategy(
            name=s["name"],
            description=s["description"],
            file_path=s["file_path"],
            params_schema=s.get("params_schema"),
            tags=s.get("tags"),
            status="active",
            version=1,
            factor_config=s.get("factor_config"),
            user_id=admin_user_id,
            is_published=True,
        )
        db.add(strategy)
        created += 1

    if created:
        await db.flush()
        print(f"已预置 {created} 个策略")
    return created
