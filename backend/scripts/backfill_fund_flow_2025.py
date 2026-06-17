#!/usr/bin/env python3
"""
2025年个股资金流 backfill 脚本（断点续传）
============================================

逐日调用 sync_stock_fund_flow 的 sync() 函数，补全 2025 年缺失的 daily_stock_fund_flow 数据。
每完成一天写入进度文件，支持 Ctrl+C 中断后重启自动续传。

用法:
    cd backend && source venv/bin/activate
    python scripts/backfill_fund_flow_2025.py              # 自动从进度文件恢复
    python scripts/backfill_fund_flow_2025.py --reset      # 忽略进度，重新开始
    python scripts/backfill_fund_flow_2025.py --dry-run    # 仅打印计划

进度文件: backend/scripts/.backfill_fund_flow_2025_progress.json
日志文件: backend/scripts/backfill_fund_flow_2025.log
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Ensure we can import from backend ──────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

for _env_file in (".env", ".env.production"):
    _path = BACKEND_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)

from urllib.parse import urlparse
import psycopg2

# ── Paths ──────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROGRESS_FILE = SCRIPT_DIR / ".backfill_fund_flow_2025_progress.json"
LOG_FILE = SCRIPT_DIR / "backfill_fund_flow_2025.log"

# ── Config ─────────────────────────────────────────────────────────
YEAR_START = "2025-01-01"
YEAR_END = "2025-12-31"
# 每天同步大约需要 8 分钟（105 批 × ~4.5s），加上安全余量
ESTIMATED_MINUTES_PER_DAY = 9

# ── Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ── DB helpers ─────────────────────────────────────────────────────
def get_db_conn():
    """Get a psycopg2 connection using DATABASE_URL from env."""
    raw = os.environ["DATABASE_URL"]
    url = raw.replace("+asyncpg", "").replace("+psycopg2", "")
    if "://" not in url:
        url = f"postgresql://{url}"
    r = urlparse(url)
    return psycopg2.connect(
        host=r.hostname or "localhost",
        port=r.port or 5432,
        user=r.username or "aipicking",
        password=r.password or "",
        dbname=r.path.lstrip("/") or "aipicking",
    )


def get_missing_dates() -> list[str]:
    """Return sorted list of 2025 trading dates missing from daily_stock_fund_flow."""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        # All trading days from daily table
        cur.execute(
            "SELECT DISTINCT trade_date FROM daily "
            "WHERE trade_date >= %s AND trade_date <= %s ORDER BY trade_date",
            (YEAR_START, YEAR_END),
        )
        all_days = [r[0] for r in cur.fetchall()]

        # Days already in fund_flow
        cur.execute(
            "SELECT DISTINCT trade_date FROM daily_stock_fund_flow "
            "WHERE trade_date >= %s AND trade_date <= %s",
            (YEAR_START, YEAR_END),
        )
        done = set(r[0] for r in cur.fetchall())

        missing = [d for d in all_days if d not in done]
        logger.info(
            "2025年: %d 交易日, %d 已回补, %d 缺失",
            len(all_days), len(done), len(missing),
        )
        return missing
    finally:
        conn.close()


# ── Progress persistence ───────────────────────────────────────────
def load_progress() -> dict:
    """Load progress from JSON file. Returns {completed: [...], current: str|null, errors: [...]}."""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("进度文件损坏，从头开始")
    return {"completed": [], "current": None, "errors": [], "started_at": None}


def save_progress(progress: dict):
    """Write progress to JSON file."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


# ── Graceful shutdown ──────────────────────────────────────────────
_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.info("收到 %s 信号，完成当前日期后退出...", sig_name)
    _shutdown_requested = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── Main backfill logic ────────────────────────────────────────────
