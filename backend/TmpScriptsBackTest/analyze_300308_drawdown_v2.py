"""
分析 中际旭创 (300308) 2025年6月后 局部新高→回撤>20% — 更完整的分析
"""
import psycopg2
import pandas as pd
import numpy as np

DB_URL = "postgresql://aipicking:aipicking_dev_pwd@localhost:5432/aipicking"
conn = psycopg2.connect(DB_URL)

# 获取数据
df = pd.read_sql_query("""
    SELECT trade_date, open, high, low, close, pre_close, vol, amount, adj_close
    FROM daily
    WHERE ts_code = '300308.SZ' AND trade_date >= '2025-06-01'
    ORDER BY trade_date ASC
""", conn)
conn.close()

close = df['close'].values
high = df['high'].values
low = df['low'].values
dates = df['trade_date'].values

print(f"数据范围: {dates[0]} ~ {dates[-1]}, 共 {len(df)} 个交易日")
print(f"2025-06 以来: 最高收盘 ¥{close.max():.2f}, 最低收盘 ¥{close.min():.2f}")
print(f"整体波动幅度: {(close.max()/close.min() - 1)*100:.1f}%")
print(f"区间: 从 {dates[0]} ¥{close[0]:.2f} 到 {dates[-1]} ¥{close[-1]:.2f}, 总涨跌幅 {(close[-1]/close[0]-1)*100:.1f}%")

print("\n" + "=" * 95)
print("局部高点回撤分析（滑动窗口找局部峰值 → 后续回撤 > 20%）")
print("=" * 95)

# 用滑动窗口找局部高点：往前 N 天、往后 N 天都是最高的
WINDOW = 10
peak_indices = []
for i in range(WINDOW, len(close) - WINDOW):
    before = close[i-WINDOW:i]
    after = close[i+1:i+WINDOW+1]
    if close[i] > before.max() and close[i] > after.max():
        peak_indices.append(i)

# 也加入开头的峰（只往后看）
for i in range(0, min(WINDOW, len(close))):
    after_end = min(i + WINDOW + 1, len(close))
    if after_end > i + 1 and close[i] > close[i+1:after_end].max():
        peak_indices.append(i)

peak_indices = sorted(set(peak_indices))
print(f"\n用 ±{WINDOW} 天窗口找到 {len(peak_indices)} 个局部高点")

# 对每个局部高点，追踪后续走势直到价格超过该高点或到数据末尾
drawdown_events = []

for pi in peak_indices:
    peak_price = close[pi]
    peak_date = dates[pi]
    max_dd = 0
    max_dd_date = ""
    max_dd_price = 0
    max_dd_low = 0
    max_dd_low_date = ""
    recovered = False
    recovery_date = ""

    for j in range(pi + 1, len(close)):
        dd = (close[j] - peak_price) / peak_price * 100  # negative = drawdown
        dd_low = (low[j] - peak_price) / peak_price * 100

        if dd < max_dd:
            max_dd = dd
            max_dd_date = dates[j]
            max_dd_price = close[j]
        if dd_low < max_dd_low:
            max_dd_low = dd_low
            max_dd_low_date = dates[j]

        # 如果价格回到峰值上方，视为恢复
        if close[j] >= peak_price:
            recovered = True
            recovery_date = dates[j]
            break

    if max_dd <= -20:
        days_to_low = (pd.to_datetime(max_dd_date) - pd.to_datetime(peak_date)).days
        drawdown_events.append({
            'local_peak_date': peak_date,
            'local_peak_price': round(peak_price, 2),
            'max_dd_pct': round(max_dd, 1),
            'max_dd_date': max_dd_date,
            'max_dd_price': round(max_dd_price, 2),
            'max_dd_low_pct': round(max_dd_low, 1),
            'max_dd_low_date': max_dd_low_date,
            'days_to_low': days_to_low,
            'recovered': recovered,
            'recovery_date': recovery_date if recovered else '未恢复',
        })

# 去重：同一峰值，保留最深回撤
unique_events = []
seen_peaks = set()
for e in sorted(drawdown_events, key=lambda x: x['max_dd_pct']):
    if e['local_peak_date'] not in seen_peaks:
        seen_peaks.add(e['local_peak_date'])
        unique_events.append(e)
unique_events.sort(key=lambda x: x['local_peak_date'])

print(f"其中回撤 > 20% 的事件: {len(unique_events)} 个\n")

for i, e in enumerate(unique_events):
    print(f"━━━ 事件 {i+1} ━━━")
    print(f"  局部高点: {e['local_peak_date']}  收盘价 ¥{e['local_peak_price']}")
    print(f"  最深回撤: {e['max_dd_date']}  收盘价 ¥{e['max_dd_price']}  ({e['max_dd_pct']}%)")
    print(f"  日内最低: {e['max_dd_low_date']}  ¥? (日内最大回撤 {e['max_dd_low_pct']}%)")
    print(f"  从高点到低点: {e['days_to_low']} 个自然日")
    print(f"  恢复情况: {'已恢复于 ' + e['recovery_date'] if e['recovered'] else '至今未恢复'}")
    print()

# 价格走势概览
print("=" * 95)
print("价格走势概览（关键价格区间）")
print("=" * 95)
print(f"2025-06-03  ~  2025-09-11: ¥{close[0]:.2f} → ¥438.57 (新高)")
print(f"2025-09-11  ~  2025-10-14: ¥438.57 → ¥345.10 (-21.3%)")
# Check what happened after Oct 14
oct14_idx = list(dates).index('2025-10-14') if '2025-10-14' in dates else None
if oct14_idx:
    print(f"2025-10-14  ~  2025-10-31: ¥{close[oct14_idx]:.2f} → "
          f"¥{close[min(oct14_idx+13, len(close)-1)]:.2f} (短期反弹)")
# 2026 年份
jan_idx = [i for i, d in enumerate(dates) if d.startswith('2026')]
if jan_idx:
    idx = jan_idx[0]
    print(f"2026-01-02  ~  {dates[-1]}: ¥{close[idx]:.2f} → ¥{close[-1]:.2f}")
    seg = close[idx:]
    peak_2026 = seg.max()
    peak_2026_i = idx + list(seg).index(peak_2026)
    print(f"  2026最高: {dates[peak_2026_i]} ¥{peak_2026:.2f}")
    trough_2026 = seg.min()
    trough_2026_i = idx + list(seg).index(trough_2026)
    drawdown_2026 = (trough_2026 - peak_2026) / peak_2026 * 100
    print(f"  2026最低: {dates[trough_2026_i]} ¥{trough_2026:.2f} (从最高回撤 {drawdown_2026:.1f}%)")
