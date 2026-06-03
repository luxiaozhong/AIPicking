import { useEffect, useState } from 'react';
import { Card, Button, Table, Space, message, Select, Popconfirm, Radio } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useBacktestStore } from '@/stores/backtestStore';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import ReturnLabel from '@/components/shared/ReturnLabel';
import StockSearchLookup from '@/components/shared/StockSearchLookup';
import { tradeSimService } from '@/services/tradeSimService';
import type { TradeSimReport, BatchTradeSimReport } from '@/types/tradeSim';

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
  const [listMode, setListMode] = useState<'simple' | 'trade-sim' | 'batch-trade-sim'>('simple');

  // 交易模拟列表
  const [tradeSims, setTradeSims] = useState<TradeSimReport[]>([]);
  const [tsTotal, setTsTotal] = useState(0);
  const [tsPage, setTsPage] = useState(1);
  const [tsLimit, setTsLimit] = useState(20);
  const [tsLoading, setTsLoading] = useState(false);

  // 批量交易模拟列表
  const [batchTs, setBatchTs] = useState<BatchTradeSimReport[]>([]);
  const [btsTotal, setBtsTotal] = useState(0);
  const [btsPage, setBtsPage] = useState(1);
  const [btsLimit, setBtsLimit] = useState(20);
  const [btsLoading, setBtsLoading] = useState(false);

  const doSearch = (stock: string) => {
    fetchBacktests({ page: 1, status: statusFilter, stock: stock || undefined });
  };

  useEffect(() => {
    fetchBacktests();
  }, [fetchBacktests]);

  useEffect(() => {
    startPolling();
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  // 交易模拟列表
  const fetchTradeSims = async (params?: { page?: number; limit?: number; status?: string }) => {
    setTsLoading(true);
    try {
      const res = await tradeSimService.getList({
        page: params?.page || tsPage,
        limit: params?.limit || tsLimit,
        status: params?.status || statusFilter,
      });
      setTradeSims(res.items);
      setTsTotal(res.total);
      setTsPage(res.page);
      setTsLimit(res.limit);
    } catch {
      // handled by user
    } finally {
      setTsLoading(false);
    }
  };

  useEffect(() => {
    if (listMode === 'trade-sim') {
      fetchTradeSims();
    } else if (listMode === 'batch-trade-sim') {
      fetchBatchTradeSims();
    }
  }, [listMode]);

  // 批量交易模拟列表
  const fetchBatchTradeSims = async (params?: { page?: number; limit?: number }) => {
    setBtsLoading(true);
    try {
      const res = await tradeSimService.getBatchList({
        page: params?.page || btsPage,
        limit: params?.limit || btsLimit,
      });
      setBatchTs(res.items);
      setBtsTotal(res.total);
      setBtsPage(res.page);
      setBtsLimit(res.limit);
    } catch {
      // handled by user
    } finally {
      setBtsLoading(false);
    }
  };

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
          <Popconfirm
            title="确定删除此回测报告？"
            onConfirm={async () => {
              try {
                await deleteBacktest(record.id);
                message.success('删除成功');
              } catch {
                // error message handled by useEffect watching store error state
              }
            }}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const tsColumns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    {
      title: '策略名称', dataIndex: 'strategy_name', key: 'strategy_name',
      render: (text: string, record: TradeSimReport) => (
        <Button type="link" onClick={() => navigate(`/backtests/trade-sim/${record.id}`)}>
          {text || `策略 #${record.id}`}
        </Button>
      ),
    },
    {
      title: '截止日', dataIndex: 'cutoff_date', key: 'cutoff_date', width: 130,
      render: (text: string) => text ? text.slice(0, 10) : '—',
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (status: string) => <StatusTag status={status} type="backtest" />,
    },
    {
      title: '交易笔数', key: 'total_trades', width: 90,
      render: (_: unknown, record: TradeSimReport) => record.summary?.total_trades ?? '—',
    },
    {
      title: '胜率', key: 'win_rate', width: 90,
      render: (_: unknown, record: TradeSimReport) =>
        record.summary ? `${record.summary.win_rate?.toFixed(1)}%` : '—',
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170,
    },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: unknown, record: TradeSimReport) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => navigate(`/backtests/trade-sim/${record.id}`)}>
            查看
          </Button>
          <Popconfirm
            title="确定删除？"
            onConfirm={async () => {
              try {
                await tradeSimService.delete(record.id);
                message.success('已删除');
                fetchTradeSims();
              } catch {
                message.error('删除失败');
              }
            }}
            okText="确定" cancelText="取消"
          >
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const btsColumns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (text: string, record: BatchTradeSimReport) => (
        <Button type="link" onClick={() => navigate(`/backtests/trade-sim/batch/${record.id}`)}>
          {text || `批量 #${record.id}`}
        </Button>
      ),
    },
    {
      title: '日期范围', key: 'date_range', width: 200,
      render: (_: unknown, record: BatchTradeSimReport) =>
        `${record.start_date} ~ ${record.end_date}`,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (status: string) => <StatusTag status={status} type="backtest" />,
    },
    {
      title: '进度', key: 'progress', width: 100,
      render: (_: unknown, record: BatchTradeSimReport) =>
        `${record.completed_days || 0} / ${record.total_days || 0}`,
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170,
    },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: unknown, record: BatchTradeSimReport) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => navigate(`/backtests/trade-sim/batch/${record.id}`)}>
            查看
          </Button>
          <Popconfirm
            title="确定删除？"
            onConfirm={async () => {
              try {
                await tradeSimService.deleteBatch(record.id);
                message.success('已删除');
                fetchBatchTradeSims();
              } catch {
                message.error('删除失败');
              }
            }}
            okText="确定" cancelText="取消"
          >
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const refreshCurrent = () => {
    if (listMode === 'simple') fetchBacktests();
    else if (listMode === 'trade-sim') fetchTradeSims();
    else fetchBatchTradeSims();
  };

  return (
    <>
      <PageHeader
        title="回测报告"
        extra={
          <Button
            icon={<ReloadOutlined />}
            onClick={refreshCurrent}
          >
            刷新
          </Button>
        }
      />

      <Card>
        <div style={{ marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <Radio.Group value={listMode} onChange={(e) => setListMode(e.target.value)}>
            <Radio.Button value="simple">简单回测</Radio.Button>
            <Radio.Button value="trade-sim">交易模拟</Radio.Button>
            <Radio.Button value="batch-trade-sim">批量交易模拟</Radio.Button>
          </Radio.Group>
          <Space>
            <span>状态筛选：</span>
            <Select
              value={statusFilter}
              onChange={(v) => {
                setStatusFilter(v);
                if (listMode === 'simple') {
                  fetchBacktests({ page: 1, status: v, stock: stockSearch || undefined });
                } else if (listMode === 'trade-sim') {
                  fetchTradeSims({ page: 1, status: v });
                }
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
          {listMode === 'simple' && (
            <>
              <StockSearchLookup
                value={stockSearch}
                onChange={(val) => {
                  setStockSearch(val);
                  doSearch(val);
                }}
                placeholder="搜索股票代码或名称"
                style={{ width: 260 }}
              />
              <Button type="primary" onClick={() => doSearch(stockSearch)} style={{ marginLeft: 8 }}>
                搜索
              </Button>
            </>
          )}
        </div>

        {listMode === 'simple' && (
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
        )}
        {listMode === 'trade-sim' && (
          <Table
            dataSource={tradeSims}
            columns={tsColumns}
            rowKey="id"
            loading={tsLoading}
            scroll={{ x: 800 }}
            pagination={{
              current: tsPage,
              pageSize: tsLimit,
              total: tsTotal,
              onChange: (p, l) => fetchTradeSims({ page: p, limit: l }),
              showSizeChanger: true,
              showTotal: (t: number) => `共 ${t} 条`,
            }}
          />
        )}
        {listMode === 'batch-trade-sim' && (
          <Table
            dataSource={batchTs}
            columns={btsColumns}
            rowKey="id"
            loading={btsLoading}
            scroll={{ x: 800 }}
            pagination={{
              current: btsPage,
              pageSize: btsLimit,
              total: btsTotal,
              onChange: (p, l) => fetchBatchTradeSims({ page: p, limit: l }),
              showSizeChanger: true,
              showTotal: (t: number) => `共 ${t} 条`,
            }}
          />
        )}
      </Card>
    </>
  );
}
