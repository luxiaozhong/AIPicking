import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChartsWrapper from '@/components/charts/EChartsWrapper';
import type { KLineItem } from '@/types/stock';
import { calcBollinger } from '@/utils/indicators';

interface BollingerInteractiveChartProps {
  data: KLineItem[];
  period: number;
  multiplier: number;
  height?: number;
}

export default function BollingerInteractiveChart({ data, period, multiplier, height = 500 }: BollingerInteractiveChartProps) {
  const option: EChartsOption = useMemo(() => {
    if (!data.length) return {};
    const dates = data.map(d => d.trade_date.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3'));
    const closes = data.map(d => d.close);
    const ohlc = data.map(d => [d.open, d.close, d.low, d.high]);
    const volumes = data.map(d => d.vol);
    const bb = calcBollinger(closes, period, multiplier);

    return {
      legend: { data: ['K 线', '中轨', '上轨', '下轨'], top: 0, right: 0, textStyle: { fontSize: 10 }, itemWidth: 14, itemHeight: 8 },
      tooltip: { trigger: 'axis' },
      graphic: [{
        type: 'group', left: '1%', bottom: 4, children: [
          { type: 'text', style: { text: '━ 中轨(SMA)    ·· 上轨/下轨 (±' + multiplier + 'σ)', fontSize: 10, fill: '#888' } },
        ],
      }],
      grid: [
        { left: '5%', right: '3%', top: '6%', height: '68%' },
        { left: '5%', right: '3%', top: '80%', height: '12%' },
      ],
      xAxis: [
        { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { onZero: false } },
        { type: 'category', data: dates, gridIndex: 1, axisLabel: { rotate: 0, formatter: (v: string) => v.slice(5) } },
      ],
      yAxis: [
        { scale: true, gridIndex: 0, axisLabel: { formatter: (v: number) => v.toFixed(1) } },
        { scale: true, gridIndex: 1, splitNumber: 2, axisLabel: { formatter: (v: number) => { if (v >= 1e8) return (v/1e8).toFixed(1)+'亿'; if (v >= 1e4) return (v/1e4).toFixed(0)+'万'; return String(v); } } },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
        { type: 'slider', xAxisIndex: [0, 1], start: 0, end: 100, height: 18, bottom: 0 },
      ],
      series: [
        { name: 'K 线', type: 'candlestick', data: ohlc, xAxisIndex: 0, yAxisIndex: 0, itemStyle: { color: '#ef5350', color0: '#26a69a', borderColor: '#ef5350', borderColor0: '#26a69a' } },
        { name: '上轨', type: 'line', data: bb.upper, xAxisIndex: 0, yAxisIndex: 0, symbol: 'none', itemStyle: { color: '#ff4d4f' }, lineStyle: { color: '#ff4d4f', width: 1, type: 'dashed' } },
        { name: '中轨', type: 'line', data: bb.middle, xAxisIndex: 0, yAxisIndex: 0, symbol: 'none', itemStyle: { color: '#fa8c16' }, lineStyle: { color: '#fa8c16', width: 1.5 } },
        { name: '下轨', type: 'line', data: bb.lower, xAxisIndex: 0, yAxisIndex: 0, symbol: 'none', itemStyle: { color: '#52c41a' }, lineStyle: { color: '#52c41a', width: 1, type: 'dashed' } },
        { name: '成交量', type: 'bar', data: volumes, xAxisIndex: 1, yAxisIndex: 1, itemStyle: { color: (p: { dataIndex: number }) => data[p.dataIndex].close >= data[p.dataIndex].open ? '#ef5350' : '#26a69a' } },
      ],
    };
  }, [data, period, multiplier]);

  return <EChartsWrapper options={option} height={height} empty={!data.length} />;
}
