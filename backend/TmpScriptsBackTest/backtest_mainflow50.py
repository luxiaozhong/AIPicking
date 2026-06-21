#!/usr/bin/env python3
"""
主力资金50指数 — 回测脚本（Top N 买入持有 + 仅换出榜股票）

策略：
  - 每期按 flow_15d 排名取 Top N，等权买入
  - 已在持仓中且仍在前 N 的股票 不动（省交易成本）
  - 只卖出跌出前 N 的，只买入新进入前 N 的
  - 扣除交易费用（卖出 0.13%，买入 0.03%）

用法：
    cd backend && source venv/bin/activate
    python TmpScriptsBackTest/backtest_mainflow50.py              # 默认 Top 50
    python TmpScriptsBackTest/backtest_mainflow50.py --top 30     # Top 30
    python TmpScriptsBackTest/backtest_mainflow50.py --no-cost    # 不计费用
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# ── env ──────────────────────────────────────────────────────
_ENV_DIR = Path(__file__).resolve().parent.parent
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)


def _get_pg_conn():
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        db_url = (
            f"postgresql://{os.getenv('DB_USER','aipicking')}:"
            f"{os.getenv('DB_PASSWORD','')}@"
            f"{os.getenv('DB_HOST','localhost')}:"
            f"{os.getenv('DB_PORT','5432')}/"
            f"{os.getenv('DB_NAME','aipicking')}"
        )
    db_url = db_url.replace("+asyncpg", "").replace("+psycopg2", "")
    if "://" not in db_url:
        db_url = f"postgresql://{db_url}"
    r = urlparse(db_url)
    return psycopg2.connect(
        host=r.hostname or "localhost",
        port=r.port or 5432,
        user=r.username or "aipicking",
        password=r.password or "",
        dbname=r.path.lstrip("/") or "aipicking",
    )


# ══════════════════════════════════════════════════════════════
# Data loading
# ══════════════════════════════════════════════════════════════

def load_rebalance_dates(conn) -> list[str]:
    """Load all rebalance dates for 900001."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT eff_date FROM index_constituents "
            "WHERE index_code = '900001' ORDER BY eff_date"
        )
        return [r[0] for r in cur.fetchall()]


