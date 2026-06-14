import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChartsWrapper from '@/components/charts/EChartsWrapper';
import type { KLineItem } from '@/types/stock';
import {
  calcMA, calcMACD, calcRSI, detectCrosses, detectDivergences, MA_LINES,
} from '@/utils/indicators';

interface IndexMACDChartProps {
  data: KLineItem[];
  macdParams: { fast: number; slow: number; signal: number };
  rsiParams: { period: number; overbought: number; oversold: number };
  height?: number;
}

export default function IndexMACDChart({
  data,
  macdParams,
  rsiParams,
  height = 580,
}: IndexMACDChartProps) {
  const option: EChartsOption = useMemo(() => {
    if (!data.length) return {};

    const dates = data.map((d) => d.trade_date.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3'));
    const closes = data.map((d) => d.close);
    const ohlc = data.map((d) => [d.open, d.close, d.low, d.high]);

    // ── 指标计算 ──
    const macd = calcMACD(closes, macdParams.fast, macdParams.slow, macdParams.signal);
    const rsi = calcRSI(closes, rsiParams.period);

    // ── 信号检测 ──
    const crosses = detectCrosses(dates, macd.dif, macd.dea);
    const divergences = detectDivergences(dates, closes, macd.dif);

    // ── MarkPoint: 金叉死叉 ──
    const crossMarkers = crosses.map((c) => ({
      name: c.type === 'golden' ? '金叉' : '死叉',
      coord: [c.date, data[c.index].high],
      value: c.type === 'golden' ? '金叉' : '死叉',
      symbol: 'pin' as const,
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

    // ── MarkPoint: 背离 ──
    const divergenceMarkers = divergences.map((d) => ({
      name: d.type === 'top' ? '顶背离' : '底背离',
      coord: [d.date, data[d.index].high],
      value: d.type === 'top' ? '顶背离' : '底背离',
      symbol: 'triangle' as const,
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

    const option: EChartsOption = {
      legend: {
        data: ['K 线', ...MA_LINES.map((m) => m.name), 'RSI'],
        top: 0,
        right: 0,
        textStyle: { fontSize: 10 },
        itemWidth: 14,
        itemHeight: 8,
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: (params: any) => {
          if (!Array.isArray(params)) return '';
          const isMACDPanel = (n: string) =>
            n.startsWith('DIF') || n.startsWith('DEA') || n === 'MACD 柱' || n === '零轴';
          const isRSIPanel = (n: string) =>
            n === 'RSI' || n.startsWith('超买') || n.startsWith('超卖');

          const kline = params.filter((p: any) => !isMACDPanel(p.seriesName) && !isRSIPanel(p.seriesName));
          const macdItems = params.filter((p: any) => isMACDPanel(p.seriesName));
          const rsiItems = params.filter((p: any) => isRSIPanel(p.seriesName));

          const label = (p: any) => {
            let marker = `<span style="display:inline-block;width:8px;height:8px;margin-right:4px;border-radius:2px;background:${p.color || '#999'}"></span>`;
            let val = p.value != null ? Number(p.value).toFixed(2) : '—';
            return `${marker} ${p.seriesName}: ${val}`;
          };

          const parts = [`<div style="font-size:12px;line-height:1.6;margin-bottom:4px">${params[0].axisValue}</div>`];
          if (kline.length) parts.push('<b>K线</b>', ...kline.map(label));
          if (macdItems.length) parts.push('<b>MACD</b>', ...macdItems.map(label));
          if (rsiItems.length) parts.push('<b>RSI</b>', ...rsiItems.map(label));
          return parts.join('<br/>');
        },
      },
      // 自定义图例
      graphic: [
        // MACD 图例
        {
          type: 'group',
          left: '1%',
          top: '62%',
          children: [
            { type: 'rect', shape: { width: 14, height: 2 }, style: { fill: '#1677ff' } },
            { type: 'text', left: 18, style: { text: 'DIF', fontSize: 10, fill: '#1677ff' } },
            { type: 'rect', left: 50, shape: { width: 14, height: 2 }, style: { fill: '#fa8c16' } },
            { type: 'text', left: 68, style: { text: 'DEA', fontSize: 10, fill: '#fa8c16' } },
            { type: 'rect', left: 104, shape: { width: 8, height: 8 }, style: { fill: '#ef5350' } },
            { type: 'rect', left: 112, shape: { width: 8, height: 8 }, style: { fill: '#26a69a' } },
            { type: 'text', left: 124, style: { text: 'MACD柱（红多绿空）', fontSize: 10, fill: '#888' } },
          ],
        },
        // RSI 图例
        {
          type: 'group',
          left: '1%',
          top: '85%',
          children: [
            { type: 'rect', shape: { width: 14, height: 2 }, style: { fill: '#7c3aed' } },
            { type: 'text', left: 18, style: { text: `RSI(${rsiParams.period})`, fontSize: 10, fill: '#7c3aed' } },
            { type: 'rect', left: 88, shape: { width: 14, height: 1 }, style: { fill: '#ff4d4f' } },
            { type: 'text', left: 106, style: { text: `超买(${rsiParams.overbought})`, fontSize: 10, fill: '#ff4d4f' } },
            { type: 'rect', left: 180, shape: { width: 14, height: 1 }, style: { fill: '#52c41a' } },
            { type: 'text', left: 198, style: { text: `超卖(${rsiParams.oversold})`, fontSize: 10, fill: '#52c41a' } },
          ],
        },
      ],
      grid: [
        { left: '5%', right: '3%', top: '6%', height: '48%' },
        { left: '5%', right: '3%', top: '60%', height: '18%' },
        { left: '5%', right: '3%', top: '83%', height: '14%' },
      ],
      xAxis: [
        { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { onZero: false } },
        { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false } },
        { type: 'category', data: dates, gridIndex: 2, axisLabel: { rotate: 0, formatter: (v: string) => v.slice(5) } },
      ],
      yAxis: [
        { scale: true, gridIndex: 0, axisLabel: { formatter: (v: number) => v.toFixed(0) } },
        { scale: true, gridIndex: 1, splitNumber: 3 },
        { min: 0, max: 100, gridIndex: 2, splitNumber: 3, axisLabel: { formatter: (v: number) => `${v}` } },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1, 2], start: 0, end: 100 },
        { type: 'slider', xAxisIndex: [0, 1, 2], start: 0, end: 100, height: 16, bottom: 0 },
      ],
      series: [
        // ── Panel 1: K线 ──
        {
          name: 'K 线',
          type: 'candlestick',
          data: ohlc,
          xAxisIndex: 0,
          yAxisIndex: 0,
          itemStyle: { color: '#ef5350', color0: '#26a69a', borderColor: '#ef5350', borderColor0: '#26a69a' },
          markPoint: {
            data: [...crossMarkers, ...divergenceMarkers],
            symbolOffset: [0, '-30%'],
          },
        },
        // MA 均线
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
        // ── Panel 2: MACD ──
        {
          name: `DIF(${macdParams.fast},${macdParams.slow})`,
          type: 'line',
          data: macd.dif,
          xAxisIndex: 1,
          yAxisIndex: 1,
          symbol: 'none',
          itemStyle: { color: '#1677ff' },
          lineStyle: { color: '#1677ff', width: 1.5 },
        },
        {
          name: `DEA(${macdParams.signal})`,
          type: 'line',
          data: macd.dea,
          xAxisIndex: 1,
          yAxisIndex: 1,
          symbol: 'none',
          itemStyle: { color: '#fa8c16' },
          lineStyle: { color: '#fa8c16', width: 1.5 },
        },
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
        // ── Panel 3: RSI ──
        {
          name: 'RSI',
          type: 'line',
          data: rsi,
          xAxisIndex: 2,
          yAxisIndex: 2,
          symbol: 'none',
          itemStyle: { color: '#7c3aed' },
          lineStyle: { color: '#7c3aed', width: 1.5 },
          markLine: {
            silent: true,
            symbol: 'none',
            data: [
              {
                yAxis: rsiParams.overbought,
                lineStyle: { color: '#ff4d4f', type: 'dashed', width: 1 },
                label: { show: true, formatter: `超买 ${rsiParams.overbought}`, fontSize: 10, color: '#ff4d4f' },
              },
              {
                yAxis: rsiParams.oversold,
                lineStyle: { color: '#52c41a', type: 'dashed', width: 1 },
                label: { show: true, formatter: `超卖 ${rsiParams.oversold}`, fontSize: 10, color: '#52c41a' },
              },
            ],
          },
        },
        // RSI 阈值辅助线
        {
          name: `超买线(${rsiParams.overbought})`,
          type: 'line',
          data: dates.map(() => rsiParams.overbought),
          xAxisIndex: 2,
          yAxisIndex: 2,
          symbol: 'none',
          lineStyle: { color: '#ff4d4f', width: 1, type: 'dashed', opacity: 0.5 },
          silent: true,
        },
        {
          name: `超卖线(${rsiParams.oversold})`,
          type: 'line',
          data: dates.map(() => rsiParams.oversold),
          xAxisIndex: 2,
          yAxisIndex: 2,
          symbol: 'none',
          lineStyle: { color: '#52c41a', width: 1, type: 'dashed', opacity: 0.5 },
          silent: true,
        },
      ],
    };
    return option;
  }, [data, macdParams, rsiParams]);

  return <EChartsWrapper options={option} height={height} empty={!data.length} />;
}
