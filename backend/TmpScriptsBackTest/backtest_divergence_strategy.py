#!/usr/bin/env python3
"""
指数底背离买入顶背离卖出 · 回测脚本

策略逻辑：
  1. 日线 MACD DIF 底背离（观察 20 日窗口）→ 触发买入，买总仓位 7.5%
  2. 触发后每日自动加仓 7.5%，无需等新信号，上限满仓 100%
  3. 顶背离信号（20 日窗口）→ 暂停自动加仓，卖出持仓 20%
  4. 追卖：相比上次卖出价每涨 7%，再卖 20%，直到卖完
  5. 卖出过程中出现底背离 → 重启加仓逻辑

用法：
  python TmpScriptsBackTest/backtest_divergence_strategy.py
  python TmpScriptsBackTest/backtest_divergence_strategy.py --index 399006.SZ
  python TmpScriptsBackTest/backtest_divergence_strategy.py --index 000001.SH --start 2020-01-01

daily 表可用指数：
  000001.SH  上证指数     (2022-01-04 ~)
  000688.SH  科创50       (2022-01-04 ~)
  000698.SH  科创100      (2025-06-13 ~)
  399001.SZ  深证成指     (2022-01-04 ~)
  399006.SZ  创业板指     (2022-01-04 ~)
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

import psycopg2
from dotenv import load_dotenv

# ── 环境 ──────────────────────────────────────────────────
_ENV_DIR = Path(__file__).resolve().parent.parent
for f in (".env", ".env.production"):
    p = _ENV_DIR / f
    if p.exists():
        load_dotenv(p, override=True)

# ── 交易费率 ──────────────────────────────────────────────
ST = 0.001   # 卖出印花税
CM = 0.0003  # 佣金
SELL_COST = ST + CM
BUY_COST = CM

# ── MACD 参数 ─────────────────────────────────────────────
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
DIVERGENCE_WINDOW = 20  # 背离观察窗口

# ── 仓位参数 ──────────────────────────────────────────────
BUY_PCT = 0.075          # 每次买入仓位比例（相对初始资金）
MAX_POSITION_PCT = 1.0   # 满仓上限
SELL_PCT = 0.20          # 每次卖出持仓比例
TRAILING_UP_PCT = 0.07   # 追卖涨幅阈值


def _pg():
    """获取 PostgreSQL 连接"""
    u = os.getenv("DATABASE_URL", "")
    if not u:
        u = (
            f"postgresql://{os.getenv('DB_USER', 'aipicking')}:"
            f"{os.getenv('DB_PASSWORD', '')}@"
            f"{os.getenv('DB_HOST', 'localhost')}:"
            f"{os.getenv('DB_PORT', '5432')}/"
            f"{os.getenv('DB_NAME', 'aipicking')}"
        )
    u = u.replace("+asyncpg", "").replace("+psycopg2", "")
    if "://" not in u:
        u = f"postgresql://{u}"
    r = urlparse(u)
    return psycopg2.connect(
        host=r.hostname or "localhost",
        port=r.port or 5432,
        user=r.username or "aipicking",
        password=r.password or "",
        dbname=r.path.lstrip("/") or "aipicking",
    )


# ═══════════════════════════════════════════════════════════
# MACD 计算
# ═══════════════════════════════════════════════════════════

def calc_ema(series: list[float], period: int) -> list[Optional[float]]:
    """计算 EMA 序列，前 period-1 个值为 None"""
    n = len(series)
    result: list[Optional[float]] = [None] * n
    if n < period:
        return result
    k = 2.0 / (period + 1)
    # 首个值为 SMA
    ema = sum(series[:period]) / period
    result[period - 1] = ema
    for i in range(period, n):
        ema = series[i] * k + ema * (1 - k)
        result[i] = ema
    return result


def calc_macd(closes: list[float]) -> dict:
    """
    计算 MACD 指标。
    返回: {dif, dea, bar} — 各为 (number | None)[]
    """
    ema_fast = calc_ema(closes, MACD_FAST)
    ema_slow = calc_ema(closes, MACD_SLOW)

    n = len(closes)
    dif: list[Optional[float]] = [None] * n
    dif_valid: list[float] = []
    valid_start = max(MACD_FAST, MACD_SLOW) - 1
    for i in range(valid_start, n):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            d = ema_fast[i] - ema_slow[i]  # type: ignore[operator]
            dif[i] = d
            dif_valid.append(d)

    dea_raw = calc_ema(dif_valid, MACD_SIGNAL)
    dea: list[Optional[float]] = [None] * n
    for i, v in enumerate(dea_raw):
        dea[valid_start + i] = v

    bar: list[Optional[float]] = [None] * n
    for i in range(n):
        if dif[i] is not None and dea[i] is not None:
            bar[i] = 2 * (dif[i] - dea[i])  # type: ignore[operator]

    return {"dif": dif, "dea": dea, "bar": bar}


# ═══════════════════════════════════════════════════════════
# 背离检测
# ═══════════════════════════════════════════════════════════

def detect_bottom_divergence(
    closes: list[float], dif: list[Optional[float]], window: int = DIVERGENCE_WINDOW
) -> bool:
    """
    检测当前日是否出现底背离。

    条件（20 日窗口）：
      1. 今日收盘价创窗口新低（或接近新低）
      2. 今日 DIF 未创窗口新低（前期有过更低的 DIF）
    """
    if len(closes) < window + 1:
        return False

    win_closes = closes[-window:]
    win_dif = [d for d in dif[-window:] if d is not None]

    if len(win_dif) < window // 2:
        return False

    current_close = closes[-1]
    current_dif = dif[-1]
    if current_dif is None:
        return False

    price_min = min(win_closes)
    dif_min = min(win_dif)

    # 避免同一日重复触发：收盘价必须是窗口最低（允许 0.05% 误差）
    if current_close > price_min * 1.0005:
        return False

    # 底背离核心条件：价格创新低，但 DIF 未创新低
    if current_dif <= dif_min:
        return False

    # 确认 DIF 低点出现在窗口前半段，价格低点在后半段
    dif_min_idx = win_dif.index(dif_min)
    price_min_idx = len(win_closes) - 1 - win_closes[::-1].index(price_min)

    if price_min_idx > window * 0.4 and dif_min_idx < window * 0.6:
        return True

    return False


def detect_top_divergence(
    closes: list[float], dif: list[Optional[float]], window: int = DIVERGENCE_WINDOW
) -> bool:
    """
    检测当前日是否出现顶背离。

    条件（20 日窗口）：
      1. 今日收盘价创窗口新高（或接近新高）
      2. 今日 DIF 未创窗口新高（前期有过更高的 DIF）
    """
    if len(closes) < window + 1:
        return False

    win_closes = closes[-window:]
    win_dif = [d for d in dif[-window:] if d is not None]

    if len(win_dif) < window // 2:
        return False

    current_close = closes[-1]
    current_dif = dif[-1]
    if current_dif is None:
        return False

    price_max = max(win_closes)
    dif_max = max(win_dif)

    # 避免同一日重复触发：收盘价必须是窗口最高（允许 0.05% 误差）
    if current_close < price_max * 0.9995:
        return False

    # 顶背离核心条件：价格创新高，但 DIF 未创新高
    if current_dif >= dif_max:
        return False

    # 确认 DIF 高点出现在窗口前半段，价格高点在后半段
    dif_max_idx = win_dif.index(dif_max)
    price_max_idx = len(win_closes) - 1 - win_closes[::-1].index(price_max)

    if price_max_idx > window * 0.4 and dif_max_idx < window * 0.6:
        return True

    return False


# ═══════════════════════════════════════════════════════════
# 回测主逻辑
# ═══════════════════════════════════════════════════════════

def run_backtest(
    index_code: str,
    start_date: str = "2022-01-01",
    end_date: str = "2026-06-20",
) -> dict:
    """
    执行背离策略回测。

    参数:
        index_code: 指数代码，如 '399006.SZ'
        start_date: 回测起始日期
        end_date: 回测截止日期

    返回:
        {index_name, index_code, points, signals, summary}
    """
    conn = _pg()
    cur = conn.cursor()

    # ── 获取指数名称 ──────────────────────────────────
    code_no_suffix = index_code.replace(".SH", "").replace(".SZ", "")
    cur.execute(
        "SELECT index_name, full_name FROM index_info WHERE index_code = %s",
        (code_no_suffix,),
    )
    row = cur.fetchone()
    index_name = row[1] if row else index_code
    index_short = row[0] if row else index_code

    # ── 加载日线数据 ──────────────────────────────────
    cur.execute(
        """
        SELECT trade_date, open, high, low, close, vol, amount
        FROM daily
        WHERE ts_code = %s AND trade_date >= %s AND trade_date <= %s
        ORDER BY trade_date
        """,
        (index_code, start_date, end_date),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        raise ValueError(f"指数 {index_code} 在 {start_date} ~ {end_date} 无数据")

    # 解析数据
    dates = [r[0] for r in rows]
    closes = [float(r[4]) for r in rows]

    # ── 计算 MACD ─────────────────────────────────────
    macd = calc_macd(closes)
    dif = macd["dif"]

    # ── 检测背离信号 ──────────────────────────────────
    # 需要足够历史数据，从第 27 天开始（26 日 EMA + 1 日缓冲）
    min_idx = MACD_SLOW + 1

    # 预计算所有背离信号
    bottom_signals = set()
    top_signals = set()
    for i in range(min_idx + DIVERGENCE_WINDOW, len(closes)):
        c = closes[: i + 1]
        d = dif[: i + 1]
        if detect_bottom_divergence(c, d, DIVERGENCE_WINDOW):
            bottom_signals.add(i)
        if detect_top_divergence(c, d, DIVERGENCE_WINDOW):
            top_signals.add(i)

    # ── 回测模拟 ──────────────────────────────────────
    initial_capital = 1000.0
    cash = initial_capital
    shares = 0.0          # 持仓份额
    cost_basis = 0.0      # 持仓成本（加权均价）
    mode = "idle"         # idle | buying | selling
    last_sell_price = 0.0
    total_buy_count = 0
    total_sell_count = 0
    buy_unit = initial_capital * BUY_PCT  # 每次买入金额 = 75

    # 记录每个交易日状态
    points: list[dict] = []

    # 从有足够 MACD 数据的第一天开始
    for i in range(min_idx + DIVERGENCE_WINDOW, len(closes)):
        td = dates[i]
        price = closes[i]
        is_bottom = i in bottom_signals
        is_top = i in top_signals

        # ── 交易逻辑 ──────────────────────────────
        action = ""   # 当日操作描述
        buy_val = 0.0
        sell_val = 0.0

        # 1) 顶背离优先处理：暂停加仓 + 卖出
        if is_top and shares > 0:
            # 卖出 20% 持仓
            sell_shares = shares * SELL_PCT
            sell_val = sell_shares * price
            cash += sell_val * (1 - SELL_COST)
            shares -= sell_shares
            last_sell_price = price
            mode = "selling"
            total_sell_count += 1
            action = f"🔴 顶背离卖出 {SELL_PCT*100:.0f}%"

            if shares < 1e-8:
                shares = 0.0
                cost_basis = 0.0
                mode = "idle"

        # 2) 底背离：启动/重启买入
        if is_bottom:
            if mode == "selling" and shares > 0:
                action += (" → " if action else "") + "🟢 底背离重启加仓"
            mode = "buying"

        # 3) 买入逻辑
        if mode == "buying" and cash >= buy_unit * 0.01:
            buy_amount = min(buy_unit, cash)
            # 计算可买份额
            buy_shares = (buy_amount * (1 - BUY_COST)) / price
            if buy_shares > 0:
                # 更新成本
                if shares > 0:
                    cost_basis = (
                        (cost_basis * shares + buy_shares * price)
                        / (shares + buy_shares)
                    )
                else:
                    cost_basis = price
                shares += buy_shares
                cash -= buy_amount
                buy_val = buy_amount
                total_buy_count += 1

                if is_bottom:
                    action += (" → " if action else "") + f"🟢 底背离建仓 {buy_amount:.0f}"
                elif not action:
                    action = f"📈 自动加仓 {buy_amount:.0f}"

        # 4) 追卖：相比上次卖出价涨超 7%，再卖 20%
        if mode == "selling" and shares > 0 and last_sell_price > 0:
            if price >= last_sell_price * (1 + TRAILING_UP_PCT):
                sell_shares = shares * SELL_PCT
                sell_val2 = sell_shares * price
                cash += sell_val2 * (1 - SELL_COST)
                shares -= sell_shares
                last_sell_price = price
                total_sell_count += 1
                sell_val += sell_val2
                action += (" → " if action else "") + f"📉 追卖 {SELL_PCT*100:.0f}%"

                if shares < 1e-8:
                    shares = 0.0
                    cost_basis = 0.0
                    mode = "idle"

        # ── 计算净值 ──────────────────────────────
        position_value = shares * price
        nav = cash + position_value
        pnl_pct = (nav / initial_capital - 1) * 100

        # 仓位占比
        position_pct = (position_value / nav * 100) if nav > 0 else 0

        points.append({
            "date": td,
            "close": round(price, 2),
            "nav": round(nav, 2),
            "cash": round(cash, 2),
            "position_value": round(position_value, 2),
            "position_pct": round(position_pct, 1),
            "shares": round(shares, 4),
            "mode": mode,
            "action": action,
            "is_bottom_signal": is_bottom,
            "is_top_signal": is_top,
        })

    # ── 汇总统计 ──────────────────────────────────
    final_nav = points[-1]["nav"] if points else initial_capital
    total_return = (final_nav / initial_capital - 1) * 100

    # 计算最大回撤
    peak = initial_capital
    max_drawdown = 0.0
    for p in points:
        if p["nav"] > peak:
            peak = p["nav"]
        dd = (p["nav"] / peak - 1) * 100
        if dd < max_drawdown:
            max_drawdown = dd

    # 统计
    bottom_days = [p for p in points if p["is_bottom_signal"]]
    top_days = [p for p in points if p["is_top_signal"]]
    buy_days = [p for p in points if "买" in p["action"] or "加仓" in p["action"] or "建仓" in p["action"]]
    sell_days = [p for p in points if "卖" in p["action"]]

    # 计算胜率（基于完整买卖周期）
    # 简化：比较最终盈亏
    win = total_return > 0

    # 年化收益率
    from datetime import date as dt_date
    d0 = dt_date.fromisoformat(points[0]["date"])
    d1 = dt_date.fromisoformat(points[-1]["date"])
    years = (d1 - d0).days / 365.25
    annual_return = ((final_nav / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0

    summary = {
        "index_name": index_name,
        "index_short": index_short,
        "index_code": index_code,
        "start_date": dates[min_idx + DIVERGENCE_WINDOW],
        "end_date": dates[-1],
        "initial_capital": initial_capital,
        "final_nav": round(final_nav, 2),
        "total_return_pct": round(total_return, 2),
        "annual_return_pct": round(annual_return, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "total_trading_days": len(points),
        "bottom_signal_count": len(bottom_days),
        "top_signal_count": len(top_days),
        "total_buy_actions": len(buy_days),
        "total_sell_actions": len(sell_days),
        "final_position_pct": points[-1]["position_pct"],
        "years": round(years, 2),
    }

    return {
        "index_name": index_name,
        "index_short": index_short,
        "index_code": index_code,
        "points": points,
        "summary": summary,
    }


# ═══════════════════════════════════════════════════════════
# HTML 报告生成
# ═══════════════════════════════════════════════════════════

def generate_html(result: dict) -> str:
    """生成自包含 HTML 报告"""
    summary = result["summary"]
    points = result["points"]
    index_name = result["index_name"]

    # 准备图表数据
    dates_js = json.dumps([p["date"] for p in points])
    nav_series = json.dumps([p["nav"] for p in points])
    close_series = json.dumps([p["close"] for p in points])
    position_pct_series = json.dumps([p["position_pct"] for p in points])

    # 信号标记
    bottom_markers = json.dumps([
        {"date": p["date"], "value": p["close"], "nav": p["nav"]}
        for p in points if p["is_bottom_signal"]
    ])
    top_markers = json.dumps([
        {"date": p["date"], "value": p["close"], "nav": p["nav"]}
        for p in points if p["is_top_signal"]
    ])

    # 买卖操作
    trades = []
    for p in points:
        if p["action"]:
            color = "#52c41a" if "买" in p["action"] or "加仓" in p["action"] or "建仓" in p["action"] else "#ff4d4f"
            trades.append({
                "date": p["date"],
                "action": p["action"],
                "nav": p["nav"],
                "color": color,
            })

    # 汇总卡片
    cards = [
        ("最终净值", f'{summary["final_nav"]:.2f}', f'{summary["total_return_pct"]:+.2f}%'),
        ("年化收益", f'{summary["annual_return_pct"]:+.2f}%', f'{summary["years"]} 年'),
        ("最大回撤", f'{summary["max_drawdown_pct"]:+.2f}%', ""),
        ("底背离信号", str(summary["bottom_signal_count"]), f'买入 {summary["total_buy_actions"]} 次'),
        ("顶背离信号", str(summary["top_signal_count"]), f'卖出 {summary["total_sell_actions"]} 次'),
        ("最终仓位", f'{summary["final_position_pct"]:.1f}%', f'{summary["total_trading_days"]} 个交易日'),
    ]

    cards_html = ""
    for title, val, sub in cards:
        color = "#52c41a" if val.startswith("+") else "#ff4d4f" if val.startswith("-") else "#e0e0e0"
        cards_html += f"""
        <div class="card">
          <h3>{title}</h3>
          <div class="val" style="color:{color}">{val}</div>
          <div class="sub">{sub}</div>
        </div>"""

    # 交易记录表
    trade_rows = ""
    for t in trades[-30:]:  # 最近 30 条
        trade_rows += f"""
        <tr>
          <td>{t['date']}</td>
          <td style="color:{t['color']}">{t['action']}</td>
          <td style="text-align:right">{t['nav']:.2f}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>背离策略回测 · {index_name}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#1a1a2e;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#e0e0e0}}
