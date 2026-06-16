import React, { useMemo } from 'react';
import { Spin, Empty } from 'antd';
import ReactECharts from 'echarts-for-react';
import type { IndustrySummaryItem } from '@/services/indexFundFlowService';

const RED_COLOR = '#cf1322';
const GREEN_COLOR = '#3f8600';

interface Props {
  data: IndustrySummaryItem[];
  loading: boolean;
}

const IndustrySummaryBar: React.FC<Props> = ({ data, loading }) => {
  const option = useMemo(() => {
    if (!data || data.length === 0) return {};

    // Sort by abs value descending
    const sorted = [...data].sort(
      (a, b) => Math.abs(b.main_net_yi) - Math.abs(a.main_net_yi)
    );
    const names = sorted.map((d) => d.industry_name).reverse();
    const values = sorted.map((d) => d.main_net_yi).reverse();

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: any) => {
          const p = Array.isArray(params) ? params[0] : params;
          const idx = sorted.length - 1 - p.dataIndex;
          const item = sorted[idx];
          if (!item) return '';
          return `<strong>${item.industry_name}</strong><br/>` +
            `主力净流入: ${item.main_net_yi.toFixed(2)}亿<br/>` +
            `超大单: ${item.jumbo_net_yi.toFixed(2)}亿<br/>` +
            `大单: ${item.block_net_yi.toFixed(2)}亿<br/>` +
            `正向占比: ${item.positive_pct}%<br/>` +
            `成分股数: ${item.stock_count}`;
        },
      },
      grid: { left: 160, right: 60, top: 10, bottom: 20 },
      xAxis: {
        type: 'value',
        axisLabel: {
          formatter: (v: number) => v.toFixed(1) + '亿',
        },
        splitLine: { lineStyle: { type: 'dashed' } },
      },
      yAxis: {
        type: 'category',
        data: names,
        axisTick: { show: false },
        axisLine: { show: false },
      },
      series: [
        {
          type: 'bar',
          data: values.map((v) => ({
            value: v,
            itemStyle: {
              color: v >= 0 ? RED_COLOR : GREEN_COLOR,
              borderRadius: [0, 4, 4, 0],
            },
          })),
          label: {
            show: true,
            position: 'right',
            formatter: (params: any) => {
              const sign = params.value >= 0 ? '+' : '';
              return `${sign}${params.value.toFixed(1)}亿`;
            },
            fontSize: 11,
          },
        },
      ],
    };
  }, [data]);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
        <Spin tip="加载行业汇总..." />
      </div>
    );
  }

  if (!data || data.length === 0) {
    return <Empty description="暂无行业数据" />;
  }

  return (
    <ReactECharts option={option} style={{ height: 350, width: '100%' }} notMerge />
  );
};

export default IndustrySummaryBar;
