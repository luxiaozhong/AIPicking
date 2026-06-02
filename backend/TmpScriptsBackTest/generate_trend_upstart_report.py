"""
生成 Trend Upstart Flow 批量回测 HTML 汇总报告
读取 batch_backtest_reports 表中名为 'Trend Upstart Flow_20260101_20260529' 的报告
"""
import asyncio
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

from app.database import AsyncSessionLocal
from app.models.backtest import BatchBacktestReport
from sqlalchemy import select

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


async def fetch_report():
    async with AsyncSessionLocal() as session:
        stmt = select(BatchBacktestReport).where(
            BatchBacktestReport.name.ilike('%Trend Upstart%')
        )
        result = await session.execute(stmt)
        report = result.scalars().first()
        if not report:
            raise ValueError("Report not found: Trend Upstart Flow")
        return report


def parse_report(report):
    """解析报告数据"""
    daily_results = json.loads(report.daily_results) if report.daily_results else []
    config = json.loads(report.config) if report.config else {}

    # 收集所有日的统计
    days_data = []
    all_signals = 0

    for day in daily_results:
        if day.get('status') != 'completed':
            continue
        summary = day.get('summary', {})
        recs = day.get('recommendations', [])
        if not recs:
            continue

        cutoff_date = day['cutoff_date']
        n = summary.get('total_recommendations', len(recs))
        all_signals += n

        # 计算平均值（从 individual recommendations）
        returns_0d = [r['return_0d'] for r in recs if r.get('return_0d') is not None]
        returns_3d = [r['return_3d'] for r in recs if r.get('return_3d') is not None]
        returns_7d = [r['return_7d'] for r in recs if r.get('return_7d') is not None]
        returns_15d = [r['return_15d'] for r in recs if r.get('return_15d') is not None]

        avg_0d = sum(returns_0d) / len(returns_0d) if returns_0d else 0
        avg_3d = sum(returns_3d) / len(returns_3d) if returns_3d else 0
        avg_7d = sum(returns_7d) / len(returns_7d) if returns_7d else 0
        avg_15d = sum(returns_15d) / len(returns_15d) if returns_15d else 0

        win_3d = sum(1 for r in returns_3d if r > 0)
        win_7d = sum(1 for r in returns_7d if r > 0)
        win_15d = sum(1 for r in returns_15d if r > 0)

        total_3d = len(returns_3d)
        total_7d = len(returns_7d)
        total_15d = len(returns_15d)

        days_data.append({
            'cutoff_date': cutoff_date,
            'date_obj': datetime.strptime(cutoff_date, '%Y%m%d'),
            'n': n,
            'avg_0d': avg_0d,
            'avg_3d': avg_3d,
            'avg_7d': avg_7d,
            'avg_15d': avg_15d,
            'win_3d': win_3d,
            'win_7d': win_7d,
            'win_15d': win_15d,
            'total_3d': total_3d,
            'total_7d': total_7d,
            'total_15d': total_15d,
            'recommendations': recs,
            'returns_0d': returns_0d,
            'returns_3d': returns_3d,
            'returns_7d': returns_7d,
            'returns_15d': returns_15d,
        })

    # 排序
    days_data.sort(key=lambda d: d['date_obj'])

    # 总体统计
    all_r3 = []
    all_r7 = []
    all_r15 = []
    for d in days_data:
        all_r3.extend(d['returns_3d'])
        all_r7.extend(d['returns_7d'])
        all_r15.extend(d['returns_15d'])

    overall = {
        'total_signals': all_signals,
        'total_days': len(days_data),
        'avg_daily_signals': all_signals / len(days_data) if days_data else 0,
        'avg_return_3d': sum(all_r3) / len(all_r3) if all_r3 else 0,
        'avg_return_7d': sum(all_r7) / len(all_r7) if all_r7 else 0,
        'avg_return_15d': sum(all_r15) / len(all_r15) if all_r15 else 0,
        'win_rate_3d': sum(1 for r in all_r3 if r > 0) / len(all_r3) if all_r3 else 0,
        'win_rate_7d': sum(1 for r in all_r7 if r > 0) / len(all_r7) if all_r7 else 0,
        'win_rate_15d': sum(1 for r in all_r15 if r > 0) / len(all_r15) if all_r15 else 0,
        'win_count_3d': sum(1 for r in all_r3 if r > 0),
        'win_count_7d': sum(1 for r in all_r7 if r > 0),
        'win_count_15d': sum(1 for r in all_r15 if r > 0),
        'total_3d': len(all_r3),
        'total_7d': len(all_r7),
        'total_15d': len(all_r15),
        'best_3d': max(all_r3) if all_r3 else 0,
        'worst_3d': min(all_r3) if all_r3 else 0,
        'best_7d': max(all_r7) if all_r7 else 0,
        'worst_7d': min(all_r7) if all_r7 else 0,
        'best_15d': max(all_r15) if all_r15 else 0,
        'worst_15d': min(all_r15) if all_r15 else 0,
    }

    # 按月分组
    months = defaultdict(list)
    for d in days_data:
        ym = d['date_obj'].strftime('%Y年%-m月')
        months[ym].append(d)

    return {
        'report_name': report.name,
        'start_date': report.start_date,
        'end_date': report.end_date,
        'config': config,
        'overall': overall,
        'days_data': days_data,
        'months': months,
    }


