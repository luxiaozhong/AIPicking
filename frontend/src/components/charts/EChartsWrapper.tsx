import { Empty, Spin } from 'antd';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';

interface EChartsWrapperProps {
  options: EChartsOption;
  loading?: boolean;
  height?: number;
  empty?: boolean;
}

export default function EChartsWrapper({ options, loading, height = 300, empty }: EChartsWrapperProps) {
  if (loading) return <Spin style={{ display: 'block', margin: '60px auto' }} />;
  if (empty) return <Empty description="暂无数据" />;

  return (
    <ReactECharts
      option={options}
      style={{ height, width: '100%' }}
      opts={{ renderer: 'canvas' }}
    />
  );
}