def run_backfill(dry_run: bool = False, reset: bool = False):
    """Main backfill loop."""
    # 1. Load/reset progress
    if reset:
        progress = {"completed": [], "current": None, "errors": [], "started_at": None}
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
        logger.info("进度已重置")
    else:
        progress = load_progress()

    if progress["started_at"] is None:
        progress["started_at"] = datetime.now().isoformat()

    # 2. Get missing dates
    missing = get_missing_dates()
    if not missing:
        logger.info("✅ 2025年资金流数据已完整，无需 backfill！")
        return

    # 3. Filter out already-completed dates
    completed_set = set(progress["completed"])
    remaining = [d for d in missing if d not in completed_set]

    if not remaining:
        logger.info("✅ 所有缺失日期已完成！(进度文件: %d 天)", len(completed_set))
        return

    total_remaining = len(remaining)
    estimated_hours = total_remaining * ESTIMATED_MINUTES_PER_DAY / 60

    logger.info("=" * 60)
    logger.info(
        "待回补: %d 天 (%s ~ %s)，预计耗时 %.1f 小时",
        total_remaining,
        remaining[0],
        remaining[-1],
        estimated_hours,
    )
    logger.info("已完成: %d 天，失败: %d 天", len(completed_set), len(progress["errors"]))
    logger.info("=" * 60)

    if dry_run:
        logger.info("[DRY RUN] 不会实际执行，仅打印前10天和后10天:")
        for d in remaining[:10]:
            logger.info("  [DRY RUN] %s", d)
        if len(remaining) > 10:
            logger.info("  ... %d 天省略 ...", len(remaining) - 20)
            for d in remaining[-10:]:
                logger.info("  [DRY RUN] %s", d)
        return

    # 4. Import sync function (lazy import so dry-run is fast)
    logger.info("加载 sync_stock_fund_flow 模块...")
    import importlib.util

    sync_path = BACKEND_DIR / "scripts" / "sync_stock_fund_flow.py"
    spec = importlib.util.spec_from_file_location("sync_stock_fund_flow", sync_path)
    sync_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync_mod)

    # 5. Loop over remaining dates
    overall_start = time.time()
    date_timings = []  # (date, elapsed_s)

    for idx, date_str in enumerate(remaining):
        if _shutdown_requested:
            logger.info("⚠️ 收到退出信号，已处理 %d/%d，进度已保存", idx, total_remaining)
            break

        day_num = idx + 1
        eta = ""
        if date_timings:
            avg_s = sum(t[1] for t in date_timings) / len(date_timings)
            remaining_s = avg_s * (total_remaining - idx)
            eta = f" | 预计剩余 {remaining_s/3600:.1f}h"

        logger.info(
            "━━━ [%d/%d] %s ━━━%s",
            day_num, total_remaining, date_str, eta,
        )
        progress["current"] = date_str
        save_progress(progress)

        t0 = time.time()
        try:
            result = sync_mod.sync(date_str=date_str)
            elapsed = time.time() - t0

            if result["total_saved"] > 0:
                progress["completed"].append(date_str)
                date_timings.append((date_str, elapsed))
                logger.info(
                    "✅ %s: %d 行写入, %.0fs (%d/%d 批次成功)",
                    date_str,
                    result["total_saved"],
                    elapsed,
                    result["success_batches"],
                    result["batches"],
                )
            else:
                # No data saved — could be a holiday or non-trading day
                # Mark as completed anyway (API returned empty)
                progress["completed"].append(date_str)
                date_timings.append((date_str, elapsed))
                logger.warning(
                    "⚠️ %s: 0 行写入 (可能是假日或API无数据), %.0fs",
                    date_str, elapsed,
                )

        except Exception as e:
            elapsed = time.time() - t0
            progress["errors"].append({"date": date_str, "error": str(e)})
            logger.error("❌ %s: %s (%.0fs)", date_str, e, elapsed)

        progress["current"] = None
        save_progress(progress)

    # 6. Final report
    overall_elapsed = time.time() - overall_start
    logger.info("=" * 60)
    logger.info("Backfill 结束")
    logger.info("  本轮完成: %d 天", len([d for d in remaining if d in progress["completed"]]))
    logger.info("  累计完成: %d 天", len(progress["completed"]))
    logger.info("  失败:     %d 天", len(progress["errors"]))
    logger.info("  总耗时:   %.1f 分钟 (%.1f 小时)", overall_elapsed / 60, overall_elapsed / 3600)

    if progress["errors"]:
        logger.info("  失败列表:")
        for e in progress["errors"]:
            logger.info("    - %s: %s", e["date"], e["error"][:100])

    remaining_after = len(missing) - len(progress["completed"])
    if remaining_after > 0:
        logger.info("  剩余: %d 天，重新运行脚本即可续传", remaining_after)
    else:
        logger.info("  🎉 2025年全部回补完成！")
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
            logger.info("  进度文件已清理")

    logger.info("=" * 60)


# ── CLI ────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="2025年个股资金流 backfill（断点续传）")
    p.add_argument("--reset", action="store_true", help="忽略进度文件，重新开始")
    p.add_argument("--dry-run", action="store_true", help="仅打印计划，不执行")
    args = p.parse_args()

    logger.info("Backfill 脚本启动")
    run_backfill(dry_run=args.dry_run, reset=args.reset)


if __name__ == "__main__":
    main()
