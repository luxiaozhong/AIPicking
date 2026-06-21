#!/usr/bin/env python3
"""
主力资金50指数 — 每周五盘后更新成分股（节假日顺延）

从 daily_stock_fund_flow 表中聚合全市场 A 股最近 15 个交易日的
main_net_flow（主力净流入）总和，排除 ST/*ST/次新股/北交所，
取 Top 50 等权写入 index_constituents 表。

依赖：sync_stock_fund_flow.py 必须先跑完（全市场资金流入 daily_stock_fund_flow）。

Usage:
    cd backend && source venv/bin/activate

    # 默认：自动取最近交易日
    python scripts/update_mainflow_index.py

    # 指定日期
    python scripts/update_mainflow_index.py --date 2026-06-16

    # Dry-run：预览 Top 50 不写入
    python scripts/update_mainflow_index.py --dry-run

    # 自定义成分股数量
    python scripts/update_mainflow_index.py --top 30

Cron（通过 sync_all.py 统一调度，无需单独 cron）:
    30 17 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_all.py
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# ── Load .env (dev) then .env.production (server override) ──────────────
_ENV_DIR = Path(__file__).resolve().parent.parent  # backend/
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)


# ═════════════════════════════════════════════════════════════════════════
# PostgreSQL connection
# ═════════════════════════════════════════════════════════════════════════

def _parse_pg_url(url: str) -> dict:
    url = url.replace("+asyncpg", "").replace("+psycopg2", "")
    if "://" not in url:
        url = f"postgresql://{url}"
    r = urlparse(url)
    return {
        "host": r.hostname or "localhost",
        "port": r.port or 5432,
        "user": r.username or "aipicking",
        "password": r.password or "",
        "dbname": r.path.lstrip("/") or "aipicking",
    }


_default_db = os.getenv("DATABASE_URL", "")
if not _default_db:
    _user = os.getenv("DB_USER", "aipicking")
    _pass = os.getenv("DB_PASSWORD", "")
    _host = os.getenv("DB_HOST", "localhost")
    _port = os.getenv("DB_PORT", "5432")
    _name = os.getenv("DB_NAME", "aipicking")
    _default_db = f"postgresql://{_user}:{_pass}@{_host}:{_port}/{_name}"
_PG_PARAMS = _parse_pg_url(_default_db)


def get_conn():
    return psycopg2.connect(**_PG_PARAMS)


# ═════════════════════════════════════════════════════════════════════════
# Constants
# ═════════════════════════════════════════════════════════════════════════

INDEX_CODE = "900001"
INDEX_NAME = "主力资金50"
FULL_NAME = "主力资金50指数"
PUBLISHER = "自定义"
DATA_SOURCE = "custom.main_flow_15d"
DEFAULT_TOP_N = 50
LOOKBACK_DAYS = 15          # 滚动交易日数
MIN_LIST_DAYS = 60          # 上市最少自然日
EQUAL_WEIGHT = 2.0          # 等权 2%

# ── 节假日（与 update_daily.py 保持一致）─────────────────────────────
HOLIDAYS = {
    2024: {"0101", "0210", "0211", "0212", "0213", "0214", "0215", "0216", "0217",
           "0404", "0405", "0406", "0501", "0502", "0503", "0504", "0505",
           "0608", "0609", "0610", "0929", "0930", "1001", "1002", "1003",
           "1004", "1005", "1006", "1007"},
    2025: {"0101", "0128", "0129", "0130", "0131", "0203", "0204",
           "0404", "0405", "0406", "0501", "0502", "0503", "0504", "0505",
           "0531", "0601", "0602", "1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008"},
    2026: {"0101", "0217", "0218", "0219", "0220", "0221", "0222", "0223",
           "0405", "0406", "0407", "0501", "0502", "0503", "0504", "0505",
           "0625", "0626", "0627", "0929", "0930", "1001", "1002", "1003", "1004", "1005", "1006", "1007"},
}

BUFFER_KICK_RANK = 55       # 持仓排名 > 此值则强制踢出
BUFFER_ENTER_RANK = 45      # 未持仓排名 ≤ 此值则优先纳入
RANKING_LIMIT = 60          # 计算排名时取 top 60（>= BUFFER_KICK_RANK）

MA_PERIOD = 20              # 均线周期
MAX_5D_GAIN = 0.15          # 5日最大涨幅（15%）


def is_trade_day(date_str: str) -> bool:
    """判断是否为交易日，输入 YYYYMMDD 或 YYYY-MM-DD"""
    date_str = date_str.replace("-", "")
    d = datetime.strptime(date_str, "%Y%m%d")
    if d.weekday() >= 5:
        return False
    mmdd = d.strftime("%m%d")
    year = d.year
    if year in HOLIDAYS and mmdd in HOLIDAYS[year]:
        return False
    return True


def get_latest_trade_day() -> str:
    """获取最近一个交易日（含今天），返回 YYYY-MM-DD"""
    now = datetime.now()
    for _ in range(10):
        ds = now.strftime("%Y%m%d")
        if is_trade_day(ds):
            return f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"
        now -= timedelta(days=1)
    raise RuntimeError("无法找到最近交易日")


def is_rebalance_day(date_str: str) -> bool:
    """判断 date_str 是否为调仓日。

    规则：最近一个周五（含当日），如果周五是节假日则顺延到下一交易日。

    Args:
        date_str: YYYY-MM-DD 格式日期

    Returns:
        True 如果当天是调仓日
    """
    d = datetime.strptime(date_str, "%Y-%m-%d")

    # 1. 找最近一个周五
    days_since_friday = (d.weekday() - 4) % 7
    last_friday = d - timedelta(days=days_since_friday)
    last_friday_key = last_friday.strftime("%Y%m%d")

    # 2. 最近周五是交易日 且 今天就是那个周五 → 调仓日
    if is_trade_day(last_friday_key) and d == last_friday:
        return True

    # 3. 最近周五是节假日 → 找顺延后的第一个交易日
    if not is_trade_day(last_friday_key):
        next_day = last_friday + timedelta(days=1)
        for _ in range(7):
            if is_trade_day(next_day.strftime("%Y%m%d")):
                return d == next_day  # 今天就是顺延日
            next_day += timedelta(days=1)

    return False


def get_lookback_trade_dates(conn, end_date: str, n: int = LOOKBACK_DAYS) -> list[str]:
    """从 daily 表中取最近 N 个有日线数据的交易日（降序），返回 YYYY-MM-DD 列表。"""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT trade_date FROM daily
            WHERE trade_date <= %s
            ORDER BY trade_date DESC
            LIMIT %s
            """,
            (end_date, n),
        )
        rows = cur.fetchall()
    dates = [r[0] for r in rows]
    logging.info("最近 %d 个交易日（截止 %s）: %s ... %s", len(dates), end_date,
                 dates[0] if dates else "N/A", dates[-1] if dates else "N/A")
    return dates


