import React, { useEffect, useState, useCallback } from 'react';
import { Spin, Switch, Radio, Collapse, Slider, Button } from 'antd';
import { UndoOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import educationService from '@/services/educationService';
import { stockService } from '@/services/stockService';
import type { MACDCase, MACDCasesData } from '@/services/educationService';
import type { KLineItem } from '@/types/stock';
import type { MACDParams } from '@/components/education/ParameterPanel';
import CaseSelector from '@/components/education/CaseSelector';
import MACDInteractiveChart from '@/components/education/MACDInteractiveChart';
import StepNavigator from '@/components/education/StepNavigator';

const InteractiveMACDPage: React.FC = () => {
  const [casesData, setCasesData] = useState<MACDCasesData | null>(null);
  const [loading, setLoading] = useState(true);

  // State
  const [mode, setMode] = useState<'preset' | 'free'>('preset');
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);
  const [klineData, setKlineData] = useState<KLineItem[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [params, setParams] = useState<MACDParams>({ fast: 12, slow: 26, signal: 9 });
  const [currentStep, setCurrentStep] = useState(1);
  const [showComparison, setShowComparison] = useState(false);
  const [periodMonths, setPeriodMonths] = useState<number>(6);

  const PERIOD_OPTIONS = [
    { label: '1月', value: 1 },
    { label: '3月', value: 3 },
    { label: '6月', value: 6 },
    { label: '1年', value: 12 },
    { label: '2年', value: 24 },
  ];

  // Load case configs
  useEffect(() => {
    educationService.getMACDCases().then((data) => {
      setCasesData(data);
      if (data.cases.length > 0) {
        setActiveCaseId(data.cases[0].id);
      }
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const activeCase: MACDCase | undefined = casesData?.cases.find((c) => c.id === activeCaseId);
  const defaultParams: MACDParams = casesData?.default_params
    ? { ...casesData.default_params }
    : { fast: 12, slow: 26, signal: 9 };

  // Load K-line data
  const loadKline = useCallback(async (tsCode: string, start: string, end: string) => {
    setChartLoading(true);
    try {
      const startDate = start.replace(/-/g, '');
      const endDate = end.replace(/-/g, '');
      const days = Math.ceil(
        (new Date(end).getTime() - new Date(start).getTime()) / 86400000
      ) + 30;
      const result = await stockService.getKLine(tsCode, Math.min(days, 365));
      const items = result.items || [];
      // Filter by date range
      const filtered = items.filter(
        (item) => item.trade_date >= startDate && item.trade_date <= endDate
      );
      setKlineData(filtered.length > 0 ? filtered : items.slice(0, Math.min(days, items.length)));
    } finally {
      setChartLoading(false);
    }
  }, []);

  // Reload data + reset state when case changes
  useEffect(() => {
    if (!activeCase) return;
    setParams({ ...defaultParams });
    setCurrentStep(1);
    setMode('preset');
    // 用 periodMonths 调整 start，保持 end 不变
    const end = new Date(activeCase.date_range.end);
    const start = new Date(end);
    start.setMonth(start.getMonth() - periodMonths);
    loadKline(
      activeCase.stock.ts_code,
      start.toISOString().slice(0, 10),
      activeCase.date_range.end
    );
  }, [activeCaseId]);

  // Period change → reload with adjusted range
  useEffect(() => {
    if (mode === 'free') {
      const today = new Date();
      const start = new Date(today);
      start.setMonth(start.getMonth() - periodMonths);
      loadKline(
        activeCase?.stock.ts_code || '',
        start.toISOString().slice(0, 10),
        today.toISOString().slice(0, 10)
      );
      return;
    }
    if (!activeCase) return;
    const end = new Date(activeCase.date_range.end);
    const start = new Date(end);
    start.setMonth(start.getMonth() - periodMonths);
    loadKline(
      activeCase.stock.ts_code,
      start.toISOString().slice(0, 10),
      activeCase.date_range.end
    );
  }, [periodMonths]);

  const currentStepData = activeCase?.steps?.find((s) => s.step === currentStep);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <h2 style={{ marginBottom: 8 }}>MACD 交互学习</h2>

      {/* Zone 1: Case Selector */}
      <CaseSelector
        cases={casesData?.cases || []}
        activeCaseId={activeCaseId}
        mode={mode}
        onSelectCase={(id) => {
          setActiveCaseId(id);
        }}
        onSearchStock={(code) => {
          setMode('free');
          setActiveCaseId(null);
          setCurrentStep(1);
          setParams({ ...defaultParams });
          const today = new Date();
          const start = new Date(today);
          start.setMonth(start.getMonth() - periodMonths);
          loadKline(code, start.toISOString().slice(0, 10), today.toISOString().slice(0, 10));
        }}
      />

      {/* Period Selector */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
        <span style={{ fontSize: 12, color: '#666' }}>📅 K 线周期：</span>
        <Radio.Group
          value={periodMonths}
          onChange={(e) => setPeriodMonths(e.target.value)}
          size="small"
          optionType="button"
          buttonStyle="solid"
          options={PERIOD_OPTIONS}
        />
      </div>

      {/* Zone 2: Interactive Chart */}
      {chartLoading ? (
        <div style={{ textAlign: 'center', padding: 60 }}>
          <Spin size="large" />
        </div>
      ) : (
        <MACDInteractiveChart
          data={klineData}
          fast={params.fast}
          slow={params.slow}
          signal={params.signal}
          defaultFast={defaultParams.fast}
          defaultSlow={defaultParams.slow}
          defaultSignal={defaultParams.signal}
          annotations={activeCase?.annotations || []}
          visibleAnnotationIds={
            currentStepData?.visible_annotations || (mode === 'free' ? [] : [])
          }
          showComparison={showComparison}
          height={mode === 'free' ? 450 : 400}
        />
      )}

      {/* Zone 3: Step Navigator (preset mode only) */}
      {mode === 'preset' && activeCase?.steps && (
        <StepNavigator
          steps={activeCase.steps}
          currentStep={currentStep}
          onStepChange={setCurrentStep}
        />
      )}

      {/* Zone 4a: Step Content */}
      <div style={{ marginTop: 16 }}>
        {currentStepData?.content ? (
          <ReactMarkdown>{currentStepData.content}</ReactMarkdown>
        ) : mode === 'free' ? (
          <div style={{ color: '#666', fontSize: 13 }}>
            <p>🔍 <strong>自由探索模式</strong> — 图上标注了自动检测到的金叉/死叉/背离信号。调节下方参数观察 MACD 变化，勾选对比开关查看与默认参数的差异。</p>
          </div>
        ) : null}
      </div>

      {/* Zone 4b: Parameter Panel — horizontal below content */}
      <div style={{ marginTop: 16, padding: '12px 16px', background: '#fafafa', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, fontWeight: 'bold', whiteSpace: 'nowrap' }}>🎚️ 参数</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: '#666' }}>快线</span>
          <Slider style={{ width: 100, margin: 0 }} min={2} max={50} value={params.fast} onChange={(v) => setParams({ ...params, fast: v })} />
          <strong style={{ fontSize: 12, minWidth: 20 }}>{params.fast}</strong>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: '#666' }}>慢线</span>
          <Slider style={{ width: 100, margin: 0 }} min={5} max={100} value={params.slow} onChange={(v) => setParams({ ...params, slow: v })} />
          <strong style={{ fontSize: 12, minWidth: 20 }}>{params.slow}</strong>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: '#666' }}>信号线</span>
          <Slider style={{ width: 100, margin: 0 }} min={2} max={30} value={params.signal} onChange={(v) => setParams({ ...params, signal: v })} />
          <strong style={{ fontSize: 12, minWidth: 20 }}>{params.signal}</strong>
        </div>
        <Button size="small" icon={<UndoOutlined />} onClick={() => setParams({ ...defaultParams })}>恢复默认</Button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, borderLeft: '1px solid #ddd', paddingLeft: 16 }}>
          <Switch checked={showComparison} onChange={setShowComparison} size="small" />
          <span style={{ fontSize: 11, color: '#666' }}>对比 ({defaultParams.fast},{defaultParams.slow},{defaultParams.signal})</span>
        </div>
      </div>

      {/* Glossary / 术语说明 */}
      <Collapse
        style={{ marginTop: 24 }}
        size="small"
        items={[
          {
            key: 'glossary',
            label: '📖 术语说明',
            children: (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '12px 24px', fontSize: 13 }}>
                <div>
                  <strong>EMA（指数移动平均）</strong>
                  <p style={{ margin: '4px 0 0', color: '#666' }}>
                    一种加权移动平均算法，近期价格权重更高，比简单均线（MA）更灵敏地反映价格变化。
                  </p>
                </div>
                <div>
                  <strong>DIF（差离值）</strong>
                  <p style={{ margin: '4px 0 0', color: '#666' }}>
                    DIF = 快线 EMA - 慢线 EMA。代表短期与长期趋势的差值。默认快线=12日，慢线=26日。
                  </p>
                </div>
                <div>
                  <strong>DEA（信号线）</strong>
                  <p style={{ margin: '4px 0 0', color: '#666' }}>
                    DEA = DIF 的 EMA（默认9日）。对 DIF 做平滑处理，作为信号参考线。
                  </p>
                </div>
                <div>
                  <strong>MACD 柱</strong>
                  <p style={{ margin: '4px 0 0', color: '#666' }}>
                    MACD 柱 = 2 × (DIF - DEA)。柱子在零轴上方为红色（多头），下方为绿色（空头）。
                  </p>
                </div>
                <div>
                  <strong>金叉（Golden Cross）</strong>
                  <p style={{ margin: '4px 0 0', color: '#666' }}>
                    DIF 从下方向上穿过 DEA，视为买入信号。
                  </p>
                </div>
                <div>
                  <strong>死叉（Death Cross）</strong>
                  <p style={{ margin: '4px 0 0', color: '#666' }}>
                    DIF 从上方向下穿过 DEA，视为卖出信号。
                  </p>
                </div>
                <div>
                  <strong>顶背离</strong>
                  <p style={{ margin: '4px 0 0', color: '#666' }}>
                    股价创出新高，但 MACD 的 DIF 未能同步创出新高，预示上涨动能减弱，可能见顶。
                  </p>
                </div>
                <div>
                  <strong>底背离</strong>
                  <p style={{ margin: '4px 0 0', color: '#666' }}>
                    股价创出新低，但 MACD 的 DIF 未能同步创出新低，预示下跌动能减弱，可能见底。
                  </p>
                </div>
              </div>
            ),
          },
        ]}
      />
    </div>
  );
};

export default InteractiveMACDPage;
