import React, { useMemo } from 'react';
import { Card, Segmented, Spin, Empty } from 'antd';
import ReactECharts from 'echarts-for-react';
import type { SectorItem } from '@/services/marketHeatService';

interface Props {
  sectors: SectorItem[];
  sectorType: 'industry' | 'concept';
  loading: boolean;
  onSectorTypeChange: (type: 'industry' | 'concept') => void;
  onSectorClick: (sector: SectorItem) => void;
}

const SectorTreemap: React.FC<Props> = ({
  sectors, sectorType, loading, onSectorTypeChange, onSectorClick,
}) => {
  const option = useMemo(() => {
    if (!sectors.length) return {};

    // 按净流入排序：正流入(多→少) → 负流出(少→多)
    const sorted = [...sectors].sort((a, b) => {
      if (a.net_inflow >= 0 && b.net_inflow >= 0) return b.net_inflow - a.net_inflow;
      if (a.net_inflow < 0 && b.net_inflow < 0) return a.net_inflow - b.net_inflow;
      return a.net_inflow >= 0 ? -1 : 1;
    });

    const data = sorted.map((s) => ({
      name: s.sector_name,
      value: Math.abs(s.net_inflow || 0.01),
      itemStyle: {
        color: s.change_pct >= 0
          ? `rgba(207, 19, 34, ${Math.min(Math.abs(s.change_pct) / 8, 0.9)})`
          : `rgba(35, 149, 74, ${Math.min(Math.abs(s.change_pct) / 8, 0.9)})`,
      },
      sectorData: s,
    }));

    return {
      tooltip: {
        formatter: (params: any) => {
          const d = params.data?.sectorData;
          if (!d) return params.name;
          return [
            `<strong>${d.sector_name}</strong>`,
            `涨跌幅: ${d.change_pct > 0 ? '+' : ''}${d.change_pct?.toFixed(2)}%`,
            `主力净流入: ${d.main_net_yi?.toFixed(2)}亿`,
            `上涨/下跌: ${d.up_count}/${d.down_count}`,
            `领涨股: ${d.leader_stock} ${d.leader_change > 0 ? '+' : ''}${d.leader_change?.toFixed(2)}%`,
          ].join('<br/>');
        },
      },
      series: [{
        type: 'treemap',
        width: '100%',
        height: '100%',
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        label: {
          show: true,
          formatter: '{b}',
          fontSize: 11,
          overflow: 'truncate',
        },
        upperLabel: { show: true, height: 20 },
        data,
      }],
    };
  }, [sectors]);

  return (
    <Card
      title="板块资金流"
      extra={
        <Segmented
          size="small"
          value={sectorType}
          onChange={(v) => onSectorTypeChange(v as 'industry' | 'concept')}
          options={[
            { label: '行业', value: 'industry' },
            { label: '概念', value: 'concept' },
          ]}
        />
      }
    >
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spin /></div>
      ) : sectors.length === 0 ? (
        <Empty description="暂无数据" />
      ) : (
        <ReactECharts
          option={option}
          style={{ height: 350 }}
          onEvents={{
            click: (params: any) => {
              if (params.data?.sectorData) {
                onSectorClick(params.data.sectorData);
              }
            },
          }}
        />
      )}
    </Card>
  );
};

export default SectorTreemap;
