import { useEffect, useState } from 'react';
import { Card, Spin, Alert, Descriptions, Table, Button, Row, Col, Space, message } from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import { useBacktestStore } from '@/stores/backtestStore';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import ReturnLabel from '@/components/shared/ReturnLabel';
import StockKLineModal from '@/components/shared/StockKLineModal';
import StatCard from '@/components/shared/StatCard';
import LoadingSkeleton from '@/components/shared/LoadingSkeleton';
import ReturnComparisonChart from '@/components/charts/ReturnComparisonChart';
import WinRateDonutChart from '@/components/charts/WinRateDonutChart';
import type { RecommendationItem } from '@/types/backtest';

export default function BacktestDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentBacktest, fetchBacktest, loading, error, clearError } = useBacktestStore();

  useEffect(() => {
    if (id) fetchBacktest(parseInt(id));
  }, [id, fetchBacktest]);

  // Poll pending/running
  useEffect(() => {
    if (currentBacktest && (currentBacktest.status === 'pending' || currentBacktest.status === 'running')) {
      const timer = setInterval(() => {
        fetchBacktest(parseInt(id!));
      }, 3000);
      return () => clearInterval(timer);
    }
  }, [currentBacktest?.status, id, fetchBacktest]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const [selectedStock, setSelectedStock] = useState<RecommendationItem | null>(null);

  if (loading && !currentBacktest) {
    return <LoadingSkeleton type="detail" />;
  }

  if (!currentBacktest) {
    return <Alert type="error" title="回测报告不存在" />;
  }

  const { currentBacktest: bt } = useBacktestStore.getState();
  const summary = bt?.summary;
  const recommendations = bt?.recommendations || [];
  const isPending = bt?.status === 'pending' || bt?.status === 'running';
  const isCompleted = bt?.status === 'completed';
  const isFailed = bt?.status === 'failed';

  const columns = [
    { title: '排名', key: 'index', width: 60, render: (_: unknown, __: unknown, i: number) => i + 1 },
    {
      title: '股票代码',
      dataIndex: 'ts_code',
      key: 'ts_code',
      width: 110,
      render: (code: string, record: RecommendationItem) => (
        <a onClick={() => setSelectedStock(record)}>{code}</a>
      ),
    },
    { title: '股票名称', dataIndex: 'name', key: 'name', width: 100 },
    { title: '得分', dataIndex: 'score', key: 'score', width: 80, sorter: (a: { score: number }, b: { score: number }) => a.score - b.score },
    { title: '信号说明', dataIndex: 'signal', key: 'signal' },
    { title: '当日涨跌', dataIndex: 'return_0d', key: 'return_0d', width: 110, render: (v: number) => <ReturnLabel value={v} /> },
    { title: '3天涨跌', dataIndex: 'return_3d', key: 'return_3d', width: 110, render: (v: number) => <ReturnLabel value={v} /> },
    { title: '7天涨跌', dataIndex: 'return_7d', key: 'return_7d', width: 110, render: (v: number) => <ReturnLabel value={v} /> },
    { title: '15天涨跌', dataIndex: 'return_15d', key: 'return_15d', width: 110, render: (v: number) => <ReturnLabel value={v} /> },
  ];

  return (
    <>
      <PageHeader
        title="回测报告详情"
        breadcrumb={[
          { title: '回测报告', path: '/backtests' },
          { title: bt?.name || `报告 #${bt?.id}` },
        ]}
        extra={
          <Button onClick={() => navigate('/backtests')}>返回列表</Button>
        }
      />

      {/* Basic Info */}
      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="策略名称">{bt?.strategy_name || '—'}</Descriptions.Item>
          <Descriptions.Item label="截止日">
            {bt?.cutoff_date
              ? `${bt.cutoff_date.slice(0, 4)}-${bt.cutoff_date.slice(4, 6)}-${bt.cutoff_date.slice(6, 8)}`
              : '—'}
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <Space>
              <StatusTag status={bt?.status || ''} type="backtest" />
              {isPending && <Spin size="small" />}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">{bt?.created_at ? new Date(bt.created_at).toLocaleString() : '—'}</Descriptions.Item>
          {bt?.completed_at && (
            <Descriptions.Item label="完成时间" span={2}>
              {new Date(bt.completed_at).toLocaleString()}
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      {/* Error */}
      {isFailed && bt?.error_message && (
        <Alert type="error" message="执行失败" description={bt.error_message} style={{ marginBottom: 16 }} />
      )}

      {/* Summary Stats */}
      {isCompleted && summary && (
        <Card title="汇总指标" style={{ marginBottom: 16 }}>
          <Row gutter={[16, 16]}>
            <Col xs={12} sm={6}>
              <StatCard title="3天平均收益" value={`${(summary.avg_return_3d * 100).toFixed(2)}%`} color="#52c41a" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="7天平均收益" value={`${(summary.avg_return_7d * 100).toFixed(2)}%`} color="#52c41a" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="15天平均收益" value={`${(summary.avg_return_15d * 100).toFixed(2)}%`} color="#52c41a" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="15天胜率" value={`${(summary.win_rate_15d * 100).toFixed(1)}%`} color="#1677ff" />
            </Col>
          </Row>

          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={12} sm={8}>
              <StatCard
                title="入选总数"
                value={`${summary.total_qualifying ?? '—'}`}
                color="#1677ff"
              />
            </Col>
            <Col xs={12} sm={8}>
              <StatCard
                title="基础总股数"
                value={`${summary.base_stock_count ?? '—'}`}
                color="#722ed1"
              />
            </Col>
            <Col xs={12} sm={8}>
              <StatCard
                title="入选率"
                value={summary.pick_rate != null ? `${(summary.pick_rate * 100).toFixed(2)}%` : '—'}
                color="#52c41a"
              />
            </Col>
          </Row>

          {/* Charts */}
          <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
            <Col span={24}>
              <Card size="small" title="持仓期收益对比">
                <ReturnComparisonChart recommendations={recommendations} />
              </Card>
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col span={24}>
              <Card size="small" title="胜率分布">
                <WinRateDonutChart summary={summary} />
              </Card>
            </Col>
          </Row>
        </Card>
      )}

      {/* Recommendations Table */}
      {isCompleted && recommendations.length > 0 && (
        <Card title={`推荐股票（共 ${recommendations.length} 只）`}>
          <Table
            dataSource={recommendations}
            columns={columns}
            rowKey="ts_code"
            pagination={false}
            size="middle"
            scroll={{ x: 860 }}
          />
        </Card>
      )}

      {/* Pending / Running */}
      {isPending && (
        <Card>
          <Spin tip={bt?.status === 'pending' ? '等待中...' : '执行中...'}>
            <div style={{ padding: 60, textAlign: 'center', color: '#999' }}>
              {bt?.status === 'pending' ? '回测任务已提交，等待执行...' : '回测正在执行中，请稍候...'}
            </div>
          </Spin>
        </Card>
      )}

      <StockKLineModal
        ts_code={selectedStock?.ts_code ?? ''}
        name={selectedStock?.name}
        open={!!selectedStock}
        onClose={() => setSelectedStock(null)}
      />
    </>
  );
}