def fmt_pct(v):
    """格式化百分比"""
    if v == 0:
        return '0.00%'
    return f'{v * 100:+.2f}%'


def fmt_pct_pos(v):
    """格式化百分比带颜色class，如果数据为空返回 N/A"""
    if v is None or (isinstance(v, float) and v == 0.0):
        # Check if this is a "true zero" or "no data" — we rely on caller for context
        pass
    pct = f'{v * 100:+.2f}%'
    cls = 'pos' if v > 0 else ('neg' if v < 0 else '')
    return cls, pct

def fmt_pct_or_na(v):
    """格式化百分比，如果无有效数据返回 N/A"""
    if v is None:
        return '', 'N/A'
    pct = f'{v * 100:+.2f}%'
    cls = 'pos' if v > 0 else ('neg' if v < 0 else '')
    return cls, pct


def fmt_winrate(win, total):
    """格式化胜率"""
    if total == 0:
        return 'N/A'
    rate = win / total * 100
    return f'{win}/{total} ({rate:.0f}%)'


def generate_html(data):
    """生成 HTML 报告"""
    o = data['overall']

    months_sorted = sorted(data['months'].items())

    html = f'''<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>{data['report_name']} 批量回测报告</title>

    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1300px; margin: 0 auto; padding: 20px; background: #f8f9fa; color: #333; }}
        h1 {{ color: #1a1a2e; border-bottom: 3px solid #e74c3c; padding-bottom: 10px; }}
        h2 {{ color: #1a1a2e; border-bottom: 2px solid #ddd; padding-bottom: 8px; margin-top: 40px; }}
        h3 {{ color: #2c3e50; margin-top: 30px; }}
        h4 {{ color: #34495e; margin-top: 25px; padding: 8px 12px; background: #ecf0f1; border-radius: 4px; }}
        .meta {{ background: #fff; padding: 15px; border-radius: 8px; margin-bottom: 30px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .meta p {{ margin: 4px 0; color: #666; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 6px; overflow: hidden; font-size: 13px; }}
        th {{ background: #1a1a2e; color: #fff; padding: 10px 12px; text-align: center; font-weight: 600; font-size: 13px; white-space: nowrap; }}
        td {{ padding: 8px 12px; text-align: center; border-bottom: 1px solid #eee; font-size: 13px; }}
        tr:hover {{ background: #f0f4ff; }}
        .pos {{ color: #e74c3c; font-weight: 600; }}
        .neg {{ color: #27ae60; font-weight: 600; }}
        .summary-box {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #fff; padding: 15px 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }}
        .stat-card .label {{ font-size: 12px; color: #999; text-transform: uppercase; }}
        .stat-card .value {{ font-size: 24px; font-weight: 700; color: #1a1a2e; margin: 5px 0; }}
        .stat-card .sub {{ font-size: 12px; color: #666; }}
        tr.total-row {{ font-weight: 700; background: #fff3cd !important; }}
        tr.month-total {{ font-weight: 700; background: #e8f4fd !important; }}
    </style>

</head><body>
<h1>📊 {data['report_name']} 批量回测报告</h1>
<div class='meta'>
<p><strong>生成时间：</strong>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<p><strong>回测范围：</strong>{data['start_date'][:4]}-{data['start_date'][4:6]}-{data['start_date'][6:]} ~ {data['end_date'][:4]}-{data['end_date'][4:6]}-{data['end_date'][6:]}（{o['total_days']} 个有信号交易日）</p>
<p><strong>策略名称：</strong>{data['report_name']}</p>
<p><strong>追踪周期：</strong>{data['config'].get('track_days', 'N/A')} 天</p>
</div>
<h2>📈 关键指标</h2>
<div class='summary-box'>
<div class='stat-card'><div class='label'>有信号交易日</div><div class='value'>{o['total_days']}</div><div class='sub'>天</div></div>
<div class='stat-card'><div class='label'>总信号数</div><div class='value'>{o['total_signals']}</div><div class='sub'>日均 {o['avg_daily_signals']:.1f} 条</div></div>
<div class='stat-card'><div class='label'>3日平均收益</div><div class='value' style='color:{'#e74c3c' if o['avg_return_3d'] > 0 else '#27ae60'}'>{fmt_pct(o['avg_return_3d'])}</div><div class='sub'>上涨率 {fmt_winrate(o['win_count_3d'], o['total_3d'])}</div></div>
<div class='stat-card'><div class='label'>7日平均收益</div><div class='value' style='color:{'#e74c3c' if o['avg_return_7d'] > 0 else '#27ae60'}'>{fmt_pct(o['avg_return_7d'])}</div><div class='sub'>上涨率 {fmt_winrate(o['win_count_7d'], o['total_7d'])}</div></div>
<div class='stat-card'><div class='label'>15日平均收益</div><div class='value' style='color:{'#e74c3c' if o['avg_return_15d'] > 0 else '#27ae60'}'>{fmt_pct(o['avg_return_15d'])}</div><div class='sub'>上涨率 {fmt_winrate(o['win_count_15d'], o['total_15d'])}</div></div>
<div class='stat-card'><div class='label'>3日最大盈利</div><div class='value' style='color:#e74c3c'>{fmt_pct(o['best_3d'])}</div><div class='sub'>最大亏损 {fmt_pct(o['worst_3d'])}</div></div>
<div class='stat-card'><div class='label'>7日最大盈利</div><div class='value' style='color:#e74c3c'>{fmt_pct(o['best_7d'])}</div><div class='sub'>最大亏损 {fmt_pct(o['worst_7d'])}</div></div>
<div class='stat-card'><div class='label'>15日最大盈利</div><div class='value' style='color:#e74c3c'>{fmt_pct(o['best_15d'])}</div><div class='sub'>最大亏损 {fmt_pct(o['worst_15d'])}</div></div>
</div>
<h2>一、每日汇总</h2>
'''

    for month_label, days in months_sorted:
        html += f'<h3>{month_label}（{len(days)}天）</h3>\n'
        html += '''<table><thead><tr>
<th>信号日</th>
<th>平均当日涨跌</th>
<th>平均3日涨跌</th>
<th>平均7日涨跌</th>
<th>平均15日涨跌</th>
<th>上涨占比(3日)</th>
<th>上涨占比(7日)</th>
<th>上涨占比(15日)</th>
</tr></thead><tbody>
'''

        # 月小计
        m_avg_0 = sum(d['avg_0d'] for d in days) / len(days) if days else 0
        m_avg_3 = sum(d['avg_3d'] for d in days) / len(days) if days else 0
        m_avg_7 = sum(d['avg_7d'] for d in days) / len(days) if days else 0
        m_avg_15 = sum(d['avg_15d'] for d in days) / len(days) if days else 0
        m_win3 = sum(d['win_3d'] for d in days)
        m_win7 = sum(d['win_7d'] for d in days)
        m_win15 = sum(d['win_15d'] for d in days)
        m_tot3 = sum(d['total_3d'] for d in days)
        m_tot7 = sum(d['total_7d'] for d in days)
        m_tot15 = sum(d['total_15d'] for d in days)
        m_n = sum(d['n'] for d in days)

        for d in days:
            cls0, p0 = fmt_pct_pos(d['avg_0d'])
            cls3, p3 = fmt_pct_pos(d['avg_3d'])
            cls7, p7 = fmt_pct_pos(d['avg_7d'])
            cls15, p15 = fmt_pct_pos(d['avg_15d'])

            html += f'''<tr>
<td>{d['cutoff_date'][:4]}-{d['cutoff_date'][4:6]}-{d['cutoff_date'][6:]}</td>
<td class='{cls0}'>{p0}</td>
<td class='{cls3}'>{p3}</td>
<td class='{cls7}'>{p7}</td>
<td class='{cls15}'>{p15}</td>
<td>{fmt_winrate(d['win_3d'], d['total_3d'])}</td>
<td>{fmt_winrate(d['win_7d'], d['total_7d'])}</td>
<td>{fmt_winrate(d['win_15d'], d['total_15d'])}</td>
</tr>
'''

        # 月合计行
        cls0m, p0m = fmt_pct_pos(m_avg_0)
        cls3m, p3m = fmt_pct_pos(m_avg_3)
        cls7m, p7m = fmt_pct_pos(m_avg_7)
        cls15m, p15m = fmt_pct_pos(m_avg_15)

        html += f'''<tr class='month-total'>
<td><strong>{month_label} 小计（{m_n}条/{len(days)}天）</strong></td>
<td class='{cls0m}'><strong>{p0m}</strong></td>
<td class='{cls3m}'><strong>{p3m}</strong></td>
<td class='{cls7m}'><strong>{p7m}</strong></td>
<td class='{cls15m}'><strong>{p15m}</strong></td>
<td><strong>{fmt_winrate(m_win3, m_tot3)}</strong></td>
<td><strong>{fmt_winrate(m_win7, m_tot7)}</strong></td>
<td><strong>{fmt_winrate(m_win15, m_tot15)}</strong></td>
</tr>
'''
        html += '</tbody></table>\n'

    # 合计行
    html += '<h3>全期合计</h3>\n'
    html += '''<table><thead><tr>
<th>信号日</th>
<th>平均当日涨跌</th>
<th>平均3日涨跌</th>
<th>平均7日涨跌</th>
<th>平均15日涨跌</th>
<th>上涨占比(3日)</th>
<th>上涨占比(7日)</th>
<th>上涨占比(15日)</th>
</tr></thead><tbody>
'''
    cls0o, p0o = fmt_pct_pos(0)  # not enough data, skip 0d overall
    cls3o, p3o = fmt_pct_pos(o['avg_return_3d'])
    cls7o, p7o = fmt_pct_pos(o['avg_return_7d'])
    cls15o, p15o = fmt_pct_pos(o['avg_return_15d'])
    html += f'''<tr class='total-row'>
<td><strong>合计（{o['total_signals']}条/{o['total_days']}天）</strong></td>
<td>-</td>
<td class='{cls3o}'><strong>{p3o}</strong></td>
<td class='{cls7o}'><strong>{p7o}</strong></td>
<td class='{cls15o}'><strong>{p15o}</strong></td>
<td><strong>{fmt_winrate(o['win_count_3d'], o['total_3d'])}</strong></td>
<td><strong>{fmt_winrate(o['win_count_7d'], o['total_7d'])}</strong></td>
<td><strong>{fmt_winrate(o['win_count_15d'], o['total_15d'])}</strong></td>
</tr>
'''
    html += '</tbody></table>\n'

    # 二、按评分分组统计
    html += '<h2>二、评分与收益关系</h2>\n'
    # 先收集所有信号按评分分组
    all_signals_list = []
    for d in data['days_data']:
        for r in d['recommendations']:
            all_signals_list.append({
                'score': r.get('score', 0),
                'return_3d': r.get('return_3d'),
                'return_7d': r.get('return_7d'),
                'return_15d': r.get('return_15d'),
            })

    # 评分分组
    score_bins = [
        ('< 60', lambda s: s < 60),
        ('60-75', lambda s: 60 <= s < 75),
        ('75-90', lambda s: 75 <= s < 90),
        ('90-105', lambda s: 90 <= s < 105),
        ('≥ 105', lambda s: s >= 105),
    ]

    html += '''<table><thead><tr>
<th>评分区间</th>
<th>信号数</th>
<th>平均3日收益</th>
<th>平均7日收益</th>
<th>平均15日收益</th>
<th>上涨占比(3日)</th>
<th>上涨占比(7日)</th>
<th>上涨占比(15日)</th>
</tr></thead><tbody>
'''
    for label, pred in score_bins:
        group = [s for s in all_signals_list if pred(s['score'])]
        n = len(group)
        if n == 0:
            html += f'<tr><td>{label}</td><td>0</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>\n'
            continue
        r3 = [s['return_3d'] for s in group if s['return_3d'] is not None]
        r7 = [s['return_7d'] for s in group if s['return_7d'] is not None]
        r15 = [s['return_15d'] for s in group if s['return_15d'] is not None]
        avg3 = sum(r3) / len(r3) if r3 else 0
        avg7 = sum(r7) / len(r7) if r7 else 0
        avg15 = sum(r15) / len(r15) if r15 else 0
        w3 = sum(1 for x in r3 if x > 0)
        w7 = sum(1 for x in r7 if x > 0)
        w15 = sum(1 for x in r15 if x > 0)
        c3, p3 = fmt_pct_pos(avg3)
        c7, p7 = fmt_pct_pos(avg7)
        c15, p15 = fmt_pct_pos(avg15)
        html += f'''<tr>
<td>{label}</td>
<td><strong>{n}</strong></td>
<td class='{c3}'>{p3}</td>
<td class='{c7}'>{p7}</td>
<td class='{c15}'>{p15}</td>
<td>{fmt_winrate(w3, len(r3))}</td>
<td>{fmt_winrate(w7, len(r7))}</td>
<td>{fmt_winrate(w15, len(r15))}</td>
</tr>
'''
    html += '</tbody></table>\n'

    # 三、每月信号数分布（柱状图用表格替代）
    html += '<h2>三、月度统计汇总</h2>\n'
    html += '''<table><thead><tr>
<th>月份</th>
<th>有信号天数</th>
<th>总信号数</th>
<th>日均信号</th>
<th>平均3日收益</th>
<th>平均7日收益</th>
<th>平均15日收益</th>
<th>上涨占比(3日)</th>
<th>上涨占比(7日)</th>
<th>上涨占比(15日)</th>
</tr></thead><tbody>
'''
    for month_label, days in months_sorted:
        n = sum(d['n'] for d in days)
        nd = len(days)
        avg_daily = n / nd if nd else 0
        all_3 = []
        all_7 = []
        all_15 = []
        for d in days:
            all_3.extend(d['returns_3d'])
            all_7.extend(d['returns_7d'])
            all_15.extend(d['returns_15d'])
        m3 = sum(all_3) / len(all_3) if all_3 else 0
        m7 = sum(all_7) / len(all_7) if all_7 else 0
        m15 = sum(all_15) / len(all_15) if all_15 else 0
        w3 = sum(1 for x in all_3 if x > 0)
        w7 = sum(1 for x in all_7 if x > 0)
        w15 = sum(1 for x in all_15 if x > 0)
        c3, p3 = fmt_pct_pos(m3)
        c7, p7 = fmt_pct_pos(m7)
        c15, p15 = fmt_pct_pos(m15)
        html += f'''<tr>
<td><strong>{month_label}</strong></td>
<td>{nd}</td>
<td><strong>{n}</strong></td>
<td>{avg_daily:.1f}</td>
<td class='{c3}'>{p3}</td>
<td class='{c7}'>{p7}</td>
<td class='{c15}'>{p15}</td>
<td>{fmt_winrate(w3, len(all_3))}</td>
<td>{fmt_winrate(w7, len(all_7))}</td>
<td>{fmt_winrate(w15, len(all_15))}</td>
</tr>
'''
    html += '</tbody></table>\n'

    html += '</body></html>'
    return html


async def main():
    print("正在读取数据库...")
    report = await fetch_report()
    print(f"找到报告: {report.name}")
    print(f"状态: {report.status}")

    data = parse_report(report)
    print(f"有信号交易日: {data['overall']['total_days']} 天")
    print(f"总信号数: {data['overall']['total_signals']}")
    print(f"3日平均收益: {fmt_pct(data['overall']['avg_return_3d'])}")
    print(f"7日平均收益: {fmt_pct(data['overall']['avg_return_7d'])}")
    print(f"15日平均收益: {fmt_pct(data['overall']['avg_return_15d'])}")

    html = generate_html(data)

    output_path = os.path.join(OUTPUT_DIR, 'trend-upstart-flow-report.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n✅ HTML 报告已生成: {output_path}")
    print(f"   文件大小: {len(html):,} 字节")


if __name__ == '__main__':
    asyncio.run(main())
