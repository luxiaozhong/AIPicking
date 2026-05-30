import React, { useEffect, useState, useCallback } from 'react';
import { Spin, Switch, Radio } from 'antd';
import ReactMarkdown from 'react-markdown';
import educationService from '@/services/educationService';
import { stockService } from '@/services/stockService';
import type { MACDCase, MACDCasesData } from '@/services/educationService';
import type { KLineItem } from '@/types/stock';
import type { MACDParams } from '@/components/education/ParameterPanel';
import CaseSelector from '@/components/education/CaseSelector';
import MACDInteractiveChart from '@/components/education/MACDInteractiveChart';
import StepNavigator from '@/components/education/StepNavigator';
import ParameterPanel from '@/components/education/ParameterPanel';

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

      {/* Zone 4: Content + Parameters */}
      <div style={{ display: 'flex', gap: 24, marginTop: 16 }}>
        {/* Zone 4a: Step Content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {currentStepData?.content ? (
            <ReactMarkdown>{currentStepData.content}</ReactMarkdown>
          ) : mode === 'free' ? (
            <div style={{ color: '#666', fontSize: 13 }}>
              <p>
                🔍 <strong>自由探索模式</strong> — 图上标注了自动检测到的金叉/死叉/背离信号。
              </p>
              <p>调节右侧参数观察 MACD 变化，勾选下方对比开关查看与默认参数的差异。</p>
            </div>
          ) : null}
        </div>

        {/* Zone 4b: Parameter Panel */}
        <div style={{ width: 260, flexShrink: 0 }}>
          <ParameterPanel
            params={params}
            defaultParams={defaultParams}
            highlightParam={currentStepData?.highlight_params || null}
            onChange={setParams}
          />
          {/* Comparison Toggle */}
          <div style={{ marginTop: 12, padding: '8px 0', borderTop: '1px solid #f0f0f0' }}>
            <Switch
              checked={showComparison}
              onChange={setShowComparison}
              size="small"
            />{' '}
            <span style={{ fontSize: 12, color: '#666' }}>
              显示默认参数对比线
            </span>
            <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
              虚线 = 默认参数 ({defaultParams.fast}, {defaultParams.slow},{' '}
              {defaultParams.signal})
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default InteractiveMACDPage;
