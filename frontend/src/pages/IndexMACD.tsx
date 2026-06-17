import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  Card, Tabs, Radio, Slider, Row, Col, Tag, Spin, Collapse, Select,
  Breadcrumb, Typography, theme, Space, message,
} from 'antd';
import {
  RiseOutlined, FallOutlined, MinusOutlined,
  WarningOutlined, BulbOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import IndexMACDChart from '@/components/charts/IndexMACDChart';
import StockSearchLookup from '@/components/shared/StockSearchLookup';
import { stockService } from '@/services/stockService';
import { backtestService } from '@/services/backtestService';
import type { KLineItem } from '@/types/stock';
import type { RecommendationItem } from '@/types/backtest';
import { calcMACD, calcRSI, detectCrosses, detectDivergences } from '@/utils/indicators';
import { computeAllPredictions } from '@/utils/predictions';
import type { IndexPredictions, PredictionStatus } from '@/utils/predictions';

const { Text, Title } = Typography;

// ── 四大指数配置 ──
const INDICES = [
  { tsCode: '000001.SH', name: '上证指数', market: '沪' },
  { tsCode: '399001.SZ', name: '深证成指', market: '深' },
  { tsCode: '399006.SZ', name: '创业板指', market: '深' },
  { tsCode: '000688.SH', name: '科创50', market: '沪' },
] as const;

const PERIOD_OPTIONS = [
  { label: '1个月', value: 22 },
  { label: '3个月', value: 66 },
  { label: '6个月', value: 132 },
  { label: '1年', value: 250 },
];

const DEFAULT_MACD = { fast: 12, slow: 26, signal: 9 };
const DEFAULT_RSI = { period: 14, overbought: 70, oversold: 30 };

// ── 辅助函数 ──
function getMACDSignal(
  dif: number | null,
  dea: number | null,
  bar: number | null
): { label: string; color: string } {
  if (dif === null || dea === null) return { label: '计算中', color: 'default' };
  if (dif > dea) {
    return { label: '金叉中', color: 'red' };
  }
  return { label: '死叉中', color: 'green' };
}

function getRSITag(rsi: number | null, overbought: number, oversold: number) {
  if (rsi === null) return { label: '—', color: 'default' as const };
  if (rsi >= overbought) return { label: '超买', color: 'red' as const };
  if (rsi <= oversold) return { label: '超卖', color: 'green' as const };
  return { label: '正常', color: 'default' as const };
}

function statusBadge(status: PredictionStatus): { color: string; text: string } {
  switch (status) {
    case 'already': return { color: '#fa8c16', text: '已触发' };
    case 'imminent': return { color: '#ff4d4f', text: '⚠ 即将触发' };
    case 'moderate': return { color: '#1677ff', text: '中等距离' };
    case 'far': return { color: '#999', text: '较远' };
    default: return { color: '#999', text: '—' };
  }
}

// ── 预测面板子组件 ──
function PredictionRow({
  label, icon, pred, unit = '点',
}: {
  label: string;
  icon: React.ReactNode;
  pred: {
    status: PredictionStatus;
    description: string;
    thresholdPrice: number | null;
    thresholdChangePct: number | null;
  };
  unit?: string;
}) {
  const badge = statusBadge(pred.status);
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '6px 0',
        borderBottom: '1px solid #f0f0f0',
        gap: 12,
      }}
    >
      <Space size={4}>
        {icon}
        <Text strong style={{ fontSize: 13 }}>{label}</Text>
        <Tag color={badge.color} style={{ fontSize: 11, lineHeight: '18px' }}>
          {badge.text}
        </Tag>
      </Space>
      <Text style={{ fontSize: 12, color: '#666', flex: 1, textAlign: 'right' }}>
        {pred.description}
      </Text>
    </div>
  );
}

// ── 辅助函数：解析回测 config（后端可能返回字符串或已解析对象）──
function parseConfig(config: any): Record<string, any> | null {
  if (!config) return null;
  if (typeof config === 'string') {
    try {
      const parsed = JSON.parse(config);
      return typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
    } catch {
      return null;
    }
  }
  if (typeof config === 'object' && !Array.isArray(config)) {
    return config;
  }
  return null;
}

