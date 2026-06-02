"""
超跌反弹策略 历史信号表现分析脚本
==============================================
对指定日期运行策略（返回全部结果），跟踪每只股票和四大指数的后续表现。
生成 Markdown 报表。

用法: cd backend && source venv/bin/activate && python ../analysis_oversold_bounce.py
"""

import sys
import os
from datetime import datetime, timedelta, date
from collections import defaultdict

# 确保 backend 在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from app.config import settings

# ── 同步引擎 ──
_sync_engine = create_engine(settings.SYNC_DATABASE_URL)
SyncSession = sessionmaker(bind=_sync_engine)

# ── 配置 ──
TARGET_DATES = [
    # 2月
    ("20260202", "2026-02-02"),
    ("20260205", "2026-02-05"),
    ("20260206", "2026-02-06"),
    # 3月
    ("20260305", "2026-03-05"),
    ("20260306", "2026-03-06"),
    ("20260309", "2026-03-09"),
    ("20260323", "2026-03-23"),
    ("20260331", "2026-03-31"),
    # 4月
    ("20260402", "2026-04-02"),
    ("20260403", "2026-04-03"),
    ("20260407", "2026-04-07"),
]

INDICES = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000688.SH": "科创50",
}

# ── 策略参数（与 oversold_bounce.py 默认值完全一致）──
CONFIG = {
    "drawdown_pct": 15.0,
    "lookback_days": 20,
    "panic_vol_ratio": 2.0,
    "shrink_vol_ratio": 0.6,
    "bounce_vol_ratio": 1.2,
    "close_upper_ratio": 0.0,
    "ma20_deviation": 5.0,
    "low_tolerance": 0.04,
    "stabilize_window": 3,
    "min_list_days": 60,
    "market_timing": True,
    "market_index": "399006",
    "market_ma20_below": 1.5,
}


# ═══════════════════════════════════════════════
# 策略核心逻辑（从 oversold_bounce.py 复制，去掉了 top-N 限制）
# ═══════════════════════════════════════════════

def _compute_turnover(vol, amount, close, float_shares):
    """计算换手率，自适应检测 vol 单位（手 vs 股）"""
    if not float_shares or float_shares <= 0:
        return 0.0
    if not vol or vol <= 0 or not close or close <= 0:
        return 0.0
    if not amount or amount <= 0:
        ratio = 100
    else:
        theoretical_amount = close * vol
        if theoretical_amount <= 0:
            return 0.0
        ratio = amount / theoretical_amount
    if ratio > 50:
        vol_shares = vol * 100
    else:
        vol_shares = vol
    turnover = (vol_shares / float_shares) * 100
    return min(turnover, 100.0)


def _is_market_oversold(daily, index_code, threshold):
    """检查指数是否处于超跌状态"""
    full_code = index_code if "." in index_code else f"{index_code}.SZ"
    if full_code not in daily:
        return False
    rows = daily[full_code]
    if len(rows) < 20:
        return False
    closes = [r["close"] for r in rows if r.get("close") and r["close"] > 0]
    if len(closes) < 20:
        return False
    ma20 = sum(closes[-20:]) / 20
    last_close = closes[-1]
    if ma20 <= 0:
        return False
    deviation = (ma20 - last_close) / ma20 * 100
    return deviation >= threshold


