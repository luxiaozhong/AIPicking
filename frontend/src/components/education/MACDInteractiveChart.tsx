import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChartsWrapper from '@/components/charts/EChartsWrapper';
import type { KLineItem } from '@/types/stock';
import { calcMACD, detectCrosses, detectDivergences } from '@/utils/indicators';

export interface ChartAnnotation {
  id: string;
  date: string;
  type: 'golden_cross' | 'death_cross' | 'top_divergence' | 'bottom_divergence';
  label: string;
  desc: string;
}

interface MACDInteractiveChartProps {
  data: KLineItem[];
  fast: number;
  slow: number;
  signal: number;
  defaultFast: number;
  defaultSlow: number;
  defaultSignal: number;
  annotations: ChartAnnotation[];
  visibleAnnotationIds: string[];
  showComparison: boolean;
  height?: number;
}

export default function MACDInteractiveChart({
  data,
  fast,
  slow,
  signal,
  defaultFast,
  defaultSlow,
  defaultSignal,
  annotations,
  visibleAnnotationIds,
  showComparison,
  height = 550,
}: MACDInteractiveChartProps) {
  const option: EChartsOption = useMemo(() => {
    if (!data.length) return {};

    const dates = data.map((d) => d.trade_date.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3'));
    const closes = data.map((d) => d.close);
    const ohlc = data.map((d) => [d.open, d.close, d.low, d.high]);
    const volumes = data.map((d) => d.vol);

    // Current params MACD
    const macd = calcMACD(closes, fast, slow, signal);
    // Default params MACD (for comparison overlay)
    const macdDefault = showComparison
      ? calcMACD(closes, defaultFast, defaultSlow, defaultSignal)
      : null;

    // Signal annotations from auto-detection
    const crosses = detectCrosses(dates, macd.dif, macd.dea);
    const crossMarkers = crosses.map((c) => ({
      coord: [c.date, data[c.index].high],
      value: c.type === 'golden' ? '金叉' : '死叉',
      symbol: 'pin',
      symbolSize: 28,
      itemStyle: {
        color: c.type === 'golden' ? '#52c41a' : '#ff4d4f',
      },
      label: {
        show: true,
        formatter: c.type === 'golden' ? '金叉' : '死叉',
        fontSize: 10,
      },
    }));

    const divergences = detectDivergences(dates, closes, macd.dif);
    const divergenceMarkers = divergences.map((d) => ({
      coord: [d.date, data[d.index].high],
      value: d.type === 'top' ? '顶背离' : '底背离',
      symbol: 'triangle',
      symbolSize: 20,
      itemStyle: {
        color: d.type === 'top' ? '#ff4d4f' : '#52c41a',
      },
      label: {
        show: true,
        formatter: d.type === 'top' ? '顶背离' : '底背离',
        fontSize: 10,
        position: 'top' as const,
      },
    }));

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
      },
      grid: [
        { left: '5%', right: '3%', top: '5%', height: '56%' },
        { left: '5%', right: '3%', top: '66%', height: '22%' },
      ],
      xAxis: [
        {
          type: 'category',
          data: dates,
          gridIndex: 0,
          axisLabel: { show: false },
          axisLine: { onZero: false },
        },
        {
          type: 'category',
          data: dates,
          gridIndex: 1,
          axisLabel: { rotate: 0, formatter: (v: string) => v.slice(5) },
        },
      ],
      yAxis: [
        {
          scale: true,
          gridIndex: 0,
          axisLabel: { formatter: (v: number) => v.toFixed(1) },
        },
        {
          scale: true,
          gridIndex: 1,
          splitNumber: 3,
        },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
        { type: 'slider', xAxisIndex: [0, 1], start: 0, end: 100, height: 18, bottom: 0 },
      ],
      series: [
        // K-line
        {
          name: 'K 线',
          type: 'candlestick',
          data: ohlc,
          xAxisIndex: 0,
          yAxisIndex: 0,
          itemStyle: {
            color: '#ef5350',
            color0: '#26a69a',
            borderColor: '#ef5350',
            borderColor0: '#26a69a',
          },
          markPoint: {
            data: [...crossMarkers, ...divergenceMarkers],
            symbolOffset: [0, '-30%'],
          },
        },
        // DIF
        {
          name: `DIF(${fast},${slow})`,
          type: 'line',
          data: macd.dif,
          xAxisIndex: 1,
          yAxisIndex: 1,
          symbol: 'none',
          lineStyle: { color: '#1677ff', width: 1.5 },
        },
        // DEA
        {
          name: `DEA(${signal})`,
          type: 'line',
          data: macd.dea,
          xAxisIndex: 1,
          yAxisIndex: 1,
          symbol: 'none',
          lineStyle: { color: '#fa8c16', width: 1.5 },
        },
        // MACD Bar
        {
          name: 'MACD 柱',
          type: 'bar',
          data: macd.bar.map((v) => (v !== null ? v : 0)),
          xAxisIndex: 1,
          yAxisIndex: 1,
          itemStyle: {
            color: (params: { dataIndex: number }) => {
              const v = macd.bar[params.dataIndex];
              return v !== null && v >= 0 ? '#ef5350' : '#26a69a';
            },
          },
        },
        // Default param comparison lines (optional)
        ...(macdDefault
          ? [
              {
                name: `DIF(${defaultFast},${defaultSlow}) 默认`,
                type: 'line' as const,
                data: macdDefault.dif,
                xAxisIndex: 1,
                yAxisIndex: 1,
                symbol: 'none',
                lineStyle: { color: '#1677ff', width: 1, type: 'dashed' as const, opacity: 0.4 },
              },
              {
                name: `DEA(${defaultSignal}) 默认`,
                type: 'line' as const,
                data: macdDefault.dea,
                xAxisIndex: 1,
                yAxisIndex: 1,
                symbol: 'none',
                lineStyle: { color: '#fa8c16', width: 1, type: 'dashed' as const, opacity: 0.4 },
              },
            ]
          : []),
        // Zero reference line in MACD panel
        {
          name: '零轴',
          type: 'line',
          data: dates.map(() => 0),
          xAxisIndex: 1,
          yAxisIndex: 1,
          symbol: 'none',
          lineStyle: { color: '#999', width: 1, type: 'dotted' },
          silent: true,
        },
      ],
    };
  }, [data, fast, slow, signal, showComparison, defaultFast, defaultSlow, defaultSignal]);

  return <EChartsWrapper options={option} height={height} empty={!data.length} />;
}