def load_trade_dates(conn, start: str, end: str) -> list[str]:
    """Load all trading days in range."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT trade_date FROM daily "
            "WHERE trade_date >= %s AND trade_date <= %s "
            "ORDER BY trade_date",
            (start, end),
        )
        return [r[0] for r in cur.fetchall()]


def load_constituents(conn, eff_date: str, top_n: int) -> list[dict]:
    """Load top N constituents for an eff_date, ranked by flow_15d."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ts_code, stock_name, market_cap AS flow_15d
            FROM index_constituents
            WHERE index_code = '900001' AND eff_date = %s
            ORDER BY market_cap DESC NULLS LAST
            LIMIT %s
            """,
            (eff_date, top_n),
        )
        return [
            {"ts_code": r[0], "stock_name": r[1], "flow_15d": float(r[2] or 0)}
            for r in cur.fetchall()
        ]


def load_prices(conn, codes: list[str], start: str, end: str) -> dict:
    """Load close prices: {date: {ts_code: close}}."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ts_code, trade_date, close FROM daily
            WHERE ts_code = ANY(%s) AND trade_date >= %s AND trade_date <= %s
            ORDER BY ts_code, trade_date
            """,
            (codes, start, end),
        )
        prices = {}
        for code, date, close in cur.fetchall():
            prices.setdefault(date, {})[code] = close
    return prices


def find_next_trade_day(trade_dates: list[str], target: str) -> Optional[str]:
    """First trading day >= target."""
    for td in trade_dates:
        if td >= target:
            return td
    return None


# ══════════════════════════════════════════════════════════════
# Simulation
# ══════════════════════════════════════════════════════════════

STAMP_TAX = 0.001   # 0.1%
COMMISSION = 0.0003  # 0.03%


def run_backtest(top_n: int = 50, include_cost: bool = True, detail: bool = False):
    conn = _get_pg_conn()
    try:
        # ── Load data ────────────────────────────────────────
        eff_dates = load_rebalance_dates(conn)
        print(f"加载 {len(eff_dates)} 个调仓日: {eff_dates[0]} ~ {eff_dates[-1]}")

        all_codes = set()
        constituents_by_date = {}
        for d in eff_dates:
            cs = load_constituents(conn, d, top_n)
            constituents_by_date[d] = cs
            for c in cs:
                all_codes.add(c["ts_code"])

        trade_dates = load_trade_dates(conn, eff_dates[0], eff_dates[-1])
        print(f"加载 {len(trade_dates)} 个交易日, {len(all_codes)} 只股票")

        prices = load_prices(conn, list(all_codes), eff_dates[0], eff_dates[-1])
        conn.close()
    except Exception as e:
        conn.close()
        raise

    # ── Simulate ─────────────────────────────────────────────
    nav = 1000.0
    holdings: dict[str, float] = {}  # {ts_code: shares}

    sell_cost_rate = STAMP_TAX + COMMISSION if include_cost else 0
    buy_cost_rate = COMMISSION if include_cost else 0

    # Header
    cost_label = "(含费用)" if include_cost else "(不含费用)"
    print(f"\n{'='*120}")
    print(f"  主力资金50 回测 — Top {top_n} 买入持有 {cost_label}")
    print(f"  规则: 每期等权买入 Top {top_n}，已在持仓且未跌出前 {top_n} 的股票不动（省换手）")
    print(f"{'='*120}")
    print(f"{'调仓日':<12} {'净值':>10} {'周收益':>8} {'持仓':>5} "
          f"{'保留':>5} {'卖出':>5} {'买入':>5} "
          f"{'换手%':>7} {'费用':>8} {'Top3':>30}")
    print(f"{'-'*120}")

    # Initial buy
    first_eff = eff_dates[0]
    buy_date = find_next_trade_day(trade_dates, first_eff)
    if not buy_date:
        print("ERROR: no trading day found for first rebalance")
        return

    day_px = prices.get(buy_date, {})
    targets = constituents_by_date[first_eff]
    n_target = len(targets)
    if n_target == 0:
        print("ERROR: no constituents on first date")
        return

    eq_weight = 1.0 / n_target
    total_invested = 0.0
    for s in targets:
        px = day_px.get(s["ts_code"], 0)
        if px and px > 0:
            shares = (nav * eq_weight) / px
            holdings[s["ts_code"]] = shares
            total_invested += shares * px

    nav = total_invested
    prev_nav = nav
    last_report_nav = nav  # for weekly return calc

    print(f"{first_eff:<12} {nav:>10.2f} {'—':>8} {len(holdings):>5} "
          f"{'—':>5} {'—':>5} {len(holdings):>5} "
          f"{'—':>7} {'—':>8} "
          f"{targets[0]['ts_code'].split('.')[0] if targets else '—'} "
          f"{targets[1]['ts_code'].split('.')[0] if len(targets)>1 else ''} "
          f"{targets[2]['ts_code'].split('.')[0] if len(targets)>2 else ''}")

    if detail:
        holdings_sorted = sorted(targets, key=lambda s: s["flow_15d"], reverse=True)
        codes_line = " ".join(
            f"{s['ts_code'].split('.')[0]}({s['flow_15d']/1e8:.1f}亿)"
            for s in holdings_sorted
        )
        print(f"           持仓详情: {codes_line}")

    last_report_nav = nav

    for i, eff_date in enumerate(eff_dates[1:], 1):
        rebal_date = find_next_trade_day(trade_dates, eff_date)
        if not rebal_date:
            print(f"  SKIP {eff_date}: no trading day")
            continue

        pre_px = prices.get(rebal_date, {})
        pre_nav = sum(
            holdings[c] * pre_px.get(c, 0)
            for c in holdings
            if pre_px.get(c, 0) > 0
        )
        if pre_nav == 0:
            print(f"  SKIP {eff_date}: zero NAV")
            continue

        targets = constituents_by_date[eff_date]
        target_codes = {s["ts_code"] for s in targets}
        old_codes = set(holdings.keys())

        sell_codes = old_codes - target_codes
        buy_codes = target_codes - old_codes
        keep_codes = old_codes & target_codes

        n_target = len(targets)
        eq_weight = 1.0 / n_target

        # 1) Sell removed stocks, pay sell cost
        sell_gross = 0.0
        for code in list(sell_codes):
            px = pre_px.get(code, 0)
            if px and px > 0:
                sell_gross += holdings[code] * px
            del holdings[code]
        sell_cost = sell_gross * sell_cost_rate
        sell_net = sell_gross - sell_cost

        # 2) Value of kept stocks
        kept_value = sum(
            holdings[c] * pre_px.get(c, 0)
            for c in keep_codes
            if pre_px.get(c, 0) > 0
        )

        # 3) Cash available for new buys
        available_cash = sell_net
        # Target: each holding should be worth portfolio * eq_weight
        # For kept stocks: their current value stays as-is (no rebalancing — "不动")
        # For new stocks: each gets (available_cash / len(buy_codes)), minus buy cost

        buy_cost_total = 0.0
        if buy_codes:
            n_buy = len(buy_codes)
            cash_per_buy = available_cash / n_buy  # gross allocation per new stock
            for code in buy_codes:
                px = pre_px.get(code, 0)
                if px and px > 0:
                    buy_cost = cash_per_buy * buy_cost_rate
                    shares = (cash_per_buy - buy_cost) / px
                    holdings[code] = shares
                    buy_cost_total += buy_cost

        # 4) Post-rebalance NAV
        nav = sum(
            holdings[c] * pre_px.get(c, 0)
            for c in holdings
            if pre_px.get(c, 0) > 0
        )

        # Stats
        trade_value = sell_gross + (available_cash if buy_codes else 0)
        turnover_pct = (trade_value / pre_nav * 100) if pre_nav > 0 else 0
        cost_total = sell_cost + buy_cost_total

        week_return = (nav / last_report_nav - 1) * 100 if last_report_nav > 0 else 0
        last_report_nav = nav

        top3 = targets[:3]
        top3_str = " ".join(s["ts_code"].split(".")[0] for s in top3)

        print(f"{eff_date:<12} {nav:>10.2f} {week_return:>7.2f}% {len(holdings):>5} "
              f"{len(keep_codes):>5} {len(sell_codes):>5} {len(buy_codes):>5} "
              f"{turnover_pct:>6.1f}% {cost_total:>8.2f} "
              f"{top3_str:<30}")

        if detail:
            # Print all holdings sorted by flow_15d
            holdings_sorted = sorted(targets, key=lambda s: s["flow_15d"], reverse=True)
            codes_line = " ".join(
                f"{s['ts_code'].split('.')[0]}({s['flow_15d']/1e8:.1f}亿)"
                for s in holdings_sorted
            )
            print(f"           持仓详情: {codes_line}")

    # ── Final line ──────────────────────────────────────────
    total_return = (nav / 1000 - 1) * 100
    weeks = len(eff_dates) - 1
    print(f"{'-'*120}")
    print(f"\n  📊 回测结果")
    print(f"  起始: {eff_dates[0]} = 1000.00")
    print(f"  截止: {eff_dates[-1]} = {nav:.2f}")
    print(f"  总收益: {total_return:+.2f}%")
    print(f"  调仓次数: {weeks}")
    print(f"  规则: 每期等权买入 Top {top_n}，持仓股未跌出前 {top_n} 则不动（省换手）")
    if include_cost:
        print(f"  费用: 卖出 {STAMP_TAX*100:.1f}%印花税 + {COMMISSION*100:.2f}%佣金，买入 {COMMISSION*100:.2f}%佣金")


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="主力资金50指数回测")
    p.add_argument("--top", type=int, default=50, help="Top N (default 50)")
    p.add_argument("--no-cost", action="store_true", help="不计交易费用")
    p.add_argument("--detail", action="store_true", help="每期显示全部持仓明细")
    args = p.parse_args()

    run_backtest(top_n=args.top, include_cost=not args.no_cost, detail=args.detail)


if __name__ == "__main__":
    main()
