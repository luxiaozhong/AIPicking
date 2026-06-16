import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Select, DatePicker, Row, Col, InputNumber, Button, Table,
  Typography, Spin, Empty, Tag, message, Space, Statistic, Alert, Tooltip,
  Popconfirm, Modal,
} from 'antd';
import {
  ReloadOutlined, InfoCircleOutlined, PlayCircleOutlined,
  DeleteOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';
import dayjs from 'dayjs';
import { strategyService } from '@/services/strategyService';
import { fundFlowService } from '@/services/fundFlowService';
import strategyTrackerService from '@/services/strategyTrackerService';
import paperTradeService from '@/services/paperTradeService';
import StockKLineModal from '@/components/shared/StockKLineModal';
import RebalanceModal from '@/components/RebalanceModal';
import type { StockTrend, StockTrendDay } from '@/services/fundFlowService';
import type { Strategy } from '@/types/strategy';
import type { Recommendation } from '@/services/strategyTrackerService';
import type {
  PaperStatus, PaperHolding, PaperTradeRecord, ExecuteResult,
} from '@/services/paperTradeService';

const { Title, Text } = Typography;

function isWeekend(date: string): boolean {
  const d = dayjs(date);
  return d.day() === 0 || d.day() === 6;
}

function calcRolling5(days: StockTrendDay[]): number[] {
  const flows = days.map((d) => d.main_net_flow);
  const rolling: number[] = [];
  for (let i = 0; i < flows.length; i++) {
    const start = Math.max(0, i - 4);
    let sum = 0;
    for (let j = start; j <= i; j++) sum += flows[j];
    rolling.push(sum);
  }
  return rolling;
}

function fmtFlow(yi: number): string {
  const abs = Math.abs(yi);
  if (abs >= 1e8) return `${(yi / 1e8).toFixed(2)}万亿`;
  if (abs >= 1e4) return `${(yi / 1e4).toFixed(2)}亿`;
  if (abs >= 1e3) return `${(yi / 1e3).toFixed(2)}千万`;
  return `${yi.toFixed(0)}万`;
}

function fmtMoney(v: number): string {
  return `¥ ${v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`;
}

function getLotSize(tsCode: string): number {
  // 科创板 688 为 200 股/手，其余为 100 股/手
  return tsCode.startsWith('688') ? 200 : 100;
}

interface LotInfo {
  lots: number;
  amount: number;
}

function calcLots(rec: Recommendation, capital: number): LotInfo | null {
  if (!rec.close || rec.close <= 0) return null;
  const lotSize = getLotSize(rec.ts_code);
  const perStockBudget = capital / 3;
  const perLotCost = lotSize * rec.close;
  const lots = Math.floor(perStockBudget / perLotCost);
  if (lots < 1) return null;
  return { lots, amount: lots * perLotCost };
}

// 交易记录表格列定义
const tradeColumns = [
  {
    title: '执行日', dataIndex: 'exec_date', key: 'exec_date', width: 100,
  },
  {
    title: '操作', dataIndex: 'action', key: 'action', width: 60,
    render: (a: string) => (
      <Tag color={a === 'buy' ? 'red' : 'green'}>{a === 'buy' ? '买入' : '卖出'}</Tag>
    ),
  },
  { title: '股票', dataIndex: 'stock_name', key: 'stock_name', width: 100 },
  {
    title: '股数', dataIndex: 'shares', key: 'shares', width: 80,
    render: (v: number) => v.toLocaleString(),
  },
  {
    title: '成交价', dataIndex: 'price', key: 'price', width: 80,
    render: (v: number) => v.toFixed(2),
  },
  {
    title: '成交金额', dataIndex: 'amount', key: 'amount', width: 110,
    render: (v: number) => fmtMoney(v),
  },
  {
    title: '手续费', dataIndex: 'commission', key: 'commission', width: 80,
    render: (v: number) => v.toFixed(2),
  },
  {
    title: '印花税', dataIndex: 'stamp_duty', key: 'stamp_duty', width: 80,
    render: (v: number) => v > 0 ? v.toFixed(2) : '-',
  },
  {
    title: '净额', dataIndex: 'net_amount', key: 'net_amount', width: 110,
    render: (v: number) => (
      <Text style={{ color: v >= 0 ? '#3f8600' : '#cf1322' }}>{fmtMoney(v)}</Text>
    ),
  },
];

export default function StrategyTracker() {
  // ── 策略 & 日期 ──
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [strategyId, setStrategyId] = useState<number | undefined>();
  const [selectedDate, setSelectedDate] = useState<string>(dayjs().format('YYYY-MM-DD'));
  const [loading, setLoading] = useState(false);

  // ── 推荐 ──
  const [tradeDate, setTradeDate] = useState<string>(selectedDate);
  const [cached, setCached] = useState(false);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);

  // ── Top 10 资金流 ──
  const [trendCache, setTrendCache] = useState<Record<string, StockTrend>>({});
  const [trendsLoading, setTrendsLoading] = useState(false);

  // ── K 线弹窗 ──
  const [klineStock, setKlineStock] = useState<{ ts_code: string; name: string } | null>(null);

  // ── 模拟盘状态 ──
  const [initialCapital, setInitialCapital] = useState<number>(500000);
  const [status, setStatus] = useState<PaperStatus | null>(null);
  const [navData, setNavData] = useState<{ date: string; cash: number; holdings_value: number; total_value: number }[]>([]);
  const [trades, setTrades] = useState<PaperTradeRecord[]>([]);
  const [tradesTotal, setTradesTotal] = useState(0);
  const [tradesPage, setTradesPage] = useState(1);
  const [executing, setExecuting] = useState(false);
  const [rebalanceOpen, setRebalanceOpen] = useState(false);

  const navChartRef = useRef<ReactECharts>(null);

  // ── 加载策略列表 ──
  useEffect(() => {
    strategyService.getStrategies({ limit: 100, scope: 'all' }).then((res) => {
      const list = res.items || [];
      setStrategies(list);
      const gwm = list.find((s) => s.name === 'grow_with_money');
      if (gwm) setStrategyId(gwm.id);
      else if (list.length > 0) setStrategyId(list[0].id);
    }).catch(() => {});
  }, []);

  // ── 加载本金 ──
  useEffect(() => {
    if (!strategyId) return;
    strategyTrackerService.getConfig(strategyId).then((cfg) => {
      setInitialCapital(cfg.initial_capital);
    }).catch(() => {});
  }, [strategyId]);

  // ── 本金变更 → 同步到后端 ──
  const handleCapitalChange = (v: number | null) => {
    const val = v ?? 500000;
    setInitialCapital(val);
    if (strategyId) {
      paperTradeService.start(strategyId, val).catch(() => {});
    }
  };

  // ── 加载数据 ──
  const loadData = useCallback(async (sid: number, date: string) => {
    setLoading(true);
    setCached(false);
    try {
      const [recRes, statusRes, navRes, tradesRes] = await Promise.all([
        strategyTrackerService.getRecommendations(sid, date, false, 5, 10).catch(() => null),
        paperTradeService.getStatus(sid).catch(() => null),
        paperTradeService.getNav(sid).catch(() => null),
        paperTradeService.getTrades(sid, 1, 20).catch(() => null),
      ]);

      if (recRes) {
        setRecommendations(recRes.recommendations || []);
        setTradeDate(recRes.trade_date || date);
        setCached(recRes.cached);
      } else {
        setRecommendations([]);
        setTradeDate(date);
      }
      setStatus(statusRes);
      if (navRes) {
        setNavData(navRes.nav || []);
      }
      if (tradesRes) {
        setTrades(tradesRes.trades || []);
        setTradesTotal(tradesRes.total);
        setTradesPage(tradesRes.page);
      }
    } catch (err) {
      console.error('Failed to load data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (strategyId) loadData(strategyId, selectedDate);
  }, [strategyId, selectedDate, loadData]);

  // ── 强制刷新 ──
  const handleForceRefresh = () => {
    if (!strategyId) return;
    setLoading(true);
    setCached(false);
    Promise.all([
      strategyTrackerService.getRecommendations(strategyId, selectedDate, true, 5, 10),
      paperTradeService.getStatus(strategyId),
      paperTradeService.getNav(strategyId),
      paperTradeService.getTrades(strategyId, 1, 20),
    ]).then(([recRes, statusRes, navRes, tradesRes]) => {
      if (recRes) {
        setRecommendations(recRes.recommendations || []);
        setTradeDate(recRes.trade_date || selectedDate);
        setCached(recRes.cached);
      }
      setStatus(statusRes);
      if (navRes) setNavData(navRes.nav || []);
      if (tradesRes) {
        setTrades(tradesRes.trades || []);
        setTradesTotal(tradesRes.total);
        setTradesPage(tradesRes.page);
      }
    }).catch(() => {}).finally(() => setLoading(false));
  };

  // ── 执行调仓 ──
  const handleExecute = () => {
    if (!strategyId) return;
    setRebalanceOpen(true);
  };

  const handleRebalanceSubmit = async (payload: {
    strategy_id: number;
    date: string;
    sells: { ts_code: string; shares: number }[];
    buys: { ts_code: string; shares: number; stock_name?: string }[];
    additional_capital: number;
    exec_date: string;
  }) => {
    setExecuting(true);
    try {
      const result = await paperTradeService.execute(payload);
      const parts = ['调仓完成！'];
      if (result.summary.sell_count > 0) parts.push(`${result.summary.sell_count} 卖`);
      if (result.summary.buy_count > 0) parts.push(`${result.summary.buy_count} 买`);
      if (result.summary.keep_count > 0) parts.push(`${result.summary.keep_count} 保持`);
      parts.push(`手续费 ¥${result.summary.total_commission.toFixed(2)}`);
      parts.push(`印花税 ¥${result.summary.total_stamp_duty.toFixed(2)}`);
      if (result.summary.additional_capital_added > 0) {
        parts.push(`追加本金 ¥${result.summary.additional_capital_added.toFixed(2)}`);
      }
      message.success(parts.join(' · '), 5);
      setRebalanceOpen(false);
      await loadData(strategyId, selectedDate);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (err as Error)?.message ||
        '执行失败';
      message.error(msg);
    } finally {
      setExecuting(false);
    }
  };

  // ── 重置模拟盘 ──
  const handleReset = async () => {
    if (!strategyId) return;
    try {
      const res = await paperTradeService.reset(strategyId);
      message.success(res.message);
      await loadData(strategyId, selectedDate);
    } catch {
      message.error('重置失败');
    }
  };

  // ── 交易分页 ──
  const handleTradesPageChange = async (page: number) => {
    if (!strategyId) return;
    const res = await paperTradeService.getTrades(strategyId, page, 20);
    setTrades(res.trades || []);
    setTradesTotal(res.total);
    setTradesPage(res.page);
  };

  // ── Top 10 资金流 ──
  useEffect(() => {
    if (recommendations.length === 0) return;
    const top10 = recommendations.slice(0, 10);
    const toFetch = top10.filter((r) => !trendCache[r.ts_code]);
    if (toFetch.length === 0) return;
    setTrendsLoading(true);
    Promise.all(
      toFetch.map((r) => fundFlowService.getStockTrend(r.ts_code, 20).catch(() => null)),
    ).then((results) => {
      const newCache = { ...trendCache };
      results.forEach((trend, i) => {
        if (trend) newCache[toFetch[i].ts_code] = trend;
      });
      setTrendCache(newCache);
      setTrendsLoading(false);
    });
  }, [recommendations]);

  const handleDateChange = (date: dayjs.Dayjs | null) => {
    if (date) setSelectedDate(date.format('YYYY-MM-DD'));
  };

  const top3 = recommendations.slice(0, 3);

  const dateOffsetMsg =
    selectedDate !== tradeDate
      ? `${selectedDate} 是${isWeekend(selectedDate) ? '周末' : '非交易日'}，已回退到最近交易日 ${tradeDate}`
      : null;

  // ── 是否已执行（当天推荐已调仓）──
  const hasExecutedToday = status?.last_rec_date === tradeDate;

  // ── Mini 资金流 chart ──
  const makeMiniOption = (trend: StockTrend) => {
    const dates = trend.days.map((d) => d.trade_date.slice(5));
    const rolling5 = calcRolling5(trend.days);
    return {
      grid: { top: 8, right: 6, bottom: 14, left: 6 },
      tooltip: {
        trigger: 'axis' as const,
        formatter: (params: { data: number; axisValue: string }[]) => {
          const val = params[0]?.data ?? 0;
          return `${params[0]?.axisValue}<br/>5日滚动: ${fmtFlow(val)}`;
        },
      },
      xAxis: { type: 'category' as const, data: dates, show: false },
      yAxis: { type: 'value' as const, show: false },
      series: [{
        type: 'line', data: rolling5, smooth: true, symbol: 'none',
        lineStyle: { width: 1.5 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: rolling5[rolling5.length - 1] >= 0 ? 'rgba(207,19,34,0.3)' : 'rgba(63,134,0,0.3)' },
            { offset: 1, color: 'rgba(255,255,255,0.02)' },
          ]),
        },
      }],
    };
  };

  // ── NAV chart option ──
  const navOption = {
    grid: { top: 40, right: 20, bottom: 30, left: 70 },
    tooltip: {
      trigger: 'axis' as const,
      formatter: (params: { seriesName: string; data: number; axisValue: string }[]) => {
        const lines = params.map((p) => {
          const v = p.data ?? 0;
          return `${p.seriesName}: ¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`;
        });
        const totalP = params.find((p) => p.seriesName === '总净值');
        if (totalP && initialCapital > 0) {
          const pct = (((totalP.data ?? 0) - initialCapital) / initialCapital * 100).toFixed(2);
          const color = Number(pct) >= 0 ? '#cf1322' : '#3f8600';
          lines.push(`<b style="color:${color}">收益率: ${pct}%</b>`);
        }
        return lines.join('<br/>');
      },
    },
    legend: { data: ['持仓市值', '现金', '总净值'] },
    xAxis: { type: 'category' as const, data: navData.map((p) => p.date.slice(5)) },
    yAxis: {
      type: 'value' as const,
      axisLabel: { formatter: (v: number) => `¥${(v / 10000).toFixed(0)}万` },
      splitLine: { lineStyle: { type: 'dashed' } },
    },
    series: [
      {
        name: '持仓市值', type: 'line',
        data: navData.map((p) => p.holdings_value),
        smooth: true, symbol: 'circle', symbolSize: 4,
        itemStyle: { color: '#1677ff' },
      },
      {
        name: '现金', type: 'line',
        data: navData.map((p) => p.cash),
        smooth: true, symbol: 'diamond', symbolSize: 3,
        lineStyle: { type: 'dashed', width: 1.5 },
        itemStyle: { color: '#52c41a' },
      },
      {
        name: '总净值', type: 'line',
        data: navData.map((p) => p.total_value),
        smooth: true, symbol: 'circle', symbolSize: 5,
        lineStyle: { width: 2.5 },
        itemStyle: { color: '#cf1322' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(207,19,34,0.08)' },
            { offset: 1, color: 'rgba(255,255,255,0.02)' },
          ]),
        },
      },
    ],
  };

  // ── Render ──
  return (
    <div style={{ padding: '0 0 24px' }}>
      {/* 顶部工具栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col>
            <Text strong>策略：</Text>
            <Select
              value={strategyId}
              onChange={(v) => setStrategyId(v)}
              placeholder="选择策略"
              style={{ width: 260 }}
              showSearch
              filterOption={(input, option) =>
                (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
              }
              options={strategies.map((s) => ({ value: s.id, label: s.name }))}
            />
          </Col>
          <Col>
            <Text strong>数据日期：</Text>
            <DatePicker
              value={dayjs(selectedDate)}
              onChange={handleDateChange}
              allowClear={false}
              style={{ width: 160 }}
            />
          </Col>
          <Col>
            <Space size={4}>
              <Text strong>本金：</Text>
              <Tooltip title="初始投入资金">
                <InfoCircleOutlined style={{ color: '#999', fontSize: 12 }} />
              </Tooltip>
              <InputNumber
                value={initialCapital}
                onChange={handleCapitalChange}
                min={10000}
                step={10000}
                style={{ width: 140 }}
                formatter={(value) => `¥ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                parser={(value) => value?.replace(/¥\s?|(,*)/g, '') as unknown as number}
              />
            </Space>
          </Col>
          <Col>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleExecute}
              loading={executing}
              disabled={hasExecutedToday}
            >
              {hasExecutedToday ? '已执行' : '执行调仓'}
            </Button>
          </Col>
          <Col>
            <Space size={8}>
              <Button icon={<ReloadOutlined />} onClick={handleForceRefresh} loading={loading}>
                强制刷新
              </Button>
              {status && status.trade_count > 0 && (
                <Popconfirm
                  title="确认清空所有模拟交易？本金不变。"
                  onConfirm={handleReset}
                  okText="确认"
                  cancelText="取消"
                >
                  <Button icon={<DeleteOutlined />} danger size="small">
                    重置
                  </Button>
                </Popconfirm>
              )}
            </Space>
          </Col>
          <Col flex="auto">
            <Space size={8}>
              {tradeDate && <Tag color="blue">实际数据: {tradeDate}</Tag>}
              {cached && <Tag color="green">缓存</Tag>}
              {status && status.trade_count > 0 && (
                <Tag color="purple">
                  模拟盘: {status.last_rec_date} → {status.last_exec_date}
                </Tag>
              )}
            </Space>
          </Col>
        </Row>
        {dateOffsetMsg && (
          <Alert title={dateOffsetMsg} type="info" showIcon
            style={{ marginTop: 8, padding: '4px 12px' }} />
        )}
      </Card>

      <Spin spinning={loading || trendsLoading} description="加载中...">
        {/* Row 1: Top 10 资金流 */}
        <Card
          title={`策略 Top 10 — 近 20 日 5 日滚动主力净流入 (${tradeDate})`}
          size="small" style={{ marginBottom: 16 }}
        >
          {recommendations.length === 0 ? (
            <Empty description="暂无推荐数据" />
          ) : (
            <Row gutter={[12, 12]}>
              {recommendations.slice(0, 10).map((rec, idx) => {
                const trend = trendCache[rec.ts_code];
                return (
                  <Col span={Math.floor(24 / 5)} key={rec.ts_code}>
                    <Card
                      size="small"
                      styles={{ body: { padding: 8 } }}
                      title={
                        <Space size={4}>
                          <Tag color={idx < 3 ? 'red' : 'default'} style={{ margin: 0 }}>
                            #{idx + 1}
                          </Tag>
                          <Text
                            strong
                            style={{ fontSize: 12, cursor: 'pointer' }}
                            onClick={() => setKlineStock({ ts_code: rec.ts_code, name: rec.name })}
                          >
                            {rec.name}
                          </Text>
                        </Space>
                      }
                    >
                      {trend?.days?.length ? (
                        <>
                          <ReactECharts option={makeMiniOption(trend)} style={{ height: 100 }} />
                          <div style={{ textAlign: 'center', marginTop: 4 }}>
                            <Text style={{ fontSize: 11, color: '#888' }}>
                              {rec.score} · {rec.signal?.slice(0, 30)}
                            </Text>
                          </div>
                        </>
                      ) : (
                        <div style={{ height: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <Spin size="small" />
                        </div>
                      )}
                    </Card>
                  </Col>
                );
              })}
            </Row>
          )}
        </Card>

        {/* Row 2: 左列（推荐 + 持仓） + 右列（NAV + 交易记录） */}
        <Row gutter={16}>
          {/* 左列 */}
          <Col span={6}>
            {/* Top 3 推荐 */}
            <Card
              title={`推荐持仓 Top 3 (${tradeDate})`}
              size="small" style={{ marginBottom: 16 }}
              extra={
                <DatePicker
                  value={dayjs(selectedDate)}
                  onChange={handleDateChange}
                  allowClear={false}
                  size="small"
                  style={{ width: 130 }}
                />
              }
            >
              {top3.length === 0 ? (
                <Empty description="暂无推荐" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                top3.map((rec, idx) => {
                    const lotInfo = calcLots(rec, initialCapital);
                    const isHeld = status?.holdings?.some(h => h.ts_code === rec.ts_code);
                    return (
                  <Card key={rec.ts_code} size="small"
                    style={{ marginBottom: 8 }} styles={{ body: { padding: 10 } }}>
                    <Space>
                      <Tag color={idx === 0 ? 'red' : idx === 1 ? 'orange' : 'blue'}>
                        #{idx + 1}
                      </Tag>
                      <Tag color={isHeld ? 'green' : 'red'} style={{ fontSize: 11 }}>
                        {isHeld ? '持仓' : '新买入'}
                      </Tag>
                      <div>
                        <div>
                          <Text strong>{rec.name}</Text>
                          <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                            {rec.ts_code}
                          </Text>
                        </div>
                        <div style={{ marginTop: 4 }}>
                          <Text style={{ fontSize: 12, color: '#888' }}>评分: {rec.score}</Text>
                          {rec.close > 0 && (
                            <Text style={{ fontSize: 12, color: '#888', marginLeft: 12 }}>
                              收盘: ¥{rec.close.toFixed(2)}
                            </Text>
                          )}
                        </div>
                        {lotInfo && (
                          <div style={{ marginTop: 2 }}>
                            <Text style={{ fontSize: 12, color: '#1677ff' }}>
                              {lotInfo.lots} 手 · {fmtMoney(lotInfo.amount)}
                            </Text>
                          </div>
                        )}
                        <Text style={{ fontSize: 11, color: '#999' }} ellipsis={{ tooltip: true }}>
                          {rec.signal}
                        </Text>
                      </div>
                    </Space>
                  </Card>
                )})
              )}
            </Card>

            {/* 当前持仓（模拟盘） */}
            <Card title="当前持仓" size="small" style={{ marginBottom: 16 }}>
              {!status || status.trade_count === 0 ? (
                <Empty
                  description="尚未开始模拟交易，点击「执行调仓」开始"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              ) : (
                <>
                  {status.holdings.map((h: PaperHolding) => (
                    <Card key={h.ts_code} size="small"
                      style={{ marginBottom: 8 }} styles={{ body: { padding: 10 } }}>
                      <div>
                        <Text strong>{h.stock_name}</Text>
                        <Text type="secondary" style={{ fontSize: 11, marginLeft: 6 }}>
                          {h.ts_code}
                        </Text>
                      </div>
                      <Row style={{ marginTop: 4 }}>
                        <Col span={12}>
                          <Text style={{ fontSize: 11, color: '#888' }}>
                            {h.shares.toLocaleString()} 股
                          </Text>
                        </Col>
                        <Col span={12}>
                          <Text style={{ fontSize: 11, color: '#888' }}>
                            均价 ¥{h.avg_cost.toFixed(2)}
                          </Text>
                        </Col>
                      </Row>
                      <Row style={{ marginTop: 2 }}>
                        <Col span={12}>
                          <Text style={{ fontSize: 11, color: '#888' }}>
                            市值 {fmtMoney(h.market_value)}
                          </Text>
                        </Col>
                        <Col span={12}>
                          <Text style={{
                            fontSize: 11,
                            color: h.unrealized_pnl >= 0 ? '#cf1322' : '#3f8600',
                          }}>
                            盈亏 {fmtMoney(h.unrealized_pnl)}
                          </Text>
                        </Col>
                      </Row>
                    </Card>
                  ))}
                  <Row gutter={12} style={{ marginTop: 12 }}>
                    <Col span={12}>
                      <Statistic title="可用现金" value={status.cash}
                        precision={0} prefix="¥"
                        valueStyle={{ fontSize: 14, color: '#52c41a' }} />
                    </Col>
                    <Col span={12}>
                      <Statistic title="持仓市值" value={status.total_market_value}
                        precision={0} prefix="¥"
                        valueStyle={{ fontSize: 14 }} />
                    </Col>
                  </Row>
                  <Row gutter={12} style={{ marginTop: 8 }}>
                    <Col span={12}>
                      <Statistic title="总净值" value={status.total_nav}
                        precision={0} prefix="¥"
                        valueStyle={{ fontSize: 14, color: '#cf1322' }} />
                    </Col>
                    <Col span={12}>
                      <Statistic title="累计收益率" value={status.total_return_pct}
                        suffix="%" precision={2}
                        valueStyle={{
                          fontSize: 14,
                          color: status.total_return_pct >= 0 ? '#cf1322' : '#3f8600',
                        }} />
                    </Col>
                  </Row>
                </>
              )}
            </Card>
          </Col>

          {/* 右列 */}
          <Col span={18}>
            {/* NAV 图 */}
            <Card title="账户净值变化" size="small" style={{ marginBottom: 16 }}>
              {navData.length === 0 ? (
                <Empty
                  description={status && status.trade_count > 0 ? '暂无净值数据' : '请先执行调仓'}
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              ) : (
                <>
                  <ReactECharts ref={navChartRef} option={navOption} style={{ height: 320 }} />
                  <Row gutter={16} style={{ marginTop: 12 }} justify="center">
                    <Col>
                      <Statistic title="初始本金" value={initialCapital}
                        precision={0} prefix="¥" valueStyle={{ fontSize: 16, color: '#666' }} />
                    </Col>
                    <Col>
                      <Statistic title="最新市值" value={navData[navData.length - 1]?.holdings_value ?? 0}
                        precision={0} prefix="¥" valueStyle={{ fontSize: 16 }} />
                    </Col>
                    <Col>
                      <Statistic title="剩余现金" value={navData[navData.length - 1]?.cash ?? 0}
                        precision={0} prefix="¥" valueStyle={{ fontSize: 16, color: '#52c41a' }} />
                    </Col>
                    <Col>
                      <Statistic title="总净值" value={navData[navData.length - 1]?.total_value ?? 0}
                        precision={0} prefix="¥" valueStyle={{ fontSize: 16, color: '#cf1322' }} />
                    </Col>
                    <Col>
                      {(() => {
                        const latest = navData[navData.length - 1];
                        const pct = latest && initialCapital > 0
                          ? ((latest.total_value - initialCapital) / initialCapital * 100).toFixed(2)
                          : '0.00';
                        return (
                          <Statistic title="累计收益率" value={pct}
                            suffix="%" valueStyle={{
                              fontSize: 16,
                              color: Number(pct) >= 0 ? '#cf1322' : '#3f8600',
                            }} />
                        );
                      })()}
                    </Col>
                    <Col>
                      <Statistic title="数据天数" value={navData.length}
                        valueStyle={{ fontSize: 16, color: '#999' }} />
                    </Col>
                  </Row>
                </>
              )}
            </Card>

            {/* 交易记录 Table */}
            <Card title="交易记录" size="small">
              {trades.length === 0 ? (
                <Empty description="暂无交易记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <Table
                  dataSource={trades}
                  columns={tradeColumns}
                  rowKey="id"
                  size="small"
                  scroll={{ x: 800 }}
                  pagination={{
                    current: tradesPage,
                    total: tradesTotal,
                    pageSize: 20,
                    showSizeChanger: false,
                    showTotal: (t) => `共 ${t} 笔`,
                    onChange: handleTradesPageChange,
                  }}
                />
              )}
            </Card>
          </Col>
        </Row>
      </Spin>
      <StockKLineModal
        ts_code={klineStock?.ts_code ?? ''}
        name={klineStock?.name}
        open={!!klineStock}
        onClose={() => setKlineStock(null)}
      />
      <RebalanceModal
        open={rebalanceOpen}
        strategyId={strategyId!}
        top3={top3}
        holdings={status?.holdings || []}
        cash={status?.cash || 0}
        totalValue={status?.total_nav || 0}
        recDate={tradeDate || selectedDate}
        loading={executing}
        onClose={() => setRebalanceOpen(false)}
        onSubmit={handleRebalanceSubmit}
      />
    </div>
  );
}
