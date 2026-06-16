import React, { useMemo } from 'react';
import { Spin, Empty } from 'antd';
import ReactECharts from 'echarts-for-react';
import type { MultiStockTrend } from '@/services/indexFundFlowService';

interface Props {
  data: MultiStockTrend | null;
  loading: boolean;
}

const STOCK_COLORS = [
  '#cf1322', '#1677ff', '#fa8c16', '#722ed1', '#13c2c2',
  '#eb2f96', '#52c41a', '#faad14', '#2f54eb', '#a0d911',
  '#f5222d', '#1890ff', '#fa541c', '#531dab', '#08979c',
  '#c41d7f', '#237804', '#d48806', '#1d39c4', '#7cb305',
];

function fmtYi(v: number): string {
  const sign = v >= 0 ? '+' : '';
  return sign + (v / 1e8).toFixed(2) + '亿';
}

const MultiStockTrendChart: React.FC<Props> = ({ data, loading }) => {
  const option = useMemo(() => {
    if (!data || !data.stocks || data.stocks.length === 0) return {};

    const dates = data.stocks[0]?.days?.map((d) => d.trade_date) || [];

    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          if (!Array.isArray(params) || params.length === 0) return '';
          let html = `<strong>${params[0].axisValue}</strong><br/>`;
          params.forEach((p: any) => {
            html +=
              `<span style="display:inline-block;margin-right:5px;border-radius:50%;width:10px;height:10px;background:${p.color}"></span>` +
              `${p.seriesName}: ${fmtYi(p.value)}<br/>`;
          });
          return html;
        },
      },
      legend: {
        data: data.stocks.map((s) => s.stock_name || s.ts_code),
        bottom: 0,
        type: 'scroll',
      },
      grid: { left: 80, right: 30, top: 20, bottom: 60 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: {
          formatter: (v: string) => v.slice(5), // MM-DD
        },
      },
      yAxis: {
        type: 'value',
        axisLabel: {
          formatter: (v: number) => (v / 1e8).toFixed(1) + '亿',
        },
        splitLine: { lineStyle: { type: 'dashed' } },
      },
      series: data.stocks.map((s, idx) => ({
        name: s.stock_name || s.ts_code,
        type: 'line',
        data: s.days.map((d) => d.main_net_flow),
        smooth: true,
        symbol: 'none',
        lineStyle: {
          color: STOCK_COLORS[idx % STOCK_COLORS.length],
          width: 2,
        },
        itemStyle: {
          color: STOCK_COLORS[idx % STOCK_COLORS.length],
        },
      })),
    };
  }, [data]);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
        <Spin tip="加载趋势..." />
      </div>
    );
  }

  if (!data || !data.stocks || data.stocks.length === 0) {
    return <Empty description="暂无趋势数据" />;
  }

  return (
    <ReactECharts option={option} style={{ height: 350, width: '100%' }} notMerge />
  );
};

export default MultiStockTrendChart;