# ═════════════════════════════════════════════════════════════════════════
# Core logic
# ═════════════════════════════════════════════════════════════════════════

def compute_rankings(conn, trade_dates: list[str], limit: int = RANKING_LIMIT) -> list[dict]:
    """
    聚合最近 N 日主力净流入，返回排名列表（降序）。

    排除规则同 compute_top_stocks。

    Returns:
        [{ts_code, stock_name, flow_15d}, ...]  按 flow_15d 降序，最多 limit 条
    """
    if not trade_dates:
        logging.error("没有交易日数据，无法计算")
        return []

    min_list_date = (datetime.now() - timedelta(days=MIN_LIST_DAYS)).strftime("%Y%m%d")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                sff.ts_code,
                s.name AS stock_name,
                SUM(sff.main_net_flow) AS flow_15d
            FROM daily_stock_fund_flow sff
            JOIN stocks s ON s.ts_code = sff.ts_code
            WHERE sff.trade_date = ANY(%s)
              AND s.type = 'stock'
              AND s.name NOT LIKE '%%ST%%'
              AND sff.ts_code NOT LIKE '%%.BJ'
              AND (s.list_date IS NULL OR s.list_date = '' OR s.list_date <= %s)
            GROUP BY sff.ts_code, s.name
            HAVING SUM(sff.main_net_flow) > 0
            ORDER BY flow_15d DESC
            LIMIT %s
            """,
            (trade_dates, min_list_date, limit),
        )
        rows = cur.fetchall()

    stocks = [
        {
            "ts_code": r[0],
            "stock_name": r[1],
            "flow_15d": float(r[2]),
        }
        for r in rows
    ]

    if len(stocks) < limit:
        logging.warning(
            "符合条件的股票仅 %d 只（查询 limit=%d）—— 全市场主力净流入>0 的不足",
            len(stocks), limit,
        )
    else:
        logging.info("排名计算完成: %d 只，主力净流入范围: %.2f亿 ~ %.2f亿",
                     len(stocks),
                     stocks[-1]["flow_15d"] / 1e8,
                     stocks[0]["flow_15d"] / 1e8)

    return stocks


def get_current_holdings(conn) -> list[dict]:
    """读取最新一批成分股持仓。

    Returns:
        [{ts_code, stock_name, weight}, ...]，无历史持仓时返回空列表
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ts_code, stock_name, weight
            FROM index_constituents
            WHERE index_code = %s
              AND eff_date = (
                  SELECT MAX(eff_date) FROM index_constituents
                  WHERE index_code = %s
              )
            """,
            (INDEX_CODE, INDEX_CODE),
        )
        rows = cur.fetchall()
    holdings = [
        {"ts_code": r[0], "stock_name": r[1], "weight": float(r[2])}
        for r in rows
    ]
    if holdings:
        logging.info("当前持仓: %d 只（eff_date 最新批次）", len(holdings))
    else:
        logging.info("无历史持仓，将直接取 Top %d", DEFAULT_TOP_N)
    return holdings


def apply_buffer(rankings: list[dict], holdings: list[dict], top_n: int) -> list[dict]:
    """应用缓冲垫规则，返回最终成分股列表。

    规则：
      1. 持仓股中排名 ≤ BUFFER_KICK_RANK → 保留
      2. 持仓股中排名 > BUFFER_KICK_RANK 或不在排名中 → 踢出
      3. 未持仓股中排名 ≤ BUFFER_ENTER_RANK → 优先纳入
      4. 保留+纳入 < top_n → 从排名最高未持仓股中补满

    Args:
        rankings: 排名列表，index 0 = rank 1（已过滤趋势）
        holdings: 当前持仓列表
        top_n: 目标成分股数量

    Returns:
        [{ts_code, stock_name, flow_15d, weight}, ...]
    """
    holding_codes = {h["ts_code"] for h in holdings}
    ranking_by_code = {r["ts_code"]: r for r in rankings}

    # 1. 保留持仓中排名仍在 BUFFER_KICK_RANK 以内的
    keep = []
    kicked = []
    for h in holdings:
        if h["ts_code"] in ranking_by_code:
            # 查找排名位置（0-based）
            rank_pos = next(
                i for i, r in enumerate(rankings) if r["ts_code"] == h["ts_code"]
            )
            if rank_pos < BUFFER_KICK_RANK:
                keep.append(dict(ranking_by_code[h["ts_code"]]))
            else:
                kicked.append((h["ts_code"], rank_pos + 1))
        else:
            # 不在排名中（可能退市/停牌）→ 踢出
            kicked.append((h["ts_code"], None))

    if kicked:
        for code, rank in kicked:
            if rank:
                logging.info("  踢出: %s（排名 %d > %d）", code, rank, BUFFER_KICK_RANK)
            else:
                logging.info("  踢出: %s（不在排名中，可能退市/停牌）", code)
    logging.info("保留持仓: %d 只", len(keep))

    # 2. 优先纳入：未持仓中排名 ≤ BUFFER_ENTER_RANK
    priority_add = []
    for i, r in enumerate(rankings):
        if r["ts_code"] not in holding_codes and i < BUFFER_ENTER_RANK:
            priority_add.append(dict(r))
    logging.info("优先纳入: %d 只（排名 ≤ %d）", len(priority_add), BUFFER_ENTER_RANK)

    result = keep + priority_add
    result_codes = {r["ts_code"] for r in result}

    # 3. 补满到 top_n
    if len(result) < top_n:
        for r in rankings:
            if r["ts_code"] not in result_codes and r["ts_code"] not in holding_codes:
                result.append(dict(r))
                result_codes.add(r["ts_code"])
                if len(result) >= top_n:
                    break
        logging.info("补满: %d 只", len(result) - len(keep) - len(priority_add))

    # 4. 赋等权重
    for r in result:
        r["weight"] = EQUAL_WEIGHT

    logging.info("缓冲垫调整完成: 保留 %d + 纳入 %d → 最终 %d 只",
                 len(keep), len(result) - len(keep), len(result))

    return result[:top_n]


def apply_trend_filter(conn, ts_codes: list[str], end_date: str) -> set[str]:
    """批量趋势过滤，返回通过过滤的 ts_code 集合。

    两个条件（AND）：
      1. 收盘价 > 20日均线（基于最近 20 个交易日的 AVG(close)）
      2. 5日涨幅 < 15%（(close - close_5d_ago) / close_5d_ago）

    Args:
        conn: psycopg2 连接
        ts_codes: 待检查的股票代码列表
        end_date: 截止交易日 YYYY-MM-DD

    Returns:
        通过过滤的 ts_code 集合
    """
    if not ts_codes:
        return set()

    with conn.cursor() as cur:
        cur.execute(
            """
            WITH daily_window AS (
                SELECT
                    ts_code,
                    trade_date,
                    close,
                    AVG(close) OVER (
                        PARTITION BY ts_code ORDER BY trade_date
                        ROWS BETWEEN %s PRECEDING AND CURRENT ROW
                    ) AS ma,
                    LAG(close, %s) OVER (
                        PARTITION BY ts_code ORDER BY trade_date
                    ) AS close_5d_ago
                FROM daily
                WHERE ts_code = ANY(%s)
                  AND trade_date <= %s
            ),
            latest AS (
                SELECT DISTINCT ON (ts_code)
                    ts_code, close, ma, close_5d_ago
                FROM daily_window
                WHERE trade_date = (
                    SELECT MAX(trade_date) FROM daily_window
                    WHERE ts_code = daily_window.ts_code
                )
            )
            SELECT ts_code FROM latest
            WHERE close > ma
              AND close_5d_ago IS NOT NULL
              AND close_5d_ago > 0
              AND (close - close_5d_ago) / close_5d_ago < %s
            """,
            (MA_PERIOD - 1, 4, ts_codes, end_date, MAX_5D_GAIN),
        )
        passed = {r[0] for r in cur.fetchall()}

    failed = len(ts_codes) - len(passed)
    if failed:
        logging.info("趋势过滤: %d/%d 通过, %d 未通过（20MA或5日涨幅≥15%%）",
                     len(passed), len(ts_codes), failed)
    else:
        logging.info("趋势过滤: %d/%d 全部通过", len(passed), len(ts_codes))

    return passed


# ═════════════════════════════════════════════════════════════════════════
# Database upsert
# ═════════════════════════════════════════════════════════════════════════

def upsert_index_info(conn, eff_date: str, count: int) -> None:
    """幂等写入指数元数据到 index_info"""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO index_info (index_code, index_name, full_name, publisher,
                                    constituent_count, data_source, last_sync_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (index_code) DO UPDATE SET
                constituent_count = EXCLUDED.constituent_count,
                last_sync_date = EXCLUDED.last_sync_date,
                updated_at = NOW() AT TIME ZONE 'Asia/Shanghai'
            """,
            (INDEX_CODE, INDEX_NAME, FULL_NAME, PUBLISHER,
             count, DATA_SOURCE, eff_date),
        )
    conn.commit()
    logging.info("指数元数据已更新: %s (%s), %d 只成分股", FULL_NAME, INDEX_CODE, count)


