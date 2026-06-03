import { useEffect, useState } from 'react';
import { Card, Spin, Alert, Descriptions, Table, Button, Row, Col, Space, message, Collapse, Progress } from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import backtestService from '@/services/backtestService';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import ReturnLabel from '@/components/shared/ReturnLabel';
import StatCard from '@/components/shared/StatCard';
import ReturnComparisonChart from '@/components/charts/ReturnComparisonChart';
import WinRateDonutChart from '@/components/charts/WinRateDonutChart';
import StockKLineModal from '@/components/shared/StockKLineModal';
import type { BatchBacktestReport, DailyResultItem, RecommendationItem, BacktestSummary } from '@/types/backtest';
import ReactECharts from 'echarts-for-react';
import type { KLineItem } from '@/types/stock';
import { useKLineData } from '@/hooks/useKLineData';

function DailyTrackingPanel({ ts_code, cutoffDate }: { ts_code: string; cutoffDate: string }) {
  const { data, loading } = useKLineData(ts_code, 180);

  if (loading || !data) {
    return <Spin tip="加载中..." style={{ display: 'block', padding: 24 }} />;
  }

  const cutoffDateStr = `${cutoffDate.slice(0, 4)}-${cutoffDate.slice(4, 6)}-${cutoffDate.slice(6, 8)}`;
  const trackedItems = data.items.filter(
    (item: KLineItem) => item.trade_date > cutoffDateStr
  );

  if (trackedItems.length === 0) {
    return <div style={{ color: '#999', padding: 16 }}>暂无后续交易日数据</div>;
  }

  const trackingCols = [
    { title: '日期', dataIndex: 'trade_date', key: 'trade_date', width: 110 },
    { title: '开盘', dataIndex: 'open', key: 'open', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: '收盘', dataIndex: 'close', key: 'close', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: '最高', dataIndex: 'high', key: 'high', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: '最低', dataIndex: 'low', key: 'low', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: '成交量', dataIndex: 'vol', key: 'vol', width: 100, render: (v: number) => (v / 10000).toFixed(0) + '万' },
  ];

  const chartOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 10, bottom: 30 },
    xAxis: {
      type: 'category',
      data: trackedItems.map((d: KLineItem) => d.trade_date.slice(5)),
      axisLabel: { fontSize: 10 },
    },
    yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
    series: [{
      type: 'line',
      data: trackedItems.map((d: KLineItem) => d.close),
      smooth: true,
      lineStyle: { width: 2 },
      itemStyle: { color: '#1677ff' },
    }],
  };

  return (
    <div style={{ padding: 16 }}>
      <Card size="small" title={`每日追踪 — 截止日 ${cutoffDateStr}`} style={{ marginBottom: 12 }}>
        <Table
          dataSource={trackedItems}
          columns={trackingCols}
          rowKey="trade_date"
          pagination={false}
          size="small"
          scroll={{ x: 600 }}
        />
      </Card>
      <ReactECharts option={chartOption} style={{ height: 200 }} />
    </div>
  );
}

