import React, { useEffect, useState } from 'react';
import { Modal, Spin, Empty, Table, Segmented } from 'antd';
import ReactECharts from 'echarts-for-react';
import marketHeatService, {
  type NorthboundItem, type ChangeBucket, type LeadingStock,
} from '@/services/marketHeatService';

interface Props {
  open: boolean;
  type: 'northbound' | 'advance_decline' | 'leading_sector' | 'lagging_sector' | null;
  tradeDate?: string;
  sectorName?: string;
  onClose: () => void;
  onStockClick?: (code: string, name: string) => void;
}

const KpiDetailModal: React.FC<Props> = ({ open, type, tradeDate, sectorName, onClose, onStockClick }) => {
  const [northbound, setNorthbound] = useState<NorthboundItem[]>([]);
  const [distribution, setDistribution] = useState<ChangeBucket[]>([]);
  const [stocks, setStocks] = useState<LeadingStock[]>([]);
  const [loading, setLoading] = useState(false);
  const [board, setBoard] = useState<string>('全部');

  const BOARD_OPTIONS = ['全部', '上证', '深圳', '科创', '创业'];
  const BOARD_MAP: Record<string, string | undefined> = {
    全部: undefined,
    上证: 'sh_main',
    深圳: 'sz_main',
    科创: 'sh_star',
    创业: 'sz_chi',
  };

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    if (type === 'northbound') {
      marketHeatService.getNorthbound(10).then(setNorthbound).finally(() => setLoading(false));
    } else if (type === 'advance_decline') {
      marketHeatService.getChangeDistribution(tradeDate, BOARD_MAP[board]).then(setDistribution).finally(() => setLoading(false));
    } else if ((type === 'leading_sector' || type === 'lagging_sector') && sectorName) {
      const sortOrder = type === 'lagging_sector' ? 'asc' : 'desc';
      marketHeatService.getLeadingSectorStocks(sectorName, tradeDate, sortOrder).then(setStocks).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [open, type, tradeDate, sectorName, board]);

  const title = type === 'northbound' ? '北向资金(深股通)近 10 日 — 历史净值' :
    type === 'advance_decline' ? '涨跌幅度分布' :
    type === 'leading_sector' ? `${sectorName} — 涨幅前 15` :
    type === 'lagging_sector' ? `${sectorName} — 跌幅前 15` : '';

  const northboundOption = React.useMemo(() => {
    if (!northbound.length) return {};
    const dates = northbound.map((n) => n.trade_date.slice(5, 10));
    const netData = northbound.map((n) => n.total_net_yi);
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const v = params[0]?.data;
          const dir = (v ?? 0) >= 0 ? '净流入' : '净流出';
          return `${params[0]?.name}<br/>📊 ${dir} ${v?.toFixed(2)}亿`;
        },
      },
      grid: { left: 50, right: 20, top: 20, bottom: 30 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { rotate: 30, fontSize: 11 },
      },
      yAxis: { type: 'value', name: '亿' },
      series: [
        {
          name: '净额',
          type: 'line',
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          data: netData,
          lineStyle: { color: '#1677ff', width: 2 },
          itemStyle: { color: '#1677ff' },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(22,119,255,0.25)' },
                { offset: 1, color: 'rgba(22,119,255,0.02)' },
              ],
            },
          },
          markLine: {
            silent: true,
            data: [{ yAxis: 0, lineStyle: { color: '#8c8c8c', type: 'dashed' } }],
            symbol: 'none',
          },
        },
      ],
    };
  }, [northbound]);

  const distributionOption = React.useMemo(() => {
    if (!distribution.length) return {};
    const labels = distribution.map((d) => d.label);
    const data = distribution.map((d) => d.count);
    const maxCount = Math.max(...data, 1);
    const redShades = data.map((v) => {
      const intensity = v / maxCount;
      return `rgba(207, 19, 34, ${0.3 + intensity * 0.6})`;
    });
    const greenShades = data.map((v) => {
      const intensity = v / maxCount;
      return `rgba(35, 149, 74, ${0.3 + intensity * 0.6})`;
    });
    // Green for negative buckets (first half), red for positive (second half)
    const colors = data.map((_, i) => i < Math.floor(data.length / 2) ? greenShades[i] : redShades[i]);

    return {
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: labels, axisLabel: { rotate: 30, fontSize: 10 } },
      yAxis: { type: 'value', name: '只' },
      series: [{
        type: 'bar',
        data: data.map((v, i) => ({ value: v, itemStyle: { color: colors[i] } })),
        label: { show: true, position: 'top', fontSize: 10 },
      }],
    };
  }, [distribution]);

  const advDeclineSummary = React.useMemo(() => {
    if (!distribution.length) return null;
    const upCount = distribution.filter(d => d.lo >= 0).reduce((s, d) => s + d.count, 0);
    const downCount = distribution.filter(d => d.hi <= 0).reduce((s, d) => s + d.count, 0);
    const total = upCount + downCount;
    if (total === 0) return null;
    return { upCount, downCount, total, ratio: (upCount / total * 100).toFixed(0) };
  }, [distribution]);

  const stockColumns = [
    {
      title: '股票', dataIndex: 'name', key: 'name',
      render: (_: any, r: LeadingStock) => (
        <a onClick={() => onStockClick?.(r.ts_code, r.name)}>{r.name}</a>
      ),
    },
    {
      title: '涨幅', dataIndex: 'change_pct', key: 'change_pct',
      render: (v: number | null) => (
        <span style={{ color: (v ?? 0) >= 0 ? '#cf1322' : '#389e0d', fontWeight: 600 }}>
          {v != null ? `${v > 0 ? '+' : ''}${v.toFixed(2)}%` : '-'}
        </span>
      ),
    },
    { title: '收盘价', dataIndex: 'close', key: 'close', render: (v: number) => v?.toFixed(2) },
  ];

  return (
    <Modal title={title} open={open} onCancel={onClose} footer={null} width={700} destroyOnClose>
      {loading ? (
        <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
      ) : (
        <>
          {type === 'northbound' && (
            northbound.length ? <ReactECharts option={northboundOption} style={{ height: 300 }} /> : <Empty description="暂无数据" />
          )}
          {type === 'advance_decline' && (
            <>
              {advDeclineSummary && (
                <div style={{ marginBottom: 16, textAlign: 'center', fontSize: 18, fontWeight: 600 }}>
                  <span style={{ color: '#cf1322' }}>涨 {advDeclineSummary.upCount} 家</span>
                  <span style={{ margin: '0 12px', color: '#8c8c8c' }}>|</span>
                  <span style={{ color: '#389e0d' }}>跌 {advDeclineSummary.downCount} 家</span>
                  <span style={{ margin: '0 12px', color: '#8c8c8c' }}>|</span>
                  <span>涨跌比 {advDeclineSummary.ratio}%</span>
                </div>
              )}
              <div style={{ marginBottom: 16, textAlign: 'center' }}>
                <Segmented
                  options={BOARD_OPTIONS}
                  value={board}
                  onChange={(val) => setBoard(val as string)}
                />
              </div>
              {distribution.length ? <ReactECharts option={distributionOption} style={{ height: 300 }} /> : <Empty description="暂无数据" />}
            </>
          )}
          {(type === 'leading_sector' || type === 'lagging_sector') && (
            stocks.length ? (
              <Table dataSource={stocks} columns={stockColumns} rowKey="ts_code" size="small" pagination={false} />
            ) : <Empty description="暂无数据" />
          )}
        </>
      )}
    </Modal>
  );
};

export default KpiDetailModal;
