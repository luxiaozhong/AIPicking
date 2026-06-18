import { useState, useEffect, useCallback } from 'react';
import { Table, Button, Space, message, Popconfirm, Tag, Typography } from 'antd';
import { PlusOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons';
import { useAuthStore } from '@/stores/authStore';
import StockSearchLookup from '@/components/shared/StockSearchLookup';
import PageHeader from '@/components/shared/PageHeader';
import watchlistService from '@/services/watchlistService';
import type { WatchlistStock, WatchlistIndexInfo } from '@/services/watchlistService';
import type { ColumnsType } from 'antd/es/table';

const { Text } = Typography;

export default function Watchlist() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  const [stocks, setStocks] = useState<WatchlistStock[]>([]);
  const [indexInfo, setIndexInfo] = useState<WatchlistIndexInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [searchValue, setSearchValue] = useState('');
  const [pendingStocks, setPendingStocks] = useState<string[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await watchlistService.getWatchlist();
      setStocks(data.stocks);
      setIndexInfo(data.index_info);
    } catch (err) {
      message.error('获取临时观察列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSearchSelect = (tsCode: string) => {
    if (pendingStocks.includes(tsCode)) {
      message.warning('该股票已在待添加列表中');
      return;
    }
    if (stocks.some((s) => s.ts_code === tsCode)) {
      message.warning('该股票已在观察列表中');
      return;
    }
    setPendingStocks((prev) => [...prev, tsCode]);
    setSearchValue('');
  };

  const handleRemovePending = (tsCode: string) => {
    setPendingStocks((prev) => prev.filter((c) => c !== tsCode));
  };

  const handleAddStocks = async () => {
    if (!pendingStocks.length) return;
    setAdding(true);
    try {
      await watchlistService.addStocks(pendingStocks);
      message.success(`已添加 ${pendingStocks.length} 只股票`);
      setPendingStocks([]);
      await fetchData();
    } catch (err) {
      message.error('添加失败');
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (tsCode: string) => {
    try {
      await watchlistService.removeStock(tsCode);
      message.success('已移除');
      await fetchData();
    } catch (err) {
      message.error('删除失败');
    }
  };

  const columns: ColumnsType<WatchlistStock> = [
    {
      title: '#',
      key: 'idx',
      width: 50,
      render: (_: unknown, __: WatchlistStock, idx: number) => idx + 1,
    },
    {
      title: '代码',
      dataIndex: 'ts_code',
      key: 'ts_code',
      width: 130,
      render: (code: string) => <Text code>{code}</Text>,
    },
    {
      title: '名称',
      dataIndex: 'stock_name',
      key: 'stock_name',
      width: 120,
    },
    {
      title: '加入日期',
      dataIndex: 'eff_date',
      key: 'eff_date',
      width: 120,
    },
    ...(isAdmin
      ? [
          {
            title: '操作',
            key: 'action',
            width: 80,
            render: (_: unknown, record: WatchlistStock) => (
              <Popconfirm
                title="确认移除"
                description={`确定从临时观察中移除 ${record.stock_name}？`}
                onConfirm={() => handleDelete(record.ts_code)}
                okText="确认"
                cancelText="取消"
              >
                <Button type="text" danger size="small" icon={<DeleteOutlined />}>
                  移除
                </Button>
              </Popconfirm>
            ),
          },
        ]
      : []),
  ];

  return (
    <div>
      <PageHeader
        title="临时观察"
        breadcrumb={[{ title: '首页', path: '/' }, { title: '临时观察' }]}
        extra={
          <Space>
            <Text type="secondary">
              {indexInfo?.constituent_count ?? stocks.length} 只成分股
            </Text>
            <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>
              刷新
            </Button>
          </Space>
        }
      />

      {/* 添加区域（仅管理员可见） */}
      {isAdmin && (
        <div
          style={{
            marginBottom: 16,
            padding: 16,
            background: 'var(--ant-color-bg-container-disabled, #fafafa)',
            borderRadius: 8,
          }}
        >
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            {/* 待添加列表 */}
            {pendingStocks.length > 0 && (
              <div>
                <Text strong>待添加：</Text>
                <Space wrap style={{ marginLeft: 8 }}>
                  {pendingStocks.map((code) => (
                    <Tag key={code} closable onClose={() => handleRemovePending(code)}>
                      {code}
                    </Tag>
                  ))}
                </Space>
                <Button
                  type="primary"
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={handleAddStocks}
                  loading={adding}
                  style={{ marginLeft: 8 }}
                >
                  确认添加 ({pendingStocks.length})
                </Button>
              </div>
            )}

            {/* 搜索框 */}
            <StockSearchLookup
              value={searchValue}
              onChange={setSearchValue}
              onSelect={handleSearchSelect}
              placeholder="搜索股票代码或名称添加到临时观察（可多次搜索批量添加）"
              style={{ width: 500 }}
            />
          </Space>
        </div>
      )}

      {/* 成分股表格 */}
      <Table<WatchlistStock>
        columns={columns}
        dataSource={stocks}
        rowKey="ts_code"
        loading={loading}
        size="middle"
        pagination={stocks.length > 50 ? { pageSize: 50 } : false}
        locale={{ emptyText: '暂无成分股，请管理员添加' }}
      />
    </div>
  );
}
