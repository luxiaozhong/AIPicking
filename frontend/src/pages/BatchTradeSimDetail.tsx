import { useEffect, useState } from 'react';
import {
  Card, Spin, Alert, Descriptions, Table, Button, Row, Col, Space, message, Typography, Collapse,
} from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import StatCard from '@/components/shared/StatCard';
import LoadingSkeleton from '@/components/shared/LoadingSkeleton';
import StockKLineModal from '@/components/shared/StockKLineModal';
import { tradeSimService } from '@/services/tradeSimService';
import type { BatchTradeSimReport, BatchDailyResult, TradeItem, DailyTrackingItem } from '@/types/tradeSim';
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

export default function BatchTradeSimDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [report, setReport] = useState<BatchTradeSimReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedStock, setSelectedStock] = useState<TradeItem | null>(null);

  const fetchDetail = async () => {
    if (!id) return;
    try {
      const data = await tradeSimService.getBatchDetail(parseInt(id));
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

  const isPending = report.status === 'pending' || report.status === 'running';

  // Calculate aggregate summary
  const dailyResults = report.daily_results || [];
  const completedDays = dailyResults.filter(d => d.status === 'completed');
  const totalTrades = completedDays.reduce((sum, d) => sum + (d.summary?.total_trades || 0), 0);
  const avgWinRate = completedDays.length > 0
    ? completedDays.reduce((sum, d) => sum + (d.summary?.win_rate || 0), 0) / completedDays.length
    : 0;
  const avgReturn = completedDays.length > 0
    ? completedDays.reduce((sum, d) => sum + (d.summary?.avg_return || 0), 0) / completedDays.length
    : 0;

  const dayColumns = [
    { title: '日期', dataIndex: 'cutoff_date', key: 'cutoff_date', width: 120 },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (v: string) => <StatusTag status={v} type="backtest" /> },
    { title: '交易笔数', key: 'total_trades', width: 100,
      render: (_: any, record: BatchDailyResult) => record.summary?.total_trades ?? '—' },
    { title: '胜率', key: 'win_rate', width: 90,
      render: (_: any, record: BatchDailyResult) => record.summary ? `${record.summary.win_rate?.toFixed(1)}%` : '—' },
    { title: '平均回报率', key: 'avg_return', width: 110,
      render: (_: any, record: BatchDailyResult) => {
        const v = record.summary?.avg_return;
        return v != null ? <Text style={{ color: pctColor(v), fontWeight: 'bold' }}>{formatPct(v)}</Text> : '—';
      }},
    { title: '错误信息', dataIndex: 'error_message', key: 'error_message' },
  ];

  const expandedDayRender = (record: BatchDailyResult) => {
    if (!record.trades || record.trades.length === 0) {
      return <Text type="secondary">无交易数据</Text>;
    }

    const tradeColumns = [
      { title: '股票代码', dataIndex: 'ts_code', key: 'ts_code', width: 110,
        render: (code: string, trade: TradeItem) => (
          <a onClick={(e) => { e.stopPropagation(); setSelectedStock(trade); }}
             style={{ cursor: 'pointer', color: '#1677ff', textDecoration: 'underline' }}>{code}</a>
        ),
      },
      { title: '股票名称', dataIndex: 'name', key: 'name', width: 100 },
      { title: '买入价', dataIndex: 'buy_price', key: 'buy_price', width: 80, render: (v: number) => v?.toFixed(2) },
      { title: '卖出价', dataIndex: 'sell_price', key: 'sell_price', width: 80, render: (v: number | null) => v?.toFixed(2) ?? '—' },
      { title: '持有天数', dataIndex: 'hold_days', key: 'hold_days', width: 80 },
      {
        title: '收益率', dataIndex: 'return_pct', key: 'return_pct', width: 100,
        render: (v: number | null) => <Text style={{ color: pctColor(v), fontWeight: 'bold' }}>{formatPct(v)}</Text>,
      },
      { title: '卖出原因', dataIndex: 'sell_reason', key: 'sell_reason' },
    ];

    const dailyTrackingRender = (trade: TradeItem) => {
      if (!trade.daily_tracking || trade.daily_tracking.length === 0) {
        return <Text type="secondary">无追踪数据</Text>;
      }

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
        xAxis: { type: 'category', data: trade.daily_tracking.map((d: DailyTrackingItem) => d.date.slice(5)), axisLabel: { fontSize: 10 } },
        yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
        series: [{
          type: 'line',
          data: trade.daily_tracking.map((d: DailyTrackingItem) => d.close),
          smooth: true,
          lineStyle: { width: 2 },
          itemStyle: { color: '#1677ff' },
        }],
      };

      return (
        <div style={{ padding: 16 }}>
          <Card size="small" title="每日追踪" style={{ marginBottom: 12 }}>
            <Table
              dataSource={trade.daily_tracking}
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

    return (
      <Table
        dataSource={record.trades}
        columns={tradeColumns}
        rowKey="ts_code"
        pagination={false}
        size="small"
        scroll={{ x: 700 }}
        expandable={{
          expandedRowRender: dailyTrackingRender,
          rowExpandable: (trade: TradeItem) => (trade.daily_tracking?.length || 0) > 0,
        }}
      />
    );
  };

  // 过滤掉 0 交易的日期
  const daysWithTrades = dailyResults.filter(d => d.status === 'completed' && (d.trades?.length || 0) > 0);

  return (
    <>
      <PageHeader
        title={report.name || `批量交易模拟 #${report.id}`}
        breadcrumb={[
          { title: '交易模拟报告', path: '/backtests/trade-sim' },
          { title: report.name || `批量 #${report.id}` },
        ]}
        extra={<Button onClick={() => navigate('/backtests/trade-sim')}>返回列表</Button>}
      />

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="策略名称">{report.strategy_name || '—'}</Descriptions.Item>
          <Descriptions.Item label="日期范围">{report.start_date} ~ {report.end_date}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Space>
              <StatusTag status={report.status} type="backtest" />
              {isPending && <Spin size="small" />}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="进度">{report.completed_days} / {report.total_days} 天</Descriptions.Item>
        </Descriptions>
      </Card>

      {report.status === 'failed' && report.error_message && (
        <Alert type="error" message="执行失败" description={report.error_message} style={{ marginBottom: 16 }} showIcon />
      )}

      {report.status === 'completed' && (
        <Card title="汇总指标" style={{ marginBottom: 16 }}>
          <Row gutter={[16, 16]}>
            <Col xs={12} sm={6}>
              <StatCard title="总交易日" value={`${report.total_days}`} color="#1677ff" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="完成天数" value={`${report.completed_days}`} color="#52c41a" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="平均胜率" value={`${avgWinRate.toFixed(1)}%`} color="#722ed1" />
            </Col>
            <Col xs={12} sm={6}>
              <StatCard title="总交易笔数" value={`${totalTrades}`} color="#fa8c16" />
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={12} sm={6}>
              <StatCard title="平均回报率" value={formatPct(avgReturn)} color={avgReturn > 0 ? '#cf1322' : '#3f8600'} />
            </Col>
          </Row>
        </Card>
      )}

      {report.status === 'completed' && daysWithTrades.length > 0 && (
        <Card title={`每日结果（${daysWithTrades.length} 天有交易）`}>
          <Table
            dataSource={daysWithTrades}
            columns={dayColumns}
            rowKey="cutoff_date"
            pagination={false}
            size="middle"
            scroll={{ x: 700 }}
            expandable={{
              expandedRowRender: expandedDayRender,
              rowExpandable: (record: BatchDailyResult) => record.status === 'completed' && (record.trades?.length || 0) > 0,
            }}
          />
        </Card>
      )}

      {isPending && (
        <Card>
          <Spin description={report.status === 'pending' ? '等待中...' : '执行中...'}>
            <div style={{ padding: 60, textAlign: 'center', color: '#999' }}>
              {report.status === 'pending' ? '批量任务已提交，等待执行...' : `正在回测（${report.completed_days}/${report.total_days}）...`}
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
