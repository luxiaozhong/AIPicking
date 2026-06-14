import { useEffect, useState } from 'react';
import {
  Card, Spin, Alert, Table, Button, Row, Col, Typography, Collapse, Tag,
} from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import StatCard from '@/components/shared/StatCard';
import LoadingSkeleton from '@/components/shared/LoadingSkeleton';
import rebalanceService from '@/services/rebalanceService';
import type { RebalanceReport, TradeRecord, DailySnapshot } from '@/services/rebalanceService';
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

function actionColor(action: string): string {
  return action === 'buy' ? 'red' : 'green';
}

function actionLabel(action: string): string {
  return action === 'buy' ? '买入' : '卖出';
}

export default function RebalanceDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [report, setReport] = useState<RebalanceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDetail = async () => {
    if (!id) return;
    try {
      const data = await rebalanceService.getDetail(parseInt(id));
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

  if (loading) return <LoadingSkeleton type="detail" />;
  if (!report) return <Alert type="error" title="报告不存在" showIcon />;

  const { summary, trades, daily_snapshots } = report;
  const isPending = report.status === 'pending' || report.status === 'running';

  // 资产曲线图
  const chartOption = daily_snapshots && daily_snapshots.length > 0 ? {
    tooltip: { trigger: 'axis' as const },
    grid: { left: 60, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: 'category' as const,
      data: daily_snapshots.map((s: DailySnapshot) => s.date),
      axisLabel: { rotate: 45, fontSize: 10 },
    },
    yAxis: {
      type: 'value' as const,
      name: '总资产 (元)',
      axisLabel: { formatter: (v: number) => `${(v / 10000).toFixed(0)}万` },
    },
    series: [
      {
        name: '总资产',
        type: 'line',
        data: daily_snapshots.map((s: DailySnapshot) => s.total_value),
        smooth: true,
        lineStyle: { color: '#1677ff', width: 2 },
        areaStyle: { color: 'rgba(22,119,255,0.08)' },
        markLine: summary ? {
          silent: true,
          data: [{ yAxis: summary.initial_capital, name: '初始资金', label: { formatter: '初始' } }],
          lineStyle: { color: '#999', type: 'dashed' as const },
        } : undefined,
      },
    ],
  } : null;

  const tradeColumns = [
    { title: '日期', dataIndex: 'date', key: 'date', width: 100 },
    { title: '代码', dataIndex: 'ts_code', key: 'ts_code', width: 90 },
    { title: '名称', dataIndex: 'name', key: 'name', width: 80 },
    {
      title: '方向', dataIndex: 'action', key: 'action', width: 55,
      render: (v: string) => <Tag color={actionColor(v)}>{actionLabel(v)}</Tag>,
    },
    { title: '价格', dataIndex: 'price', key: 'price', width: 70, render: (v: number) => v?.toFixed(2) },
    { title: '股数', dataIndex: 'shares', key: 'shares', width: 70, render: (v: number) => v?.toLocaleString() },
    { title: '成交额', dataIndex: 'amount', key: 'amount', width: 90, render: (v: number) => `¥${v?.toLocaleString()}` },
    {
      title: '手续费', key: 'fee', width: 70,
      render: (_: unknown, r: TradeRecord) => {
        if (r.action === 'buy') return r.commission != null ? `¥${r.commission.toFixed(2)}` : '—';
        const fee = (r.commission || 0) + (r.stamp_duty || 0);
        return `¥${fee.toFixed(2)}`;
      },
    },
    {
      title: '盈亏', key: 'pnl', width: 90,
      render: (_: unknown, r: TradeRecord) => {
        if (r.action !== 'sell' || r.pnl == null) return '—';
        return <span style={{ color: pctColor(r.pnl), fontWeight: 500 }}>¥{r.pnl.toLocaleString()}</span>;
      },
    },
    {
      title: '收益率', key: 'pnl_pct', width: 70,
      render: (_: unknown, r: TradeRecord) => {
        if (r.action !== 'sell' || r.pnl_pct == null) return '—';
        return <span style={{ color: pctColor(r.pnl_pct) }}>{formatPct(r.pnl_pct)}</span>;
      },
    },
    { title: '原因', dataIndex: 'reason', key: 'reason', width: 100, ellipsis: true },
  ];

  // 每日快照折叠面板
  const snapshotPanels = daily_snapshots?.slice(-20).reverse().map((s: DailySnapshot, i: number) => ({
    key: s.date,
    label: (
      <span>
        {s.date}
        <Tag color={s.action === 'rebalance' ? 'orange' : 'green'} style={{ marginLeft: 8 }}>
          {s.action === 'rebalance' ? '调仓' : '持有'}
        </Tag>
        <Text style={{ marginLeft: 12, color: pctColor(s.daily_return_pct) }}>
          日收益 {formatPct(s.daily_return_pct)}
        </Text>
        <Text style={{ marginLeft: 12 }}>
          总资产 ¥{s.total_value?.toLocaleString()}
        </Text>
      </span>
    ),
    children: (
      <Table
        dataSource={s.holdings.map((h, j) => ({ ...h, key: j }))}
        columns={[
          { title: '代码', dataIndex: 'ts_code', width: 90 },
          { title: '名称', dataIndex: 'name', width: 80 },
          { title: '持仓', dataIndex: 'shares', width: 70, render: (v: number) => v?.toLocaleString() },
          { title: '买入价', dataIndex: 'buy_price', width: 70, render: (v: number) => v?.toFixed(2) },
          { title: '收盘价', dataIndex: 'close_price', width: 70, render: (v: number) => v?.toFixed(2) },
          { title: '市值', dataIndex: 'market_value', width: 90, render: (v: number) => `¥${v?.toLocaleString()}` },
          {
            title: '未实现盈亏', key: 'unrealized', width: 110,
            render: (_: unknown, h: any) => {
              if (h.unrealized_pnl == null) return '—';
              return <span style={{ color: pctColor(h.unrealized_pnl) }}>¥{h.unrealized_pnl?.toLocaleString()} ({formatPct(h.unrealized_pnl_pct)})</span>;
            },
          },
        ]}
        pagination={false}
        size="small"
      />
    ),
  }));

  return (
    <>
      <PageHeader
        title={report.name || `调仓回测 #${report.id}`}
        breadcrumb={[
          { title: '回测列表', path: '/backtests' },
          { title: '调仓回测详情' },
        ]}
      />

      {isPending && (
        <Alert
          type="info"
          message={`回测进行中... ${report.completed_days}/${report.total_days} 天已完成`}
          style={{ marginBottom: 16 }}
          showIcon
        />
      )}

      {report.error_message && (
        <Alert type="error" message={report.error_message} style={{ marginBottom: 16 }} showIcon />
      )}

      {report.status === 'completed' && summary && (
        <>
          {/* 统计卡片 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <StatCard title="总收益率" value={formatPct(summary.total_return_pct)} valueColor={pctColor(summary.total_return_pct)} />
            </Col>
            <Col span={6}>
              <StatCard title="年化收益率" value={formatPct(summary.annualized_return_pct)} valueColor={pctColor(summary.annualized_return_pct)} />
            </Col>
            <Col span={6}>
              <StatCard title="最大回撤" value={formatPct(summary.max_drawdown_pct)} valueColor="#3f8600" />
            </Col>
            <Col span={6}>
              <StatCard title="夏普比率" value={summary.sharpe_ratio?.toFixed(2)} />
            </Col>
          </Row>

          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <StatCard title="最终资产" value={`¥${summary.final_value?.toLocaleString()}`} />
            </Col>
            <Col span={6}>
              <StatCard title="日胜率" value={`${summary.daily_win_rate?.toFixed(1)}%`} />
            </Col>
            <Col span={6}>
              <StatCard title="交易总次数" value={String(summary.total_trades)} subtitle={`${summary.total_buys}买 / ${summary.total_sells}卖`} />
            </Col>
            <Col span={6}>
              <StatCard title="换手率" value={summary.turnover_rate?.toFixed(2)} />
            </Col>
          </Row>

          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <StatCard title="初始资金" value={`¥${summary.initial_capital?.toLocaleString()}`} />
            </Col>
            <Col span={6}>
              <StatCard title="交易天数" value={String(summary.total_trading_days)} />
            </Col>
            <Col span={6}>
              <StatCard title="累计费用" value={`¥${summary.total_fees_paid?.toLocaleString()}`} subtitle="手续费 + 印花税" />
            </Col>
            <Col span={6}>
              <StatCard title="已实现盈亏" value={`¥${summary.realized_pnl?.toLocaleString()}`} valueColor={pctColor(summary.realized_pnl)} subtitle={`${summary.win_trades}赢 / ${summary.lose_trades}亏`} />
            </Col>
          </Row>
        </>
      )}

      {/* 资产曲线 */}
      {chartOption && (
        <Card title="资产曲线" style={{ marginBottom: 16 }}>
          <ReactECharts option={chartOption} style={{ height: 350 }} />
        </Card>
      )}

      {/* 策略参数 */}
      {report.config && (
        <Card title="回测参数" size="small" style={{ marginBottom: 16 }}>
          <Row gutter={[24, 8]}>
            <Col span={6}><Text type="secondary">策略：</Text>{report.strategy_name || `#${report.strategy_id}`}</Col>
            <Col span={6}><Text type="secondary">日期范围：</Text>{report.start_date} ~ {report.end_date}</Col>
            <Col span={6}><Text type="secondary">初始资金：</Text>¥{report.config.initial_capital?.toLocaleString()}</Col>
            <Col span={6}><Text type="secondary">指数：</Text>{report.config.index_code}</Col>
            <Col span={6}><Text type="secondary">推荐数 N：</Text>{report.config.N}</Col>
            <Col span={6}><Text type="secondary">回顾天数 M：</Text>{report.config.M}</Col>
            <Col span={6}><Text type="secondary">排序方式：</Text>{report.config.variant === 'value' ? '资金流/市值 (V1)' : '资金流'}</Col>
          </Row>
        </Card>
      )}

      {/* 交易记录 */}
      {trades && trades.length > 0 && (
        <Card title={`交易记录 (${trades.length} 笔)`} style={{ marginBottom: 16 }}>
          <Table
            dataSource={trades.map((t: TradeRecord, i: number) => ({ ...t, key: i }))}
            columns={tradeColumns}
            pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `共 ${total} 笔` }}
            size="small"
          />
        </Card>
      )}

      {/* 每日持仓明细 */}
      {snapshotPanels && snapshotPanels.length > 0 && (
        <Card title="每日持仓明细（最近20天）" style={{ marginBottom: 16 }}>
          <Collapse items={snapshotPanels} size="small" />
        </Card>
      )}

      <Button onClick={() => navigate(-1)} style={{ marginTop: 16 }}>
        返回
      </Button>
    </>
  );
}
