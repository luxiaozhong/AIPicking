import React, { useEffect, useState } from 'react';
import { Drawer, Descriptions, Spin, Empty, Table, Tag } from 'antd';
import ReactECharts from 'echarts-for-react';
import marketHeatService, { type SectorDetail } from '@/services/marketHeatService';

interface Props {
  open: boolean;
  sectorCode: string | null;
  sectorName: string | null;
  tradeDate?: string;
  onClose: () => void;
  onStockClick?: (code: string, name: string) => void;
}

const SectorDrawer: React.FC<Props> = ({ open, sectorCode, sectorName, tradeDate, onClose, onStockClick }) => {
  const [data, setData] = useState<SectorDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open && sectorCode) {
      setLoading(true);
      marketHeatService.getSectorDetail(sectorCode, tradeDate)
        .then(setData)
        .finally(() => setLoading(false));
    }
  }, [open, sectorCode, tradeDate]);

  const chartOption = React.useMemo(() => {
    if (!data?.trend?.length) return {};
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['主力净流入(亿)', '涨跌幅(%)'], bottom: 0 },
      grid: { top: 10, left: 50, right: 50, bottom: 30 },
      xAxis: {
        type: 'category',
        data: data.trend.map((t) => t.trade_date.slice(4)),
      },
      yAxis: [
        { type: 'value', name: '亿' },
        { type: 'value', name: '%' },
      ],
      series: [
        {
          name: '主力净流入(亿)',
          type: 'bar',
          data: data.trend.map((t) => t.main_net_yi),
          itemStyle: {
            color: (params: any) => params.value >= 0 ? '#cf1322' : '#389e0d',
          },
        },
        {
          name: '涨跌幅(%)',
          type: 'line',
          yAxisIndex: 1,
          data: data.trend.map((t) => t.change_pct),
          itemStyle: { color: '#1677ff' },
        },
      ],
    };
  }, [data]);

  const stockColumns = [
    {
      title: '股票', dataIndex: 'name', key: 'name',
      render: (_: any, record: any) => (
        <a onClick={() => onStockClick?.(record.ts_code, record.name)}>{record.name}</a>
      ),
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_pct',
      key: 'change_pct',
      render: (_: any, record: any) => {
        if (record.change_pct == null) return '-';
        const pct = record.change_pct;
        return <span style={{ color: pct >= 0 ? '#cf1322' : '#389e0d' }}>{pct.toFixed(2)}%</span>;
      },
    },
    { title: '收盘价', dataIndex: 'close', key: 'close', render: (v: number) => v?.toFixed(2) },
  ];

  return (
    <Drawer
      title={
        <span>
          {sectorName}
          {data?.info && (
            <Tag color={data.info.change_pct >= 0 ? 'red' : 'green'} style={{ marginLeft: 8 }}>
              {data.info.change_pct > 0 ? '+' : ''}{data.info.change_pct.toFixed(2)}%
            </Tag>
          )}
        </span>
      }
      open={open}
      onClose={onClose}
      width={640}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
      ) : !data?.info ? (
        <Empty description="暂无数据" />
      ) : (
        <>
          <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
            <Descriptions.Item label="主力净流入">{data.info.main_net_yi?.toFixed(2)}亿</Descriptions.Item>
            <Descriptions.Item label="上涨/下跌">{data.info.up_count}/{data.info.down_count}</Descriptions.Item>
            <Descriptions.Item label="领涨股">{data.info.leader_stock}</Descriptions.Item>
            <Descriptions.Item label="排名">#{data.info.rank}</Descriptions.Item>
          </Descriptions>

          <h4 style={{ marginTop: 16 }}>近 10 日资金流趋势</h4>
          <ReactECharts option={chartOption} style={{ height: 240 }} />

          <h4 style={{ marginTop: 16 }}>成分股 Top 5</h4>
          <Table
            dataSource={data.stocks}
            columns={stockColumns}
            rowKey="ts_code"
            size="small"
            pagination={false}
          />
        </>
      )}
    </Drawer>
  );
};

export default SectorDrawer;
