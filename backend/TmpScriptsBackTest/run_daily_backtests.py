#!/usr/bin/env python3
"""
一键串行触发四个核心策略的简单回测，逐个执行避免并发 OOM。

用法：
    cd backend && source venv/bin/activate
    python TmpScriptsBackTest/run_daily_backtests.py              # 今天，全部策略
    python TmpScriptsBackTest/run_daily_backtests.py 2026-06-05   # 指定日期
    python TmpScriptsBackTest/run_daily_backtests.py -q           # 安静模式
    python TmpScriptsBackTest/run_daily_backtests.py -s "Trend Upstart Flow"  # 仅单个策略

依赖：后端需在 localhost:8000 运行，仅使用 Python 标准库。
"""

import argparse
import json
import sys
import time
from datetime import date
from urllib.request import Request, urlopen
from urllib.error import URLError

API = "http://localhost:8000/api/v1"
ALL_STRATEGY_NAMES = [
    "laoyatou",
    "Oversold Bounce",
    "Oversold Bounce SS",
    "Trend Upstart Flow",
    "grow_with_money",
]
TRACK_DAYS = [3, 7, 15]
POLL_INTERVAL = 5    # seconds between status checks
MAX_WAIT = 600        # max seconds per backtest（Trend Upstart Flow 较慢）


# ── helpers ──────────────────────────────────────────────────────────────

def _req(method, path, body=None, token=None):
    """Minimal HTTP helper — stdlib only."""
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except URLError as e:
        print(f"❌ HTTP {method} {path} 失败: {e}")
        sys.exit(1)


def login():
    """用 admin 账号登录，返回 access_token。"""
    resp = _req("POST", "/auth/login", {"username": "admin", "password": "admin123"})
    return resp["data"]["access_token"]


def find_strategy_ids(token):
    """按名称查找四个策略的 ID（支持分页）。"""
    name_to_id = {}
    page = 1
    while True:
        resp = _req("GET", f"/strategies?limit=100&page={page}", token=token)
        items = resp.get("items", [])
        if not items:
            break
        for s in items:
            if s["name"] in ALL_STRATEGY_NAMES:
                name_to_id[s["name"]] = s["id"]
        if page >= resp.get("total", 0) // 100 + 1:
            break
        page += 1
    return name_to_id


def submit_one(token, strategy_id, name, cutoff_date):
    """提交单个异步回测，返回 backtest id。"""
    body = {
        "strategy_id": strategy_id,
        "cutoff_date": cutoff_date.replace("-", ""),
        "track_days": TRACK_DAYS,
    }
    bt = _req("POST", "/backtests", body=body, token=token)
    return bt["id"]


def wait_one(token, bt_id, name, quiet):
    """轮询直到单个回测完成，返回 backtest 对象。"""
    waited = 0
    while waited < MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
        d = _req("GET", f"/backtests/{bt_id}", token=token)
        status = d["status"]
        if status == "running":
            if not quiet and waited % 30 == 0:
                print(f"     …{name} 仍在执行 ({waited}s)")
            continue
        return d

    print(f"  ⚠️  {name} 超时 ({MAX_WAIT}s)，视为失败")
    return {"status": "timeout", "recommendations": None, "summary": None, "error_message": "timeout"}


# ── main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="一键串行触发四个核心策略简单回测"
    )
    parser.add_argument(
        "date", nargs="?", default=None,
        help="截止日期 YYYY-MM-DD（默认今天）",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="安静模式，只打印最终摘要",
    )
    parser.add_argument(
        "-s", "--strategy", action="append", default=None,
        help="只运行指定策略（可多次指定，如 -s 'Trend Upstart Flow'）。默认运行全部四个策略。",
    )
    args = parser.parse_args()

    cutoff = args.date or date.today().strftime("%Y-%m-%d")
    quiet = args.quiet

    # 确定要运行的策略列表
    if args.strategy:
        strategy_names = []
        for s in args.strategy:
            if s in ALL_STRATEGY_NAMES:
                strategy_names.append(s)
            else:
                print(f"⚠️  未知策略 '{s}'，已跳过。可选: {ALL_STRATEGY_NAMES}")
        if not strategy_names:
            print("❌ 没有有效的策略名称，退出。")
            sys.exit(1)
    else:
        strategy_names = list(ALL_STRATEGY_NAMES)

    print(f"📅 回测截止日: {cutoff}")
    print(f"📊 策略: {', '.join(strategy_names)}")
    print(f"🔁 模式: 串行（逐个执行，避免并发 OOM）")
    print()

    # 1. 登录
    if not quiet:
        print("🔑 登录中...")
    token = login()

    # 2. 查找策略 ID
    name_to_id = find_strategy_ids(token)
    missing = [n for n in strategy_names if n not in name_to_id]
    if missing:
        print(f"❌ 未找到策略: {missing}")
        sys.exit(1)

    # 3. 串行执行：提交一个 → 等待完成 → 提交下一个
    results = {}  # name → backtest dict

    for i, name in enumerate(strategy_names, 1):
        sid = name_to_id[name]
        print(f"[{i}/{len(strategy_names)}] 🚀 {name} ...", end=" ", flush=True)

        bid = submit_one(token, sid, name, cutoff)
        print(f"id={bid}", end="", flush=True)

        data = wait_one(token, bid, name, quiet)
        results[name] = data

        status = data["status"]
        recs = data.get("recommendations") or []
        n = len(recs)
        emoji = "✅" if status == "completed" else "❌"
        print(f" {emoji} {status} ({n} 选股)")

    # 4. 打印摘要
    print()
    print("=" * 74)
    print(f"  回测摘要 — {cutoff}")
    print("=" * 74)
    header = f"  {'策略':<25s} {'状态':<10s} {'选股':>4s}"
    print(header)
    print("-" * 74)

    for name in strategy_names:
        data = results.get(name)
        if data is None:
            print(f"  {name:<25s} {'未执行':<10s}")
            continue

        status = data["status"]
        recs = data.get("recommendations") or []
        n_picks = len(recs)
        print(f"  {name:<25s} {status:<10s} {n_picks:>4d}")

        if recs:
            stocks = ", ".join(
                f"{r.get('ts_code','?').split('.')[0]} {r.get('name','')}"
                for r in recs[:10]
            )
            print(f"    ── {stocks}")

    # 错误信息
    errors = [(n, d) for n, d in results.items() if d["status"] in ("failed", "timeout")]
    if errors:
        print()
        for n, d in errors:
            print(f"  ⚠️  {n}: {d.get('error_message', '未知错误')}")

    # 耗时统计
    print()
    print(f"✅ 全部完成。前端报告: http://localhost:5173")


if __name__ == "__main__":
    main()
