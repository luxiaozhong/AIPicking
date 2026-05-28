import { useEffect, useMemo, useState } from 'react';
import { Card, Button, Table, Input, Select, Space, message, Popconfirm } from 'antd';
import { UploadOutlined, AppstoreOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useStrategyStore } from '@/stores/strategyStore';
import { useAuthStore } from '@/stores/authStore';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';

const { Search } = Input;

export default function StrategyList() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';
  const {
    strategies,
    total,
    page,
    limit,
    loading,
    error,
    fetchStrategies,
    deleteStrategy,
    clearError,
  } = useStrategyStore();

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

  useEffect(() => {
    fetchStrategies();
  }, [fetchStrategies]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const handleSearch = (value: string) => {
    setSearch(value);
    fetchStrategies({ page: 1, search: value || undefined, status: statusFilter });
  };

  const handleStatusFilter = (value: string | undefined) => {
    setStatusFilter(value);
    fetchStrategies({ page: 1, search: search || undefined, status: value });
  };

  const handlePageChange = (newPage: number, newLimit: number) => {
    fetchStrategies({ page: newPage, limit: newLimit, search: search || undefined, status: statusFilter });
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteStrategy(id);
      message.success('删除成功');
    } catch {
      message.error('删除失败');
    }
  };

  const columns = useMemo(() => {
    const cols: any[] = [
      {
        title: '策略名称',
        dataIndex: 'name',
        key: 'name',
        width: 180,
        render: (text: string, record: { id: number }) => (
          <Button type="link" onClick={() => navigate(`/strategies/${record.id}`)}>
            {text}
          </Button>
        ),
      },
      {
        title: '描述',
        dataIndex: 'description',
        key: 'description',
        ellipsis: true,
        width: 200,
      },
    ];

    if (isAdmin) {
      cols.push({
        title: '创建者',
        dataIndex: 'owner_name',
        key: 'owner_name',
        width: 110,
        render: (name: string) => name || '—',
      });
    }

    cols.push(
      {
        title: '标签',
        dataIndex: 'tags',
        key: 'tags',
        width: 160,
        render: (tags: string[]) =>
          tags?.length
            ? tags.map((tag) => (
                <StatusTag key={tag} status={tag} />
              ))
            : '—',
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 90,
        render: (status: string) => <StatusTag status={status} />,
      },
      {
        title: '版本',
        dataIndex: 'version',
        key: 'version',
        width: 60,
      },
      {
        title: '创建时间',
        dataIndex: 'created_at',
        key: 'created_at',
        width: 170,
      },
      {
        title: '更新时间',
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 170,
      },
      {
        title: '操作',
        key: 'action',
        width: 180,
        render: (_: unknown, record: { id: number }) => (
          <Space size="small">
            <Button type="link" size="small" onClick={() => navigate(`/strategies/${record.id}`)}>
              查看
            </Button>
            <Button type="link" size="small" onClick={() => navigate(`/strategies/${record.id}/edit`)}>
              编辑
            </Button>
            <Popconfirm
              title="确定删除此策略？"
              onConfirm={() => handleDelete(record.id)}
              okText="确定"
              cancelText="取消"
            >
              <Button type="link" size="small" danger>
                删除
              </Button>
            </Popconfirm>
          </Space>
        ),
      }
    );

    return cols;
  }, [isAdmin, navigate]);

  return (
    <>
      <PageHeader
        title="策略管理"
        breadcrumb={[{ title: '策略管理', path: '/strategies' }]}
        extra={
          <>
            <Button icon={<AppstoreOutlined />} onClick={() => navigate('/strategies/builder')}>
              可视化构建
            </Button>
            <Button type="primary" icon={<UploadOutlined />} onClick={() => navigate('/strategies/upload')}>
              上传策略
            </Button>
          </>
        }
      />

      <Card>
        <div style={{ marginBottom: 16, display: 'flex', gap: 12 }}>
          <Search
            placeholder="搜索策略名称"
            onSearch={handleSearch}
            style={{ width: 300 }}
            allowClear
          />
          <Select
            placeholder="状态筛选"
            value={statusFilter}
            onChange={handleStatusFilter}
            style={{ width: 130 }}
            allowClear
            options={[
              { label: '活跃', value: 'active' },
              { label: '已归档', value: 'archived' },
              { label: '已删除', value: 'deleted' },
            ]}
          />
        </div>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={strategies}
          loading={loading}
          scroll={{ x: 1100 }}
          pagination={{
            current: page,
            pageSize: limit,
            total,
            onChange: handlePageChange,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (t: number) => `共 ${t} 条`,
          }}
        />
      </Card>
    </>
  );
}
