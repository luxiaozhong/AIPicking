import { useEffect, useState } from 'react';
import { Card, Table, Button, message, Popconfirm, Select } from 'antd';
import { useNavigate } from 'react-router-dom';
import backtestService from '@/services/backtestService';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import type { BatchBacktestReport } from '@/types/backtest';

export default function BatchBacktestList() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<BatchBacktestReport[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [strategyFilter, setStrategyFilter] = useState<number | undefined>();
  const [deleting, setDeleting] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await backtestService.getBatchBacktests({
        page,
        limit: 20,
        strategy_id: strategyFilter,
      });
      setData(res.items);
      setTotal(res.total);
    } catch {
      message.error('获取批量回测列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [page, strategyFilter]);

  // Poll when any task is running
  useEffect(() => {
    const hasActive = data.some((b) => b.status === 'pending' || b.status === 'running');
    if (!hasActive) return;
    const timer = setInterval(fetchData, 3000);
    return () => clearInterval(timer);
  }, [data]);

  const handleDelete = async (id: number) => {
    setDeleting(true);
    try {
      await backtestService.deleteBatchBacktest(id);
      message.success('已删除');
      fetchData();
    } catch {
      message.error('删除失败');
    } finally {
      setDeleting(false);
    }
  };

  const columns = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (text: string, record: BatchBacktestReport) => (
        <a onClick={() => navigate(`/backtests/batch/${record.id}`)}>{text || `批量回测 #${record.id}`}</a>
      ),
    },
    {
      title: '策略', dataIndex: 'strategy_name', key: 'strategy',
      render: (text: string) => text || '—',
    },
    {
      title: '日期范围', key: 'range',
      render: (_: unknown, r: BatchBacktestReport) =>
        `${r.start_date.slice(0, 4)}-${r.start_date.slice(4, 6)}-${r.start_date.slice(6, 8)} ~ ${r.end_date.slice(0, 4)}-${r.end_date.slice(4, 6)}-${r.end_date.slice(6, 8)}`,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 120,
      render: (status: string) => <StatusTag status={status} type="backtest" />,
    },
    {
      title: '进度', key: 'progress', width: 100,
      render: (_: unknown, r: BatchBacktestReport) =>
        r.status === 'completed' ? `${r.total_days}/${r.total_days}` : `${r.completed_days}/${r.total_days}`,
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180,
      render: (v: string) => v ? new Date(v).toLocaleString() : '—',
    },
    {
      title: '操作', key: 'actions', width: 120,
      render: (_: unknown, r: BatchBacktestReport) => (
        <Popconfirm title="确认删除？" onConfirm={() => handleDelete(r.id)}>
          <Button type="link" danger loading={deleting}>删除</Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="批量回测"
      />

      <Card>
        <div style={{ marginBottom: 16 }}>
          <Select
            allowClear
            placeholder="按策略筛选"
            style={{ width: 200 }}
            value={strategyFilter}
            onChange={(v) => { setStrategyFilter(v); setPage(1); }}
          />
        </div>

        <Table
          dataSource={data}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: (p) => setPage(p),
            showTotal: (t) => `共 ${t} 条`,
          }}
        />
      </Card>
    </>
  );
}
