import React, { useMemo, useRef, useEffect } from 'react';
import { Spin, Empty } from 'antd';
import ReactECharts from 'echarts-for-react';
import type { TreemapItem } from '@/services/indexFundFlowService';

const RED_COLOR = '#cf1322';
const GREEN_COLOR = '#3f8600';

interface Props {
  data: TreemapItem[];
  loading: boolean;
  onStockClick?: (tsCode: string) => void;
}

const RED_SHADES = [
  '#cf1322', '#e84749', '#f07377', '#f29b9e',
  '#f5bcbf', '#f8d8d9', '#fbeced',
];
const GREEN_SHADES = [
  '#3f8600', '#5ba81c', '#78c23a', '#97d65c',
  '#b5e683', '#d2f0a9', '#e8f5d0',
];

function getColor(value: number): string {
  if (value >= 0) {
    const abs = value;
    if (abs >= 5e8) return RED_SHADES[0];
    if (abs >= 3e8) return RED_SHADES[1];
    if (abs >= 1.5e8) return RED_SHADES[2];
    if (abs >= 5e7) return RED_SHADES[3];
    if (abs >= 1e7) return RED_SHADES[4];
    if (abs >= 1e6) return RED_SHADES[5];
    return RED_SHADES[6];
  } else {
    const abs = Math.abs(value);
    if (abs >= 5e8) return GREEN_SHADES[0];
    if (abs >= 3e8) return GREEN_SHADES[1];
    if (abs >= 1.5e8) return GREEN_SHADES[2];
    if (abs >= 5e7) return GREEN_SHADES[3];
    if (abs >= 1e7) return GREEN_SHADES[4];
    if (abs >= 1e6) return GREEN_SHADES[5];
    return GREEN_SHADES[6];
  }
}

function fmtFlow(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1e8) return (v / 1e8).toFixed(2) + '亿';
  if (abs >= 1e4) return (v / 1e4).toFixed(1) + '万';
  return v.toFixed(0);
}

const ConstituentTreemap: React.FC<Props> = ({ data, loading, onStockClick }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);

  // Keep chart size in sync when container width changes (e.g. modal opens)
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver(() => {
      const instance = chartRef.current?.getEchartsInstance?.();
      instance?.resize?.();
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const option = useMemo(() => {
    if (!data || data.length === 0) return {};

    // Flat: each stock is a direct tile (no industry grouping)
    const treeData = data.map((s) => ({
      name: s.stock_name || s.ts_code,
      value: Math.max(Math.abs(s.main_net_flow), 1),
      ts_code: s.ts_code,
      industry_name: s.industry_name || '',
      main_net_flow: s.main_net_flow,
      jumbo_net_flow: s.jumbo_net_flow,
      block_net_flow: s.block_net_flow,
      itemStyle: { color: getColor(s.main_net_flow) },
    }));

    return {
      tooltip: {
        formatter: (params: any) => {
          const d = params.data;
          if (!d || !d.ts_code) return params.name;
          return `<strong>${d.name}</strong> (${d.ts_code})<br/>` +
            `行业: ${d.industry_name}<br/>` +
            `主力净流入: <span style="color:${d.main_net_flow >= 0 ? RED_COLOR : GREEN_COLOR}">${fmtFlow(d.main_net_flow)}</span><br/>` +
            `超大单: ${fmtFlow(d.jumbo_net_flow)}<br/>` +
            `大单: ${fmtFlow(d.block_net_flow)}`;
        },
      },
      series: [
        {
          type: 'treemap',
          width: '100%',
          height: '100%',
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          label: {
            show: true,
            formatter: (params: any) => {
              const d = params.data;
              if (!d || !d.ts_code) return params.name;
              const sign = d.main_net_flow >= 0 ? '+' : '';
              const shortName = d.name.length > 5 ? d.name.slice(0, 5) + '..' : d.name;
              return `${shortName}\n${sign}${fmtFlow(d.main_net_flow)}`;
            },
            fontSize: 10,
          },
          itemStyle: { borderColor: '#fff', borderWidth: 1, gapWidth: 1 },
          data: treeData,
        },
      ],
    };
  }, [data]);

  const onEvents: Record<string, Function> | undefined = useMemo(() => {
    if (!onStockClick) return undefined;
    return {
      click: (params: any) => {
        if (params.data && params.data.ts_code) {
          onStockClick(params.data.ts_code);
        }
      },
    };
  }, [onStockClick]);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
        <Spin tip="加载中..." />
      </div>
    );
  }

  if (!data || data.length === 0) {
    return <Empty description="暂无资金流数据" />;
  }

  return (
    <div ref={containerRef} style={{ width: '100%' }}>
      <ReactECharts
        ref={chartRef}
        option={option}
        style={{ height: 420, width: '100%' }}
        onEvents={onEvents}
        notMerge
      />
    </div>
  );
};

export default ConstituentTreemap;
