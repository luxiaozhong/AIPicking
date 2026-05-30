import React, { useEffect, useState, useCallback } from 'react';
import { Spin, Radio, Collapse, Slider, Button } from 'antd';
import { UndoOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import educationService from '@/services/educationService';
import { stockService } from '@/services/stockService';
import type { MACDCase, MACDCasesData } from '@/services/educationService';
import type { KLineItem } from '@/types/stock';
import CaseSelector from '@/components/education/CaseSelector';
import RSIInteractiveChart from '@/components/education/RSIInteractiveChart';
import StepNavigator from '@/components/education/StepNavigator';

const PERIOD_OPTIONS = [
  { label: '1月', value: 1 }, { label: '3月', value: 3 }, { label: '6月', value: 6 },
  { label: '1年', value: 12 }, { label: '2年', value: 24 },
];

const InteractiveRSIPage: React.FC = () => {
  const [casesData, setCasesData] = useState<MACDCasesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<'preset' | 'free'>('preset');
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);
  const [klineData, setKlineData] = useState<KLineItem[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [period, setPeriod] = useState(14);
  const [overbought, setOverbought] = useState(70);
  const [oversold, setOversold] = useState(30);
  const [currentStep, setCurrentStep] = useState(1);
  const [periodMonths, setPeriodMonths] = useState<number>(6);

  useEffect(() => {
    educationService.getRSICases().then((data) => {
      setCasesData(data);
      if (data.cases.length > 0) setActiveCaseId(data.cases[0].id);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const activeCase = casesData?.cases.find((c) => c.id === activeCaseId);
  const defaultParams: any = casesData?.default_params || { period: 14, overbought: 70, oversold: 30 };

  const loadKline = useCallback(async (tsCode: string, start: string, end: string) => {
    setChartLoading(true);
    try {
      const startDate = start.replace(/-/g, '');
      const endDate = end.replace(/-/g, '');
      const days = Math.ceil((new Date(end).getTime() - new Date(start).getTime()) / 86400000) + 30;
      const result = await stockService.getKLine(tsCode, Math.min(days, 365));
      const items = result.items || [];
      const filtered = items.filter((item) => item.trade_date >= startDate && item.trade_date <= endDate);
      setKlineData(filtered.length > 0 ? filtered : items);
    } finally {
      setChartLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!activeCase) return;
    setPeriod(defaultParams.period);
    setCurrentStep(1);
    setMode('preset');
    const end = new Date(activeCase.date_range.end);
    const start = new Date(end);
    start.setMonth(start.getMonth() - periodMonths);
    loadKline(activeCase.stock.ts_code, start.toISOString().slice(0, 10), activeCase.date_range.end);
  }, [activeCaseId]);

  useEffect(() => {
    if (mode === 'free') {
      const today = new Date();
      const start = new Date(today);
      start.setMonth(start.getMonth() - periodMonths);
      loadKline(activeCase?.stock.ts_code || '', start.toISOString().slice(0, 10), today.toISOString().slice(0, 10));
      return;
    }
    if (!activeCase) return;
    const end = new Date(activeCase.date_range.end);
    const start = new Date(end);
    start.setMonth(start.getMonth() - periodMonths);
    loadKline(activeCase.stock.ts_code, start.toISOString().slice(0, 10), activeCase.date_range.end);
  }, [periodMonths]);

  const currentStepData = activeCase?.steps?.find((s) => s.step === currentStep);

  if (loading) return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>;

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <h2 style={{ marginBottom: 8 }}>RSI 交互学习</h2>
      <CaseSelector
        cases={casesData?.cases || []}
        activeCaseId={activeCaseId}
        mode={mode}
        onSelectCase={setActiveCaseId}
        onSearchStock={(code) => { setMode('free'); setActiveCaseId(null); setCurrentStep(1); const today = new Date(); const start = new Date(today); start.setMonth(start.getMonth() - periodMonths); loadKline(code, start.toISOString().slice(0, 10), today.toISOString().slice(0, 10)); }}
      />
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
        <span style={{ fontSize: 12, color: '#666' }}>📅 K 线周期：</span>
        <Radio.Group value={periodMonths} onChange={(e) => setPeriodMonths(e.target.value)} size="small" optionType="button" buttonStyle="solid" options={PERIOD_OPTIONS} />
      </div>
      {chartLoading ? <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div> : (
        <RSIInteractiveChart data={klineData} period={period} overbought={overbought} oversold={oversold} height={mode === 'free' ? 450 : 400} />
      )}
      {mode === 'preset' && activeCase?.steps && <StepNavigator steps={activeCase.steps} currentStep={currentStep} onStepChange={setCurrentStep} />}
      {/* Content */}
      <div style={{ marginTop: 16 }}>
        {currentStepData?.content ? <ReactMarkdown>{currentStepData.content}</ReactMarkdown> :
         mode === 'free' ? <div style={{ color: '#666', fontSize: 13 }}><p>🔍 <strong>自由探索模式</strong> — RSI 超买超卖线已在图中标注。调节下方参数观察 RSI 变化。</p></div> : null}
      </div>

      {/* Parameter Panel — horizontal below content */}
      <div style={{ marginTop: 16, padding: '12px 16px', background: '#fafafa', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, fontWeight: 'bold', whiteSpace: 'nowrap' }}>🎚️ 参数</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, border: currentStepData?.highlight_params === 'period' ? '2px solid #1677ff' : '2px solid transparent', borderRadius: 6, padding: '2px 6px' }}>
          <span style={{ fontSize: 12, color: '#666' }}>周期</span>
          <Slider style={{ width: 100, margin: 0 }} min={2} max={50} value={period} onChange={setPeriod} />
          <strong style={{ fontSize: 12, minWidth: 20 }}>{period}</strong>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: '#666' }}>超买</span>
          <Slider style={{ width: 100, margin: 0 }} min={60} max={90} value={overbought} onChange={setOverbought} />
          <strong style={{ fontSize: 12, minWidth: 20 }}>{overbought}</strong>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: '#666' }}>超卖</span>
          <Slider style={{ width: 100, margin: 0 }} min={10} max={40} value={oversold} onChange={setOversold} />
          <strong style={{ fontSize: 12, minWidth: 20 }}>{oversold}</strong>
        </div>
        <Button size="small" icon={<UndoOutlined />} onClick={() => { setPeriod(defaultParams.period); setOverbought(defaultParams.overbought); setOversold(defaultParams.oversold); }}>恢复默认</Button>
      </div>
      <Collapse style={{ marginTop: 24 }} size="small" items={[{
        key: 'glossary', label: '📖 术语说明', children: (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '12px 24px', fontSize: 13 }}>
            <div><strong>RSI（相对强弱指数）</strong><p style={{ margin: '4px 0 0', color: '#666' }}>通过比较一定周期内涨幅和跌幅的力度，衡量价格变动的速度和幅度。数值在 0-100 之间。</p></div>
            <div><strong>超买区（RSI &gt; 70）</strong><p style={{ margin: '4px 0 0', color: '#666' }}>价格短期涨幅过大，买方力量可能衰竭。RSI 从 70 上方回落是卖出信号。</p></div>
            <div><strong>超卖区（RSI &lt; 30）</strong><p style={{ margin: '4px 0 0', color: '#666' }}>价格短期跌幅过大，卖方力量可能衰竭。RSI 从 30 下方反弹是买入信号。</p></div>
            <div><strong>RSI 背离</strong><p style={{ margin: '4px 0 0', color: '#666' }}>价格方向与 RSI 方向不一致时形成背离，是趋势反转的预警信号。</p></div>
            <div><strong>计算周期</strong><p style={{ margin: '4px 0 0', color: '#666' }}>默认 14 日，周期越短 RSI 越敏感。5-7 适合短线，14-21 适合中长线。</p></div>
          </div>),
      }]} />
    </div>
  );
};

export default InteractiveRSIPage;
