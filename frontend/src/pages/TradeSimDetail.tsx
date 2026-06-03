// frontend/src/pages/TradeSimDetail.tsx
import { useEffect, useState } from 'react';
import {
  Card, Spin, Alert, Descriptions, Table, Button, Row, Col, Space, message, Typography,
} from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import StatCard from '@/components/shared/StatCard';
import LoadingSkeleton from '@/components/shared/LoadingSkeleton';
import { tradeSimService } from '@/services/tradeSimService';
import type { TradeSimReport, TradeItem, DailyTrackingItem } from '@/types/tradeSim';
import ReactECharts from 'echarts-for-react';

const { Text } = Typography;

function formatPct(v: number | null | undefined): string {
  if (v == null) return '—';
  const sign = v > 0 ? '+' : '';
  return `${sign}${v.toFixed(2)}%`;
}

function pctColor(v: number | null | undefined): string {
  if (v == null) return '#999';
  if (v > 0) return '#cf1322';
  if (v < 0) return '#3f8600';
  return '#999';
}

export default function TradeSimDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [report, setReport] = useState<TradeSimReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDetail = async () => {
    if (!id) return;
    try {
      const data = await tradeSimService.getDetail(parseInt(id));
      setReport(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDetail();
  }, [id]);

  // 轮询 pending/running
  useEffect(() => {
    if (report && (report.status === 'pending' || report.status === 'running')) {
      const timer = setInterval(fetchDetail, 3000);
      return () => clearInterval(timer);
    }
  }, [report?.status, id]);

  useEffect(() => {
    if (error) message.error(error);
  }, [error]);

  if (loading) return <LoadingSkeleton type="detail" />;
  if (!report) return <Alert type="error" title="报告不存在" />;

  const { trades, summary } = report;
  const isPending = report.status === 'pending' || report.status === 'running';

  const tradeColumns = [
    { title: '排名', key: 'index', width: 60, render: (_: any, __: any, i: number) => i + 1 },
    { title: '股票代码', dataIndex: 'ts_code', key: 'ts_code', width: 110 },
    { title: '股票名称', dataIndex: 'name', key: 'name', width: 100 },
    { title: '分数', dataIndex: 'score', key: 'score', width: 70 },
    { title: '买入价', dataIndex: 'buy_price', key: 'buy_price', width: 80, render: (v: number) => v?.toFixed(2) },
    { title: '卖出价', dataIndex: 'sell_price', key: 'sell_price', width: 80, render: (v: number | null) => v?.toFixed(2) ?? '—' },
    { title: '持有天数', dataIndex: 'hold_days', key: 'hold_days', width: 80 },
    {
      title: '收益率', dataIndex: 'return_pct', key: 'return_pct', width: 100,
      render: (v: number | null) => <Text style={{ color: pctColor(v), fontWeight: 'bold' }}>{formatPct(v)}</Text>,
    },
    {
      title: '最大回撤', dataIndex: 'max_drawdown', key: 'max_drawdown', width: 100,
      render: (v: number | null) => <Text style={{ color: '#3f8600' }}>{v != null ? `${v.toFixed(2)}%` : '—'}</Text>,
    },
    { title: '卖出原因', dataIndex: 'sell_reason', key: 'sell_reason' },
  ];

  const expandedRowRender = (record: TradeItem) => {
    const trackingCols = [
      { title: '日期', dataIndex: 'date', key: 'date', width: 110 },
      { title: '开盘', dataIndex: 'open', key: 'open', width: 80, render: (v: number) => v?.toFixed(2) },
      { title: '收盘', dataIndex: 'close', key: 'close', width: 80, render: (v: number) => v?.toFixed(2) },
      { title: '最高', dataIndex: 'high', key: 'high', width: 80, render: (v: number) => v?.toFixed(2) },
      { title: '最低', dataIndex: 'low', key: 'low', width: 80, render: (v: number) => v?.toFixed(2) },
      { title: 'MA10', dataIndex: 'ma10', key: 'ma10', width: 80, render: (v: number | null) => v?.toFixed(2) ?? '—' },
      { title: '止损线', dataIndex: 'ma10_stop_line', key: 'ma10_stop_line', width: 80, render: (v: number | null) => v?.toFixed(2) ?? '—' },
      {
        title: '浮盈', dataIndex: 'return_pct', key: 'return_pct', width: 90,
        render: (v: number) => <Text style={{ color: pctColor(v) }}>{formatPct(v)}</Text>,
      },
      {
        title: '状态', dataIndex: 'status', key: 'status', width: 90,
        render: (v: string) => {
          const colorMap: Record<string, string> = { holding: '#1677ff', stopped: '#ff4d4f', take_profit: '#52c41a', force_close: '#faad14' };
          return <Text style={{ color: colorMap[v] || '#999' }}>{v}</Text>;
        },
      },
    ];

    const chartOption = {
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 20, top: 10, bottom: 30 },
      xAxis: { type: 'category', data: record.daily_tracking.map((d: DailyTrackingItem) => d.date.slice(5)), axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
      series: [{
        type: 'line',
        data: record.daily_tracking.map((d: DailyTrackingItem) => d.close),
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#1677ff' },
      }],
    };

    return (
      <div style={{ padding: 16 }}>
        <Card size="small" title="每日追踪" style={{ marginBottom: 12 }}>
          <Table
            dataSource={record.daily_tracking}
            columns={trackingCols}
            rowKey="date"
            pagination={false}
            size="small"
            scroll={{ x: 800 }}
          />
        </Card>
        <ReactECharts option={chartOption} style={{ height: 200 }} />
      </div>
    );
  };

  const distChartOption = summary?.return_distribution ? {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ['<-10%', '-10%~0', '0~5%', '5%~10%', '>10%'] },
    yAxis: { type: 'value' },
    series: [{
      type: 'bar',
      data: [
        summary.return_distribution['lt_-10'] ?? 0,
        summary.return_distribution['-10_0'] ?? 0,
        summary.return_distribution['0_5'] ?? 0,
        summary.return_distribution['5_10'] ?? 0,
        summary.return_distribution['gt_10'] ?? 0,
      ],
      itemStyle: {
        color: (params: any) => ['#cf1322', '#ff7875', '#95de64', '#52c41a', '#237804'][params.dataIndex],
      },
    }],
  } : null;

  return (
    <>
      <PageHeader
        title="交易模拟回测详情"
        breadcrumb={[
          { title: '交易模拟报告', path: '/backtests/trade-sim' },
          { title: `交易模拟 #${report.id}` },
        ]}
        extra={<Button onClick={() => navigate('/backtests/trade-sim')}>返回列表</Button>}
      />

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="策略名称">{report.strategy_name || '—'}</Descriptions.Item>
          <Descriptions.Item label="截止日">{report.cutoff_date}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Space>
              <StatusTag status={report.status} type="backtest" />
              {isPending && <Spin size="small" />}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">{report.created_at ? new Date(report.created_at).toLocaleString() : '—'}</Descriptions.Item>
        </Descriptions>
      </Card>

      {report.status === 'failed' && report.error_message && (
        <Alert type="error" message="执行失败" description={report.error_message} style={{ marginBottom: 16 }} />
      )}

      {report.status === 'completed' && summary && (
        <Card title="汇总指标" style={{ marginBottom: 16 }}>
          <Row gutter={[16, 16]}>
            <Col xs={12} sm={6}>
              <StatCard title="总交易笔数" value={`${summary.total_trades}`} color="#1677ff" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="胜率" value={`${summary.win_rate?.toFixed(1)}%`} color="#52c41a" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="平均回报率" value={formatPct(summary.avg_return)} color={summary.avg_return > 0 ? '#cf1322' : '#3f8600'} />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="平均亏损率" value={formatPct(summary.avg_loss)} color="#3f8600" />
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={12} sm={6}>
              <StatCard title="盈亏比" value={summary.profit_loss_ratio?.toFixed(2) || '—'} color="#722ed1" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="最大连续盈利" value={`${summary.max_consecutive_wins} 笔`} color="#cf1322" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="最大连续亏损" value={`${summary.max_consecutive_losses} 笔`} color="#3f8600" />
            </Col>
          </Row>

          {distChartOption && (
            <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
              <Col span={24}>
                <Card size="small" title="收益分布">
                  <ReactECharts option={distChartOption} style={{ height: 250 }} />
                </Card>
              </Col>
            </Row>
          )}
        </Card>
      )}

      {report.status === 'completed' && trades && trades.length > 0 && (
        <Card title={`交易明细（共 ${trades.length} 笔）`}>
          <Table
            dataSource={trades}
            columns={tradeColumns}
            rowKey="ts_code"
            pagination={false}
            size="middle"
            scroll={{ x: 1000 }}
            expandable={{
              expandedRowRender,
              rowExpandable: (record: TradeItem) => record.daily_tracking.length > 0,
            }}
          />
        </Card>
      )}

      {isPending && (
        <Card>
          <Spin tip={report.status === 'pending' ? '等待中...' : '执行中...'}>
            <div style={{ padding: 60, textAlign: 'center', color: '#999' }}>
              {report.status === 'pending' ? '任务已提交，等待执行...' : '正在模拟交易，请稍候...'}
            </div>
          </Spin>
        </Card>
      )}
    </>
  );
}
