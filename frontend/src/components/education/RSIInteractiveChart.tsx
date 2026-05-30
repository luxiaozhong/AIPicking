import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChartsWrapper from '@/components/charts/EChartsWrapper';
import type { KLineItem } from '@/types/stock';
import { calcMA, calcRSI, MA_LINES } from '@/utils/indicators';

export interface RSIAnnotation {
  id: string;
  date: string;
  type: 'overbought' | 'oversold' | 'top_divergence' | 'bottom_divergence';
  label: string;
  desc: string;
}

interface RSIInteractiveChartProps {
  data: KLineItem[];
  period: number;
  overbought: number;
  oversold: number;
  height?: number;
}

export default function RSIInteractiveChart({
  data,
  period,
  overbought,
  oversold,
  height = 550,
}: RSIInteractiveChartProps) {
  const option: EChartsOption = useMemo(() => {
    if (!data.length) return {};

    const dates = data.map((d) => d.trade_date.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3'));
    const closes = data.map((d) => d.close);
    const ohlc = data.map((d) => [d.open, d.close, d.low, d.high]);
    const rsi = calcRSI(closes, period);

    return {
      legend: {
        data: ['K 线', ...MA_LINES.map((m) => m.name)],
        top: 0,
        right: 0,
        textStyle: { fontSize: 10 },
        itemWidth: 14,
        itemHeight: 8,
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          if (!Array.isArray(params)) return '';
          const isRSI = (n: string) => n.includes('RSI') || n.includes('超买') || n.includes('超卖');
          const kline = params.filter((p: any) => !isRSI(p.seriesName));
          const rsiPanel = params.filter((p: any) => isRSI(p.seriesName));
          const active = rsiPanel.some((p: any) => p.value != null) ? rsiPanel : kline;
          const label = (p: any) => {
            const marker = `<span style="display:inline-block;width:8px;height:8px;margin-right:4px;border-radius:50%;background:${p.color}"></span>`;
            let val: string;
            if (p.seriesName === 'K 线') {
              const o = p.data as number[];
              val = o ? `开${o[0]?.toFixed(2)} 收${o[1]?.toFixed(2)} 低${o[2]?.toFixed(2)} 高${o[3]?.toFixed(2)}` : '—';
            } else if (isRSI(p.seriesName)) {
              val = p.value != null ? Number(p.value).toFixed(1) : '—';
            } else {
              val = p.data != null ? Number(p.data).toFixed(2) : '—';
            }
            return `${marker} ${p.seriesName}: ${val}`;
          };
          return `<div style="font-size:12px;line-height:1.6">${params[0].axisValue}</div>${active.map(label).join('<br/>')}`;
        },
      },
      graphic: [
        {
          type: 'group',
          left: '1%',
          top: '66%',
          children: [
            { type: 'rect', shape: { width: 14, height: 2 }, style: { fill: '#1677ff' } },
            { type: 'text', left: 18, style: { text: `RSI(${period})`, fontSize: 10, fill: '#1677ff' } },
            { type: 'rect', left: 72, shape: { width: 14, height: 1 }, style: { fill: '#ff4d4f' } },
            { type: 'text', left: 90, style: { text: `超买线(${overbought})`, fontSize: 10, fill: '#ff4d4f' } },
            { type: 'rect', left: 165, shape: { width: 14, height: 1 }, style: { fill: '#52c41a' } },
            { type: 'text', left: 183, style: { text: `超卖线(${oversold})`, fontSize: 10, fill: '#52c41a' } },
          ],
        },
      ],
      grid: [
        { left: '5%', right: '3%', top: '6%', height: '56%' },
        { left: '5%', right: '3%', top: '70%', height: '20%' },
      ],
      xAxis: [
        { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { onZero: false } },
        { type: 'category', data: dates, gridIndex: 1, axisLabel: { rotate: 0, formatter: (v: string) => v.slice(5) } },
      ],
      yAxis: [
        { scale: true, gridIndex: 0, axisLabel: { formatter: (v: number) => v.toFixed(1) } },
        { min: 0, max: 100, gridIndex: 1, splitNumber: 5 },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
        { type: 'slider', xAxisIndex: [0, 1], start: 0, end: 100, height: 18, bottom: 0 },
      ],
      series: [
        { name: 'K 线', type: 'candlestick', data: ohlc, xAxisIndex: 0, yAxisIndex: 0, itemStyle: { color: '#ef5350', color0: '#26a69a', borderColor: '#ef5350', borderColor0: '#26a69a' } },
        ...MA_LINES.map((m) => ({ name: m.name, type: 'line' as const, data: calcMA(closes, m.period), xAxisIndex: 0, yAxisIndex: 0, smooth: true, itemStyle: { color: m.color }, lineStyle: { color: m.color, width: 1 }, symbol: 'none' as const })),
        { name: `RSI(${period})`, type: 'line', data: rsi, xAxisIndex: 1, yAxisIndex: 1, symbol: 'none', itemStyle: { color: '#1677ff' }, lineStyle: { color: '#1677ff', width: 1.5 }, markLine: { silent: true, symbol: 'none', data: [{ yAxis: overbought, lineStyle: { color: '#ff4d4f', type: 'dashed', width: 1 } }, { yAxis: oversold, lineStyle: { color: '#52c41a', type: 'dashed', width: 1 } }] } },
      ],
    };
  }, [data, period, overbought, oversold]);

  return <EChartsWrapper options={option} height={height} empty={!data.length} />;
}
