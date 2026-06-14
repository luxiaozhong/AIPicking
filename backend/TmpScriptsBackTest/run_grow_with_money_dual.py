#!/usr/bin/env python3
"""
grow_with_money 策略 — 双方法对比执行

方法1：简单资金流 — 按主力净流入总额排名
方法2：资金流/市值 — 按主力净流入 / 流通市值比率排名

用法：
    cd backend && source venv/bin/activate
    python TmpScriptsBackTest/run_grow_with_money_dual.py              # 默认 6/12
    python TmpScriptsBackTest/run_grow_with_money_dual.py 2026-06-10   # 指定日期
"""

import sys
import os
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.models.stock_tables import Stock, Daily, DailyStockFundFlow
from app.models.index_tables import IndexConstituent

# ── 参数 ──────────────────────────────────────────────────
INDEX_CODE = "980080"       # 国证成长100
N = 5                       # 推荐数量
M = 20                      # 资金流回顾天数（交易日）

# ── 数据库 ────────────────────────────────────────────────
engine = create_engine(settings.SYNC_DATABASE_URL)
SyncSession = sessionmaker(bind=engine)


def load_stocks(session):
    """加载全量股票基础信息"""
    stmt = select(Stock.__table__)
    rows = [dict(row._mapping) for row in session.execute(stmt)]
    # 构建 ts_code → info 映射
    stocks = {}
    for r in rows:
        ts_code = r["ts_code"]
        raw_code = ts_code.split(".")[0] if "." in ts_code else ts_code
        stocks[ts_code] = {
            **r,
            "raw_code": raw_code,
        }
    return stocks


def load_index_constituents(session, index_code):
    """加载指定指数的最新成分股"""
    from sqlalchemy import func
    # 获取最新 eff_date
    latest_date = session.execute(
        select(func.max(IndexConstituent.eff_date))
        .where(IndexConstituent.index_code == index_code)
    ).scalar()

    if not latest_date:
        return []

    stmt = select(IndexConstituent.__table__).where(
        IndexConstituent.index_code == index_code,
        IndexConstituent.eff_date == latest_date,
    )
    return [dict(row._mapping) for row in session.execute(stmt)]


def load_fund_flow(session, trade_dates):
    """加载指定交易日的资金流数据"""
    if not trade_dates:
        return []
    stmt = select(DailyStockFundFlow.__table__).where(
        DailyStockFundFlow.trade_date.in_(trade_dates)
    )
    return [dict(row._mapping) for row in session.execute(stmt)]


def load_daily_for_stocks(session, ts_codes, trade_date):
    """加载指定股票在 cutoff_date 的日线数据（用于市值计算）"""
    if not ts_codes:
        return {}
    stmt = select(Daily.__table__).where(
        Daily.ts_code.in_(ts_codes),
        Daily.trade_date == trade_date,
    )
    rows = [dict(row._mapping) for row in session.execute(stmt)]
    return {r["ts_code"]: r for r in rows}


def get_recent_trade_dates(session, cutoff_date, limit):
    """获取 cutoff_date 及之前最近的 limit 个有资金流数据的交易日"""
    stmt = (
        select(DailyStockFundFlow.trade_date)
        .where(DailyStockFundFlow.trade_date <= cutoff_date)
        .distinct()
        .order_by(DailyStockFundFlow.trade_date.desc())
        .limit(limit)
    )
    rows = session.execute(stmt).fetchall()
    return [r[0] for r in rows]


def format_yi(val):
    """格式化为亿单位"""
    yi = val / 1e8
    if yi >= 0:
        return f"+{yi:.2f}亿"
    return f"{yi:.2f}亿"


