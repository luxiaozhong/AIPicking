"""
分析 中际旭创 (300308) 2025年6月后 新高→回撤>20% 的时段
"""

import psycopg2
import pandas as pd

DB_URL = "postgresql://aipicking:aipicking_dev_pwd@localhost:5432/aipicking"

conn = psycopg2.connect(DB_URL)

# 查询 300308 所有日线数据（ts_code 格式可能为 "300308.SZ"）
# 先看实际存储格式
cur = conn.cursor()
cur.execute("""
    SELECT DISTINCT ts_code FROM daily WHERE ts_code LIKE '%300308%'
""")
ts_codes = [r[0] for r in cur.fetchall()]
print(f"300308 在 daily 表中格式: {ts_codes}")

if not ts_codes:
    print("未找到 300308 的日线数据！")
    conn.close()
    exit()

ts_code = ts_codes[0]

# 获取 2025-06 之后的数据
df = pd.read_sql_query("""
    SELECT trade_date, open, high, low, close, pre_close, vol, amount, adj_close
    FROM daily
    WHERE ts_code = %s AND trade_date >= '2025-06-01'
    ORDER BY trade_date ASC
""", conn, params=(ts_code,))
conn.close()

print(f"\n数据范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
print(f"总交易日: {len(df)}")

# 使用 close 作为参考价
close = df['close'].values
dates = df['trade_date'].values

# 找新高后回撤 > 20% 的时段
print("\n" + "=" * 90)
print("新高（rolling high）后回撤超过 20% 的时段分析")
print("=" * 90)

# 逐日追踪当前 rolling high
rolling_high = 0
rolling_high_date = ""
results = []

for i in range(len(df)):
    price = close[i]
    date = dates[i]

    # 新高判断
    if price > rolling_high:
        rolling_high = price
        rolling_high_date = date

    # 计算从 rolling high 回撤幅度
    if rolling_high > 0:
        drawdown_pct = (price - rolling_high) / rolling_high * 100  # 负值表示回撤
        if drawdown_pct <= -20:
            results.append({
                '新高日期': rolling_high_date,
                '新高价格': round(rolling_high, 2),
                '回撤日期': date,
                '回撤价格': round(price, 2),
                '回撤幅度%': round(drawdown_pct, 1),
                '从新高到回撤天数': (pd.to_datetime(date) - pd.to_datetime(rolling_high_date)).days,
            })

if not results:
    print("\n未发现 2025年6月后新高回撤超过20%的时段。")
else:
    # 合并连续回撤区间
    merged = []
    current = None
    for r in results:
        if current is None:
            current = r.copy()
        elif r['新高日期'] == current['新高日期']:
            # 同一新高，更新最深回撤
            if r['回撤幅度%'] < current['回撤幅度%']:
                current['回撤日期'] = r['回撤日期']
                current['回撤价格'] = r['回撤价格']
                current['回撤幅度%'] = r['回撤幅度%']
                current['从新高到回撤天数'] = r['从新高到回撤天数']
        else:
            merged.append(current)
            current = r.copy()
    if current:
        merged.append(current)

    print(f"\n共找到 {len(merged)} 个新高→回撤>20% 时段：\n")

    for i, m in enumerate(merged):
        print(f"--- 第 {i+1} 段 ---")
        print(f"  创新高日期: {m['新高日期']}  价格: ¥{m['新高价格']}")
        print(f"  最深回撤日: {m['回撤日期']}  价格: ¥{m['回撤价格']}")
        print(f"  回撤幅度: {m['回撤幅度%']}%")
        print(f"  下跌历时: {m['从新高到回撤天数']} 个自然日")
        print()

    # 显示所有触及-20%的日期明细（含期间日内最低价）
    print("=" * 90)
    print("明细：按新高分段展示")
    print("=" * 90)

    for m in merged:
        hd = m['新高日期']
        dd = m['回撤日期']
        print(f"\n新高 {hd} (¥{m['新高价格']}) → 回撤至 {dd} (¥{m['回撤价格']}, {m['回撤幅度%']}%)")

        # 期间日内最低点
        seg = df[(df['trade_date'] >= hd) & (df['trade_date'] <= dd)]
        max_close = seg['close'].max()
        min_close = seg['close'].min()
        min_low = seg['low'].min()
        min_low_row = seg.loc[seg['low'].idxmin()]
        max_dd_close = (min_close - max_close) / max_close * 100
        max_dd_low = (min_low - max_close) / max_close * 100

        print(f"  期间收盘价范围: ¥{min_close:.2f} ~ ¥{max_close:.2f} (最低收盘回撤 {max_dd_close:.1f}%)")
        print(f"  期间最低日内价: ¥{min_low:.2f} ({min_low_row['trade_date']}) (日内最大回撤 {max_dd_low:.1f}%)")
        print(f"  成交量: 最高 {seg['vol'].max():.0f} 最低 {seg['vol'].min():.0f}")

        # 是否在期间出现了新低点后才反弹
        after_low = df[(df['trade_date'] >= min_low_row['trade_date']) & (df['trade_date'] <= dd)]
        if len(after_low) > 1:
            print(f"  日内最低点 ({min_low_row['trade_date']}) 后走势: → 最终 {after_low.iloc[-1]['close']:.2f}")

print("\n分析完成。")
