import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChartsWrapper from '@/components/charts/EChartsWrapper';
import type { KLineItem } from '@/types/stock';

export interface TradeMarker {
  date: string;
  price: number;
  label?: string;
}

interface KLineChartProps {
  data: KLineItem[];
  loading?: boolean;
  height?: number;
  buyMarker?: TradeMarker;
  sellMarker?: TradeMarker;
}

function calcMA(data: number[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    sum += data[i];
    if (i >= period) {
      sum -= data[i - period];
    }
    result.push(i >= period - 1 ? sum / period : null);
  }
  return result;
}

const MA_LINES = [
  { period: 5, name: 'MA5', color: '#757575' },
  { period: 10, name: 'MA10', color: '#f5a623' },
  { period: 20, name: 'MA20', color: '#e040fb' },
  { period: 60, name: 'MA60', color: '#1e88e5' },
] as const;

export default function KLineChart({ data, loading, height = 500, buyMarker, sellMarker }: KLineChartProps) {
  const option: EChartsOption = useMemo(() => {
    if (!data.length) return {};

    const dates = data.map((d) => d.trade_date.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3'));
    const ohlc = data.map((d) => [d.open, d.close, d.low, d.high]);
    const volumes = data.map((d) => d.vol);
    const closes = data.map((d) => d.close);

    // 规范化日期为 YYYY-MM-DD
    const normDate = (d: string) => d.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3');

    // 构建买卖标记（使用 as const 确保类型兼容 ECharts）
    const buyMark = buyMarker ? {
      name: buyMarker.label || '买入',
      coord: [normDate(buyMarker.date), buyMarker.price] as [string, number],
      value: '买',
      symbol: 'arrow' as const,
      symbolRotate: 180,
      symbolSize: 14,
      symbolOffset: [0, -10] as [number, number],
      itemStyle: { color: '#ef5350' },
      label: { show: true, fontSize: 11, fontWeight: 'bold' as const, color: '#ef5350', formatter: `买\n${buyMarker.price.toFixed(2)}` },
    } : null;

    const sellMark = sellMarker ? {
      name: sellMarker.label || '卖出',
      coord: [normDate(sellMarker.date), sellMarker.price] as [string, number],
      value: '卖',
      symbol: 'arrow' as const,
      symbolSize: 14,
      symbolOffset: [0, 10] as [number, number],
      itemStyle: { color: '#26a69a' },
      label: { show: true, fontSize: 11, fontWeight: 'bold' as const, color: '#26a69a', formatter: `卖\n${sellMarker.price.toFixed(2)}` },
    } : null;

    const markPointData = [buyMark, sellMark].filter((x): x is NonNullable<typeof x> => x != null);

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        valueFormatter: (value: unknown) => (typeof value === 'number' ? value.toFixed(2) : String(value)),
      },
      legend: {
        data: ['K 线', ...MA_LINES.map((m) => m.name)],
        top: 0,
      },
      grid: [
        { left: '8%', right: '2%', top: '8%', height: '62%' },
        { left: '8%', right: '2%', top: '76%', height: '16%' },
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
          splitArea: { show: true },
          axisLabel: { formatter: (v: number) => v.toFixed(1) },
        },
        {
          scale: true,
          gridIndex: 1,
          splitNumber: 2,
          axisLabel: {
            formatter: (v: number) => {
              if (v >= 1e8) return `${(v / 1e8).toFixed(1)}亿`;
              if (v >= 1e4) return `${(v / 1e4).toFixed(0)}万`;
              return String(v);
            },
          },
        },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
        { type: 'slider', xAxisIndex: [0, 1], start: 0, end: 100, height: 20, bottom: 0 },
      ],
      series: [
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
          ...(markPointData.length > 0 ? { markPoint: { data: markPointData, symbolOffset: [0, 0] } } : {}),
        },
        ...MA_LINES.map((m) => ({
          name: m.name,
          type: 'line' as const,
          data: calcMA(closes, m.period),
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: true,
          lineStyle: { color: m.color, width: 1 },
          itemStyle: { color: m.color },
          symbol: 'none' as const,
        })),
        {
          name: '成交量',
          type: 'bar',
          data: volumes,
          xAxisIndex: 1,
          yAxisIndex: 1,
          itemStyle: {
            color: (params: { dataIndex: number }) => {
              const d = data[params.dataIndex];
              return d.close >= d.open ? '#ef5350' : '#26a69a';
            },
          },
        },
      ],
    };
  }, [data, buyMarker, sellMarker]);

  return <EChartsWrapper options={option} loading={loading} height={height} empty={!data.length} />;
}
