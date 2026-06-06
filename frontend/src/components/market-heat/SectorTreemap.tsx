import React, { useMemo } from 'react';
import { Card, Segmented, Spin, Empty, Statistic } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
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
  // 汇总统计：总流入 / 总流出 / 净值
  const summary = useMemo(() => {
    if (!sectors.length) return { totalInflow: 0, totalOutflow: 0, net: 0 };
    let inflow = 0, outflow = 0;
    for (const s of sectors) {
      const v = s.net_inflow || 0;
      if (v > 0) inflow += v;
      else outflow += v; // 负值累加
    }
    return {
      totalInflow: inflow,
      totalOutflow: Math.abs(outflow),
      net: inflow + outflow,
    };
  }, [sectors]);

  // 按净流入绝对值降序排列（最大波动在最上）
  const sorted = useMemo(() => {
    if (!sectors.length) return [];
    return [...sectors].sort((a, b) =>
      Math.abs(b.net_inflow || 0) - Math.abs(a.net_inflow || 0)
    );
  }, [sectors]);

  const option = useMemo(() => {
    if (!sorted.length) return {};

    const names = sorted.map((s) => s.sector_name);
    const values = sorted.map((s) => s.net_inflow || 0);
    const absVals = sorted.map((s) => Math.abs(s.net_inflow || 0));
    const maxAbs = Math.max(...absVals, 1);

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: any) => {
          const d = params[0];
          const i = d.dataIndex;
          const s = sorted[i];
          if (!s) return '';
          return [
            `<strong>${s.sector_name}</strong>`,
            `净流入: ${s.net_inflow > 0 ? '+' : ''}${s.net_inflow?.toFixed(2)}亿`,
            `涨跌幅: ${s.change_pct > 0 ? '+' : ''}${s.change_pct?.toFixed(2)}%`,
            `上涨/下跌: ${s.up_count}/${s.down_count}`,
            `领涨股: ${s.leader_stock} ${s.leader_change > 0 ? '+' : ''}${s.leader_change?.toFixed(2)}%`,
          ].join('<br/>');
        },
      },
      grid: { left: 90, right: 30, top: 5, bottom: 5 },
      xAxis: {
        type: 'value',
        min: -maxAbs * 1.15,
        max: maxAbs * 1.15,
        axisLabel: { formatter: (v: number) => `${v.toFixed(0)}亿`, fontSize: 10 },
        splitLine: { lineStyle: { type: 'dashed', color: '#e8e8e8' } },
      },
      yAxis: {
        type: 'category',
        data: names,
        inverse: true,
        axisLabel: { fontSize: 10, width: 85, overflow: 'truncate' },
        axisTick: { show: false },
        axisLine: { show: false },
      },
      series: [{
        type: 'bar',
        data: values.map((v, i) => ({
          value: v,
          itemStyle: {
            color: v >= 0
              ? `rgba(207, 19, 34, ${0.4 + Math.abs(v) / maxAbs * 0.55})`
              : `rgba(35, 149, 74, ${0.4 + Math.abs(v) / maxAbs * 0.55})`,
            borderRadius: v >= 0 ? [4, 0, 0, 4] : [0, 4, 4, 0],
          },
        })),
        barMaxWidth: 20,
      }],
      dataZoom: [{
        type: 'slider',
        yAxisIndex: 0,
        width: 12,
        right: 2,
        show: sorted.length > 30,
      }],
    };
  }, [sorted]);

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
      {/* 汇总统计 */}
      {!loading && sectors.length > 0 && (
        <div style={{
          display: 'flex', justifyContent: 'center', gap: 48,
          padding: '8px 0 16px', borderBottom: '1px solid #f0f0f0', marginBottom: 4,
        }}>
          <Statistic
            title="总流入"
            value={summary.totalInflow}
            precision={2}
            suffix="亿"
            valueStyle={{ color: '#cf1322', fontSize: 18 }}
            prefix={<ArrowUpOutlined />}
          />
          <Statistic
            title="总流出"
            value={summary.totalOutflow}
            precision={2}
            suffix="亿"
            valueStyle={{ color: '#23954a', fontSize: 18 }}
            prefix={<ArrowDownOutlined />}
          />
          <Statistic
            title="净值"
            value={summary.net}
            precision={2}
            suffix="亿"
            valueStyle={{
              color: summary.net >= 0 ? '#cf1322' : '#23954a',
              fontSize: 18,
            }}
            prefix={summary.net >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
          />
        </div>
      )}

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spin /></div>
      ) : sectors.length === 0 ? (
        <Empty description="暂无数据" />
      ) : (
        <ReactECharts
          option={option}
          style={{ height: Math.max(350, sectors.length * 20) }}
          onEvents={{
            click: (params: any) => {
              const i = params.dataIndex;
              if (i != null && sorted[i]) {
                onSectorClick(sorted[i]);
              }
            },
          }}
        />
      )}
    </Card>
  );
};

export default SectorTreemap;
