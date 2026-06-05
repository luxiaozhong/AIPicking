#!/usr/bin/env python3
"""
每日数据同步总调度 — 按依赖顺序串行执行所有同步任务

用法：
    venv/bin/python scripts/sync_all.py                    # 默认模式
    venv/bin/python scripts/sync_all.py --date 2026-06-04  # 指定日期
    venv/bin/python scripts/sync_all.py --dry-run          # 仅打印不执行

cron（每个交易日 16:15）：
    15 16 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_all.py >> /var/log/aipicking/sync_all.log 2>&1
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PYTHON = str(Path(__file__).resolve().parent.parent / "venv" / "bin" / "python")

# 按依赖顺序排列：日线 → 指数 → 龙虎榜 → 估值 → 市场信号 → 日报
JOBS = [
    {
        "script": "update_daily.py",
        "desc": "日线数据 + 市值",
        "log_key": "update_daily",
    },
    {
        "script": "update_index_daily.py",
        "desc": "指数日线",
        "log_key": "update_index_daily",
    },
    {
        "script": "sync_dragon_tiger.py",
        "desc": "龙虎榜",
        "log_key": "dragon_tiger",
    },
    {
        "script": "sync_valuation.py",
        "desc": "估值数据 PE/PB",
        "log_key": "valuation",
    },
    {
        "script": "sync_market_data.py",
        "desc": "市场信号",
        "log_key": "market_data",
    },
    {
        "script": "sync_report.py",
        "desc": "数据同步日报",
        "log_key": "report",
    },
]


def run_job(script: str, date_arg: str | None) -> tuple[bool, float]:
    """运行单个同步脚本，返回 (成功, 耗时秒)"""
    cmd = [PYTHON, str(SCRIPT_DIR / script)]
    if date_arg:
        cmd.extend(["--date", date_arg])

    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"  ✗ 失败 (exit={result.returncode})")
        if result.stderr:
            print(f"  stderr: {result.stderr.strip()[-500:]}")
        return False, elapsed
    else:
        print(f"  ✓ 完成 ({elapsed:.1f}s)")
        # 打印最后几行输出
        lines = result.stdout.strip().split("\n")
        for line in lines[-5:]:
            if line.strip():
                print(f"    {line.strip()}")
        return True, elapsed


def main():
    parser = argparse.ArgumentParser(description="每日数据同步总调度")
    parser.add_argument("--date", type=str, help="指定日期 YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="仅打印任务列表，不执行")
    parser.add_argument("--skip", type=str, nargs="*", default=[],
                        choices=[j["log_key"] for j in JOBS],
                        help="跳过的任务（按 log_key）")
    args = parser.parse_args()

    # 默认昨天（因为盘后同步的是上一个交易日的数据）
    if args.date:
        date_arg = args.date
        date_str = date_arg
    else:
        # 不传 --date，让各脚本自行决定默认日期
        date_arg = None
        date_str = "（各脚本默认）"

    print(f"{'='*60}")
    print(f"  数据同步总调度 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  日期: {date_str}")
    if args.skip:
        print(f"  跳过: {', '.join(args.skip)}")
    print(f"  共 {len(JOBS)} 个任务")
    print(f"{'='*60}")

    if args.dry_run:
        print("\n[Dry-run] 将按以下顺序执行：")
        for i, job in enumerate(JOBS, 1):
            skipped = job["log_key"] in args.skip
            marker = " (跳过)" if skipped else ""
            print(f"  {i}. {job['script']} — {job['desc']}{marker}")
        return

    total_ok = 0
    total_fail = 0
    total_start = time.time()

    for i, job in enumerate(JOBS, 1):
        if job["log_key"] in args.skip:
            print(f"\n[{i}/{len(JOBS)}] {job['script']} — {job['desc']} [跳过]")
            continue

        print(f"\n[{i}/{len(JOBS)}] {job['script']} — {job['desc']}")
        ok, elapsed = run_job(job["script"], date_arg)
        if ok:
            total_ok += 1
        else:
            total_fail += 1

    total_elapsed = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"  完成: {total_ok} 成功, {total_fail} 失败, 总耗时 {total_elapsed:.1f}s")
    print(f"{'='*60}")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
