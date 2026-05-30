import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChartsWrapper from '@/components/charts/EChartsWrapper';
import type { KLineItem } from '@/types/stock';
import { calcMA, calcMACD, detectCrosses, detectDivergences, MA_LINES } from '@/utils/indicators';

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
      name: c.type === 'golden' ? '金叉' : '死叉',
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
      name: d.type === 'top' ? '顶背离' : '底背离',
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

    const klineLegendNames = ['K 线', ...MA_LINES.map((m) => m.name)];

    const option: EChartsOption = {
      legend: {
        data: klineLegendNames,
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
          const isMACDPanel = (name: string) =>
            name.startsWith('DIF') || name.startsWith('DEA') || name === 'MACD 柱' || name === '零轴';
          // Separate by panel
          const kline = params.filter((p: any) => !isMACDPanel(p.seriesName));
          const macd = params.filter((p: any) => isMACDPanel(p.seriesName));
          // Guess which panel the user is hovering based on MACD bar having a real value
          const macdBar = macd.find((p: any) => p.seriesName === 'MACD 柱');
          const isMACDHover = macdBar && macdBar.value !== undefined;
          const active = isMACDHover ? macd : kline;

          const label = (p: any) => {
            let marker: string;
            if (p.seriesName === 'MACD 柱') {
              const v = Number(p.value) || 0;
              const bg = v >= 0 ? '#ef5350' : '#26a69a';
              marker = `<span style="display:inline-block;width:8px;height:8px;margin-right:4px;border-radius:2px;background:${bg}"></span>`;
            } else if (p.seriesName === 'K 线') {
              const ohlc = p.data as number[];
              marker = `<span style="display:inline-block;width:8px;height:8px;margin-right:4px;border-radius:50%;background:${ohlc?.[1] >= ohlc?.[0] ? '#ef5350' : '#26a69a'}"></span>`;
            } else {
              marker = `<span style="display:inline-block;width:8px;height:8px;margin-right:4px;border-radius:50%;background:${p.color}"></span>`;
            }

            let val: string;
            if (p.seriesName === 'K 线') {
              const o = p.data as number[];
              val = o ? `开${o[0]?.toFixed(2)} 收${o[1]?.toFixed(2)} 低${o[2]?.toFixed(2)} 高${o[3]?.toFixed(2)}` : '—';
            } else if (isMACDPanel(p.seriesName)) {
              val = p.value != null ? Number(p.value).toFixed(4) : '—';
            } else {
              val = p.data != null ? Number(p.data).toFixed(2) : '—';
            }
            return `${marker} ${p.seriesName}: ${val}`;
          };

          return `<div style="font-size:12px;line-height:1.6">${params[0].axisValue}</div>` +
            active.map(label).join('<br/>');
        },
      },
      graphic: [
        {
          type: 'text',
          left: '5%',
          top: '68%',
          style: {
            text: '━ DIF 快线（蓝）  ━ DEA 信号线（橙）  ▊ MACD 柱（红多绿空）  ·· 零轴',
            fontSize: 10,
            fill: '#888',
          },
        },
      ],
      grid: [
        { left: '5%', right: '3%', top: '6%', height: '56%' },
        { left: '5%', right: '3%', top: '70%', height: '20%' },
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
        // MA 均线叠加
        ...MA_LINES.map((m) => ({
          name: m.name,
          type: 'line' as const,
          data: calcMA(closes, m.period),
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: true,
          itemStyle: { color: m.color },
          lineStyle: { color: m.color, width: 1 },
          symbol: 'none' as const,
        })),
        // DIF
        {
          name: `DIF(${fast},${slow})`,
          type: 'line',
          data: macd.dif,
          xAxisIndex: 1,
          yAxisIndex: 1,
          symbol: 'none',
          itemStyle: { color: '#1677ff' },
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
          itemStyle: { color: '#fa8c16' },
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
                itemStyle: { color: '#1677ff', opacity: 0.4 },
                lineStyle: { color: '#1677ff', width: 1, type: 'dashed' as const, opacity: 0.4 },
              },
              {
                name: `DEA(${defaultSignal}) 默认`,
                type: 'line' as const,
                data: macdDefault.dea,
                xAxisIndex: 1,
                yAxisIndex: 1,
                symbol: 'none',
                itemStyle: { color: '#fa8c16', opacity: 0.4 },
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
    return option;
  }, [data, fast, slow, signal, showComparison, defaultFast, defaultSlow, defaultSignal]);

  return <EChartsWrapper options={option} height={height} empty={!data.length} />;
}
