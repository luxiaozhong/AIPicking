#!/usr/bin/env python3
"""
每日数据同步总调度 — 按依赖顺序串行执行所有同步任务

用法：
    venv/bin/python scripts/sync_all.py                    # 默认模式
    venv/bin/python scripts/sync_all.py --date 2026-06-04  # 指定日期
    venv/bin/python scripts/sync_all.py --dry-run          # 仅打印不执行

cron（每个交易日 17:30）：
    30 17 * * 1-5 cd /opt/AIpicking/backend && venv/bin/python scripts/sync_all.py >> /var/log/aipicking/sync_all.log 2>&1
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PYTHON = str(Path(__file__).resolve().parent.parent / "venv" / "bin" / "python")

# sync_report.py 读取的日线日志
_UPDATE_DAILY_LOG = SCRIPT_DIR.parent.parent / "logs" / "update_daily.log"
# 服务器路径（cron 环境）
_SERVER_LOG = Path("/var/log/aipicking/update_daily.log")
# 结构化摘要输出（供 sync_report.py 消费）
# 优先用项目目录（本地可写），服务器上 /var/log/aipicking 存在且可写时用服务器路径
def _find_summary_dir() -> Path:
    """Pick a writable directory for sync_summary.json."""
    for candidate in (_UPDATE_DAILY_LOG.parent, _SERVER_LOG.parent):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            if candidate.is_dir() and os.access(candidate, os.W_OK):
                return candidate
        except (OSError, PermissionError):
            continue
    return _UPDATE_DAILY_LOG.parent  # 最后的 fallback
_SUMMARY_DIR = _find_summary_dir()
_SUMMARY_FILE = _SUMMARY_DIR / "sync_summary.json"

# 按依赖顺序排列：日线 → 指数 → 估值 → 市场信号 → 日报
JOBS = [
    {
        "script": "update_daily.py",
        "desc": "日线数据 + 市值",
        "log_key": "update_daily",
        "force_today": True,  # 盘后始终拉历史数据，防止被盘中实时数据 count 误导 skip
    },
    {
        "script": "update_index_daily.py",
        "desc": "指数日线",
        "log_key": "update_index_daily",
        "force_today": True,
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
        "script": "sync_stock_fund_flow.py",
        "desc": "个股资金流向",
        "log_key": "stock_fund_flow",
    },
    {
        "script": "update_mainflow_index.py",
        "desc": "主力资金50指数",
        "log_key": "mainflow_index",
    },
    {
        "script": "sync_market_temperature.py",
        "desc": "市场温度计算",
        "log_key": "market_temperature",
    },
    {
        "script": "sync_report.py",
        "desc": "数据同步日报",
        "log_key": "report",
    },
]


def run_job(script: str, date_arg: Optional[str],
            force_today: bool = False) -> Tuple[bool, float, str]:
    """运行单个同步脚本，返回 (成功, 耗时秒, stdout)

    force_today: 盘后 cron 默认模式下传 --date today，确保不因 count 检查而跳过。
                 但显式传入 date_arg（手动补历史）时，date_arg 优先。
    """
    cmd = [PYTHON, str(SCRIPT_DIR / script)]
    if date_arg:
        cmd.extend(["--date", date_arg])
    elif force_today:
        cmd.extend(["--date", "today"])

    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    elapsed = time.time() - start
    stdout = result.stdout

    if result.returncode != 0:
        print(f"  ✗ 失败 (exit={result.returncode})")
        if result.stderr:
            print(f"  stderr: {result.stderr.strip()[-500:]}")
        return False, elapsed, stdout
    else:
        print(f"  ✓ 完成 ({elapsed:.1f}s)")
        # 打印最后几行输出
        lines = stdout.strip().split("\n")
        for line in lines[-5:]:
            if line.strip():
                print(f"    {line.strip()}")
        return True, elapsed, stdout


def _extract_trade_date_from_stdout(stdout: str) -> Optional[str]:
    """从脚本 stdout 中提取实际同步的交易日期（YYYYMMDD）。

    优先级：
    1. 历史日线模式的 end_date：🚀 历史日线模式：20260715 ~ 20260715
    2. 日期标记：📅 盘后更新今天(20260715)
    3. 实时更新日期：📅 今天(20260715)无数据 / ✅ 今天(20260715)已有
    """
    # 历史日线模式：start ~ end
    m = re.search(r"🚀 历史日线模式：(\d{8}) ~ (\d{8})", stdout)
    if m:
        return m.group(2)  # end_date
    # 日期标记（盘后更新今天）
    m = re.search(r"📅 盘后更新今天\((\d{8})\)", stdout)
    if m:
        return m.group(1)
    # 实时更新相关日期
    m = re.search(r"📅 今天\((\d{8})\)", stdout)
    if m:
        return m.group(1)
    # 最近交易日
    m = re.search(r"📅 最近交易日\((\d{8})\)", stdout)
    if m:
        return m.group(1)
    return None


def parse_job_result(log_key: str, stdout: str, ok: bool, elapsed: float) -> Dict[str, Any]:
    """从 job stdout 中提取关键指标，返回结构化 dict。"""
    result: Dict[str, Any] = {"ok": ok, "elapsed_s": round(elapsed, 1)}

    if not ok:
        result["error"] = stdout.strip()[-200:] if stdout.strip() else "unknown"
        return result

    out = stdout

    # ── update_daily ──
    if log_key == "update_daily":
        # 提取实际同步的交易日
        trade_date = _extract_trade_date_from_stdout(out)
        if trade_date:
            result["trade_date"] = trade_date

        # 🎉 历史更新完成！新增/覆盖 X 条数据
        m = re.search(r"🎉 历史更新完成！新增/覆盖 ([\d,]+) 条", out)
        if m:
            result["records"] = int(m.group(1).replace(",", ""))
            result["mode"] = "history"
        else:
            m = re.search(r"📊 历史更新完成！跳过 — 已有 ([\d,]+) 条", out)
            if m:
                result["records"] = int(m.group(1).replace(",", ""))
                result["mode"] = "skip"
            else:
                m = re.search(r"🎉 实时更新完成！成功 ([\d,]+) 只", out)
                if m:
                    result["records"] = int(m.group(1))
                    result["mode"] = "intraday"
                else:
                    result["mode"] = "unknown"
        # qt 兜底数量
        m = re.search(r"📊 qt 兜底 ([\d,]+) 只", out)
        if m:
            result["qt_fallback"] = int(m.group(1).replace(",", ""))

    # ── update_index_daily ──
    elif log_key == "update_index_daily":
        # 提取实际同步的交易日
        trade_date = _extract_trade_date_from_stdout(out)
        if trade_date:
            result["trade_date"] = trade_date

        m = re.search(r"🎉 历史更新完成！新增/覆盖 ([\d,]+) 条指数数据", out)
        if m:
            result["records"] = int(m.group(1).replace(",", ""))
            result["mode"] = "history"
        else:
            m = re.search(r"📊 指数历史更新完成！跳过 — 已有 ([\d,]+) 条", out)
            if m:
                result["records"] = int(m.group(1).replace(",", ""))
                result["mode"] = "skip"
            else:
                m = re.search(r"🎉 实时更新完成！成功 ([\d,]+)/4 个指数", out)
                if m:
                    result["records"] = int(m.group(1))
                    result["mode"] = "intraday"
                else:
                    result["mode"] = "unknown"

    # ── dragon_tiger ──
    elif log_key == "dragon_tiger":
        m = re.search(r"Saved (\d+) dragon tiger stocks", out)
        if m:
            result["count"] = int(m.group(1))
        else:
            m = re.search(r"No dragon tiger data", out)
            if m:
                result["count"] = 0
                result["note"] = "非交易日或数据未发布"

    # ── valuation ──
    elif log_key == "valuation":
        m = re.search(r"✅ 完成！\S+ 写入 ([\d,]+) 条估值数据", out)
        if m:
            result["count"] = int(m.group(1).replace(",", ""))
        else:
            # 可能被跳过
            m = re.search(r"不是交易日.*跳过", out)
            if m:
                result["count"] = 0
                result["note"] = "非交易日，跳过"

    # ── market_data ──
    elif log_key == "market_data":
        m = re.search(
            r"Sync \S+ complete: stocks=(\d+) themes=(\d+) northbound=(\S+) industries=(\d+) concepts=(\d+)",
            out,
        )
        if m:
            result["hot_stocks"] = int(m.group(1))
            result["themes"] = int(m.group(2))
            result["northbound"] = m.group(3)
            result["industries"] = int(m.group(4))
            result["concepts"] = int(m.group(5))

    # ── stock_fund_flow ──
    elif log_key == "stock_fund_flow":
        m = re.search(r"成功写入:\s+([\d,]+)", out)
        if m:
            result["saved"] = int(m.group(1).replace(",", ""))
        m = re.search(r"成功批次:\s+([\d,]+)", out)
        if m:
            result["batches_ok"] = int(m.group(1).replace(",", ""))
        m = re.search(r"失败批次:\s+([\d,]+)", out)
        if m:
            result["batches_fail"] = int(m.group(1).replace(",", ""))

    # ── mainflow_index ──
    elif log_key == "mainflow_index":
        m = re.search(r"✅ 主力资金50 更新完成：([\d,]+) 只成分股", out)
        if m:
            result["count"] = int(m.group(1).replace(",", ""))
            result["status"] = "updated"
        else:
            m = re.search(r"⏭ 非调仓日，已跳过", out)
            if m:
                result["count"] = 0
                result["status"] = "skipped"
                result["note"] = "非调仓日"

    # ── market_temperature ──
    elif log_key == "market_temperature":
        m = re.search(r"得分: (\d+) \(([^)]+)\)", out)
        if m:
            result["score"] = int(m.group(1))
            result["level"] = m.group(2)
        # 细分
        m = re.search(r"指数跌幅: ([\d/]+)\s+波动率: ([\d/]+)\s+跌停潮: ([\d/]+)\s+下跌广度: ([\d/]+)\s+北向出逃: ([\d/]+)", out)
        if m:
            result["details"] = {
                "index_decline": m.group(1),
                "volatility": m.group(2),
                "limit_down": m.group(3),
                "breadth": m.group(4),
                "northbound_outflow": m.group(5),
            }

    # ── report ──
    elif log_key == "report":
        m = re.search(r"✅ 邮件已发送至 (\S+)", out)
        if m:
            result["email_sent"] = True
            result["email_to"] = m.group(1)
        else:
            result["email_sent"] = False

    return result


def _write_report_marker():
    """向 update_daily.log 写入日期标记，确保 sync_report.py 能找到最新同步日期。"""
    today = datetime.now().strftime("%Y%m%d")
    marker = f"📅 盘后更新今天({today})"
    for log_path in (_SERVER_LOG, _UPDATE_DAILY_LOG):
        try:
            if log_path.parent.exists():
                with open(log_path, "a") as f:
                    f.write(f"{marker}  # sync_all\n")
                break
        except (OSError, PermissionError):
            continue


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
    jobs_results: Dict[str, Any] = {}

    for i, job in enumerate(JOBS, 1):
        log_key = job["log_key"]
        if log_key in args.skip:
            print(f"\n[{i}/{len(JOBS)}] {job['script']} — {job['desc']} [跳过]")
            continue

        print(f"\n[{i}/{len(JOBS)}] {job['script']} — {job['desc']}")
        ok, elapsed, stdout = run_job(job["script"], date_arg,
                                      force_today=job.get("force_today", False))
        if ok:
            total_ok += 1
        else:
            total_fail += 1

        # Parse structured result for sync_report.py
        jobs_results[log_key] = parse_job_result(log_key, stdout, ok, elapsed)
        jobs_results[log_key]["desc"] = job["desc"]

    total_elapsed = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"  完成: {total_ok} 成功, {total_fail} 失败, 总耗时 {total_elapsed:.1f}s")
    print(f"{'='*60}")

    # 在 update_daily.log 写入日期标记，确保 sync_report.py 能识别最新同步日期
    _write_report_marker()

    # 写入结构化摘要 JSON（供 sync_report.py 消费）
    # date 优先取 update_daily 实际同步的交易日，其次 update_index_daily，最后用系统日期
    ud_result = jobs_results.get("update_daily", {})
    idx_result = jobs_results.get("update_index_daily", {})
    sync_date = ud_result.get("trade_date") or idx_result.get("trade_date") or datetime.now().strftime("%Y%m%d")
    summary = {
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": sync_date,
        "total_ok": total_ok,
        "total_fail": total_fail,
        "total_elapsed_s": round(total_elapsed, 1),
        "jobs": jobs_results,
    }
    try:
        _SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SUMMARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"\n📋 摘要已写入 {_SUMMARY_FILE}")
    except (OSError, PermissionError) as e:
        print(f"\n⚠️ 无法写入摘要文件: {e}")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