def upsert_constituents(conn, stocks: list[dict], eff_date: str) -> int:
    """写入成分股到 index_constituents（保留历史 eff_date，可回溯）"""
    if not stocks:
        return 0

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO index_constituents (index_code, ts_code, stock_name,
                                            industry, market_cap, weight, eff_date)
            VALUES %s
            ON CONFLICT (index_code, ts_code, eff_date) DO UPDATE SET
                stock_name = EXCLUDED.stock_name,
                weight     = EXCLUDED.weight,
                market_cap = EXCLUDED.market_cap,
                updated_at = NOW() AT TIME ZONE 'Asia/Shanghai'
            """,
            [
                (INDEX_CODE, s["ts_code"], s["stock_name"],
                 "", s.get("flow_15d"), s["weight"], eff_date)
                for s in stocks
            ],
            template="(%s, %s, %s, %s, %s, %s, %s)",
        )
    conn.commit()
    logging.info("已写入 %d 条成分股记录（eff_date=%s）", len(stocks), eff_date)
    return len(stocks)


# ═════════════════════════════════════════════════════════════════════════
# Verify
# ═════════════════════════════════════════════════════════════════════════

def verify(conn, eff_date: str) -> None:
    """打印验证结果"""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ts_code, stock_name, weight::numeric(10,2),
                   ROUND(main_net_flow::numeric, 0) AS flow_wan
            FROM (
                SELECT ic.ts_code, ic.stock_name, ic.weight,
                       SUM(sff.main_net_flow) AS main_net_flow
                FROM index_constituents ic
                JOIN daily_stock_fund_flow sff
                  ON sff.ts_code = ic.ts_code
                 AND sff.trade_date IN (
                     SELECT DISTINCT trade_date FROM daily
                     WHERE trade_date <= %s
                     ORDER BY trade_date DESC
                     LIMIT %s
                 )
                WHERE ic.index_code = %s AND ic.eff_date = %s
                GROUP BY ic.ts_code, ic.stock_name, ic.weight
                ORDER BY main_net_flow DESC
            ) sub
            """,
            (eff_date, LOOKBACK_DAYS, INDEX_CODE, eff_date),
        )
        rows = cur.fetchall()
    if rows:
        logging.info("── 验证：Top 10 成分股 ──")
        for i, (code, name, weight, flow_wan) in enumerate(rows[:10], 1):
            logging.info("  %2d. %s %-8s 权重=%.1f%% 15日主力净流入=%s万",
                         i, code, name, weight, f"{flow_wan:,.0f}" if flow_wan else "N/A")
    logging.info("验证完成: %d 只成分股（eff_date=%s）", len(rows), eff_date)