def main():
    cutoff_date = sys.argv[1] if len(sys.argv) > 1 else "2026-06-12"
    print(f"📅 截止日期: {cutoff_date}")
    print(f"📊 指数: {INDEX_CODE} (国证成长100)")
    print(f"🔢 回顾交易日: M={M}")
    print(f"🎯 推荐数量: N={N}")
    print()

    session = SyncSession()

    try:
        # ── 1. 加载成分股 ──────────────────────────────────
        print("⏳ 加载指数成分股...")
        constituents = load_index_constituents(session, INDEX_CODE)
        target_raw_codes = set(c["ts_code"] for c in constituents)
        print(f"   成分股数量: {len(target_raw_codes)}")

        # ── 2. 加载全量 stocks ─────────────────────────────
        print("⏳ 加载股票基础信息...")
        all_stocks = load_stocks(session)

        # 构建 raw_code → ts_code 映射
        raw_to_tscode = {}
        ts_code_to_info = {}
        target_ts_codes = []
        for ts_code, info in all_stocks.items():
            raw = info["raw_code"]
            if raw in target_raw_codes:
                raw_to_tscode[raw] = ts_code
                ts_code_to_info[ts_code] = info
                target_ts_codes.append(ts_code)

        print(f"   匹配到 {len(target_ts_codes)} 只成分股")

        # ── 3. 获取最近 M 个交易日 ─────────────────────────
        print("⏳ 获取最近交易日...")
        trade_dates = get_recent_trade_dates(session, cutoff_date, M)
        if not trade_dates:
            print("❌ 未找到资金流数据！")
            return
        print(f"   交易日范围: {trade_dates[-1]} ~ {trade_dates[0]} ({len(trade_dates)} 天)")

        # ── 4. 加载资金流数据 ──────────────────────────────
        print("⏳ 加载资金流数据...")
        fund_flow_rows = load_fund_flow(session, trade_dates)
        print(f"   资金流记录: {len(fund_flow_rows)} 条")

        # ── 5. 加载 cutoff_date 当天的日线数据（用于市值） ──
        print("⏳ 加载日线数据（市值计算）...")
        daily_map = load_daily_for_stocks(session, target_ts_codes, cutoff_date)
        print(f"   日线数据: {len(daily_map)} 条")

        # ── 6. 聚合 M 日资金流 ──────────────────────────────
        print()
        print("=" * 70)
        print("  计算中...")
        print("=" * 70)

        # 按 ts_code 聚合 M 日主力净流入
        main_flow_sum = defaultdict(float)
        trade_date_set = set(trade_dates)

        for row in fund_flow_rows:
            if row["trade_date"] in trade_date_set:
                ts_code = row["ts_code"]
                main_flow_sum[ts_code] += row.get("main_net_flow") or 0.0

        # ── 7. 方法1：简单资金流 ───────────────────────────
        method1_results = []
        for raw_code in target_raw_codes:
            ts_code = raw_to_tscode.get(raw_code)
            if not ts_code:
                continue
            total_flow = main_flow_sum.get(ts_code, 0.0)
            info = ts_code_to_info.get(ts_code, {})
            method1_results.append({
                "ts_code": ts_code,
                "name": info.get("name", raw_code),
                "raw_code": raw_code,
                "total_flow": total_flow,
                "score": round(total_flow / 1e8, 2),  # 亿
            })

        method1_results.sort(key=lambda x: x["score"], reverse=True)

        # ── 8. 方法2：资金流/流通市值 ──────────────────────
        method2_results = []
        skipped_no_cap = 0
        for raw_code in target_raw_codes:
            ts_code = raw_to_tscode.get(raw_code)
            if not ts_code:
                continue

            total_flow = main_flow_sum.get(ts_code, 0.0)

            # 计算流通市值 = 流通股本 × 收盘价
            info = ts_code_to_info.get(ts_code, {})
            float_shares = info.get("float_shares") or 0
            daily_row = daily_map.get(ts_code)
            close_price = daily_row["close"] if daily_row else 0

            if float_shares <= 0 or not close_price or close_price <= 0:
                skipped_no_cap += 1
                continue

            circ_market_cap = float_shares * close_price  # 流通市值（元）

            if circ_market_cap <= 0:
                skipped_no_cap += 1
                continue

            # 资金流 / 流通市值 比率（乘以 1e8 放大，转为更直观的数值）
            flow_cap_ratio = total_flow / circ_market_cap

            method2_results.append({
                "ts_code": ts_code,
                "name": info.get("name", raw_code),
                "raw_code": raw_code,
                "total_flow": total_flow,
                "circ_market_cap_yi": round(circ_market_cap / 1e8, 2),  # 亿
                "score": round(flow_cap_ratio * 1e4, 2),  # 乘以 10000 放大
                "flow_cap_ratio_raw": flow_cap_ratio,
            })

        method2_results.sort(key=lambda x: x["score"], reverse=True)

        # ── 9. 输出结果 ────────────────────────────────────
        print()
        print("=" * 70)
        print(f"  📈 方法1：简单资金流 Top {N}")
        print(f"     按 M={M} 日主力净流入总额排名")
        print("=" * 70)
        print(f"  {'排名':<4s} {'代码':<12s} {'名称':<10s} {'主力净流入':>14s}")
        print("-" * 70)
        for i, r in enumerate(method1_results[:N], 1):
            print(f"  {i:<4d} {r['ts_code']:<12s} {r['name']:<10s} {format_yi(r['total_flow']):>14s}")

        print()
        print("=" * 70)
        print(f"  📈 方法2：资金流/流通市值 Top {N}")
        print(f"     按 M={M} 日主力净流入 / 流通市值 比率排名")
        print("=" * 70)
        print(f"  {'排名':<4s} {'代码':<12s} {'名称':<10s} {'主力净流入':>14s} {'流通市值':>12s} {'比率(‱)':>10s}")
        print("-" * 70)
        for i, r in enumerate(method2_results[:N], 1):
            print(f"  {i:<4d} {r['ts_code']:<12s} {r['name']:<10s} {format_yi(r['total_flow']):>14s} {r['circ_market_cap_yi']:>10.2f}亿 {r['score']:>10.2f}")

        if skipped_no_cap:
            print(f"\n  ⚠️  跳过 {skipped_no_cap} 只（无流通市值数据）")

        # ── 10. 对比交集 ───────────────────────────────────
        m1_top5 = set(r["ts_code"] for r in method1_results[:N])
        m2_top5 = set(r["ts_code"] for r in method2_results[:N])
        common = m1_top5 & m2_top5
        only_m1 = m1_top5 - m2_top5
        only_m2 = m2_top5 - m1_top5

        print()
        print("=" * 70)
        print("  🔀 两种方法对比")
        print("=" * 70)
        print(f"  共同推荐: {len(common)} 只")
        if common:
            for ts_code in common:
                info = ts_code_to_info.get(ts_code, {})
                m1_rank = next(i for i, r in enumerate(method1_results, 1) if r["ts_code"] == ts_code)
                m2_rank = next(i for i, r in enumerate(method2_results, 1) if r["ts_code"] == ts_code)
                print(f"    {ts_code} {info.get('name', '')} — 方法1第{m1_rank}名 / 方法2第{m2_rank}名")
        print(f"  仅方法1推荐: {len(only_m1)} 只")
        if only_m1:
            for ts_code in only_m1:
                info = ts_code_to_info.get(ts_code, {})
                m1_rank = next(i for i, r in enumerate(method1_results, 1) if r["ts_code"] == ts_code)
                print(f"    {ts_code} {info.get('name', '')} — 方法1第{m1_rank}名")
        print(f"  仅方法2推荐: {len(only_m2)} 只")
        if only_m2:
            for ts_code in only_m2:
                info = ts_code_to_info.get(ts_code, {})
                m2_rank = next(i for i, r in enumerate(method2_results, 1) if r["ts_code"] == ts_code)
                print(f"    {ts_code} {info.get('name', '')} — 方法2第{m2_rank}名")

        print()
        print("✅ 完成")

    finally:
        session.close()


if __name__ == "__main__":
    main()
