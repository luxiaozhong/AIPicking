import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChartsWrapper from '@/components/charts/EChartsWrapper';
import type { KLineItem } from '@/types/stock';
import { calcMA, detectMACrosses, MA_LINES } from '@/utils/indicators';

interface MAInteractiveChartProps { data: KLineItem[]; fast: number; slow: number; height?: number; }

export default function MAInteractiveChart({ data, fast, slow, height = 500 }: MAInteractiveChartProps) {
  const option: EChartsOption = useMemo(() => {
    if (!data.length) return {};
    const dates = data.map(d => d.trade_date.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3'));
    const closes = data.map(d => d.close);
    const ohlc = data.map(d => [d.open, d.close, d.low, d.high]);
    const volumes = data.map(d => d.vol);
    const fastMA = calcMA(closes, fast);
    const slowMA = calcMA(closes, slow);
    const crosses = detectMACrosses(dates, closes, fast, slow);
    const markers = crosses.map(c => ({
      name: c.type === 'golden' ? '金叉' : '死叉',
      coord: [c.date, c.type === 'golden' ? Math.min(data[c.index].low, data[c.index].low) : data[c.index].high],
      value: c.type === 'golden' ? '金叉' : '死叉',
      symbol: 'pin', symbolSize: 28,
      itemStyle: { color: c.type === 'golden' ? '#52c41a' : '#ff4d4f' },
      label: { show: true, formatter: c.type === 'golden' ? '金叉' : '死叉', fontSize: 10 },
    }));

    return {
      legend: { data: ['K 线', `MA${fast}`, `MA${slow}`], top: 0, right: 0, textStyle: { fontSize: 10 }, itemWidth: 14, itemHeight: 8 },
      tooltip: { trigger: 'axis' },
      grid: [{ left: '5%', right: '3%', top: '6%', height: '68%' }, { left: '5%', right: '3%', top: '80%', height: '12%' }],
      xAxis: [
        { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { onZero: false } },
        { type: 'category', data: dates, gridIndex: 1, axisLabel: { rotate: 0, formatter: (v: string) => v.slice(5) } },
      ],
      yAxis: [
        { scale: true, gridIndex: 0, axisLabel: { formatter: (v: number) => v.toFixed(1) } },
        { scale: true, gridIndex: 1, splitNumber: 2, axisLabel: { formatter: (v: number) => { if (v >= 1e8) return (v/1e8).toFixed(1)+'亿'; if (v >= 1e4) return (v/1e4).toFixed(0)+'万'; return String(v); } } },
      ],
      dataZoom: [{ type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 }, { type: 'slider', xAxisIndex: [0, 1], start: 0, end: 100, height: 18, bottom: 0 }],
      series: [
        { name: 'K 线', type: 'candlestick', data: ohlc, xAxisIndex: 0, yAxisIndex: 0, itemStyle: { color: '#ef5350', color0: '#26a69a', borderColor: '#ef5350', borderColor0: '#26a69a' }, markPoint: { data: markers, symbolOffset: [0, '-40%'] } },
        { name: `MA${fast}`, type: 'line', data: fastMA, xAxisIndex: 0, yAxisIndex: 0, smooth: true, symbol: 'none', itemStyle: { color: '#1677ff' }, lineStyle: { color: '#1677ff', width: 2 } },
        { name: `MA${slow}`, type: 'line', data: slowMA, xAxisIndex: 0, yAxisIndex: 0, smooth: true, symbol: 'none', itemStyle: { color: '#e040fb' }, lineStyle: { color: '#e040fb', width: 2 } },
        { name: '成交量', type: 'bar', data: volumes, xAxisIndex: 1, yAxisIndex: 1, itemStyle: { color: (p: {dataIndex: number}) => data[p.dataIndex].close >= data[p.dataIndex].open ? '#ef5350' : '#26a69a' } },
      ],
    };
  }, [data, fast, slow]);
  return <EChartsWrapper options={option} height={height} empty={!data.length} />;
}
