import { useEffect, useState, useCallback } from 'react';
import { Card, Button, Table, Space, message, Select, Popconfirm, Radio } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useBacktestStore } from '@/stores/backtestStore';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import ReturnLabel from '@/components/shared/ReturnLabel';
import StockSearchLookup from '@/components/shared/StockSearchLookup';
import backtestService from '@/services/backtestService';
import rebalanceService from '@/services/rebalanceService';
import type { BatchBacktestReport } from '@/types/backtest';
import type { RebalanceReport } from '@/services/rebalanceService';

export default function BacktestList() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<'single' | 'batch' | 'rebalance'>('single');

  // —— 单回测 ——
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

  const doSearch = (stock: string) => {
    fetchBacktests({ page: 1, status: statusFilter, stock: stock || undefined });
  };

  const fetchSingle = useCallback(
    (p?: { page?: number; limit?: number; status?: string }) => {
      fetchBacktests({
        page: p?.page ?? page,
        limit: p?.limit ?? limit,
        status: p?.status !== undefined ? p.status : statusFilter,
        stock: stockSearch || undefined,
      });
    },
    [fetchBacktests, page, limit, statusFilter, stockSearch],
  );

  useEffect(() => { fetchSingle(); }, []);
  useEffect(() => {
    startPolling();
    return () => stopPolling();
  }, [startPolling, stopPolling]);
  useEffect(() => {
    if (error) { message.error(error); clearError(); }
  }, [error, clearError]);

  // —— 批量回测 ——
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchData, setBatchData] = useState<BatchBacktestReport[]>([]);
  const [batchTotal, setBatchTotal] = useState(0);
  const [batchPage, setBatchPage] = useState(1);
  const [strategyFilter, setStrategyFilter] = useState<number | undefined>();

  const fetchBatch = useCallback(async (p?: { page?: number }) => {
    setBatchLoading(true);
    try {
      const res = await backtestService.getBatchBacktests({
        page: p?.page ?? batchPage,
        limit: 20,
        strategy_id: strategyFilter,
      });
      setBatchData(res.items);
      setBatchTotal(res.total);
    } catch {
      message.error('获取批量回测列表失败');
    } finally {
      setBatchLoading(false);
    }
  }, [batchPage, strategyFilter]);

  useEffect(() => {
    if (mode === 'batch') fetchBatch();
  }, [mode, fetchBatch]);

  // —— 调仓回测 ——
  const [rebalanceLoading, setRebalanceLoading] = useState(false);
  const [rebalanceData, setRebalanceData] = useState<RebalanceReport[]>([]);
  const [rebalanceTotal, setRebalanceTotal] = useState(0);
  const [rebalancePage, setRebalancePage] = useState(1);

  const fetchRebalance = useCallback(async (p?: { page?: number }) => {
    setRebalanceLoading(true);
    try {
      const res = await rebalanceService.getList({
        page: p?.page ?? rebalancePage,
        limit: 20,
        strategy_id: strategyFilter,
      });
      setRebalanceData(res.items);
      setRebalanceTotal(res.total);
    } catch {
      message.error('获取调仓回测列表失败');
    } finally {
      setRebalanceLoading(false);
    }
  }, [rebalancePage, strategyFilter]);

  useEffect(() => {
    if (mode === 'rebalance') fetchRebalance();
  }, [mode, fetchRebalance]);

  // 调仓回测轮询
  useEffect(() => {
    const hasActive = rebalanceData.some((r) => r.status === 'pending' || r.status === 'running');
    if (!hasActive) return;
    const timer = setInterval(() => fetchRebalance(), 3000);
    return () => clearInterval(timer);
  }, [rebalanceData, fetchRebalance]);

  const handleRebalanceDelete = async (id: number) => {
    try {
      await rebalanceService.delete(id);
      message.success('已删除');
      fetchRebalance();
    } catch {
      message.error('删除失败');
    }
  };

  // 批量回测轮询
  useEffect(() => {
    const hasActive = batchData.some((b) => b.status === 'pending' || b.status === 'running');
    if (!hasActive) return;
    const timer = setInterval(() => fetchBatch(), 3000);
    return () => clearInterval(timer);
  }, [batchData, fetchBatch]);

  const handleBatchDelete = async (id: number) => {
    try {
      await backtestService.deleteBatchBacktest(id);
      message.success('已删除');
      fetchBatch();
    } catch {
      message.error('删除失败');
    }
  };

  // —— 列定义 ——

  const rebalanceCols = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (text: string, record: RebalanceReport) => (
        <Button type="link" onClick={() => navigate(`/backtests/rebalance/${record.id}`)}>
          {text || `调仓回测 #${record.id}`}
        </Button>
      ),
    },
    {
      title: '策略', dataIndex: 'strategy_name', key: 'strategy',
      render: (text: string) => text || '—',
    },
    {
      title: '日期范围', key: 'range',
      render: (_: unknown, r: RebalanceReport) =>
        `${r.start_date.slice(0, 4)}-${r.start_date.slice(4, 6)}-${r.start_date.slice(6, 8)} ~ ${r.end_date.slice(0, 4)}-${r.end_date.slice(4, 6)}-${r.end_date.slice(6, 8)}`,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 120,
      render: (status: string) => <StatusTag status={status} type="backtest" />,
    },
    {
      title: '进度', key: 'progress', width: 100,
      render: (_: unknown, r: RebalanceReport) =>
        r.status === 'completed' ? `${r.total_days}/${r.total_days}` : `${r.completed_days}/${r.total_days}`,
    },
    {
      title: '总收益', key: 'return', width: 100,
      render: (_: unknown, r: RebalanceReport) => {
        if (!r.summary?.total_return_pct) return '—';
        const v = r.summary.total_return_pct;
        return <span style={{ color: v > 0 ? '#cf1322' : v < 0 ? '#3f8600' : '#999' }}>{v > 0 ? '+' : ''}{v.toFixed(2)}%</span>;
      },
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180,
      render: (v: string) => v ? new Date(v).toLocaleString() : '—',
    },
    {
      title: '操作', key: 'actions', width: 120,
      render: (_: unknown, r: RebalanceReport) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => navigate(`/backtests/rebalance/${r.id}`)}>
            查看
          </Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleRebalanceDelete(r.id)}>
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const singleCols = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    {
      title: '策略名称', dataIndex: 'strategy_name', key: 'strategy_name',
      render: (text: string, record: { id: number }) => (
        <Button type="link" onClick={() => navigate(`/backtests/${record.id}`)}>
          {text || `策略 #${record.id}`}
        </Button>
      ),
    },
    {
      title: '截止日', dataIndex: 'cutoff_date', key: 'cutoff_date', width: 120,
      render: (text: string) =>
        text ? `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}` : '—',
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (status: string) => <StatusTag status={status} type="backtest" />,
    },
    {
      title: '3天收益', key: 'avg_return_3d', width: 110,
      render: (_: unknown, record: { summary?: { avg_return_3d?: number } }) => (
        <ReturnLabel value={record.summary?.avg_return_3d} />
      ),
    },
    {
      title: '7天胜率', key: 'win_rate_7d', width: 110,
      render: (_: unknown, record: { summary?: { win_rate_7d?: number } }) => {
        if (!record.summary?.win_rate_7d) return '—';
        return `${(record.summary.win_rate_7d * 100).toFixed(1)}%`;
      },
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170,
    },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: unknown, record: { id: number }) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => navigate(`/backtests/${record.id}`)}>
            查看
          </Button>
          <Popconfirm
            title="确定删除此回测报告？"
            onConfirm={async () => {
              try {
                await deleteBacktest(record.id);
                message.success('删除成功');
              } catch { /* error handled by store */ }
            }}
            okText="确定" cancelText="取消"
          >
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const batchCols = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (text: string, record: BatchBacktestReport) => (
        <Button type="link" onClick={() => navigate(`/backtests/batch/${record.id}`)}>
          {text || `批量回测 #${record.id}`}
        </Button>
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
        <Space size="small">
          <Button type="link" size="small" onClick={() => navigate(`/backtests/batch/${r.id}`)}>
            查看
          </Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleBatchDelete(r.id)}>
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="简单回测"
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => {
            if (mode === 'single') fetchSingle();
            else if (mode === 'batch') fetchBatch();
            else fetchRebalance();
          }}>
            刷新
          </Button>
        }
      />

      <Card>
        <div style={{ marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)}>
            <Radio.Button value="single">单策略回测</Radio.Button>
            <Radio.Button value="batch">批量回测</Radio.Button>
            <Radio.Button value="rebalance">调仓回测</Radio.Button>
          </Radio.Group>

          {mode === 'single' && (
            <>
              <Space>
                <span>状态筛选：</span>
                <Select
                  value={statusFilter}
                  onChange={(v) => { setStatusFilter(v); fetchSingle({ page: 1, status: v }); }}
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
              <StockSearchLookup
                value={stockSearch}
                onChange={(val) => { setStockSearch(val); doSearch(val); }}
                placeholder="搜索股票代码或名称"
                style={{ width: 260 }}
              />
              <Button type="primary" onClick={() => doSearch(stockSearch)} style={{ marginLeft: 8 }}>
                搜索
              </Button>
            </>
          )}

          {mode === 'batch' && (
            <Select
              allowClear
              placeholder="按策略筛选"
              style={{ width: 200 }}
              value={strategyFilter}
              onChange={(v) => { setStrategyFilter(v); setBatchPage(1); }}
            />
          )}
          {mode === 'rebalance' && (
            <Select
              allowClear
              placeholder="按策略筛选"
              style={{ width: 200 }}
              value={strategyFilter}
              onChange={(v) => { setStrategyFilter(v); setRebalancePage(1); }}
            />
          )}
        </div>

        {mode === 'single' && (
          <Table
            dataSource={backtests}
            columns={singleCols}
            rowKey="id"
            loading={loading}
            scroll={{ x: 900 }}
            pagination={{
              current: page,
              pageSize: limit,
              total,
              onChange: (p, l) => fetchSingle({ page: p, limit: l }),
              showSizeChanger: true,
              showTotal: (t: number) => `共 ${t} 条`,
            }}
          />
        )}
        {mode === 'batch' && (
          <Table
            dataSource={batchData}
            columns={batchCols}
            rowKey="id"
            loading={batchLoading}
            pagination={{
              current: batchPage,
              total: batchTotal,
              pageSize: 20,
              onChange: (p) => { setBatchPage(p); },
              showTotal: (t) => `共 ${t} 条`,
            }}
          />
        )}
        {mode === 'rebalance' && (
          <Table
            dataSource={rebalanceData}
            columns={rebalanceCols}
            rowKey="id"
            loading={rebalanceLoading}
            scroll={{ x: 900 }}
            pagination={{
              current: rebalancePage,
              total: rebalanceTotal,
              pageSize: 20,
              onChange: (p) => { setRebalancePage(p); },
              showTotal: (t: number) => `共 ${t} 条`,
            }}
          />
        )}
      </Card>
    </>
  );
}
