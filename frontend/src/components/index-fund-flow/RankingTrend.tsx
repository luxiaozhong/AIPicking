import React from 'react';
import { Table, Typography, Spin, Empty, Tag } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type { ColumnsType } from 'antd/es/table';

const { Text } = Typography;
const RED_COLOR = '#cf1322';
const GREEN_COLOR = '#3f8600';

export interface TrendItem {
  dates: string[];
  ranks: number[];
  flows5d: number[];
  flows15d: number[];
  flows: number[];
  improvement: number;
  current_rank: number;
  current_flow_5d: number;
  current_flow_15d: number;
  current_flow: number;
  ts_code?: string;
  stock_name?: string;
  sector_name?: string;
}

interface Props {
  data: { items: TrendItem[] } | null;
  loading: boolean;
  /** 名称字段：股票场景用 stock_name，板块场景用 sector_name（默认股票） */
  nameField?: 'stock_name' | 'sector_name';
  /** 股票点击回调（nameField=stock_name 时生效） */
  onStockClick?: (tsCode: string) => void;
  /** 板块点击回调（nameField=sector_name 时生效） */
  onItemClick?: (sector: string) => void;
}

function rankSparklineOption(ranks: number[]) {
  if (!ranks || ranks.length < 2) return {};
  // Invert ranks so rising (smaller rank number) = higher line
  const maxR = Math.max(...ranks, 1);
  const inverted = ranks.map((r) => maxR - r + 1);
  return {
    grid: { left: 0, right: 0, top: 2, bottom: 2 },
    xAxis: { type: 'category' as const, show: false, data: ranks.map((_, i) => i) },
    yAxis: { type: 'value' as const, show: false, min: Math.min(...inverted) - 1, max: Math.max(...inverted) + 1 },
    series: [
      {
        type: 'line' as const,
        data: inverted,
        smooth: true,
        symbol: 'none' as const,
        lineStyle: { color: '#1677ff', width: 1.5 },
        areaStyle: { color: 'rgba(22,119,255,0.1)' },
      },
    ],
  };
}

const RankingTrend: React.FC<Props> = ({ data, loading, nameField = 'stock_name', onStockClick, onItemClick }) => {
  const isSector = nameField === 'sector_name';

  const columns: ColumnsType<TrendItem> = [
    {
      title: '趋势',
      dataIndex: 'improvement',
      width: 60,
      align: 'center',
      render: (v: number) => {
        if (v > 0) return <Tag color="red" icon={<ArrowUpOutlined />}>{`+${v}`}</Tag>;
        if (v < 0) return <Tag color="green" icon={<ArrowDownOutlined />}>{v}</Tag>;
        return <Tag icon={<MinusOutlined />}>0</Tag>;
      },
      sorter: (a, b) => b.improvement - a.improvement,
    },
    {
      title: isSector ? '板块' : '股票',
      dataIndex: nameField,
      width: 110,
      ellipsis: true,
      render: (name: string, record) => {
        const key = isSector ? (record.sector_name || '') : (record.ts_code || '');
        const label = name || (isSector ? record.sector_name : record.ts_code);
        const handler = isSector ? onItemClick : onStockClick;
        return (
          <a onClick={() => handler?.(key)} style={{ cursor: handler ? 'pointer' : 'default' }}>
            {label}
          </a>
        );
      },
    },
    {
      title: '今日变化',
      dataIndex: 'ranks',
      width: 70,
      align: 'center',
      sorter: (a, b) => {
        const aChange = (a.ranks[a.ranks.length - 2] || 0) - (a.ranks[a.ranks.length - 1] || 0);
        const bChange = (b.ranks[b.ranks.length - 2] || 0) - (b.ranks[b.ranks.length - 1] || 0);
        return bChange - aChange;
      },
      render: (_ranks: number[]) => {
        if (_ranks.length < 2) return <Tag>--</Tag>;
        const prev = _ranks[_ranks.length - 2];
        const curr = _ranks[_ranks.length - 1];
        const change = prev - curr;
        if (change > 0) return <Tag color="red" style={{ margin: 0 }}>↑{change}</Tag>;
        if (change < 0) return <Tag color="green" style={{ margin: 0 }}>↓{Math.abs(change)}</Tag>;
        return <Tag style={{ margin: 0 }}>→0</Tag>;
      },
    },
    {
      title: '当前排名',
      dataIndex: 'current_rank',
      width: 75,
      align: 'center',
      sorter: (a, b) => a.current_rank - b.current_rank,
      render: (v: number) => <Text strong>{v}</Text>,
    },
    {
      title: '5日累计',
      dataIndex: 'current_flow_5d',
      width: 95,
      align: 'right',
      sorter: (a, b) => b.current_flow_5d - a.current_flow_5d,
      render: (v: number) => (
        <Text style={{ color: v >= 0 ? RED_COLOR : GREEN_COLOR, fontWeight: 500 }}>
          {isSector ? `${v.toFixed(2)}亿` : `${(v / 1e8).toFixed(2)}亿`}
        </Text>
      ),
    },
    {
      title: '15日累计',
      dataIndex: 'current_flow_15d',
      width: 95,
      align: 'right',
      sorter: (a, b) => b.current_flow_15d - a.current_flow_15d,
      render: (v: number) => (
        <Text style={{ color: v >= 0 ? RED_COLOR : GREEN_COLOR, fontWeight: 500 }}>
          {isSector ? `${v.toFixed(2)}亿` : `${(v / 1e8).toFixed(2)}亿`}
        </Text>
      ),
    },
    {
      title: `排名轨迹（${data?.items?.[0]?.dates?.length || 0}日）`,
      dataIndex: 'ranks',
      width: 100,
      render: (ranks: number[]) => (
        <ReactECharts option={rankSparklineOption(ranks)} style={{ height: 30, width: 90 }} />
      ),
    },
    {
      title: '今日主力',
      dataIndex: 'current_flow',
      width: 90,
      align: 'right',
      sorter: (a, b) => b.current_flow - a.current_flow,
      render: (v: number) => (
        <Text style={{ color: v >= 0 ? RED_COLOR : GREEN_COLOR }}>
          {isSector ? `${v.toFixed(2)}亿` : `${(v / 1e8).toFixed(2)}亿`}
        </Text>
      ),
    },
  ];

  if (loading) {
    return <Spin style={{ display: 'block', padding: 40 }} tip="计算排名变化..." />;
  }

  if (!data || !data.items || data.items.length === 0) {
    return <Empty description="暂无排名变化数据（需要至少 2 个交易日数据）" />;
  }

  return (
    <Table<TrendItem>
      columns={columns}
      dataSource={data.items}
      rowKey={isSector ? 'sector_name' : 'ts_code'}
      size="small"
      pagination={{ pageSize: 20, showSizeChanger: false }}
      scroll={{ x: 600 }}
      onRow={(record) => {
        const key = isSector ? (record.sector_name || '') : (record.ts_code || '');
        const handler = isSector ? onItemClick : onStockClick;
        return {
          onClick: () => handler?.(key),
          style: { cursor: handler ? 'pointer' : 'default' },
        };
      }}
    />
  );
};

export default RankingTrend;