# ═════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═════════════════════════════════════════════════════════════════════════

def run(eff_date: str, top_n: int = DEFAULT_TOP_N, dry_run: bool = False, force: bool = False) -> dict:
    """主流程"""
    conn = get_conn()
    try:
        # 0. 调仓日检查
        if not force and not is_rebalance_day(eff_date):
            logging.info("非调仓日（%s），跳过。可用 --force 强制运行", eff_date)
            return {"success": True, "mode": "skip", "reason": "not_rebalance_day", "eff_date": eff_date}

        # 1. 取最近 N 个交易日
        trade_dates = get_lookback_trade_dates(conn, eff_date, LOOKBACK_DAYS)
        if len(trade_dates) < 3:
            logging.error("交易日数据不足（仅 %d 天），无法计算滚动 %d 日",
                          len(trade_dates), LOOKBACK_DAYS)
            return {"success": False, "error": "insufficient_trade_days"}

        # 2. 计算排名
        rankings = compute_rankings(conn, trade_dates, RANKING_LIMIT)
        if not rankings:
            logging.error("无符合条件的股票")
            return {"success": False, "error": "no_qualified_stocks"}

        # 3. 获取当前持仓
        holdings = get_current_holdings(conn)

        # 4. 趋势过滤（仅对未持仓的候选股）
        holding_codes = {h["ts_code"] for h in holdings}
        candidate_codes = [
            r["ts_code"] for r in rankings if r["ts_code"] not in holding_codes
        ]
        if candidate_codes:
            passed_codes = apply_trend_filter(conn, candidate_codes, trade_dates[0])
        else:
            passed_codes = set()

        # 构建过滤后的排名列表：持仓股始终保留（不受趋势过滤影响）
        filtered_rankings = [
            r for r in rankings
            if r["ts_code"] in holding_codes or r["ts_code"] in passed_codes
        ]

        # 5. 应用缓冲垫
        if holdings:
            stocks = apply_buffer(filtered_rankings, holdings, top_n)
        else:
            # 首次运行：无历史持仓，直接取过滤后 Top N
            stocks = filtered_rankings[:top_n]
            for s in stocks:
                s["weight"] = EQUAL_WEIGHT
            logging.info("首次运行: 直接取过滤后 Top %d", len(stocks))

        if len(stocks) < top_n:
            logging.warning(
                "最终成分股仅 %d 只（目标 %d）—— 趋势过滤/缓冲垫后符合条件的不足",
                len(stocks), top_n,
            )

        if dry_run:
            logging.info("[DRY RUN] 不写入数据库")
            print("\n  排名 | 代码       | 名称       | 15日主力净流入(亿)")
            print("  " + "-" * 55)
            for i, s in enumerate(stocks, 1):
                print(f"  {i:>4} | {s['ts_code']:<10} | {s['stock_name']:<8} | {s['flow_15d']/1e8:>10.2f}")
            return {"success": True, "mode": "dry_run", "count": len(stocks)}

        # 6. 写入
        upsert_index_info(conn, eff_date, len(stocks))
        upsert_constituents(conn, stocks, eff_date)

        # 7. 验证
        verify(conn, eff_date)

        return {"success": True, "count": len(stocks), "eff_date": eff_date}

    finally:
        conn.close()


