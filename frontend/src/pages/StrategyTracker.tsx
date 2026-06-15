import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Select, DatePicker, Row, Col, Form, InputNumber, Button,
  Typography, Spin, Empty, Tag, message, Space, Descriptions, Statistic, Alert,
  Tooltip,
} from 'antd';
import { PlusOutlined, DeleteOutlined, SaveOutlined, ReloadOutlined, InfoCircleOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';
import dayjs from 'dayjs';
import { strategyService } from '@/services/strategyService';
import { fundFlowService } from '@/services/fundFlowService';
import strategyTrackerService from '@/services/strategyTrackerService';
import type { StockTrend, StockTrendDay } from '@/services/fundFlowService';
import type { Strategy } from '@/types/strategy';
import type {
  Recommendation, HoldingItem, NavPoint, HoldingsByDate,
} from '@/services/strategyTrackerService';

const { Title, Text } = Typography;

// A 股交易日：周一到周五（简化判断，精确判断由后端处理）
function isWeekend(date: string): boolean {
  const d = dayjs(date);
  return d.day() === 0 || d.day() === 6;
}

// 5 日滚动求和
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

// 金额格式化
function fmtFlow(yi: number): string {
  const abs = Math.abs(yi);
  if (abs >= 1e8) return `${(yi / 1e8).toFixed(2)}万亿`;
  if (abs >= 1e4) return `${(yi / 1e4).toFixed(2)}亿`;
  if (abs >= 1e3) return `${(yi / 1e3).toFixed(2)}千万`;
  return `${yi.toFixed(0)}万`;
}

export default function StrategyTracker() {
  // ── 策略 & 日期状态 ──
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [strategyId, setStrategyId] = useState<number | undefined>();
  const [selectedDate, setSelectedDate] = useState<string>(dayjs().format('YYYY-MM-DD'));
  const [loading, setLoading] = useState(false);

  // ── 实际交易日（后端可能回退到最近交易日）──
  const [tradeDate, setTradeDate] = useState<string>(selectedDate);
  const [cached, setCached] = useState(false);

  // ── 推荐数据 ──
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);

  // ── Top 10 资金流趋势缓存 ──
  const [trendCache, setTrendCache] = useState<Record<string, StockTrend>>({});
  const [trendsLoading, setTrendsLoading] = useState(false);

  // ── 本金 & 持仓 & 净值 ──
  const [initialCapital, setInitialCapital] = useState<number>(500000);
  const [holdingsByDate, setHoldingsByDate] = useState<HoldingsByDate>({});
  const [navData, setNavData] = useState<NavPoint[]>([]);
  const [saving, setSaving] = useState(false);

  // 持仓表单
  const [form] = Form.useForm();

  // ECharts ref
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

  // ── 加载策略配置（本金）──
  useEffect(() => {
    if (!strategyId) return;
    strategyTrackerService.getConfig(strategyId).then((cfg) => {
      setInitialCapital(cfg.initial_capital);
    }).catch(() => {});
  }, [strategyId]);

  // ── 加载推荐 & 持仓 & NAV ──
  const loadData = useCallback(async (sid: number, date: string) => {
    setLoading(true);
    setCached(false);
    try {
      const [recRes, holdingsRes, navRes] = await Promise.all([
        strategyTrackerService.getRecommendations(sid, date, false, 5, 10).catch(() => null),
        strategyTrackerService.getHoldings(sid).catch(() => ({ items: {}, total_dates: 0 })),
        strategyTrackerService.getNav(sid).catch(() => ({ nav: [], count: 0, initial_capital: 0 })),
      ]);

      if (recRes) {
        setRecommendations(recRes.recommendations || []);
        setTradeDate(recRes.trade_date || date);
        setCached(recRes.cached);
      } else {
        setRecommendations([]);
        setTradeDate(date);
      }
      setHoldingsByDate(holdingsRes.items || {});
      setNavData(navRes.nav || []);
      // 同步后端存储的本金到前端状态
      if (navRes?.initial_capital) {
        setInitialCapital(navRes.initial_capital);
      }
    } catch (err) {
      console.error('Failed to load data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // 策略变化时重新加载（日期不变时也用缓存）
  useEffect(() => {
    if (strategyId) {
      loadData(strategyId, selectedDate);
    }
  }, [strategyId, selectedDate, loadData]);

  // ── 强制刷新（忽略缓存）──
  const handleForceRefresh = () => {
    if (!strategyId) return;
    // 临时方案：直接调 getRecommendations 带 force_refresh
    setLoading(true);
    setCached(false);
    Promise.all([
      strategyTrackerService.getRecommendations(strategyId, selectedDate, true, 5, 10),
      strategyTrackerService.getHoldings(strategyId),
      strategyTrackerService.getNav(strategyId),
    ]).then(([recRes, holdingsRes, navRes]) => {
      if (recRes) {
        setRecommendations(recRes.recommendations || []);
        setTradeDate(recRes.trade_date || selectedDate);
        setCached(recRes.cached);
      }
      setHoldingsByDate(holdingsRes.items || {});
      setNavData(navRes.nav || []);
      if (navRes?.initial_capital) {
        setInitialCapital(navRes.initial_capital);
      }
    }).catch(() => {}).finally(() => setLoading(false));
  };

  // ── 加载 Top 10 资金流趋势 ──
  useEffect(() => {
    if (recommendations.length === 0) return;

    const top10 = recommendations.slice(0, 10);
    const toFetch = top10.filter((r) => !trendCache[r.ts_code]);

    if (toFetch.length === 0) return;

    setTrendsLoading(true);
    Promise.all(
      toFetch.map((r) =>
        fundFlowService.getStockTrend(r.ts_code, 20).catch(() => null),
      ),
    ).then((results) => {
      const newCache = { ...trendCache };
      results.forEach((trend, i) => {
        if (trend) {
          newCache[toFetch[i].ts_code] = trend;
        }
      });
      setTrendCache(newCache);
      setTrendsLoading(false);
    });
  }, [recommendations]);

  // ── 日期变更 ──
  const handleDateChange = (date: dayjs.Dayjs | null) => {
    if (date) setSelectedDate(date.format('YYYY-MM-DD'));
  };

  // ── Top 3 推荐 ──
  const top3 = recommendations.slice(0, 3);

  // 日期偏移提示
  const dateOffsetMsg =
    selectedDate !== tradeDate
      ? `${selectedDate} 是${isWeekend(selectedDate) ? '周末' : '非交易日'}，已回退到最近交易日 ${tradeDate}`
      : null;

  // ── 持仓表单填充 ──
  const fillFormWithTop3 = () => {
    form.setFieldsValue({
      holdings: top3.map((r) => ({
        ts_code: r.ts_code,
        stock_name: r.name,
        shares: 0,
        buy_price: 0,
      })),
    });
  };

  useEffect(() => {
    if (top3.length > 0) {
      fillFormWithTop3();
    }
  }, [recommendations]);

  const loadExistingHoldings = () => {
    const dayHoldings = holdingsByDate[selectedDate] || holdingsByDate[tradeDate];
    if (dayHoldings && dayHoldings.length > 0) {
      form.setFieldsValue({
        holdings: dayHoldings.map((h) => ({
          ts_code: h.ts_code,
          stock_name: h.stock_name,
          shares: h.shares,
          buy_price: h.buy_price,
        })),
      });
      message.info('已加载该日期的持仓记录');
    } else if (top3.length > 0) {
      fillFormWithTop3();
      message.info('该日期无持仓记录，已填入推荐股票');
    }
  };

  // ── 保存持仓 ──
  const handleSaveHoldings = async () => {
    if (!strategyId) return;
    try {
      const values = await form.validateFields();
      const holdings: HoldingItem[] = (values.holdings || [])
        .filter((h: HoldingItem) => h.ts_code)
        .map((h: HoldingItem) => ({
          ts_code: h.ts_code,
          stock_name: h.stock_name || '',
          shares: h.shares || 0,
          buy_price: h.buy_price || 0,
        }));

      setSaving(true);
      // 用实际交易日保存
      const saveDate = tradeDate || selectedDate;
      await strategyTrackerService.saveHoldings({
        strategy_id: strategyId,
        date: saveDate,
        holdings,
        initial_capital: initialCapital,
      });
      message.success(`持仓已保存 (${saveDate})`);
      await loadData(strategyId, selectedDate);
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) return;
      message.error('保存失败');
    } finally {
      setSaving(false);
    }
  };

  // ── Mini 资金流 chart option ──
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
        type: 'line',
        data: rolling5,
        smooth: true,
        symbol: 'none',
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
        // 加一行收益率
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

  // ── 渲染 ──
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
              options={strategies.map((s) => ({
                value: s.id,
                label: s.name,
              }))}
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
              <Tooltip title="初始投入资金，用于计算现金 = 本金 - 持仓成本">
                <InfoCircleOutlined style={{ color: '#999', fontSize: 12 }} />
              </Tooltip>
              <InputNumber
                value={initialCapital}
                onChange={(v) => setInitialCapital(v ?? 500000)}
                min={0}
                step={10000}
                style={{ width: 140 }}
                formatter={(value) => `¥ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                parser={(value) => value?.replace(/¥\s?|(,*)/g, '') as unknown as number}
              />
            </Space>
          </Col>
          <Col>
            <Space size={8}>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleForceRefresh}
                loading={loading}
              >
                强制刷新
              </Button>
            </Space>
          </Col>
          <Col flex="auto">
            <Space size={8}>
              {tradeDate && (
                <Tag color="blue">实际数据: {tradeDate}</Tag>
              )}
              {cached && (
                <Tag color="green">缓存</Tag>
              )}
            </Space>
          </Col>
        </Row>
        {dateOffsetMsg && (
          <Alert
            title={dateOffsetMsg}
            type="info"
            showIcon
            style={{ marginTop: 8, padding: '4px 12px' }}
          />
        )}
      </Card>

      <Spin spinning={loading || trendsLoading} description="加载中...">
        {/* Row 1: Top 10 资金流 mini charts */}
        <Card
          title={`策略 Top 10 — 近 20 日 5 日滚动主力净流入 (${tradeDate})`}
          size="small"
          style={{ marginBottom: 16 }}
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
                          <Text strong style={{ fontSize: 12 }}>{rec.name}</Text>
                        </Space>
                      }
                    >
                      {trend?.days?.length ? (
                        <>
                          <ReactECharts
                            option={makeMiniOption(trend)}
                            style={{ height: 100 }}
                          />
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

        {/* Row 2: 3 列布局 */}
        <Row gutter={16}>
          {/* 左列: 日期选择 + Top 3 推荐 */}
          <Col span={6}>
            <Card
              title={`推荐持仓 Top 3 (${tradeDate})`}
              size="small"
              style={{ marginBottom: 16 }}
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
                top3.map((rec, idx) => (
                  <Card
                    key={rec.ts_code}
                    size="small"
                    style={{ marginBottom: 8 }}
                    styles={{ body: { padding: 10 } }}
                  >
                    <Space>
                      <Tag color={idx === 0 ? 'red' : idx === 1 ? 'orange' : 'blue'}>
                        #{idx + 1}
                      </Tag>
                      <div>
                        <div>
                          <Text strong>{rec.name}</Text>
                          <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                            {rec.ts_code}
                          </Text>
                        </div>
                        <div style={{ marginTop: 4 }}>
                          <Text style={{ fontSize: 12, color: '#888' }}>
                            评分: {rec.score}
                          </Text>
                        </div>
                        <Text
                          style={{ fontSize: 11, color: '#999' }}
                          ellipsis={{ tooltip: true }}
                        >
                          {rec.signal}
                        </Text>
                      </div>
                    </Space>
                  </Card>
                ))
              )}
            </Card>

            {/* 持仓表单 */}
            <Card
              title="实际持仓"
              size="small"
              extra={
                <Space size={4}>
                  <Button size="small" onClick={loadExistingHoldings}>加载已有</Button>
                  <Button size="small" onClick={fillFormWithTop3}>填入推荐</Button>
                </Space>
              }
            >
              <Form form={form} layout="vertical" size="small">
                <Form.List name="holdings">
                  {(fields, { add, remove }) => (
                    <>
                      {fields.map(({ key, name, ...rest }) => (
                        <Card
                          key={key}
                          size="small"
                          style={{ marginBottom: 8 }}
                          styles={{ body: { padding: 8 } }}
                          extra={
                            <Button type="text" size="small" danger
                              icon={<DeleteOutlined />} onClick={() => remove(name)} />
                          }
                        >
                          <Form.Item {...rest} name={[name, 'ts_code']} label="股票代码"
                            rules={[{ required: true }]}>
                            <Select showSearch
                              filterOption={(input, option) =>
                                (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                              }
                              options={recommendations.map((r) => ({
                                value: r.ts_code,
                                label: `${r.ts_code} ${r.name}`,
                              }))}
                              placeholder="选择或输入"
                            />
                          </Form.Item>
                          <Form.Item {...rest} name={[name, 'stock_name']} label="名称">
                            <Select showSearch
                              filterOption={(input, option) =>
                                (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                              }
                              options={recommendations.map((r) => ({
                                value: r.name,
                                label: r.name,
                              }))}
                              placeholder="股票名称"
                            />
                          </Form.Item>
                          <Row gutter={8}>
                            <Col span={12}>
                              <Form.Item {...rest} name={[name, 'shares']} label="股数"
                                rules={[{ required: true }]}>
                                <InputNumber min={0} step={100} style={{ width: '100%' }} />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item {...rest} name={[name, 'buy_price']} label="买入价"
                                rules={[{ required: true }]}>
                                <InputNumber min={0} step={0.01} style={{ width: '100%' }} />
                              </Form.Item>
                            </Col>
                          </Row>
                        </Card>
                      ))}
                      <Button type="dashed"
                        onClick={() => add({ ts_code: '', stock_name: '', shares: 0, buy_price: 0 })}
                        block icon={<PlusOutlined />}>
                        添加股票
                      </Button>
                    </>
                  )}
                </Form.List>
                <Form.Item style={{ marginTop: 12, marginBottom: 0 }}>
                  <Button type="primary" icon={<SaveOutlined />}
                    onClick={handleSaveHoldings} loading={saving} block>
                    保存持仓
                  </Button>
                </Form.Item>
              </Form>
            </Card>
          </Col>

          {/* 中间: NAV 图表 */}
          <Col span={18}>
            <Card title="账户净值变化" size="small" style={{ marginBottom: 16 }}>
              {navData.length === 0 ? (
                <Empty
                  description="暂无净值数据，请先保存持仓"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              ) : (
                <>
                  <ReactECharts
                    ref={navChartRef}
                    option={navOption}
                    style={{ height: 320 }}
                  />
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
                      <Statistic title="数据天数" value={navData.length} valueStyle={{ fontSize: 16, color: '#999' }} />
                    </Col>
                  </Row>
                </>
              )}
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  );
}