.container{{max-width:1400px;margin:0 auto;padding:24px}}
h1{{text-align:center;font-size:22px;margin-bottom:4px}}
.subtitle{{text-align:center;color:#888;font-size:13px;margin-bottom:24px}}
.stats{{display:grid;grid-template-columns:repeat(6,1fr);gap:16px;margin-bottom:24px}}
.card{{background:#16213e;border-radius:10px;padding:18px;text-align:center}}
.card h3{{color:#888;font-size:12px;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px}}
.card .val{{font-size:28px;font-weight:bold;margin-bottom:2px}}
.card .sub{{font-size:11px;color:#666}}
.chart-row{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
.chart-box{{background:#16213e;border-radius:10px;padding:16px}}
.chart-box h3{{color:#aaa;font-size:13px;margin-bottom:8px}}
.chart{{width:100%;height:400px}}
.trades{{background:#16213e;border-radius:10px;padding:16px;margin-bottom:16px}}
.trades h3{{color:#aaa;font-size:13px;margin-bottom:8px}}
.trades table{{width:100%;border-collapse:collapse;font-size:12px}}
.trades th{{color:#888;text-align:left;padding:6px 8px;border-bottom:1px solid #222}}
.trades td{{padding:5px 8px;border-bottom:1px solid #111}}
.trades tr:hover{{background:rgba(255,255,255,0.03)}}
.section-title{{color:#aaa;font-size:14px;margin:20px 0 10px}}
@media(max-width:900px){{.stats{{grid-template-columns:repeat(3,1fr)}}.chart-row{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="container">
<h1>📊 指数底背离买入顶背离卖出 · 回测报告</h1>
<div class="subtitle">
  {index_name}（{result['index_code']}）
  · {summary['start_date']} ~ {summary['end_date']}
  · MACD({MACD_FAST},{MACD_SLOW},{MACD_SIGNAL})
  · 背离窗口 {DIVERGENCE_WINDOW} 日
  · 每次买入 {BUY_PCT*100:.0f}% · 首次卖出 {SELL_PCT*100:.0f}% · 追卖阈值 +{TRAILING_UP_PCT*100:.0f}%
</div>

<div class="stats">{cards_html}</div>

<div class="chart-row">
  <div class="chart-box">
    <h3>净值曲线（初始 1000）</h3>
    <div class="chart" id="chart-nav"></div>
  </div>
  <div class="chart-box">
    <h3>仓位占比变化 (%)</h3>
    <div class="chart" id="chart-position"></div>
  </div>
</div>

<div class="chart-box" style="margin-bottom:16px">
  <h3>收盘价 & 背离信号</h3>
  <div class="chart" id="chart-price" style="height:450px"></div>
</div>

<div class="trades">
  <h3>📋 最近 30 条交易记录</h3>
  <table>
    <thead><tr><th>日期</th><th>操作</th><th style="text-align:right">净值</th></tr></thead>
    <tbody>{trade_rows}</tbody>
  </table>
</div>

<div class="subtitle" style="margin-top:20px">
  回测范围：{summary['start_date']} ~ {summary['end_date']}
  · 共 {summary['total_trading_days']} 个交易日
  · 年化 {summary['annual_return_pct']:+.2f}%
  · 最大回撤 {summary['max_drawdown_pct']:+.2f}%
</div>
</div>

<script>
// ── 数据 ──
var dates = {dates_js};
var navData = {nav_series};
var closeData = {close_series};
var posData = {position_pct_series};
var bottomMarkers = {bottom_markers};
var topMarkers = {top_markers};

// ── 净值图 ──
(function(){{
  var c = echarts.init(document.getElementById('chart-nav'));
  c.setOption({{
    tooltip: {{trigger:'axis',backgroundColor:'rgba(22,33,62,0.95)',borderColor:'#333',textStyle:{{color:'#e0e0e0'}},
      formatter:function(p){{return '<b>'+p[0].axisValue+'</b><br/>净值: <b>'+p[0].value.toFixed(2)+'</b> ('+((p[0].value-1000)/10).toFixed(1)+'%)'}}
    }},
    grid:{{left:55,right:20,top:10,bottom:30}},
    xAxis:{{type:'category',data:dates,axisLabel:{{color:'#888',fontSize:10,rotate:45,formatter:function(v){{return v.slice(5)}},interval:Math.floor(dates.length/15)}},axisLine:{{lineStyle:{{color:'#333'}}}}}},
    yAxis:{{type:'value',name:'净值',axisLabel:{{color:'#888'}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}}}},
    series:[
      {{name:'净值',type:'line',data:navData,smooth:true,symbol:'none',lineStyle:{{width:2,color:'#5470c6'}},itemStyle:{{color:'#5470c6'}},
        markLine:{{silent:true,data:[{{yAxis:1000,name:'初始',label:{{formatter:'初始 1000'}}}}],lineStyle:{{color:'#666',type:'dashed'}}}}
      }},
      {{name:'底背离',type:'scatter',data:bottomMarkers.map(function(m){{return[m.date,m.nav]}}),symbolSize:10,symbol:'triangle',itemStyle:{{color:'#52c41a'}}}},
      {{name:'顶背离',type:'scatter',data:topMarkers.map(function(m){{return[m.date,m.nav]}}),symbolSize:10,symbol:'triangle',symbolRotate:180,itemStyle:{{color:'#ff4d4f'}}}}
    ]
  }});
  window.addEventListener('resize',function(){{c.resize()}});
}})();

// ── 仓位图 ──
(function(){{
  var c = echarts.init(document.getElementById('chart-position'));
  c.setOption({{
    tooltip: {{trigger:'axis',backgroundColor:'rgba(22,33,62,0.95)',borderColor:'#333',textStyle:{{color:'#e0e0e0'}},
      formatter:function(p){{return '<b>'+p[0].axisValue+'</b><br/>仓位: <b>'+p[0].value.toFixed(1)+'%</b>'}}
    }},
    grid:{{left:55,right:20,top:10,bottom:30}},
    xAxis:{{type:'category',data:dates,axisLabel:{{color:'#888',fontSize:10,rotate:45,formatter:function(v){{return v.slice(5)}},interval:Math.floor(dates.length/15)}},axisLine:{{lineStyle:{{color:'#333'}}}}}},
    yAxis:{{type:'value',name:'仓位%',max:100,axisLabel:{{color:'#888'}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}}}},
    series:[
      {{name:'仓位',type:'line',data:posData,smooth:true,symbol:'none',lineStyle:{{width:2,color:'#fac858'}},
        areaStyle:{{color:new echarts.graphic.LinearGradient(0,0,0,1,[{{offset:0,color:'rgba(250,200,88,0.4)'}},{{offset:1,color:'rgba(250,200,88,0.05)'}}])}},
        markLine:{{silent:true,data:[{{yAxis:100,name:'满仓'}}],lineStyle:{{color:'#666',type:'dashed'}}}}
      }}
    ]
  }});
  window.addEventListener('resize',function(){{c.resize()}});
}})();

// ── 价格 + 背离信号图 ──
(function(){{
  var c = echarts.init(document.getElementById('chart-price'));
  c.setOption({{
    tooltip: {{trigger:'axis',backgroundColor:'rgba(22,33,62,0.95)',borderColor:'#333',textStyle:{{color:'#e0e0e0'}}}},
    legend:{{data:['收盘价','底背离','顶背离'],top:5,textStyle:{{color:'#aaa'}}}},
    grid:{{left:65,right:20,top:40,bottom:30}},
    xAxis:{{type:'category',data:dates,axisLabel:{{color:'#888',fontSize:10,rotate:45,formatter:function(v){{return v.slice(5)}},interval:Math.floor(dates.length/15)}},axisLine:{{lineStyle:{{color:'#333'}}}}}},
    yAxis:{{type:'value',name:'收盘价',axisLabel:{{color:'#888'}},splitLine:{{lineStyle:{{color:'#222',type:'dashed'}}}}}},
    series:[
      {{name:'收盘价',type:'line',data:closeData,smooth:false,symbol:'none',lineStyle:{{width:1.5,color:'#999'}},itemStyle:{{color:'#999'}}}},
      {{name:'底背离',type:'scatter',data:bottomMarkers.map(function(m){{return[m.date,m.value]}}),symbolSize:12,symbol:'triangle',itemStyle:{{color:'#52c41a'}}}},
      {{name:'顶背离',type:'scatter',data:topMarkers.map(function(m){{return[m.date,m.value]}}),symbolSize:12,symbol:'triangle',symbolRotate:180,itemStyle:{{color:'#ff4d4f'}}}}
    ]
  }});
  window.addEventListener('resize',function(){{c.resize()}});
}})();
</script>
</body>
</html>"""

    return html


# ═══════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="指数底背离买入顶背离卖出 · 回测脚本"
    )
    parser.add_argument(
        "--index",
        type=str,
        default="399006.SZ",
        help="指数代码 (default: 399006.SZ 创业板指)",
    )
    parser.add_argument(
        "--start",
        type=str,
        default="2022-01-01",
        help="回测起始日期 (default: 2022-01-01)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default="2026-06-20",
        help="回测截止日期 (default: 2026-06-20)",
    )
    parser.add_argument(
        "--buy-pct",
        type=float,
        default=0.075,
        help="每次买入仓位比例 (default: 0.075 = 7.5%%)",
    )
    parser.add_argument(
        "--sell-pct",
        type=float,
        default=0.20,
        help="每次卖出持仓比例 (default: 0.20 = 20%%)",
    )
    parser.add_argument(
        "--trailing",
        type=float,
        default=0.07,
        help="追卖涨幅阈值 (default: 0.07 = 7%%)",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=20,
        help="背离观察窗口 (default: 20)",
    )
    args = parser.parse_args()

    # 覆盖全局参数
    global BUY_PCT, SELL_PCT, TRAILING_UP_PCT, DIVERGENCE_WINDOW
    BUY_PCT = args.buy_pct
    SELL_PCT = args.sell_pct
    TRAILING_UP_PCT = args.trailing
    DIVERGENCE_WINDOW = args.window

    # 确认指数存在
    conn = _pg()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM daily WHERE ts_code = %s",
        (args.index,),
    )
    cnt = cur.fetchone()[0]
    conn.close()

    if cnt == 0:
        print(f"❌ 指数 {args.index} 在 daily 表中无数据")
        print(f"   可用指数: 000001.SH, 000688.SH, 000698.SH, 399001.SZ, 399006.SZ")
        return

    print(f"\n{'='*80}")
    print(f"  指数底背离买入顶背离卖出 · 回测")
    print(f"  指数: {args.index}  |  {args.start} ~ {args.end}")
    print(f"  MACD({MACD_FAST},{MACD_SLOW},{MACD_SIGNAL})  |  背离窗口: {DIVERGENCE_WINDOW} 日")
    print(f"  买入: {BUY_PCT*100:.1f}%/次  |  卖出: {SELL_PCT*100:.0f}%/次  |  追卖: +{TRAILING_UP_PCT*100:.0f}%")
    print(f"{'='*80}\n")

    result = run_backtest(args.index, args.start, args.end)

    summary = result["summary"]
    print(f"  📊 回测结果: {summary['start_date']} ~ {summary['end_date']}")
    print(f"     初始资金: {summary['initial_capital']:.2f}")
    print(f"     最终净值: {summary['final_nav']:.2f}")
    print(f"     总收益率: {summary['total_return_pct']:+.2f}%")
    print(f"     年化收益: {summary['annual_return_pct']:+.2f}%")
    print(f"     最大回撤: {summary['max_drawdown_pct']:+.2f}%")
    print(f"     底背离信号: {summary['bottom_signal_count']} 次  |  顶背离信号: {summary['top_signal_count']} 次")
    print(f"     买入操作: {summary['total_buy_actions']} 次  |  卖出操作: {summary['total_sell_actions']} 次")
    print(f"     最终仓位: {summary['final_position_pct']:.1f}%")
    print()

    # 信号日期列表
    points = result["points"]
    bottom_dates = [p["date"] for p in points if p["is_bottom_signal"]]
    top_dates = [p["date"] for p in points if p["is_top_signal"]]
    if bottom_dates:
        print(f"  🟢 底背离日期 ({len(bottom_dates)} 次):")
        for d in bottom_dates:
            p = next(x for x in points if x["date"] == d)
            print(f"     {d}  close={p['close']}  nav={p['nav']}")
    if top_dates:
        print(f"  🔴 顶背离日期 ({len(top_dates)} 次):")
        for d in top_dates:
            p = next(x for x in points if x["date"] == d)
            print(f"     {d}  close={p['close']}  nav={p['nav']}")

    # 生成 HTML
    html = generate_html(result)
    out_path = Path(__file__).resolve().parent / "backtest_divergence_strategy.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n  ✅ HTML 报告: {out_path}")


if __name__ == "__main__":
    main()