# ═════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="主力资金50指数 — 每周五盘后更新成分股（节假日顺延）")
    p.add_argument("--date", default=None,
                   help="生效日期 YYYY-MM-DD（默认: 盘后取最近交易日）")
    p.add_argument("--top", type=int, default=DEFAULT_TOP_N,
                   help=f"成分股数量（默认 {DEFAULT_TOP_N}）")
    p.add_argument("--dry-run", action="store_true",
                   help="仅预览 Top N，不写入数据库")
    p.add_argument("--force", action="store_true",
                   help="忽略调仓日检查，强制运行（用于回测补跑）")
    p.add_argument("--pg-url", default=None,
                   help="PostgreSQL 连接 URL（默认: $DATABASE_URL）")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    # Allow runtime override of PG connection
    if args.pg_url:
        global _PG_PARAMS
        _PG_PARAMS = _parse_pg_url(args.pg_url)

    # Determine effective date
    if args.date:
        eff_date = args.date.replace("-", "")
        eff_date = f"{eff_date[:4]}-{eff_date[4:6]}-{eff_date[6:8]}"
    else:
        eff_date = get_latest_trade_day()

    logging.info("主力资金50指数更新 — eff_date=%s top=%d", eff_date, args.top)

    # 指定 --date 时自动视为 force（允许在非周五回测）
    is_force = args.force or args.date is not None
    result = run(eff_date=eff_date, top_n=args.top, dry_run=args.dry_run, force=is_force)

    if result["success"]:
        if result.get("mode") == "skip":
            print(f"⏭ 非调仓日，已跳过（{result['eff_date']}）")
        elif result.get("mode") == "dry_run":
            print(f"\n✅ [DRY RUN] 预览完成：{result['count']} 只")
        else:
            print(f"\n✅ 主力资金50 更新完成：{result['count']} 只成分股（{result['eff_date']}）")
    else:
        print(f"\n❌ 失败: {result.get('error', 'unknown')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