function DailyPanel({
  result,
  selectedStock,
  setSelectedStock,
}: {
  result: DailyResultItem;
  selectedStock: RecommendationItem | null;
  setSelectedStock: (s: RecommendationItem | null) => void;
}) {
  const isCompleted = result.status === 'completed';
  const isFailed = result.status === 'failed';
  const recs = result.recommendations || [];
  const summary = result.summary as BacktestSummary | null;

  const panelRecColumns = [
    { title: '排名', key: 'index', width: 60, render: (_: unknown, __: unknown, i: number) => i + 1 },
    {
      title: '代码',
      dataIndex: 'ts_code',
      key: 'ts_code',
      width: 110,
      render: (code: string, record: RecommendationItem) => (
        <a onClick={(e) => { e.stopPropagation(); setSelectedStock(record); }}>{code}</a>
      ),
    },
    { title: '名称', dataIndex: 'name', key: 'name', width: 100 },
    { title: '得分', dataIndex: 'score', key: 'score', width: 70 },
    { title: '当日', dataIndex: 'return_0d', key: 'return_0d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
    { title: '3天', dataIndex: 'return_3d', key: 'return_3d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
    { title: '7天', dataIndex: 'return_7d', key: 'return_7d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
    { title: '15天', dataIndex: 'return_15d', key: 'return_15d', width: 90, render: (v: number | null) => <ReturnLabel value={v ?? null} /> },
  ];

  return (
    <>
      {isFailed && result.error_message && (
        <Alert type="error" message="执行失败" description={result.error_message} style={{ marginBottom: 12 }} showIcon />
      )}
      {isCompleted && summary && (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
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
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={8}>
              <StatCard title="入选总数" value={`${summary.total_qualifying ?? '—'}`} color="#1677ff" />
            </Col>
            <Col xs={12} sm={8}>
              <StatCard title="基础总股数" value={`${summary.base_stock_count ?? '—'}`} color="#722ed1" />
            </Col>
            <Col xs={12} sm={8}>
              <StatCard
                title="入选率"
                value={summary.pick_rate != null ? `${(summary.pick_rate * 100).toFixed(2)}%` : '—'}
                color="#52c41a"
              />
            </Col>
          </Row>
        </>
      )}
      {isCompleted && recs.length > 0 && (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col span={24}>
              <Card size="small" title="持仓期收益对比">
                <ReturnComparisonChart recommendations={recs as RecommendationItem[]} />
              </Card>
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col span={24}>
              <Card size="small" title="胜率分布">
                <WinRateDonutChart summary={summary as BacktestSummary} />
              </Card>
            </Col>
          </Row>
          <Table
            dataSource={recs}
            columns={panelRecColumns}
            rowKey="ts_code"
            pagination={false}
            size="small"
            scroll={{ x: 760 }}
            expandable={{
              expandedRowRender: (record: RecommendationItem) => (
                <DailyTrackingPanel ts_code={record.ts_code} cutoffDate={result.cutoff_date} />
              ),
              rowExpandable: () => true,
            }}
          />
        </>
      )}
      {isCompleted && recs.length === 0 && (
        <div style={{ color: '#999', padding: 16 }}>当日无推荐标的</div>
      )}
    </>
  );
}

export default function BatchBacktestDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [report, setReport] = useState<BatchBacktestReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedStock, setSelectedStock] = useState<RecommendationItem | null>(null);

  const fetchData = async () => {
    if (!id) return;
    try {
      const res = await backtestService.getBatchBacktest(parseInt(id));
      setReport(res);
    } catch (err: any) {
      setError(err.response?.data?.detail || '获取报告失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [id]);

  useEffect(() => {
    if (report && (report.status === 'pending' || report.status === 'running')) {
      const timer = setInterval(fetchData, 3000);
      return () => clearInterval(timer);
    }
  }, [report?.status, id]);

  useEffect(() => {
    if (error) message.error(error);
  }, [error]);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!report) return <Alert type="error" message="报告不存在" />;

  const isPending = report.status === 'pending' || report.status === 'running';
  const isFailed = report.status === 'failed';
  const dailyResults = report.daily_results || [];
  const progressPct = report.total_days > 0 ? Math.round((report.completed_days / report.total_days) * 100) : 0;

  const collapseItems = dailyResults
    .filter((result: DailyResultItem) =>
      result.status === 'completed' && (result.recommendations?.length || 0) > 0
    )
    .map((result: DailyResultItem) => {
    const dateStr = `${result.cutoff_date.slice(0, 4)}-${result.cutoff_date.slice(4, 6)}-${result.cutoff_date.slice(6, 8)}`;
    const recCount = result.recommendations?.length || 0;
    const avg3d = result.summary && result.status === 'completed'
      ? `${((result.summary as BacktestSummary).avg_return_3d * 100).toFixed(2)}%`
      : null;

    return {
      key: result.cutoff_date,
      label: (
        <Space>
          <span>{dateStr}</span>
          <StatusTag status={result.status} type="backtest" />
          {recCount > 0 && <span style={{ color: '#999' }}>{recCount} 只推荐</span>}
          {avg3d !== null && <span style={{ color: parseFloat(avg3d) >= 0 ? '#52c41a' : '#ff4d4f' }}>3d avg: {avg3d}</span>}
        </Space>
      ),
      children: <DailyPanel result={result} selectedStock={selectedStock} setSelectedStock={setSelectedStock} />,
    };
  });

  return (
    <>
      <PageHeader
        title={report.name || `批量回测 #${report.id}`}
        breadcrumb={[
          { title: '批量回测', path: '/backtests/batch' },
          { title: report.name || `#${report.id}` },
        ]}
        extra={<Button onClick={() => navigate('/backtests/batch')}>返回列表</Button>}
      />

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="策略名称">{report.strategy_name || '—'}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Space>
              <StatusTag status={report.status} type="backtest" />
              {isPending && <Spin size="small" />}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="日期范围">
            {`${report.start_date.slice(0, 4)}-${report.start_date.slice(4, 6)}-${report.start_date.slice(6, 8)} ~ ${report.end_date.slice(0, 4)}-${report.end_date.slice(4, 6)}-${report.end_date.slice(6, 8)}`}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {report.created_at ? new Date(report.created_at).toLocaleString() : '—'}
          </Descriptions.Item>
        </Descriptions>
        {isPending && (
          <div style={{ marginTop: 16 }}>
            <Progress percent={progressPct} status="active" format={() => `${report.completed_days}/${report.total_days}`} />
          </div>
        )}
      </Card>

      {isFailed && report.error_message && (
        <Alert type="error" message="执行失败" description={report.error_message} style={{ marginBottom: 16 }} showIcon />
      )}

      {isPending && dailyResults.length === 0 && (
        <Card>
          <Spin tip="执行中...">
            <div style={{ padding: 60, textAlign: 'center', color: '#999' }}>
              批量回测正在执行中，请稍候...
            </div>
          </Spin>
        </Card>
      )}

      {dailyResults.length > 0 && (
        <Card title={`每日结果（${collapseItems.length} 天有入选）`}>
          <Collapse
            defaultActiveKey={dailyResults.length > 0 ? [dailyResults[0].cutoff_date] : []}
            items={collapseItems}
          />
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
