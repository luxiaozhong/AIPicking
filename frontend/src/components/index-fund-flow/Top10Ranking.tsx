import React, { useMemo } from 'react';
import { Row, Col, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { ConstituentFlowItem } from '@/services/indexFundFlowService';

const { Text } = Typography;

const RED_COLOR = '#cf1322';
const GREEN_COLOR = '#3f8600';

interface Props {
  data: ConstituentFlowItem[];
  loading: boolean;
  onStockClick?: (tsCode: string) => void;
}

function fmtFlow(v: number): string {
  const sign = v >= 0 ? '+' : '';
  const abs = Math.abs(v);
  if (abs >= 1e8) return sign + (v / 1e8).toFixed(2) + '亿';
  if (abs >= 1e4) return sign + (v / 1e4).toFixed(1) + '万';
  return sign + v.toFixed(0);
}

function fmtFlowShort(v: number): string {
  const sign = v >= 0 ? '+' : '';
  return sign + (v / 1e8).toFixed(2) + '亿';
}

const Top10Ranking: React.FC<Props> = ({ data, loading, onStockClick }) => {
  const top10In = useMemo(() => {
    return [...data]
      .filter((d) => d.main_net_flow > 0)
      .sort((a, b) => b.main_net_flow - a.main_net_flow)
      .slice(0, 10);
  }, [data]);

  const top10Out = useMemo(() => {
    return [...data]
      .filter((d) => d.main_net_flow < 0)
      .sort((a, b) => a.main_net_flow - b.main_net_flow)
      .slice(0, 10);
  }, [data]);

  const columns: ColumnsType<ConstituentFlowItem> = [
    {
      title: '排名',
      dataIndex: 'rank',
      width: 50,
      render: (_, __, idx) => idx + 1,
    },
    {
      title: '股票',
      dataIndex: 'stock_name',
      width: 100,
      render: (name: string, record) => (
        <a onClick={() => onStockClick?.(record.ts_code)} style={{ cursor: 'pointer' }}>
          {name || record.ts_code}
        </a>
      ),
    },
    {
      title: '代码',
      dataIndex: 'ts_code',
      width: 100,
      render: (code: string) => <Text type="secondary">{code.split('.')[0] || code}</Text>,
    },
    {
      title: '行业',
      dataIndex: 'industry_name',
      width: 80,
      ellipsis: true,
    },
    {
      title: '主力净流入',
      dataIndex: 'main_net_flow',
      width: 100,
      align: 'right',
      render: (v: number) => (
        <Text style={{ color: v >= 0 ? RED_COLOR : GREEN_COLOR, fontWeight: 'bold' }}>
          {fmtFlowShort(v)}
        </Text>
      ),
    },
    {
      title: '超大单',
      dataIndex: 'jumbo_net_flow',
      width: 90,
      align: 'right',
      render: (v: number) => (
        <Text style={{ color: v >= 0 ? RED_COLOR : GREEN_COLOR }}>{fmtFlowShort(v)}</Text>
      ),
    },
    {
      title: '大单',
      dataIndex: 'block_net_flow',
      width: 90,
      align: 'right',
      render: (v: number) => (
        <Text style={{ color: v >= 0 ? RED_COLOR : GREEN_COLOR }}>{fmtFlowShort(v)}</Text>
      ),
    },
  ];

  // Merge show both top 10 in and out
  const showData = useMemo(() => {
    const result: { type: 'in' | 'out'; label: string; items: ConstituentFlowItem[] }[] = [];
    if (top10In.length > 0) result.push({ type: 'in', label: '🔴 主力净流入 Top 10', items: top10In });
    result.push({ type: 'out', label: '🟢 主力净流出 Top 10', items: top10Out });
    return result;
  }, [top10In, top10Out]);

  return (
    <Row gutter={16}>
      {showData.map((section) => (
        <Col xs={24} md={12} key={section.type} style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 'bold', marginBottom: 6, fontSize: 13 }}>
            {section.label}
          </div>
          <Table<ConstituentFlowItem>
            columns={columns}
            dataSource={section.items}
            rowKey="ts_code"
            loading={loading}
            pagination={false}
            size="small"
            scroll={{ x: 520 }}
            onRow={(record) => ({
              onClick: () => onStockClick?.(record.ts_code),
              style: { cursor: 'pointer' },
            })}
          />
        </Col>
      ))}
    </Row>
  );
};

export default Top10Ranking;
