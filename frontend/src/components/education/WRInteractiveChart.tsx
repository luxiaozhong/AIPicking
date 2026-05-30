import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChartsWrapper from '@/components/charts/EChartsWrapper';
import type { KLineItem } from '@/types/stock';
import { calcMA, calcWR, MA_LINES } from '@/utils/indicators';

interface WRInteractiveChartProps { data: KLineItem[]; period: number; height?: number; }

export default function WRInteractiveChart({ data, period, height = 550 }: WRInteractiveChartProps) {
  const option: EChartsOption = useMemo(() => {
    if (!data.length) return {};
    const dates = data.map(d => d.trade_date.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3'));
    const closes = data.map(d => d.close);
    const highs = data.map(d => d.high);
    const lows = data.map(d => d.low);
    const ohlc = data.map(d => [d.open, d.close, d.low, d.high]);
    const wr = calcWR(highs, lows, closes, period);

    return {
      legend: { data: ['K 线', ...MA_LINES.map(m => m.name)], top: 0, right: 0, textStyle: { fontSize: 10 }, itemWidth: 14, itemHeight: 8 },
      tooltip: { trigger: 'axis' },
      graphic: [{ type: 'group', left: '1%', top: '66%', children: [
        { type: 'rect', shape: { width: 14, height: 2 }, style: { fill: '#1677ff' } }, { type: 'text', left: 18, style: { text: `WR(${period})`, fontSize: 10, fill: '#1677ff' } },
        { type: 'rect', left: 68, shape: { width: 14, height: 1 }, style: { fill: '#ff4d4f' } }, { type: 'text', left: 86, style: { text: '超买(20)', fontSize: 10, fill: '#ff4d4f' } },
        { type: 'rect', left: 150, shape: { width: 14, height: 1 }, style: { fill: '#52c41a' } }, { type: 'text', left: 168, style: { text: '超卖(80)', fontSize: 10, fill: '#52c41a' } },
      ]}],
      grid: [{ left: '5%', right: '3%', top: '6%', height: '56%' }, { left: '5%', right: '3%', top: '70%', height: '20%' }],
      xAxis: [
        { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { onZero: false } },
        { type: 'category', data: dates, gridIndex: 1, axisLabel: { rotate: 0, formatter: (v: string) => v.slice(5) } },
      ],
      yAxis: [
        { scale: true, gridIndex: 0, axisLabel: { formatter: (v: number) => v.toFixed(1) } },
        { min: 0, max: 100, gridIndex: 1, splitNumber: 5, inverse: true },
      ],
      dataZoom: [{ type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 }, { type: 'slider', xAxisIndex: [0, 1], start: 0, end: 100, height: 18, bottom: 0 }],
      series: [
        { name: 'K 线', type: 'candlestick', data: ohlc, xAxisIndex: 0, yAxisIndex: 0, itemStyle: { color: '#ef5350', color0: '#26a69a', borderColor: '#ef5350', borderColor0: '#26a69a' } },
        ...MA_LINES.map(m => ({ name: m.name, type: 'line' as const, data: calcMA(closes, m.period), xAxisIndex: 0, yAxisIndex: 0, smooth: true, itemStyle: { color: m.color }, lineStyle: { color: m.color, width: 1 }, symbol: 'none' as const })),
        { name: `WR(${period})`, type: 'line', data: wr, xAxisIndex: 1, yAxisIndex: 1, symbol: 'none', areaStyle: { color: 'rgba(22,119,255,0.1)' }, itemStyle: { color: '#1677ff' }, lineStyle: { color: '#1677ff', width: 1.5 } },
        { name: '超买(20)', type: 'line', data: dates.map(() => 20), xAxisIndex: 1, yAxisIndex: 1, symbol: 'none', lineStyle: { color: '#ff4d4f', type: 'dashed', width: 1 }, silent: true },
        { name: '超卖(80)', type: 'line', data: dates.map(() => 80), xAxisIndex: 1, yAxisIndex: 1, symbol: 'none', lineStyle: { color: '#52c41a', type: 'dashed', width: 1 }, silent: true },
      ],
    };
  }, [data, period]);
  return <EChartsWrapper options={option} height={height} empty={!data.length} />;
}