def check_oversold_bounce(df_rows, config):
    """
    三阶段检测。df_rows 是按 trade_date 升序排列的 dict 列表。
    返回 (passed: bool, score: int, signal: str, details: dict, breakdown: dict)
    """
    valid = [r for r in df_rows if r.get("close") is not None and r.get("vol") is not None]
    if len(valid) < config["lookback_days"] + 5:
        return False, 0, "", {}, {}

    # 计算 MA20 和 vol_ma20（动态计算）
    closes = [r["close"] for r in valid]
    vols = [r["vol"] for r in valid]

    def rolling_mean(arr, window):
        result = [0.0] * len(arr)
        for i in range(len(arr)):
            if i + 1 < window:
                result[i] = sum(arr[:i + 1]) / (i + 1) if (i + 1) > 0 else 0
            else:
                result[i] = sum(arr[i - window + 1:i + 1]) / window
        return result

    ma20_arr = rolling_mean(closes, 20)
    vol_ma20_arr = rolling_mean(vols, 20)

    target_idx = len(valid) - 1
    target_row = valid[target_idx]
    target_close = target_row["close"]

    # ── 阶段一：急跌识别 ──
    lookback_start = max(0, target_idx - config["lookback_days"])
    window = valid[lookback_start: target_idx + 1]
    peak_close = max(d["close"] for d in window)

    drawdown_pct = (peak_close - target_close) / peak_close * 100
    if drawdown_pct < config["drawdown_pct"]:
        return False, 0, "", {}, {}

    ma20_val = ma20_arr[target_idx]
    if ma20_val <= 0:
        return False, 0, "", {}, {}
    ma20_dist = (ma20_val - target_close) / ma20_val * 100
    if ma20_dist < config["ma20_deviation"]:
        return False, 0, "", {}, {}

    has_panic_vol = any(
        vol_ma20_arr[lookback_start + i] > 0
        and d["vol"] > vol_ma20_arr[lookback_start + i] * config["panic_vol_ratio"]
        for i, d in enumerate(window)
    )
    if not has_panic_vol:
        return False, 0, "", {}, {}

    # ── 阶段二：缩量止跌 ──
    stabilize_idx = None
    search_start = max(1, target_idx - config["stabilize_window"])
    for s in range(target_idx - 1, search_start - 1, -1):
        sd = valid[s]
        s_vm = vol_ma20_arr[s]
        if s_vm <= 0:
            continue

        # 2a. 缩量
        if sd["vol"] >= s_vm * config["shrink_vol_ratio"]:
            continue

        # 2b. 缩量递减
        prev1 = valid[s - 1]
        if sd["vol"] >= prev1["vol"]:
            continue

        # 2c. 不再创新低
        if sd["low"] < prev1["low"] * (1 - config["low_tolerance"]):
            continue

        # 数据完整性校验
        sd_amount = sd.get("amount") or 0
        sd_close_v = sd.get("close") or 0
        sd_vol_v = sd.get("vol") or 0
        if sd_amount > 0 and sd_close_v > 0 and sd_vol_v > 0:
            if sd_amount < sd_close_v * sd_vol_v * 0.1:
                continue
        if sd_vol_v < s_vm * 0.01:
            continue

        stabilize_idx = s
        break

    if stabilize_idx is None:
        return False, 0, "", {}, {}

    stabilize_row = valid[stabilize_idx]

    # ── 阶段三：反弹触发 ──
    stab_vol = stabilize_row["vol"]
    if stab_vol <= 0:
        return False, 0, "", {}, {}
    bounce_vol_ratio = target_row["vol"] / stab_vol
    if bounce_vol_ratio < config["bounce_vol_ratio"]:
        return False, 0, "", {}, {}

    if config["close_upper_ratio"] > 0:
        if target_row["high"] <= target_row["low"]:
            return False, 0, "", {}, {}
        close_position = (target_row["close"] - target_row["low"]) / (target_row["high"] - target_row["low"])
        if close_position < config["close_upper_ratio"]:
            return False, 0, "", {}, {}

    # ── 打分 ──
    # 回撤
    if drawdown_pct >= 25:
        score_dd = 30
    elif drawdown_pct >= 20:
        score_dd = 24
    elif drawdown_pct >= 15:
        score_dd = 18
    else:
        score_dd = 10

    # MA20偏离
    if ma20_dist >= 10:
        score_ma = 20
    elif ma20_dist >= 7:
        score_ma = 15
    elif ma20_dist >= 5:
        score_ma = 10
    else:
        score_ma = 5

    # 缩量程度
    shrink_actual = stabilize_row["vol"] / vol_ma20_arr[stabilize_idx]
    if shrink_actual < 0.3:
        score_sh = 20
    elif shrink_actual < 0.5:
        score_sh = 15
    elif shrink_actual < 0.6:
        score_sh = 10
    else:
        score_sh = 5

    # 反弹放量
    if bounce_vol_ratio >= 2.5:
        score_bo = 20
    elif bounce_vol_ratio >= 2.0:
        score_bo = 16
    elif bounce_vol_ratio >= 1.5:
        score_bo = 12
    else:
        score_bo = 6

    score = score_dd + score_ma + score_sh + score_bo
    breakdown = {
        "drawdown": score_dd,
        "ma20_dev": score_ma,
        "shrink": score_sh,
        "bounce": score_bo,
        "close_pos": 0,
    }

    signal = (
        f"回撤{drawdown_pct:.1f}%→恐慌放量→"
        f"缩量至{shrink_actual:.2f}x均量→"
        f"反弹放量{bounce_vol_ratio:.1f}倍"
    )

    details = {
        "drawdown_pct": round(drawdown_pct, 2),
        "ma20_dist": round(ma20_dist, 2),
        "shrink_vol_ratio_actual": round(shrink_actual, 2),
        "bounce_vol_ratio_actual": round(bounce_vol_ratio, 1),
        "stabilize_date": stabilize_row["trade_date"],
        "stabilize_close": round(stabilize_row["close"], 2),
        "bounce_close": round(target_close, 2),
    }

    return True, score, signal, details, breakdown


