import { useEffect, useState } from 'react';
import { Card, Button, Table, Space, message, Select, Popconfirm, Radio } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import { tradeSimService } from '@/services/tradeSimService';
import type { TradeSimReport, BatchTradeSimReport } from '@/types/tradeSim';

export default function TradeSimList() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<'single' | 'batch'>('single');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

  // 单日
  const [items, setItems] = useState<TradeSimReport[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(false);

  // 批量
  const [batchItems, setBatchItems] = useState<BatchTradeSimReport[]>([]);
  const [batchTotal, setBatchTotal] = useState(0);
  const [batchPage, setBatchPage] = useState(1);
  const [batchLimit, setBatchLimit] = useState(20);
  const [batchLoading, setBatchLoading] = useState(false);

  const fetchList = async (p?: { page?: number; limit?: number; status?: string }) => {
    setLoading(true);
    try {
      const res = await tradeSimService.getList({
        page: p?.page || page,
        limit: p?.limit || limit,
        status: p?.status !== undefined ? p.status : statusFilter,
      });
      setItems(res.items);
      setTotal(res.total);
      setPage(res.page);
      setLimit(res.limit);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const fetchBatchList = async (p?: { page?: number; limit?: number }) => {
    setBatchLoading(true);
    try {
      const res = await tradeSimService.getBatchList({
        page: p?.page || batchPage,
        limit: p?.limit || batchLimit,
      });
      setBatchItems(res.items);
      setBatchTotal(res.total);
      setBatchPage(res.page);
      setBatchLimit(res.limit);
    } catch {
      // ignore
    } finally {
      setBatchLoading(false);
    }
  };

  useEffect(() => { fetchList(); }, []);
  useEffect(() => {
    if (mode === 'batch') fetchBatchList();
  }, [mode]);

  const singleCols = [
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
                fetchList();
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

  const batchCols = [
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
                fetchBatchList();
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

  return (
    <>
      <PageHeader
        title="交易模拟报告"
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => mode === 'single' ? fetchList() : fetchBatchList()}>
            刷新
          </Button>
        }
      />

      <Card>
        <div style={{ marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)}>
            <Radio.Button value="single">单日交易模拟</Radio.Button>
            <Radio.Button value="batch">批量交易模拟</Radio.Button>
          </Radio.Group>
          {mode === 'single' && (
            <Space>
              <span>状态筛选：</span>
              <Select
                value={statusFilter}
                onChange={(v) => { setStatusFilter(v); fetchList({ page: 1, status: v }); }}
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
          )}
        </div>

        {mode === 'single' ? (
          <Table
            dataSource={items}
            columns={singleCols}
            rowKey="id"
            loading={loading}
            scroll={{ x: 800 }}
            pagination={{
              current: page,
              pageSize: limit,
              total,
              onChange: (p, l) => fetchList({ page: p, limit: l }),
              showSizeChanger: true,
              showTotal: (t: number) => `共 ${t} 条`,
            }}
          />
        ) : (
          <Table
            dataSource={batchItems}
            columns={batchCols}
            rowKey="id"
            loading={batchLoading}
            scroll={{ x: 800 }}
            pagination={{
              current: batchPage,
              pageSize: batchLimit,
              total: batchTotal,
              onChange: (p, l) => fetchBatchList({ page: p, limit: l }),
              showSizeChanger: true,
              showTotal: (t: number) => `共 ${t} 条`,
            }}
          />
        )}
      </Card>
    </>
  );
}
