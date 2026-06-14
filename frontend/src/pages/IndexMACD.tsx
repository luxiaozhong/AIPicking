import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Card, Tabs, Radio, Slider, Row, Col, Tag, Spin, Collapse,
  Breadcrumb, Typography, theme, Space,
} from 'antd';
import {
  RiseOutlined, FallOutlined, MinusOutlined,
  WarningOutlined, BulbOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import IndexMACDChart from '@/components/charts/IndexMACDChart';
import { stockService } from '@/services/stockService';
import type { KLineItem } from '@/types/stock';
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

  // ── 加载数据 ──
  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all(
      INDICES.map((idx) =>
        stockService.getKLine(idx.tsCode, Math.max(days + 60, 180)).catch(() => ({
          ts_code: idx.tsCode,
          name: idx.name,
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

  // ── 当前 Tab 数据 ──
  const currentData = klineData[activeTab] || [];
  const currentIndex = INDICES.find((i) => i.tsCode === activeTab)!;

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
      {/* 面包屑 */}
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[
          { title: <a onClick={() => navigate('/dashboard')}>仪表盘</a> },
          { title: '指数MACD' },
        ]}
      />

      <Title level={4} style={{ marginBottom: 16 }}>
        <ThunderboltOutlined style={{ marginRight: 8, color: token.colorPrimary }} />
        指数 MACD 分析
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

      {/* ── 主体内容 ── */}
      <Card>
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
          {/* 指数 Tabs */}
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={INDICES.map((idx) => ({ key: idx.tsCode, label: idx.name }))}
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
    </div>
  );
}