def run_strategy(data, config):
    """执行策略，返回全部结果（不限制 Top-N）"""
    stocks = data.get("stocks", [])
    daily = data.get("daily", {})

    # 构建 name 映射
    name_map = {}
    for s in stocks:
        name_map[s["ts_code"]] = s.get("name", s["ts_code"])

    # 构建 float_shares 映射
    float_map = {}
    for s in stocks:
        fs = s.get("float_shares")
        if fs and fs > 0:
            float_map[s["ts_code"]] = fs

    # 大盘择时
    if config.get("market_timing", True):
        idx_code = config.get("market_index", "399006")
        threshold = config.get("market_ma20_below", 1.5)
        if not _is_market_oversold(daily, idx_code, threshold):
            return []

    results = []
    for ts_code, rows in daily.items():
        # 板块过滤
        if not (ts_code.startswith("300") or ts_code.startswith("301")
                or ts_code.startswith("688") or ts_code.startswith("689")):
            continue

        # ST 过滤
        name = name_map.get(ts_code, "")
        if "ST" in name:
            continue

        # 市值过滤
        if rows:
            mc = rows[-1].get("market_cap") or 0
            if mc > 0 and (mc < 20_0000_0000 or mc > 5000_0000_0000):  # 20亿~5000亿 万元
                continue

        # 数据量
        if len(rows) < 60:
            continue

        passed, score, signal, details, breakdown = check_oversold_bounce(rows, config)
        if not passed:
            continue

        # 换手率
        target_row = rows[-1]
        fs = float_map.get(ts_code, 0)
        turnover = _compute_turnover(
            target_row.get("vol"), target_row.get("amount"),
            target_row.get("close"), fs
        )

        # 换手率加分
        if turnover >= 8:
            score_to = 10
        elif turnover >= 5:
            score_to = 8
        elif turnover >= 3:
            score_to = 6
        elif turnover >= 1:
            score_to = 4
        else:
            score_to = 1

        score += score_to
        breakdown["turnover"] = score_to
        signal += f" 换手{turnover:.1f}%"

        results.append({
            "ts_code": ts_code,
            "name": name,
            "score": score,
            "signal": signal,
            "breakdown": breakdown,
            "details": details,
            "turnover": round(turnover, 2),
            "close": target_row.get("close"),
            "market_cap": target_row.get("market_cap"),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ═══════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════

def load_data(cutoff_date_str):
    """加载截止日及之前 180 天的数据"""
    session = SyncSession()
    try:
        cutoff_dt = datetime.strptime(cutoff_date_str, "%Y%m%d")
        start_date = (cutoff_dt - timedelta(days=180)).strftime("%Y%m%d")

        # 股票基础信息
        stmt = select(
            text("ts_code, symbol, name, market, industry_l1, industry_l2, industry_l3, "
                 "concepts, total_shares, float_shares")
        ).select_from(text("stocks")).where(text("ts_code IS NOT NULL AND ts_code != ''"))
        stocks_result = session.execute(stmt)
        stocks_data = [dict(row._mapping) for row in stocks_result]

        # 日线数据
        daily_stmt = select(
            text("ts_code, trade_date, open, high, low, close, vol, amount, "
                 "adj_close, market_cap, circ_market_cap")
        ).select_from(text("daily")).where(
            text(f"trade_date BETWEEN '{start_date}' AND '{cutoff_date_str}'")
        ).order_by(text("ts_code, trade_date"))
        daily_result = session.execute(daily_stmt)
        daily_rows = [dict(row._mapping) for row in daily_result]

        # 按 ts_code 分组
        daily_data = defaultdict(list)
        for row in daily_rows:
            daily_data[row["ts_code"]].append(row)

        return {"stocks": stocks_data, "daily": dict(daily_data)}
    finally:
        session.close()


def get_forward_prices(session, ts_codes, signal_date_str, calendar_days_list):
    """
    获取每只股票在 signal_date + calendar_days 之后最近的交易数据。
    返回 {ts_code: {days: {"date": ..., "close": ..., "open": ...}}}
    """
    signal_dt = datetime.strptime(signal_date_str, "%Y%m%d")
    # 取最大需要查询的日期范围
    max_days = max(calendar_days_list)
    end_dt = signal_dt + timedelta(days=max_days + 10)  # 多取一些缓冲

    result = {code: {} for code in ts_codes}

    for code in ts_codes:
        daily_stmt = select(
            text("trade_date, open, high, low, close, vol, amount")
        ).select_from(text("daily")).where(
            text(f"ts_code = '{code}' AND trade_date > '{signal_date_str}' AND trade_date <= '{end_dt.strftime('%Y%m%d')}'")
        ).order_by(text("trade_date"))
        rows = session.execute(daily_stmt).fetchall()

        for days in calendar_days_list:
            target_dt = signal_dt + timedelta(days=days)
            target_str = target_dt.strftime("%Y%m%d")
            # 找 >= target_str 的第一条
            found = None
            for row in rows:
                if row.trade_date >= target_str:
                    found = row
                    break
            if found:
                result[code][days] = {
                    "date": found.trade_date,
                    "close": float(found.close) if found.close else None,
                    "open": float(found.open) if found.open else None,
                    "high": float(found.high) if found.high else None,
                    "low": float(found.low) if found.low else None,
                }
            else:
                result[code][days] = None

    return result


# ═══════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════

def main():
    print("=" * 80)
    print("超跌反弹策略 历史信号表现分析")
    print("=" * 80)

    session = SyncSession()

    # ── 统计总股票池 ──
    total_stmt = select(text("COUNT(*)")).select_from(text("stocks")).where(
        text("(ts_code LIKE '300%' OR ts_code LIKE '301%' OR ts_code LIKE '688%' OR ts_code LIKE '689%')")
    )
    total_stocks = session.execute(total_stmt).scalar()
    print(f"\n创业板+科创板总股票数: {total_stocks}")

    # ── 预先加载所有日期的数据 ──
    all_results = {}  # {date_str: [recommendations]}
    all_index_data = {}  # {date_str: {index_code: {...}}}

    for cutoff_date, cutoff_date_fmt in TARGET_DATES:
        print(f"\n{'─' * 60}")
        print(f"处理日期: {cutoff_date_fmt} ({cutoff_date})")
        print(f"{'─' * 60}")

        # 加载数据
        data = load_data(cutoff_date)
        daily_count = len(data["daily"])
        stock_count = len(data["stocks"])
        print(f"  加载: {stock_count} 只股票, {daily_count} 只有日线数据")

        # 运行策略
        recommendations = run_strategy(data, CONFIG)
        print(f"  策略选出: {len(recommendations)} 只股票")

        if recommendations:
            print(f"  Top 5:")
            for r in recommendations[:5]:
                print(f"    {r['ts_code']} {r['name']:8s} score={r['score']:3d} | {r['signal'][:80]}")

        all_results[cutoff_date] = recommendations

        # ── 获取四大指数当日前价格 ──
        index_info = {}
        for idx_code, idx_name in INDICES.items():
            row = session.execute(
                text(f"SELECT close FROM daily WHERE ts_code='{idx_code}' AND trade_date<='{cutoff_date}' ORDER BY trade_date DESC LIMIT 1")
            ).fetchone()
            index_info[idx_code] = {
                "name": idx_name,
                "signal_date": cutoff_date,
                "signal_close": float(row.close) if row and row.close else None,
            }
        all_index_data[cutoff_date] = index_info

    # ── 收集所有选中的股票代码和信号日期 ──
    all_picked_codes = set()
    for cutoff_date, recs in all_results.items():
        for r in recs:
            all_picked_codes.add((cutoff_date, r["ts_code"]))

    # ── 获取前向价格 ──
    print(f"\n{'=' * 80}")
    print("获取前向价格...")
    print(f"{'=' * 80}")

    forward_prices = {}  # {(cutoff_date, ts_code): {days: {...}}}
    for cutoff_date, _ in TARGET_DATES:
        codes_for_date = [r["ts_code"] for r in all_results.get(cutoff_date, [])]
        if codes_for_date:
            fp = get_forward_prices(session, codes_for_date, cutoff_date, [0, 7, 15])
            for code, days_data in fp.items():
                forward_prices[(cutoff_date, code)] = days_data

    # ── 获取指数前向价格 ──
    index_forward = {}  # {(cutoff_date, idx_code): {days: close}}
    for cutoff_date, _ in TARGET_DATES:
        for idx_code in INDICES:
            fp = get_forward_prices(session, [idx_code], cutoff_date, [0, 7, 15])
            index_forward[(cutoff_date, idx_code)] = fp.get(idx_code, {})

    # ── 计算每只股票的表现 ──
    print("计算表现...")
    stock_performances = []  # [{ts_code, name, signal_date, signal_close, ret_0d, ret_7d, ret_15d, ...}]

    for cutoff_date, recs in all_results.items():
        for r in recs:
            code = r["ts_code"]
            fp = forward_prices.get((cutoff_date, code), {})
            signal_close = r.get("close")

            perf = {
                "signal_date": cutoff_date,
                "ts_code": code,
                "name": r["name"],
                "score": r["score"],
                "signal_close": signal_close,
                "turnover": r.get("turnover"),
                "drawdown_pct": r["details"].get("drawdown_pct"),
                "details": r["details"],
                "signal": r["signal"],
            }

            for days, label in [(0, "ret_0d"), (7, "ret_7d"), (15, "ret_15d")]:
                fd = fp.get(days)
                if fd and fd["close"] and signal_close and signal_close > 0:
                    ret = (fd["close"] - signal_close) / signal_close * 100
                    perf[label] = round(ret, 2)
                    perf[f"{label}_date"] = fd["date"]
                else:
                    perf[label] = None
                    perf[f"{label}_date"] = None

            stock_performances.append(perf)

    # ── 计算指数表现 ──
    index_performances = {}  # {(cutoff_date, idx_code): {ret_0d, ret_7d, ret_15d}}

    for cutoff_date, _ in TARGET_DATES:
        info = all_index_data.get(cutoff_date, {})
        for idx_code, idx_info in info.items():
            signal_close = idx_info["signal_close"]
            ifp = index_forward.get((cutoff_date, idx_code), {})
            perf = {"name": idx_info["name"], "signal_date": cutoff_date, "signal_close": signal_close}
            for days, label in [(0, "ret_0d"), (7, "ret_7d"), (15, "ret_15d")]:
                fd = ifp.get(days)
                if fd and fd["close"] and signal_close and signal_close > 0:
                    perf[label] = round((fd["close"] - signal_close) / signal_close * 100, 2)
                    perf[f"{label}_date"] = fd["date"]
                else:
                    perf[label] = None
                    perf[f"{label}_date"] = None
            index_performances[(cutoff_date, idx_code)] = perf

    session.close()

    # ═══════════════════════════════════════════════
    # 生成报表
    # ═══════════════════════════════════════════════

    # 按月份分组
    month_groups = [
        ("2026年2月", ["20260202", "20260205", "20260206"]),
        ("2026年3月", ["20260305", "20260306", "20260309", "20260323", "20260331"]),
        ("2026年4月", ["20260402", "20260403", "20260407"]),
    ]

    report = []
    report.append("# 超跌反弹策略 历史信号表现分析报告\n")
    report.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.append(f"> 策略参数：回撤≥{CONFIG['drawdown_pct']}%, MA20偏离≥{CONFIG['ma20_deviation']}%, "
                  f"恐慌量>{CONFIG['panic_vol_ratio']}x, 缩量<{CONFIG['shrink_vol_ratio']}x, "
                  f"反弹量>{CONFIG['bounce_vol_ratio']}x\n")
    report.append(f"> 大盘择时：{'启用' if CONFIG['market_timing'] else '关闭'}，"
                  f"指数低于MA20≥{CONFIG['market_ma20_below']}%\n")
    report.append(f"> 股票池：创业板(300/301) + 科创板(688/689)，共 {total_stocks} 只\n")
    report.append("\n---\n")

    # ── 汇总统计 ──
    report.append("## 一、汇总\n\n")
    report.append("| 月份 | 信号日 | 选出股票数 | 平均当日涨跌 | 平均7日涨跌 | 平均15日涨跌 | 上涨占比(7日) | 上涨占比(15日) |\n")
    report.append("|------|--------|-----------|-------------|------------|-------------|--------------|---------------|\n")

    all_month_stats = []

    for month_label, dates in month_groups:
        for d in dates:
            date_perfs = [p for p in stock_performances if p["signal_date"] == d]
            n = len(date_perfs)
            if n == 0:
                report.append(f"| {month_label} | {d[:4]}-{d[4:6]}-{d[6:8]} | 0 | - | - | - | - | - |\n")
                continue

            avg_0d = sum(p["ret_0d"] for p in date_perfs if p["ret_0d"] is not None)
            cnt_0d = sum(1 for p in date_perfs if p["ret_0d"] is not None)
            avg_7d = sum(p["ret_7d"] for p in date_perfs if p["ret_7d"] is not None)
            cnt_7d = sum(1 for p in date_perfs if p["ret_7d"] is not None)
            avg_15d = sum(p["ret_15d"] for p in date_perfs if p["ret_15d"] is not None)
            cnt_15d = sum(1 for p in date_perfs if p["ret_15d"] is not None)

            up_7d = sum(1 for p in date_perfs if p["ret_7d"] is not None and p["ret_7d"] > 0)
            up_15d = sum(1 for p in date_perfs if p["ret_15d"] is not None and p["ret_15d"] > 0)

            avg_0d_str = f"{avg_0d / cnt_0d:+.2f}%" if cnt_0d > 0 else "-"
            avg_7d_str = f"{avg_7d / cnt_7d:+.2f}%" if cnt_7d > 0 else "-"
            avg_15d_str = f"{avg_15d / cnt_15d:+.2f}%" if cnt_15d > 0 else "-"
            up_7d_str = f"{up_7d}/{cnt_7d} ({up_7d / cnt_7d * 100:.0f}%)" if cnt_7d > 0 else "-"
            up_15d_str = f"{up_15d}/{cnt_15d} ({up_15d / cnt_15d * 100:.0f}%)" if cnt_15d > 0 else "-"

            report.append(f"| {month_label} | {d[:4]}-{d[4:6]}-{d[6:8]} | **{n}** | {avg_0d_str} | {avg_7d_str} | {avg_15d_str} | {up_7d_str} | {up_15d_str} |\n")

            all_month_stats.append({
                "month": month_label, "date": d, "n": n,
                "avg_7d": avg_7d / cnt_7d if cnt_7d > 0 else None,
                "avg_15d": avg_15d / cnt_15d if cnt_15d > 0 else None,
                "up_7d_pct": up_7d / cnt_7d * 100 if cnt_7d > 0 else None,
                "up_15d_pct": up_15d / cnt_15d * 100 if cnt_15d > 0 else None,
            })

    # 总计行
    total_picked = len(stock_performances)
    if total_picked > 0:
        avg_0d_all = sum(p["ret_0d"] for p in stock_performances if p["ret_0d"] is not None)
        cnt_0d_all = sum(1 for p in stock_performances if p["ret_0d"] is not None)
        avg_7d_all = sum(p["ret_7d"] for p in stock_performances if p["ret_7d"] is not None)
        cnt_7d_all = sum(1 for p in stock_performances if p["ret_7d"] is not None)
        avg_15d_all = sum(p["ret_15d"] for p in stock_performances if p["ret_15d"] is not None)
        cnt_15d_all = sum(1 for p in stock_performances if p["ret_15d"] is not None)
        up_7d_all = sum(1 for p in stock_performances if p["ret_7d"] is not None and p["ret_7d"] > 0)
        up_15d_all = sum(1 for p in stock_performances if p["ret_15d"] is not None and p["ret_15d"] > 0)

        report.append(f"| **合计** | **{len(TARGET_DATES)}天** | **{total_picked}** | "
                      f"**{avg_0d_all / cnt_0d_all:+.2f}%** | "
                      f"**{avg_7d_all / cnt_7d_all:+.2f}%** | "
                      f"**{avg_15d_all / cnt_15d_all:+.2f}%** | "
                      f"**{up_7d_all}/{cnt_7d_all} ({up_7d_all / cnt_7d_all * 100:.0f}%)** | "
                      f"**{up_15d_all}/{cnt_15d_all} ({up_15d_all / cnt_15d_all * 100:.0f}%)** |\n")

    report.append("\n---\n")

    # ── 四大指数表现 ──
    report.append("## 二、四大指数同期表现\n\n")
    report.append("| 信号日 | 指数 | 当日收盘 | 当日涨跌 | 7日涨跌 | 15日涨跌 |\n")
    report.append("|--------|------|---------|---------|--------|----------|\n")

    for cutoff_date, _ in TARGET_DATES:
        for idx_code in ["000001.SH", "399001.SZ", "399006.SZ", "000688.SH"]:
            perf = index_performances.get((cutoff_date, idx_code), {})
            name = perf.get("name", idx_code)
            sig_close = perf.get("signal_close", "-")
            ret_0d = f"{perf['ret_0d']:+.2f}%" if perf.get("ret_0d") is not None else "-"
            ret_7d = f"{perf['ret_7d']:+.2f}%" if perf.get("ret_7d") is not None else "-"
            ret_15d = f"{perf['ret_15d']:+.2f}%" if perf.get("ret_15d") is not None else "-"
            close_str = f"{sig_close:.2f}" if isinstance(sig_close, (int, float)) else str(sig_close)

            # 只在第一个指数的行显示日期
            if idx_code == "000001.SH":
                date_label = f"{cutoff_date[:4]}-{cutoff_date[4:6]}-{cutoff_date[6:8]}"
            else:
                date_label = ""

            report.append(f"| {date_label} | {name} | {close_str} | {ret_0d} | {ret_7d} | {ret_15d} |\n")
        report.append("| | | | | | |\n")  # 空行分隔

    report.append("\n---\n")

    # ── 每日详细选股列表 ──
    report.append("## 三、每日选股详细列表\n\n")

    for month_label, dates in month_groups:
        report.append(f"### {month_label}\n\n")

        for d in dates:
            date_perfs = [p for p in stock_performances if p["signal_date"] == d]
            date_str = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            n = len(date_perfs)

            report.append(f"#### {date_str}（{n} 只）\n\n")
            if n == 0:
                report.append("*无选出股票*\n\n")
                continue

            report.append("| # | 代码 | 名称 | 评分 | 回撤% | 换手% | 买入价 | 当日涨跌 | 7日涨跌 | 15日涨跌 |\n")
            report.append("|---|------|------|------|-------|-------|--------|---------|--------|----------|\n")

            for i, p in enumerate(date_perfs, 1):
                ret_0d = f"{p['ret_0d']:+.2f}%" if p.get("ret_0d") is not None else "-"
                ret_7d = f"{p['ret_7d']:+.2f}%" if p.get("ret_7d") is not None else "-"
                ret_15d = f"{p['ret_15d']:+.2f}%" if p.get("ret_15d") is not None else "-"
                close_str = f"{p['signal_close']:.2f}" if p.get("signal_close") else "-"
                turnover_str = f"{p['turnover']:.1f}%" if p.get("turnover") else "-"
                dd_str = f"{p['drawdown_pct']:.1f}%" if p.get("drawdown_pct") else "-"

                report.append(
                    f"| {i} | {p['ts_code']} | {p['name']} | {p['score']} | "
                    f"{dd_str} | {turnover_str} | {close_str} | "
                    f"{ret_0d} | {ret_7d} | {ret_15d} |\n"
                )
            report.append("\n")

    report.append("\n---\n")

    # ── 策略 vs 指数对比 ──
    report.append("## 四、策略选股 vs 指数 表现对比\n\n")
    report.append("| 信号日 | 选股数 | 策略均7日 | 策略均15日 | 上证7日 | 上证15日 | 创业7日 | 创业15日 | 科创7日 | 科创15日 |\n")
    report.append("|--------|--------|----------|-----------|--------|---------|--------|---------|--------|----------|\n")

    for cutoff_date, _ in TARGET_DATES:
        date_perfs = [p for p in stock_performances if p["signal_date"] == cutoff_date]
        n = len(date_perfs)

        # 策略平均
        avg_7d = sum(p["ret_7d"] for p in date_perfs if p["ret_7d"] is not None)
        cnt_7d = sum(1 for p in date_perfs if p["ret_7d"] is not None)
        avg_15d = sum(p["ret_15d"] for p in date_perfs if p["ret_15d"] is not None)
        cnt_15d = sum(1 for p in date_perfs if p["ret_15d"] is not None)

        strat_7d = f"{avg_7d / cnt_7d:+.2f}%" if cnt_7d > 0 else "-"
        strat_15d = f"{avg_15d / cnt_15d:+.2f}%" if cnt_15d > 0 else "-"

        # 各指数
        def idx_ret(idx_code, days_label):
            p = index_performances.get((cutoff_date, idx_code), {})
            v = p.get(days_label)
            return f"{v:+.2f}%" if v is not None else "-"

        date_str = f"{cutoff_date[:4]}-{cutoff_date[4:6]}-{cutoff_date[6:8]}"
        report.append(
            f"| {date_str} | {n} | {strat_7d} | {strat_15d} | "
            f"{idx_ret('000001.SH', 'ret_7d')} | {idx_ret('000001.SH', 'ret_15d')} | "
            f"{idx_ret('399006.SZ', 'ret_7d')} | {idx_ret('399006.SZ', 'ret_15d')} | "
            f"{idx_ret('000688.SH', 'ret_7d')} | {idx_ret('000688.SH', 'ret_15d')} |\n"
        )

    report.append("\n---\n")

    # ── 策略总结 ──
    report.append("## 五、策略表现总结\n\n")

    # 整体统计
    all_7d = [p["ret_7d"] for p in stock_performances if p["ret_7d"] is not None]
    all_15d = [p["ret_15d"] for p in stock_performances if p["ret_15d"] is not None]

    if all_7d:
        report.append(f"- **总信号数**：{total_picked} 条（{len(TARGET_DATES)} 个交易日）\n")
        report.append(f"- **日均信号数**：{total_picked / len(TARGET_DATES):.1f} 条\n")
        report.append(f"- **7日平均收益**：{sum(all_7d) / len(all_7d):+.2f}%（{sum(1 for v in all_7d if v > 0)}/{len(all_7d)} 上涨，{sum(1 for v in all_7d if v > 0) / len(all_7d) * 100:.1f}%）\n")
        report.append(f"- **15日平均收益**：{sum(all_15d) / len(all_15d):+.2f}%（{sum(1 for v in all_15d if v > 0)}/{len(all_15d)} 上涨，{sum(1 for v in all_15d if v > 0) / len(all_15d) * 100:.1f}%）\n")

        # 7日胜率
        report.append(f"- **7日最大盈利**：{max(all_7d):+.2f}%\n")
        report.append(f"- **7日最大亏损**：{min(all_7d):+.2f}%\n")
        report.append(f"- **15日最大盈利**：{max(all_15d):+.2f}%\n")
        report.append(f"- **15日最大亏损**：{min(all_15d):+.2f}%\n")

        # 评分与收益相关性（简单分析）
        report.append(f"\n### 评分与收益关系\n\n")
        report.append("| 评分区间 | 数量 | 平均7日收益 | 平均15日收益 |\n")
        report.append("|---------|------|-----------|------------|\n")
        for lo, hi, label in [(0, 65, "60以下"), (65, 75, "65-75"), (75, 85, "75-85"), (85, 200, "85以上")]:
            bucket = [p for p in stock_performances if lo <= p["score"] < hi]
            if bucket:
                b7 = [p["ret_7d"] for p in bucket if p["ret_7d"] is not None]
                b15 = [p["ret_15d"] for p in bucket if p["ret_15d"] is not None]
                avg7 = sum(b7) / len(b7) if b7 else 0
                avg15 = sum(b15) / len(b15) if b15 else 0
                report.append(f"| {label} | {len(bucket)} | {avg7:+.2f}% | {avg15:+.2f}% |\n")

    # ── 输出 ──
    output_path = os.path.join(os.path.dirname(__file__), "docs", "oversold-bounce-performance-report.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("".join(report))

    print(f"\n{'=' * 80}")
    print(f"报表已生成: {output_path}")
    print(f"{'=' * 80}")

    # 同时输出到控制台
    print("\n" + "".join(report))


if __name__ == "__main__":
    main()
