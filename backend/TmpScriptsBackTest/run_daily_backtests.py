#!/usr/bin/env python3
"""
一键触发四个核心策略的简单回测（2026-06-04 当日）并输出结果。

用法：
    cd backend && source venv/bin/activate
    python TmpScriptsBackTest/run_daily_backtests.py              # 今天
    python TmpScriptsBackTest/run_daily_backtests.py 2026-06-05   # 指定日期
    python TmpScriptsBackTest/run_daily_backtests.py --wait       # 等待完成后打印摘要

依赖：后端需在 localhost:8000 运行，且 venv 中已安装 requests。
"""

import argparse
import json
import sys
import time
from datetime import date, datetime
from urllib.request import Request, urlopen
from urllib.error import URLError

API = "http://localhost:8000/api/v1"
STRATEGY_NAMES = [
    "laoyatou",
    "Oversold Bounce",
    "Oversold Bounce SS",
    "Trend Upstart Flow",
]
TRACK_DAYS = [3, 7, 15]
POLL_INTERVAL = 5   # seconds between status checks
MAX_WAIT = 300       # max total wait seconds


# ── helpers ──────────────────────────────────────────────────────────────

def _req(method, path, body=None, token=None):
    """Minimal HTTP helper — no third-party deps beyond stdlib."""
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
            if s["name"] in STRATEGY_NAMES:
                name_to_id[s["name"]] = s["id"]
        if page >= resp.get("total", 0) // 100 + 1:
            break
        page += 1
    return name_to_id


def submit_backtest(token, strategy_id, strategy_name, cutoff_date):
    """提交异步回测，返回 backtest id。"""
    body = {
        "strategy_id": strategy_id,
        "cutoff_date": cutoff_date.replace("-", ""),
        "track_days": TRACK_DAYS,
    }
    bt = _req("POST", "/backtests", body=body, token=token)
    # POST /backtests 直接返回 backtest 对象
    print(f"  ✅ {strategy_name:<25s} 已提交  id={bt['id']}")
    return bt["id"]


def poll_backtest(token, bt_id):
    """轮询单个回测状态，返回 (status, data)。"""
    d = _req("GET", f"/backtests/{bt_id}", token=token)
    # GET /backtests/{id} 直接返回 backtest 对象
    return d["status"], d


# ── main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="一键触发四个核心策略简单回测"
    )
    parser.add_argument(
        "date", nargs="?", default=None,
        help="截止日期 YYYY-MM-DD（默认今天）",
    )
    parser.add_argument(
        "--wait", action="store_true",
        help="等待所有回测完成后打印摘要",
    )
    args = parser.parse_args()

    cutoff = args.date or date.today().strftime("%Y-%m-%d")
    print(f"📅 回测截止日: {cutoff}")
    print(f"📊 策略: {', '.join(STRATEGY_NAMES)}")
    print()

    # 1. 登录
    print("🔑 登录中...")
    token = login()

    # 2. 查找策略 ID
    name_to_id = find_strategy_ids(token)
    missing = [n for n in STRATEGY_NAMES if n not in name_to_id]
    if missing:
        print(f"❌ 未找到策略: {missing}")
        sys.exit(1)

    # 3. 提交回测
    print("🚀 提交回测...")
    bt_ids = {}  # id → name
    for name in STRATEGY_NAMES:
        sid = name_to_id[name]
        bid = submit_backtest(token, sid, name, cutoff)
        bt_ids[bid] = name

    if not args.wait:
        print()
        print("✅ 全部已提交，后端正在执行。去前端查看报告：")
        print("   http://localhost:5173")
        return

    # 4. 等待完成
    print()
    print(f"⏳ 等待完成（最长 {MAX_WAIT}s）...")
    pending = set(bt_ids)
    results = {}
    waited = 0
    while pending and waited < MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
        for bid in list(pending):
            status, data = poll_backtest(token, bid)
            if status in ("completed", "failed"):
                pending.discard(bid)
                results[bid] = data

    if pending:
        print(f"⚠️  超时未完成: {[bt_ids[b] for b in pending]}")

    # 5. 打印摘要
    print()
    print("=" * 70)
    print(f"  回测摘要 — {cutoff}")
    print("=" * 70)
    print(f"  {'策略':<25s} {'状态':<10s} {'选股':>4s}  {'胜率3d':>6s}  {'胜率7d':>6s}  {'胜率15d':>6s}")
    print("-" * 70)

    for name in STRATEGY_NAMES:
        data = None
        for bid, n in bt_ids.items():
            if n == name and bid in results:
                data = results[bid]
                break
        if data is None:
            print(f"  {name:<25s} {'未知':<10s}")
            continue

        status = data["status"]
        recs = data.get("recommendations") or []
        summary = data.get("summary") or {}
        n_picks = len(recs)

        def pct(k):
            v = summary.get(k, 0)
            return f"{v:.0%}" if v else "-"

        print(f"  {name:<25s} {status:<10s} {n_picks:>4d}  {pct('win_rate_3d'):>6s}  {pct('win_rate_7d'):>6s}  {pct('win_rate_15d'):>6s}")

        if recs:
            print(f"    ── 推荐股票 ──")
            for r in recs[:10]:
                ts = r.get("ts_code", "?")
                name_s = r.get("name", "")
                print(f"    {ts}  {name_s}")

    if any(data and data["status"] == "failed" for data in results.values()):
        print()
        print("⚠️  有回测失败，错误信息：")
        for bid, data in results.items():
            if data["status"] == "failed":
                print(f"  {bt_ids[bid]}: {data.get('error_message', '未知错误')}")

    print()
    print("📊 前端报告: http://localhost:5173")


if __name__ == "__main__":
    main()
