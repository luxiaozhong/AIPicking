import { useEffect, useMemo, useState } from 'react';
import { Card, Button, Table, Input, Select, Space, message, Popconfirm, Tag } from 'antd';
import { AppstoreOutlined, RobotOutlined, GlobalOutlined, LockOutlined, BarChartOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useStrategyStore } from '@/stores/strategyStore';
import { useAuthStore } from '@/stores/authStore';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import { isVisualEditable } from '@/types/strategy';
import type { Strategy } from '@/types/strategy';

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
    updateStrategy,
    permanentDeleteStrategy,
    publishStrategy,
    unpublishStrategy,
    clearError,
  } = useStrategyStore();

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [scopeFilter, setScopeFilter] = useState<string>('all');

  useEffect(() => {
    fetchStrategies({ scope: 'all' });
  }, [fetchStrategies]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const handleSearch = (value: string) => {
    setSearch(value);
    fetchStrategies({ page: 1, search: value || undefined, status: statusFilter, scope: scopeFilter });
  };

  const handleStatusFilter = (value: string | undefined) => {
    setStatusFilter(value);
    fetchStrategies({ page: 1, search: search || undefined, status: value, scope: scopeFilter });
  };

  const handleScopeFilter = (value: string) => {
    setScopeFilter(value);
    fetchStrategies({ page: 1, search: search || undefined, status: statusFilter, scope: value });
  };

  const handlePageChange = (newPage: number, newLimit: number) => {
    fetchStrategies({ page: newPage, limit: newLimit, search: search || undefined, status: statusFilter, scope: scopeFilter });
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteStrategy(id);
      message.success('删除成功');
      fetchStrategies({ page: 1, search: search || undefined, status: statusFilter, scope: scopeFilter });
    } catch {
      message.error('删除失败');
    }
  };

  const handleRestore = async (id: number) => {
    try {
      await updateStrategy(id, { status: 'active' });
      message.success('恢复成功');
      fetchStrategies({ page: 1, search: search || undefined, status: statusFilter, scope: scopeFilter });
    } catch {
      message.error('恢复失败');
    }
  };

  const handlePermanentDelete = async (id: number) => {
    try {
      await permanentDeleteStrategy(id);
      message.success('彻底删除成功');
      fetchStrategies({ page: 1, search: search || undefined, status: statusFilter, scope: scopeFilter });
    } catch {
      message.error('彻底删除失败');
    }
  };

  const handlePublish = async (id: number) => {
    try {
      await publishStrategy(id);
      message.success('已发布');
    } catch {
      message.error('发布失败');
    }
  };

  const handleUnpublish = async (id: number) => {
    try {
      await unpublishStrategy(id);
      message.success('已取消发布');
    } catch {
      message.error('取消发布失败');
    }
  };

  const columns = useMemo(() => {
    const cols: any[] = [
      {
        title: '策略名称',
        dataIndex: 'name',
        key: 'name',
        width: 180,
        render: (text: string, record: Strategy) => (
          <Button
            type="link"
            onClick={() => navigate(`/strategies/${record.id}`)}
            style={{ whiteSpace: 'normal', wordBreak: 'break-word', textAlign: 'left' }}
          >
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

    cols.push({
      title: '创建者',
      dataIndex: 'owner_name',
      key: 'owner_name',
      width: 110,
      render: (name: string) => name || '—',
    });

    cols.push(
      {
        title: '发布状态',
        dataIndex: 'is_published',
        key: 'is_published',
        width: 90,
        render: (published: boolean) =>
          published ? (
            <Tag icon={<GlobalOutlined />} color="blue">已发布</Tag>
          ) : (
            <Tag icon={<LockOutlined />}>私密</Tag>
          ),
      },
      {
        title: '评分',
        dataIndex: 'avg_score',
        key: 'avg_score',
        width: 100,
        render: (score: number | null, record: Strategy) =>
          score ? (
            <span>⭐ {(score as number).toFixed(1)} ({record.rating_count})</span>
          ) : (
            <span style={{ color: '#ccc' }}>暂无</span>
          ),
      },
      {
        title: '标签',
        dataIndex: 'tags',
        key: 'tags',
        width: 160,
        render: (tags: string[]) =>
          tags?.length
            ? tags.map((tag: string) => <StatusTag key={tag} status={tag} />)
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
        width: 240,
        render: (_: unknown, record: Strategy) => {
          const isOwner = String(record.user_id) === String(user?.id);
          if (!isOwner && record.is_published) {
            return (
              <Space size="small">
                <Button type="link" size="small" onClick={() => navigate(`/strategies/${record.id}`)}>
                  查看
                </Button>
                <Button
                  type="link"
                  size="small"
                  icon={<BarChartOutlined />}
                  onClick={() => navigate(`/strategies/${record.id}/backtest`)}
                >
                  回测
                </Button>
              </Space>
            );
          }

          return (
            <Space size="small">
              <Button type="link" size="small" onClick={() => navigate(`/strategies/${record.id}`)}>
                查看
              </Button>
              {isVisualEditable(record.factor_config) && (
                <Button type="link" size="small" onClick={() => navigate(`/strategies/builder?id=${record.id}`)}>
                  编辑
                </Button>
              )}
              {record.status === 'deleted' ? (
                <>
                  <Popconfirm title="确定恢复此策略？" onConfirm={() => handleRestore(record.id)} okText="确定" cancelText="取消">
                    <Button type="link" size="small">恢复</Button>
                  </Popconfirm>
                  <Popconfirm title="彻底删除将同时删除所有关联的回测报告，不可恢复。确定继续？" onConfirm={() => handlePermanentDelete(record.id)} okText="确定" cancelText="取消">
                    <Button type="link" size="small" danger>彻底删除</Button>
                  </Popconfirm>
                </>
              ) : (
                <>
                  {record.is_published ? (
                    <Button type="link" size="small" onClick={() => handleUnpublish(record.id)}>取消发布</Button>
                  ) : (
                    <Button type="link" size="small" onClick={() => handlePublish(record.id)}>发布</Button>
                  )}
                  <Popconfirm title="确定删除此策略？" onConfirm={() => handleDelete(record.id)} okText="确定" cancelText="取消">
                    <Button type="link" size="small" danger>删除</Button>
                  </Popconfirm>
                </>
              )}
            </Space>
          );
        },
      }
    );

    return cols;
  }, [isAdmin, navigate, user?.id, scopeFilter, statusFilter, search]);

  return (
    <>
      <PageHeader
        title="策略管理"
        breadcrumb={[{ title: '策略管理', path: '/strategies' }]}
        extra={
          <>
            <Button icon={<AppstoreOutlined />} onClick={() => navigate('/strategies/builder')} data-tour-id="btn-visual-builder">
              可视化构建
            </Button>
            <Button icon={<RobotOutlined />} onClick={() => navigate('/strategies/ai-builder')} data-tour-id="btn-ai-builder">
              AI 参考选股
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
            placeholder="范围筛选"
            value={scopeFilter}
            onChange={handleScopeFilter}
            style={{ width: 130 }}
            options={[
              { label: '全部', value: 'all' },
              { label: '我的', value: 'mine' },
              { label: '已发布', value: 'published' },
            ]}
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
          scroll={{ x: 1300 }}
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