// ── 主组件 ──
export default function IndexMACD() {
  const navigate = useNavigate();
  const { token } = theme.useToken();

  const [loading, setLoading] = useState(true);
  const [klineData, setKlineData] = useState<Record<string, KLineItem[]>>({});
  const [activeTab, setActiveTab] = useState('000001.SH');
  const [days, setDays] = useState(120);

  // MACD 参数
  const [macdParams, setMacdParams] = useState(DEFAULT_MACD);

  // 自定义个股
  const [customStocks, setCustomStocks] = useState<{ tsCode: string; name: string }[]>([]);
  const [searchValue, setSearchValue] = useState('');

  // 最新回测推荐
  const [availableStrategies, setAvailableStrategies] = useState<{ id: number; name: string }[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState<number | null>(null);
  const [availableBacktests, setAvailableBacktests] = useState<{ id: number; cutoffDate: string }[]>([]);
  const [selectedBacktestId, setSelectedBacktestId] = useState<number | null>(null);
  const [currentRecs, setCurrentRecs] = useState<{
    strategyName: string;
    cutoffDate: string;
    recommendations: RecommendationItem[];
  } | null>(null);
  const [backtestParams, setBacktestParams] = useState<Record<string, any> | null>(null);

  // ── 加载数据 ──
  // 用 ref 追踪自定义股票，避免 customStocks 变化触发全量重载
  const customRef = useRef(customStocks);
  useEffect(() => {
    customRef.current = customStocks;
  }, [customStocks]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    const allCodes = [
      ...INDICES.map((idx) => idx.tsCode),
      ...customRef.current.map((s) => s.tsCode),
    ];

    Promise.all(
      allCodes.map((code) =>
        stockService.getKLine(code, Math.max(days + 60, 180)).catch(() => ({
          ts_code: code,
          name: code,
          items: [] as KLineItem[],
        }))
      )
    )
      .then((results) => {
        if (cancelled) return;
        const map: Record<string, KLineItem[]> = {};
        results.forEach((r) => {
          map[r.ts_code] = r.items.slice(-days);
        });
        setKlineData(map);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [days]);

  // ── ① 加载可选策略列表（有已完成回测的） ──
  useEffect(() => {
    let cancelled = false;
    backtestService.getBacktests({ status: 'completed', limit: 100 })
      .then((res) => {
        if (cancelled) return;
        const seen = new Map<number, string>();
        res.items.forEach((bt) => {
          if (!seen.has(bt.strategy_id)) {
            seen.set(bt.strategy_id, bt.strategy_name || bt.name || `策略${bt.strategy_id}`);
          }
        });
        const strategies = Array.from(seen.entries()).map(([id, name]) => ({ id, name }));
        setAvailableStrategies(strategies);

        // 默认选中最新回测的策略
        if (res.items.length > 0) {
          setSelectedStrategyId(res.items[0].strategy_id);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // ── ② 策略变化 → 加载该策略最近 10 条回测，默认选最新 ──
  useEffect(() => {
    if (selectedStrategyId === null) return;
    let cancelled = false;
    setAvailableBacktests([]);
    setSelectedBacktestId(null);
    setCurrentRecs(null);

    backtestService.getBacktests({ strategy_id: selectedStrategyId, status: 'completed', limit: 10 })
      .then((res) => {
        if (cancelled) return;
        const options = res.items.map((bt) => ({
          id: bt.id,
          cutoffDate: bt.cutoff_date,
        }));
        setAvailableBacktests(options);

        // 默认选中最新一条
        const latest = res.items[0];
        if (latest) {
          setSelectedBacktestId(latest.id);
          if (latest.recommendations && latest.recommendations.length > 0) {
            setCurrentRecs({
              strategyName: latest.strategy_name || latest.name || '未知策略',
              cutoffDate: latest.cutoff_date,
              recommendations: latest.recommendations,
            });
          }
          // 提取回测参数（后端可能返回字符串或已解析对象）
          setBacktestParams(parseConfig(latest.config));
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [selectedStrategyId]);

  // ── ③ 回测选择变化 → 加载该回测详情 ──
  useEffect(() => {
    if (selectedBacktestId === null) return;
    let cancelled = false;
    backtestService.getBacktest(selectedBacktestId)
      .then((bt) => {
        if (cancelled) return;
        if (bt.recommendations && bt.recommendations.length > 0) {
          setCurrentRecs({
            strategyName: bt.strategy_name || bt.name || '未知策略',
            cutoffDate: bt.cutoff_date,
            recommendations: bt.recommendations,
          });
        } else {
          setCurrentRecs(null);
        }
        // 提取回测参数（后端可能返回字符串或已解析对象）
        setBacktestParams(parseConfig(bt.config));
      })
      .catch(() => {
        if (!cancelled) setCurrentRecs(null);
      });
    return () => { cancelled = true; };
  }, [selectedBacktestId]);

  // ── 个股选择 ──
  const handleStockSelect = useCallback(
    async (tsCode: string) => {
      // 始终更新输入框的值（支持用户自由输入搜索关键词）
      setSearchValue(tsCode);

      // 只处理符合股票代码格式的选择（过滤掉用户输入的搜索关键词）
      if (!/^\d{6}\.(SH|SZ|BJ)$/.test(tsCode)) return;

      // 如果已是指数，直接切换 tab
      if (INDICES.some((i) => i.tsCode === tsCode)) {
        setActiveTab(tsCode);
        return;
      }

      // 如果已在自定义股票中，直接切换 tab
      if (customStocks.some((s) => s.tsCode === tsCode)) {
        setActiveTab(tsCode);
        return;
      }

      // 已加载过数据（例如通过其他方式），直接加入列表
      if (klineData[tsCode]) {
        // 从已加载数据推断名称
        setCustomStocks((prev) => [...prev, { tsCode, name: tsCode }]);
        setActiveTab(tsCode);
        return;
      }

      // 加载 K 线数据
      setLoading(true);
      try {
        const result = await stockService.getKLine(tsCode, Math.max(days + 60, 180));
        if (result.items.length === 0) {
          message.warning('该股票暂无数据');
          setLoading(false);
          return;
        }
        setKlineData((prev) => ({ ...prev, [tsCode]: result.items.slice(-days) }));
        setCustomStocks((prev) => [...prev, { tsCode, name: result.name || tsCode }]);
        setActiveTab(tsCode);
      } catch {
        message.error('获取股票数据失败');
      } finally {
        setLoading(false);
      }
    },
    [days, customStocks, klineData],
  );

  // ── 当前 Tab 数据 ──
  const currentData = klineData[activeTab] || [];
  const currentIndex = INDICES.find((i) => i.tsCode === activeTab);
  const currentStockName =
    currentIndex?.name ||
    customStocks.find((s) => s.tsCode === activeTab)?.name ||
    activeTab;

  const latest = currentData.length > 0 ? currentData[currentData.length - 1] : null;
  const prev = currentData.length > 1 ? currentData[currentData.length - 2] : null;
  const changePct = latest && prev ? ((latest.close - prev.close) / prev.close) * 100 : 0;

  // ── 指标计算 ──
  const closes = useMemo(() => currentData.map((d) => d.close), [currentData]);
  const dates = useMemo(
    () => currentData.map((d) => d.trade_date.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3')),
    [currentData],
  );

  const macd = useMemo(
    () => calcMACD(closes, macdParams.fast, macdParams.slow, macdParams.signal),
    [closes, macdParams],
  );
  const rsi = useMemo(() => calcRSI(closes, DEFAULT_RSI.period), [closes]);
  const crosses = useMemo(() => detectCrosses(dates, macd.dif, macd.dea), [dates, macd.dif, macd.dea]);
  const divergences = useMemo(() => detectDivergences(dates, closes, macd.dif), [dates, closes, macd.dif]);

  const lastDif = macd.dif.filter((x): x is number => x !== null).pop() ?? null;
  const lastDea = macd.dea.filter((x): x is number => x !== null).pop() ?? null;
  const lastBar = macd.bar.filter((x): x is number => x !== null).pop() ?? null;
  const lastRSI = rsi.filter((x): x is number => x !== null).pop() ?? null;

  // ── 预判 ──
  const predictions: IndexPredictions | null = useMemo(() => {
    if (closes.length < 60) return null;
    try {
      return computeAllPredictions(closes, macdParams, DEFAULT_RSI.period, DEFAULT_RSI.overbought, DEFAULT_RSI.oversold);
    } catch {
      return null;
    }
  }, [closes, macdParams]);

  // ── 汇总卡片数据 ──
  const summaryCards = INDICES.map((idx) => {
    const items = klineData[idx.tsCode] || [];
    const last = items.length > 0 ? items[items.length - 1] : null;
    const prev = items.length > 1 ? items[items.length - 2] : null;
    const pct = last && prev ? ((last.close - prev.close) / prev.close) * 100 : 0;

    if (!last) {
      return { ...idx, close: null, changePct: 0, signal: '加载中', rsiTag: '—', signalColor: 'default' as const, rsiColor: 'default' as const, rsiValue: null };
    }

    const c = items.map((d) => d.close);
    const { dif, dea } = calcMACD(c, DEFAULT_MACD.fast, DEFAULT_MACD.slow, DEFAULT_MACD.signal);
    const r = calcRSI(c, DEFAULT_RSI.period);
    const ld = dif.filter((x): x is number => x !== null).pop() ?? null;
    const le = dea.filter((x): x is number => x !== null).pop() ?? null;
    const lr = r.filter((x): x is number => x !== null).pop() ?? null;

    const sig = getMACDSignal(ld, le, null);
    const rsiTag = getRSITag(lr, DEFAULT_RSI.overbought, DEFAULT_RSI.oversold);

    return {
      ...idx,
      close: last.close,
      changePct: pct,
      signal: sig.label,
      signalColor: sig.color,
      rsiTag: rsiTag.label,
      rsiColor: rsiTag.color,
      rsiValue: lr,
    };
  });

  // ── 最近信号 ──
  const recentSignals = useMemo(() => {
    const all: { date: string; type: string; color: string }[] = [];
    crosses.slice(-5).reverse().forEach((c) => {
      all.push({
        date: c.date,
        type: c.type === 'golden' ? '金叉' : '死叉',
        color: c.type === 'golden' ? '#52c41a' : '#ff4d4f',
      });
    });
    divergences.slice(-5).reverse().forEach((d) => {
      all.push({
        date: d.date,
        type: d.type === 'top' ? '顶背离' : '底背离',
        color: d.type === 'top' ? '#ff4d4f' : '#52c41a',
      });
    });
    return all.slice(0, 5);
  }, [crosses, divergences]);

  // ── 渲染 ──
  return (
    <div>
      {/* ── 个股搜索 ── */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Text strong style={{ whiteSpace: 'nowrap', fontSize: 13 }}>
            个股分析：
          </Text>
          <StockSearchLookup
            value={searchValue}
            onChange={handleStockSelect}
            placeholder="输入股票代码或名称，选中后查看 MACD 分析"
            style={{ flex: 1, maxWidth: 480 }}
          />
          {customStocks.length > 0 && (
            <Text type="secondary" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
              已选 {customStocks.length} 只个股
            </Text>
          )}
        </div>
      </Card>

      {/* 面包屑 */}
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[
          { title: <a onClick={() => navigate('/dashboard')}>仪表盘</a> },
          { title: 'MACD 分析' },
        ]}
      />

      <Title level={4} style={{ marginBottom: 16 }}>
        <ThunderboltOutlined style={{ marginRight: 8, color: token.colorPrimary }} />
        MACD 分析
        {currentStockName && activeTab !== currentIndex?.tsCode && (
          <Tag style={{ marginLeft: 8, fontSize: 12 }} color="blue">{currentStockName}</Tag>
        )}
      </Title>

      {/* ── 汇总卡片 ── */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {summaryCards.map((card) => (
          <Col xs={24} sm={12} md={6} key={card.tsCode}>
            <Card
              size="small"
              hoverable
              style={{
                border: activeTab === card.tsCode ? `2px solid ${token.colorPrimary}` : undefined,
                cursor: 'pointer',
              }}
              onClick={() => {
                setActiveTab(card.tsCode);
                // 如果该指数数据未加载，触发 days 重新加载
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {card.name}
                    <Tag style={{ marginLeft: 4, fontSize: 10 }}>{card.market}</Tag>
                  </Text>
                  {card.close !== null ? (
                    <div style={{ marginTop: 4 }}>
                      <Text strong style={{ fontSize: 18 }}>
                        {card.close.toFixed(0)}
                      </Text>
                      <Text
                        style={{
                          fontSize: 13,
                          marginLeft: 4,
                          color: card.changePct >= 0 ? '#ef5350' : '#26a69a',
                        }}
                      >
                        {card.changePct >= 0 ? <RiseOutlined /> : <FallOutlined />}
                        {card.changePct.toFixed(2)}%
                      </Text>
                    </div>
                  ) : (
                    <Spin size="small" />
                  )}
                </div>
                <Space direction="vertical" size={2} style={{ textAlign: 'right' }}>
                  <Tag color={card.signalColor === 'red' ? 'red' : card.signalColor === 'green' ? 'green' : 'default'}>
                    {card.signal}
                  </Tag>
                  {card.rsiValue !== null && (
                    <Text style={{ fontSize: 11, color: '#888' }}>
                      RSI {card.rsiValue.toFixed(0)}
                      {card.rsiTag !== '正常' && (
                        <Tag
                          color={card.rsiColor}
                          style={{ marginLeft: 4, fontSize: 10, lineHeight: '16px' }}
                        >
                          {card.rsiTag}
                        </Tag>
                      )}
                    </Text>
                  )}
                </Space>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* ── 主体内容：左右分栏 ── */}
      <Row gutter={16}>
        {/* 左侧：最新回测推荐个股 */}
        {availableStrategies.length > 0 && (
          <Col xs={24} md={6}>
            <Card
              size="small"
              title={
                <Space wrap size={4}>
                  <RiseOutlined style={{ color: token.colorPrimary }} />
                  <Text strong style={{ fontSize: 13 }}>回测推荐</Text>
                  <Select
                    size="small"
                    style={{ minWidth: 130 }}
                    value={selectedStrategyId}
                    onChange={(val) => setSelectedStrategyId(val)}
                    options={availableStrategies.map((s) => ({ value: s.id, label: s.name }))}
                    placeholder="选择策略"
                  />
                  {availableBacktests.length > 0 && (
                    <Select
                      size="small"
                      style={{ minWidth: 110 }}
                      value={selectedBacktestId}
                      onChange={(val) => setSelectedBacktestId(val)}
                      options={availableBacktests.map((bt) => ({
                        value: bt.id,
                        label: bt.cutoffDate.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3'),
                      }))}
                      placeholder="选择回测"
                    />
                  )}
                  {backtestParams && (
                    <>
                      {backtestParams.track_days && (
                        <Tag color="blue" style={{ fontSize: 10, lineHeight: '16px' }}>追踪 {backtestParams.track_days.join('/')} 日</Tag>
                      )}
                      {Object.entries(backtestParams)
                        .filter(([k]) => k !== 'track_days')
                        .slice(0, 2)
                        .map(([k, v]) => {
                          const displayValue = Array.isArray(v)
                            ? v.join(', ')
                            : typeof v === 'object'
                              ? JSON.stringify(v)
                              : String(v);
                          return (
                            <Tag key={k} color="default" style={{ fontSize: 10, lineHeight: '16px' }}>
                              {k}: {displayValue}
                            </Tag>
                          );
                        })}
                    </>
                  )}
                </Space>
              }
              style={{ height: '100%' }}
            >
              {currentRecs ? (
                <div style={{ maxHeight: 700, overflowY: 'auto' }}>
                  <Row gutter={[8, 8]}>
                    {currentRecs.recommendations.map((rec, i) => (
                      <Col span={24} key={rec.ts_code}>
                        <Card
                          size="small"
                          hoverable
                          style={{
                            borderLeft: `3px solid ${token.colorPrimary}`,
                            cursor: 'pointer',
                          }}
                          onClick={() => handleStockSelect(rec.ts_code)}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <Space size={4}>
                                <Tag style={{ fontSize: 10, lineHeight: '16px' }}>#{i + 1}</Tag>
                                <Text strong style={{ fontSize: 13 }}>
                                  {rec.name}
                                </Text>
                              </Space>
                              <div style={{ marginTop: 2 }}>
                                <Text type="secondary" style={{ fontSize: 11 }}>
                                  {rec.ts_code}
                                </Text>
                              </div>
                            </div>
                            <div style={{ textAlign: 'right' }}>
                              <Text strong style={{ fontSize: 16, color: token.colorPrimary }}>
                                {rec.score.toFixed(1)}
                              </Text>
                              <div>
                                <Text type="secondary" style={{ fontSize: 10 }}>得分</Text>
                              </div>
                            </div>
                          </div>
                          {rec.signal && (
                            <div style={{ marginTop: 4 }}>
                              <Text
                                type="secondary"
                                style={{ fontSize: 11, lineHeight: '16px' }}
                                ellipsis={{ tooltip: rec.signal }}
                              >
                                {rec.signal}
                              </Text>
                            </div>
                          )}
                        </Card>
                      </Col>
                    ))}
                  </Row>
                </div>
              ) : (
                <Text type="secondary">该策略暂无已完成回测</Text>
              )}
            </Card>
          </Col>
        )}

        {/* 右侧：MACD 图表 + 分析 */}
        <Col xs={24} md={availableStrategies.length > 0 ? 18 : 24} style={{ overflow: 'hidden' }}>
          <Card styles={{ body: { overflow: 'hidden' } }}>
            {/* 工具栏 */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 16,
                flexWrap: 'wrap',
                gap: 12,
              }}
            >
              {/* 指数/个股 Tabs */}
              <Tabs
                activeKey={activeTab}
                onChange={setActiveTab}
                items={[
                  ...INDICES.map((idx) => ({ key: idx.tsCode, label: idx.name })),
                  ...customStocks.map((s) => ({
                    key: s.tsCode,
                    label: (
                      <span>
                        {s.name}
                        <Tag style={{ marginLeft: 4, fontSize: 10, lineHeight: '14px' }}>个股</Tag>
                      </span>
                    ),
                  })),
                ]}
                style={{ marginBottom: 0 }}
                size="small"
              />

              <Space size="middle" wrap>
                <Radio.Group
                  options={PERIOD_OPTIONS}
                  value={days}
                  onChange={(e) => setDays(e.target.value)}
                  size="small"
                />

                <Collapse
                  size="small"
                  ghost
                  items={[
                    {
                      key: 'params',
                      label: <Text style={{ fontSize: 12 }}>参数设置</Text>,
                      children: (
                        <div style={{ padding: '8px 0' }}>
                          <Row gutter={[24, 8]}>
                            <Col span={8}>
                              <Text style={{ fontSize: 12 }}>
                                MACD 快线: <Text strong>{macdParams.fast}</Text>
                              </Text>
                              <Slider
                                min={2}
                                max={50}
                                value={macdParams.fast}
                                onChange={(v) => setMacdParams((p) => ({ ...p, fast: v }))}
                              />
                            </Col>
                            <Col span={8}>
                              <Text style={{ fontSize: 12 }}>
                                MACD 慢线: <Text strong>{macdParams.slow}</Text>
                              </Text>
                              <Slider
                                min={5}
                                max={100}
                                value={macdParams.slow}
                                onChange={(v) => setMacdParams((p) => ({ ...p, slow: v }))}
                              />
                            </Col>
                            <Col span={8}>
                              <Text style={{ fontSize: 12 }}>
                                信号线: <Text strong>{macdParams.signal}</Text>
                              </Text>
                              <Slider
                                min={2}
                                max={30}
                                value={macdParams.signal}
                                onChange={(v) => setMacdParams((p) => ({ ...p, signal: v }))}
                              />
                            </Col>
                          </Row>
                        </div>
                      ),
                    },
                  ]}
                />
              </Space>
            </div>

            {/* 图表 */}
            {loading ? (
              <Spin style={{ display: 'block', margin: '60px auto' }} />
            ) : currentData.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>暂无数据</div>
            ) : (
              <>
                <IndexMACDChart
                  data={currentData}
                  macdParams={macdParams}
                  rsiParams={DEFAULT_RSI}
                  height={580}
                />

                {/* 当前指标摘要 */}
                <Row gutter={16} style={{ marginTop: 8, marginBottom: 16 }}>
                  <Col span={6}>
                    <Text style={{ fontSize: 12, color: '#888' }}>
                      最新收盘:{' '}
                      <Text strong>{latest?.close.toFixed(2)}</Text>
                      {changePct !== undefined && (
                        <span style={{ color: changePct >= 0 ? '#ef5350' : '#26a69a', marginLeft: 4 }}>
                          {changePct >= 0 ? '+' : ''}{changePct.toFixed(2)}%
                        </span>
                      )}
                    </Text>
                  </Col>
                  <Col span={6}>
                    <Text style={{ fontSize: 12, color: '#888' }}>
                      DIF:{' '}
                      <Text strong style={{ color: '#1677ff' }}>
                        {lastDif?.toFixed(2) ?? '—'}
                      </Text>
                    </Text>
                  </Col>
                  <Col span={6}>
                    <Text style={{ fontSize: 12, color: '#888' }}>
                      DEA:{' '}
                      <Text strong style={{ color: '#fa8c16' }}>
                        {lastDea?.toFixed(2) ?? '—'}
                      </Text>
                    </Text>
                  </Col>
                  <Col span={6}>
                    <Text style={{ fontSize: 12, color: '#888' }}>
                      RSI({DEFAULT_RSI.period}):{' '}
                      <Text strong style={{ color: '#7c3aed' }}>
                        {lastRSI?.toFixed(1) ?? '—'}
                      </Text>
                      {lastRSI !== null && (
                        <Tag
                          color={getRSITag(lastRSI, DEFAULT_RSI.overbought, DEFAULT_RSI.oversold).color}
                          style={{ marginLeft: 4, fontSize: 10, lineHeight: '16px' }}
                        >
                          {getRSITag(lastRSI, DEFAULT_RSI.overbought, DEFAULT_RSI.oversold).label}
                        </Tag>
                      )}
                    </Text>
                  </Col>
                </Row>

                {/* 最近信号历史 */}
                {recentSignals.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <Text type="secondary" style={{ fontSize: 12, marginRight: 8 }}>
                      最近信号:
                    </Text>
                    {recentSignals.map((s, i) => (
                      <Tag key={i} color={s.color} style={{ fontSize: 11, marginBottom: 4 }}>
                        {s.date} {s.type}
                      </Tag>
                    ))}
                  </div>
                )}

                {/* ── 明日预判面板 ── */}
                {predictions && (
                  <Card
                    size="small"
                    title={
                      <Space>
                        <BulbOutlined style={{ color: '#fa8c16' }} />
                        <Text strong>明日预判</Text>
                        <Text type="secondary" style={{ fontSize: 11, fontWeight: 'normal' }}>
                          基于今日收盘 {latest?.close.toFixed(2)}，模拟次日收盘价变化对各指标的影响
                        </Text>
                      </Space>
                    }
                    style={{ background: '#fafafa' }}
                  >
                    <PredictionRow
                      label={predictions.cross.type === 'golden_cross' ? '金叉预判' : '死叉预判'}
                      icon={
                        predictions.cross.type === 'golden_cross' ? (
                          <RiseOutlined style={{ color: '#52c41a' }} />
                        ) : (
                          <FallOutlined style={{ color: '#ff4d4f' }} />
                        )
                      }
                      pred={predictions.cross}
                    />
                    <PredictionRow
                      label="底背离预判"
                      icon={<WarningOutlined style={{ color: '#52c41a' }} />}
                      pred={predictions.divergence.bottom}
                    />
                    <PredictionRow
                      label="顶背离预判"
                      icon={<WarningOutlined style={{ color: '#ff4d4f' }} />}
                      pred={predictions.divergence.top}
                    />
                    <PredictionRow
                      label={`RSI超买(${DEFAULT_RSI.overbought})预判`}
                      icon={<RiseOutlined style={{ color: '#ff4d4f' }} />}
                      pred={predictions.rsi.overbought}
                    />
                    <PredictionRow
                      label={`RSI超卖(${DEFAULT_RSI.oversold})预判`}
                      icon={<FallOutlined style={{ color: '#52c41a' }} />}
                      pred={predictions.rsi.oversold}
                    />
                  </Card>
                )}
              </>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
