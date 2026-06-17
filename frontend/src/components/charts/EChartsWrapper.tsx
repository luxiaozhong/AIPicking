import { useRef, useEffect, useState, useCallback } from 'react';
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
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [chartWidth, setChartWidth] = useState<number | undefined>(undefined);

  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    // 测量容器实际宽度
    const measure = () => {
      const w = el.getBoundingClientRect().width;
      if (w > 0) setChartWidth(w);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (loading) return <Spin style={{ display: 'block', margin: '60px auto' }} />;
  if (empty) return <Empty description="暂无数据" />;

  return (
    <div ref={wrapperRef} style={{ overflow: 'hidden', width: '100%' }}>
      <ReactECharts
        key={chartWidth}
        option={options}
        style={{ height, width: chartWidth ?? '100%' }}
        opts={{ renderer: 'canvas' }}
      />
    </div>
  );
}
