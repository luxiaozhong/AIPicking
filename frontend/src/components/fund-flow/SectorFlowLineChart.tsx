import React, { useMemo } from 'react';
import { Spin, Empty } from 'antd';
import ReactECharts from 'echarts-for-react';
import type { HeatmapRow } from '@/services/fundFlowService';

// 多板块区分用的分类调色板（每条线一个颜色，便于辩识）
const LINE_COLORS = [
  '#cf1322', '#1677ff', '#3f8600', '#fa8c16', '#722ed1',
  '#13c2c2', '#eb2f96', '#a0d911', '#2f54eb', '#fa541c',
  '#52c41a', '#c41d7f', '#f5222d', '#1da57a', '#d48806',
  '#1890ff', '#d4380d', '#08979c', '#237804', '#ad4e00',
];

interface Props {
  rows: HeatmapRow[];
  topN: number;
  mode: 'daily' | 'cum';
  loading: boolean;
}

function buildSectorLineOption(rows: HeatmapRow[], topN: number, mode: 'daily' | 'cum') {
  if (!rows.length) return {};

  const dates = [...new Set(rows.map((r) => r.trade_date))].sort();
  const bySector: Record<string, Record<string, number>> = {};
  const sectorTotals: Record<string, number> = {};

  rows.forEach((r) => {
    if (!bySector[r.sector_name]) bySector[r.sector_name] = {};
    bySector[r.sector_name][r.trade_date] = r.main_net_yi;
    sectorTotals[r.sector_name] = (sectorTotals[r.sector_name] || 0) + r.main_net_yi;
  });

  // 取窗口内「累计净流入绝对值」最大的 Top N 个板块（同时覆盖流入/流出两端）
  const topSectors = Object.entries(sectorTotals)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, topN)
    .map(([name]) => name);

  const series: any[] = topSectors.map((name, i) => {
    const byDate = bySector[name];
    let cum = 0;
    const data = dates.map((d) => {
      const v = byDate[d] ?? 0;
      if (mode === 'cum') {
        cum += v;
        return Number(cum.toFixed(2));
      }
      return v;
    });
    return {
      name,
      type: 'line' as const,
      smooth: true,
      symbol: 'none' as const,
      lineStyle: { width: 1.5 },
      itemStyle: { color: LINE_COLORS[i % LINE_COLORS.length] },
      data,
    };
  });

  // 零轴参考线：上方=主力流入，下方=主力流出
  if (series.length) {
    series[0] = {
      ...series[0],
      markLine: {
        silent: true,
        symbol: 'none',
        data: [{ yAxis: 0 }],
        lineStyle: { color: '#999', type: 'dashed' },
        label: { show: false },
      },
    };
  }

  return {
    tooltip: {
      trigger: 'axis' as const,
      formatter: (params: any) => {
        let html = `<b>${params[0]?.axisValue || ''}</b><br/>`;
        params.forEach((p: any) => {
          const val = typeof p.value === 'number' ? p.value.toFixed(2) : p.value;
          const sign = p.value >= 0 ? '+' : '';
          html += `${p.marker} ${p.seriesName}: ${sign}${val} 亿<br/>`;
        });
        return html;
      },
    },
    legend: { type: 'scroll' as const, top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 60, right: 20, top: 44, bottom: 60 },
    xAxis: {
      type: 'category' as const,
      data: dates,
      boundaryGap: false,
      axisLabel: { rotate: 45, fontSize: 10 },
    },
    yAxis: {
      type: 'value' as const,
      name: '亿',
      splitLine: { lineStyle: { type: 'dashed', color: '#eee' } },
    },
    series,
  };
}

const SectorFlowLineChart: React.FC<Props> = ({ rows, topN, mode, loading }) => {
  const option = useMemo(() => buildSectorLineOption(rows, topN, mode), [rows, topN, mode]);

  if (loading) {
    return <Spin style={{ display: 'block', padding: 60 }} />;
  }
  if (!rows.length) {
    return <Empty description="暂无板块资金流数据" />;
  }
  return <ReactECharts option={option} style={{ height: 420 }} notMerge />;
};

export default SectorFlowLineChart;
