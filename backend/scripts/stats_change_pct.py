"""按涨跌幅分桶统计 daily 表某交易日的全市场分布，并落盘保存以便后续对比。

用法:
    venv/bin/python scripts/stats_change_pct.py                 # 默认今天
    venv/bin/python scripts/stats_change_pct.py --date 2026-07-21
    venv/bin/python scripts/stats_change_pct.py --print         # 打印历史快照对比

数据存储: logs/change_pct_stats.json（按交易日建快照，可多次对比）
涨跌幅 = (close - pre_close) / pre_close * 100
"""
import argparse
import json
import os
import statistics
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import urlparse

import psycopg2

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
STORE_FILE = PROJECT_ROOT / "logs" / "change_pct_stats.json"


def _load_env():
    for f in (".env", ".env.production"):
        p = SCRIPT_DIR.parent / f
        if p.exists():
            load_dotenv(p, override=True)


def _get_conn():
    url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "").replace("+psycopg2", "")
    if "://" not in url:
        url = f"postgresql://{url}"
    r = urlparse(url)
    return psycopg2.connect(
        host=r.hostname or "localhost", port=r.port or 5432,
        user=r.username or "aipicking", password=r.password or "",
        dbname=r.path.lstrip("/") or "aipicking",
    )


def collect(trade_date: str, source: str) -> dict:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT close, pre_close FROM daily WHERE trade_date=%s", (trade_date,))
    rows = cur.fetchall()
    conn.close()

    total = len(rows)
    pcts = []
    invalid = 0
    for close, pre_close in rows:
        if not pre_close or pre_close == 0 or close is None:
            invalid += 1
            continue
        pcts.append((close - pre_close) / pre_close * 100.0)

    n = len(pcts)
    # 与设计稿 /change-distribution 一致的 8 区间（左闭右开），按涨→跌降序
    EIGHT = [
        (10, 100, "10%以上"),
        (5, 10, "5%~10%"),
        (2, 5, "2%~5%"),
        (0, 2, "0%~2%"),
        (-2, 0, "-2%~0%"),
        (-5, -2, "-5%~-2%"),
        (-10, -5, "-10%~-5%"),
        (-100, -10, "-10%以下"),
    ]
    counts = [0] * len(EIGHT)
    for p in pcts:
        for i, (lo, hi, _label) in enumerate(EIGHT):
            if lo <= p < hi:
                counts[i] += 1
                break
    bucket_list = [
        {"lo": lo, "label": label, "count": counts[i],
         "pct": round(counts[i] / n * 100, 2) if n else 0.0}
        for i, (lo, _hi, label) in enumerate(EIGHT)
    ]

    up = sum(1 for p in pcts if p > 0)
    down = sum(1 for p in pcts if p < 0)
    flat = n - up - down
    return {
        "trade_date": trade_date,
        "source": source,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
        "valid": n,
        "invalid": invalid,
        "up": up,
        "down": down,
        "flat": flat,
        "median": round(statistics.median(pcts), 2) if pcts else None,
        "mean": round(statistics.mean(pcts), 2) if pcts else None,
        "max": round(max(pcts), 2) if pcts else None,
        "min": round(min(pcts), 2) if pcts else None,
        "buckets": bucket_list,
    }


def _print_buckets(snap: dict):
    """打印涨跌幅分桶分布：每档 [label] count(pct%) 条形，跌幅档用 ▼ 标记。"""
    print(f"\n  涨跌幅分布（样本 {snap['valid']}）：")
    for b in snap.get("buckets", []):
        lo = b["lo"]
        bar_len = max(1, int(round(b["pct"] / 2)))  # 2% 占 ≈ 1 字符
        bar = ("▼" if lo < 0 else "▲") * bar_len
        mark = "  [跌]" if lo < 0 else ("  [涨]" if lo > 0 else "")
        print(f"    {b['label']:<12} {b['count']:>5} ({b['pct']:>5.2f}%) {bar}{mark}")


def load_store() -> dict:
    if STORE_FILE.exists():
        try:
            return json.loads(STORE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"snapshots": {}}


def main():
    ap = argparse.ArgumentParser(description="全市场涨跌幅分布统计并保存")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                    help="交易日 YYYY-MM-DD（默认今天）")
    ap.add_argument("--source", default="intraday",
                    help="数据口径标记（intraday/close），仅作备注")
    ap.add_argument("--print", dest="do_print", action="store_true",
                    help="打印已保存的历史快照对比")
    args = ap.parse_args()

    if args.do_print:
        store = load_store()
        for td, snap in sorted(store["snapshots"].items()):
            print(f"\n{td} [{snap.get('source','')}]  中位={snap['median']}%  "
                  f"均值={snap['mean']}%  涨={snap['up']} 跌={snap['down']}  "
                  f"平={snap['flat']}  样本={snap['valid']}")
            _print_buckets(snap)
        return

    snap = collect(args.date, args.source)
    store = load_store()
    store["snapshots"][args.date] = snap
    STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STORE_FILE.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已保存 {args.date} 快照到 {STORE_FILE}")
    print(f"  样本={snap['valid']} (无效={snap['invalid']})  中位={snap['median']}%  "
          f"均值={snap['mean']}%  涨={snap['up']} 跌={snap['down']} 平={snap['flat']}")
    _print_buckets(snap)


if __name__ == "__main__":
    _load_env()
    main()
