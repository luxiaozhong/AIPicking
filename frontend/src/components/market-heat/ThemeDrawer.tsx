import React, { useEffect, useState } from 'react';
import { Drawer, Table, Spin, Empty, Tag } from 'antd';
import marketHeatService, { type HotStockItem } from '@/services/marketHeatService';

interface Props {
  open: boolean;
  themeName: string | null;
  tradeDate?: string;
  onClose: () => void;
}

const ThemeDrawer: React.FC<Props> = ({ open, themeName, tradeDate, onClose }) => {
  const [stocks, setStocks] = useState<HotStockItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open && themeName) {
      setLoading(true);
      marketHeatService.getThemeDetail(themeName, tradeDate)
        .then(setStocks)
        .finally(() => setLoading(false));
    }
  }, [open, themeName, tradeDate]);

  const columns = [
    { title: '股票', dataIndex: 'stock_name', key: 'stock_name', width: 100 },
    {
      title: '涨幅',
      dataIndex: 'change_pct',
      key: 'change_pct',
      width: 80,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#cf1322' : '#389e0d', fontWeight: 600 }}>
          {v > 0 ? '+' : ''}{v?.toFixed(2)}%
        </span>
      ),
    },
    {
      title: '换手率',
      dataIndex: 'turnover_pct',
      key: 'turnover_pct',
      width: 80,
      render: (v: number) => `${v?.toFixed(2)}%`,
    },
    { title: '收盘价', dataIndex: 'close', key: 'close', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: 'DDE净量', dataIndex: 'dde_net', key: 'dde_net', width: 80, render: (v: number) => v?.toFixed(2) },
    {
      title: '上涨原因',
      dataIndex: 'reason',
      key: 'reason',
      render: (v: string) => (
        <span style={{ fontSize: 12 }}>
          {(v || '').split('+').map((tag: string, i: number) => (
            <Tag key={i} color="blue" style={{ marginBottom: 2 }}>{tag.trim()}</Tag>
          ))}
        </span>
      ),
    },
  ];

  return (
    <Drawer
      title={`🔥 ${themeName} — ${stocks.length} 只关联股票`}
      open={open}
      onClose={onClose}
      width={700}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
      ) : stocks.length === 0 ? (
        <Empty description="暂无关联股票" />
      ) : (
        <Table
          dataSource={stocks}
          columns={columns}
          rowKey="stock_code"
          size="small"
          pagination={false}
        />
      )}
    </Drawer>
  );
};

export default ThemeDrawer;
