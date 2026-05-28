import { useEffect, useState, useCallback, useRef } from 'react';
import { Card, Button, Table, Space, message, Select, AutoComplete, Spin, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useBacktestStore } from '@/stores/backtestStore';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import ReturnLabel from '@/components/shared/ReturnLabel';
import stockService from '@/services/stockService';
import type { StockItem } from '@/types/stock';

export default function BacktestList() {
  const navigate = useNavigate();
  const {
    backtests,
    total,
    page,
    limit,
    loading,
    error,
    fetchBacktests,
    deleteBacktest,
    clearError,
    startPolling,
    stopPolling,
  } = useBacktestStore();

  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [stockSearch, setStockSearch] = useState<string>('');
  const [stockOptions, setStockOptions] = useState<{ value: string; label: React.ReactNode }[]>([]);
  const [stockSearching, setStockSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);

  const doSearch = (stock: string) => {
    fetchBacktests({ page: 1, status: statusFilter, stock: stock || undefined });
  };

  const handleStockSearch = useCallback((keyword: string) => {
    if (!keyword) {
      setStockOptions([]);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setStockSearching(true);
      try {
        const items: StockItem[] = await stockService.search(keyword);
        setStockOptions(items.map((s) => ({
          value: s.ts_code,
          label: <span>{s.ts_code}  <Typography.Text type="secondary">{s.name}</Typography.Text></span>,
        })));
      } catch (err) {
        console.error('Stock search failed:', err);
        setStockOptions([]);
      } finally {
        setStockSearching(false);
      }
    }, 300);
  }, []);

  useEffect(() => {
    fetchBacktests();
  }, [fetchBacktests]);

  useEffect(() => {
    startPolling();
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
    },
    {
      title: '策略名称',
      dataIndex: 'strategy_name',
      key: 'strategy_name',
      render: (text: string, record: { id: number }) => (
        <Button type="link" onClick={() => navigate(`/backtests/${record.id}`)}>
          {text || `策略 #${record.id}`}
        </Button>
      ),
    },
    {
      title: '截止日',
      dataIndex: 'cutoff_date',
      key: 'cutoff_date',
      width: 120,
      render: (text: string) =>
        text ? `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}` : '—',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => <StatusTag status={status} type="backtest" />,
    },
    {
      title: '3天收益',
      key: 'avg_return_3d',
      width: 110,
      render: (_: unknown, record: { summary?: { avg_return_3d?: number } }) => (
        <ReturnLabel value={record.summary?.avg_return_3d} />
      ),
    },
    {
      title: '7天胜率',
      key: 'win_rate_7d',
      width: 110,
      render: (_: unknown, record: { summary?: { win_rate_7d?: number } }) => {
        if (!record.summary?.win_rate_7d) return '—';
        return `${(record.summary.win_rate_7d * 100).toFixed(1)}%`;
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: unknown, record: { id: number }) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => navigate(`/backtests/${record.id}`)}>
            查看
          </Button>
          <Button type="link" size="small" danger onClick={async () => {
            try {
              await deleteBacktest(record.id);
              message.success('删除成功');
            } catch {
              // error message handled by useEffect watching store error state
            }
          }}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="回测报告"
        breadcrumb={[{ title: '回测报告', path: '/backtests' }]}
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => fetchBacktests()}>
            刷新
          </Button>
        }
      />

      <Card>
        <div style={{ marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center' }}>
          <Space>
            <span>状态筛选：</span>
            <Select
              value={statusFilter}
              onChange={(v) => {
                setStatusFilter(v);
                fetchBacktests({ page: 1, status: v, stock: stockSearch || undefined });
              }}
              style={{ width: 120 }}
              allowClear
              options={[
                { label: '待运行', value: 'pending' },
                { label: '运行中', value: 'running' },
                { label: '已完成', value: 'completed' },
                { label: '失败', value: 'failed' },
              ]}
              placeholder="全部"
            />
          </Space>
          <AutoComplete
            placeholder="搜索股票代码或名称"
            value={stockSearch}
            options={stockOptions}
            onSearch={handleStockSearch}
            onSelect={(value: string) => {
              setStockSearch(value);
              doSearch(value);
            }}
            onChange={(value: string) => setStockSearch(value)}
            allowClear
            style={{ width: 260 }}
            notFoundContent={stockSearching ? <Spin size="small" /> : null}
          />
          <Button type="primary" onClick={() => doSearch(stockSearch)} style={{ marginLeft: 8 }}>
            搜索
          </Button>
        </div>

        <Table
          dataSource={backtests}
          columns={columns}
          rowKey="id"
          loading={loading}
          scroll={{ x: 900 }}
          pagination={{
            current: page,
            pageSize: limit,
            total,
            onChange: (p, l) => fetchBacktests({ page: p, limit: l, status: statusFilter, stock: stockSearch || undefined }),
            showSizeChanger: true,
            showTotal: (t: number) => `共 ${t} 条`,
          }}
        />
      </Card>
    </>
  );
}
