import React, { useEffect, useState } from 'react';
import { Modal, Spin, Empty, Table } from 'antd';
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

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    if (type === 'northbound') {
      marketHeatService.getNorthbound(10).then(setNorthbound).finally(() => setLoading(false));
    } else if (type === 'advance_decline') {
      marketHeatService.getChangeDistribution(tradeDate).then(setDistribution).finally(() => setLoading(false));
    } else if ((type === 'leading_sector' || type === 'lagging_sector') && sectorName) {
      const sortOrder = type === 'lagging_sector' ? 'asc' : 'desc';
      marketHeatService.getLeadingSectorStocks(sectorName, tradeDate, sortOrder).then(setStocks).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [open, type, tradeDate, sectorName]);

  const title = type === 'northbound' ? '北向资金(深股通)近 10 日 — 买入·卖出·净额' :
    type === 'advance_decline' ? '涨跌幅度分布' :
    type === 'leading_sector' ? `${sectorName} — 涨幅前 15` :
    type === 'lagging_sector' ? `${sectorName} — 跌幅前 15` : '';

  const northboundOption = React.useMemo(() => {
    if (!northbound.length) return {};
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const d = params[0]?.data;
          const buy = d?.buy?.toFixed(2);
          const sell = d?.sell?.toFixed(2);
          const net = d?.net?.toFixed(2);
          const dir = (d?.net ?? 0) >= 0 ? '净流入' : '净流出';
          return `${d?.date}<br/>💰 买入 ${buy}亿<br/>💸 卖出 ${sell}亿<br/>📊 ${dir} ${net}亿`;
        },
      },
      legend: { data: ['买入', '卖出', '净额'], bottom: 0 },
      grid: { bottom: 40 },
      xAxis: {
        type: 'category',
        data: northbound.map((n) => n.trade_date.slice(5, 10)),
      },
      yAxis: { type: 'value', name: '亿' },
      series: [
        {
          name: '买入',
          type: 'bar',
          data: northbound.map((n) => ({
            value: n.sgt_buy_yi,
            date: n.trade_date.slice(0, 10),
            buy: n.sgt_buy_yi,
            sell: n.sgt_sell_yi,
            net: n.total_net_yi,
            itemStyle: { color: '#1677ff' },
          })),
        },
        {
          name: '卖出',
          type: 'bar',
          data: northbound.map((n) => ({
            value: n.sgt_sell_yi,
            date: n.trade_date.slice(0, 10),
            buy: n.sgt_buy_yi,
            sell: n.sgt_sell_yi,
            net: n.total_net_yi,
            itemStyle: { color: '#fa8c16' },
          })),
        },
        {
          name: '净额',
          type: 'bar',
          data: northbound.map((n) => ({
            value: n.total_net_yi,
            date: n.trade_date.slice(0, 10),
            buy: n.sgt_buy_yi,
            sell: n.sgt_sell_yi,
            net: n.total_net_yi,
            itemStyle: { color: n.total_net_yi >= 0 ? '#cf1322' : '#389e0d' },
          })),
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
            distribution.length ? <ReactECharts option={distributionOption} style={{ height: 300 }} /> : <Empty description="暂无数据" />
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
