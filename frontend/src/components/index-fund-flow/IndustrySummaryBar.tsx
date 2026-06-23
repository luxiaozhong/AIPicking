import React, { useMemo, useCallback } from 'react';
import { Spin, Empty } from 'antd';
import ReactECharts from 'echarts-for-react';
import type { IndustrySummaryItem } from '@/services/indexFundFlowService';

const RED_COLOR = '#cf1322';
const GREEN_COLOR = '#3f8600';

interface Props {
  data: IndustrySummaryItem[];
  loading: boolean;
  onIndustryClick?: (industryName: string) => void;
}

const IndustrySummaryBar: React.FC<Props> = ({ data, loading, onIndustryClick }) => {
  const sorted = useMemo(() => {
    if (!data || data.length === 0) return [];
    return [...data].sort(
      (a, b) => Math.abs(b.main_net_yi) - Math.abs(a.main_net_yi)
    );
  }, [data]);

  const option = useMemo(() => {
    if (!data || data.length === 0) return {};

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
  }, [data, sorted]);

  const handleChartClick = useCallback((params: any) => {
    if (!onIndustryClick || !sorted.length) return;
    // ECharts bar click gives dataIndex; map back to sorted order
    const idx = sorted.length - 1 - params.dataIndex;
    const item = sorted[idx];
    if (item) {
      onIndustryClick(item.industry_name);
    }
  }, [onIndustryClick, sorted]);

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
    <ReactECharts
      option={option}
      style={{ height: 350, width: '100%' }}
      notMerge
      onEvents={{ click: handleChartClick }}
    />
  );
};

export default IndustrySummaryBar;
