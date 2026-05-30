import React, { useEffect, useState, useCallback } from 'react';
import { Spin, Radio, Collapse, Slider, Button } from 'antd';
import { UndoOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import educationService from '@/services/educationService';
import { stockService } from '@/services/stockService';
import type { MACDCase, MACDCasesData } from '@/services/educationService';
import type { KLineItem } from '@/types/stock';
import CaseSelector from '@/components/education/CaseSelector';
import BollingerInteractiveChart from '@/components/education/BollingerInteractiveChart';
import StepNavigator from '@/components/education/StepNavigator';

const PERIOD_OPTIONS = [{ label: '1月', value: 1 }, { label: '3月', value: 3 }, { label: '6月', value: 6 }, { label: '1年', value: 12 }, { label: '2年', value: 24 }];

const InteractiveBollingerPage: React.FC = () => {
  const [casesData, setCasesData] = useState<MACDCasesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<'preset' | 'free'>('preset');
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);
  const [klineData, setKlineData] = useState<KLineItem[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [period, setPeriod] = useState(20);
  const [multiplier, setMultiplier] = useState(2);
  const [currentStep, setCurrentStep] = useState(1);
  const [periodMonths, setPeriodMonths] = useState<number>(6);

  useEffect(() => {
    educationService.getBollingerCases().then(data => { setCasesData(data); if (data.cases.length > 0) setActiveCaseId(data.cases[0].id); setLoading(false); }).catch(() => setLoading(false));
  }, []);
  const activeCase = casesData?.cases.find(c => c.id === activeCaseId);
  const defaultParams: any = casesData?.default_params || { period: 20, multiplier: 2 };
  const loadKline = useCallback(async (tsCode: string, start: string, end: string) => {
    setChartLoading(true); try { const s = start.replace(/-/g, ''); const e = end.replace(/-/g, ''); const days = Math.ceil((new Date(end).getTime() - new Date(start).getTime()) / 86400000) + 30; const result = await stockService.getKLine(tsCode, Math.min(days, 365)); const items = result.items || []; const filtered = items.filter((item: KLineItem) => item.trade_date >= s && item.trade_date <= e); setKlineData(filtered.length > 0 ? filtered : items); } finally { setChartLoading(false); }
  }, []);
  useEffect(() => { if (!activeCase) return; setPeriod(defaultParams.period); setMultiplier(defaultParams.multiplier); setCurrentStep(1); setMode('preset'); const e = new Date(activeCase.date_range.end); const s = new Date(e); s.setMonth(s.getMonth() - periodMonths); loadKline(activeCase.stock.ts_code, s.toISOString().slice(0, 10), activeCase.date_range.end); }, [activeCaseId]);
  useEffect(() => {
    if (mode === 'free') { const t = new Date(); const s = new Date(t); s.setMonth(s.getMonth() - periodMonths); loadKline('', s.toISOString().slice(0, 10), t.toISOString().slice(0, 10)); return; }
    if (!activeCase) return; const e = new Date(activeCase.date_range.end); const s = new Date(e); s.setMonth(s.getMonth() - periodMonths); loadKline(activeCase.stock.ts_code, s.toISOString().slice(0, 10), activeCase.date_range.end);
  }, [periodMonths]);
  const currentStepData = activeCase?.steps?.find(s => s.step === currentStep);
  if (loading) return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>;
  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <h2 style={{ marginBottom: 8 }}>布林带 交互学习</h2>
      <CaseSelector cases={casesData?.cases || []} activeCaseId={activeCaseId} mode={mode} onSelectCase={setActiveCaseId}
        onSearchStock={(code) => { setMode('free'); setActiveCaseId(null); setCurrentStep(1); const t = new Date(); const s = new Date(t); s.setMonth(s.getMonth() - periodMonths); loadKline(code, s.toISOString().slice(0, 10), t.toISOString().slice(0, 10)); }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}><span style={{ fontSize: 12, color: '#666' }}>📅 周期：</span><Radio.Group value={periodMonths} onChange={e => setPeriodMonths(e.target.value)} size="small" optionType="button" buttonStyle="solid" options={PERIOD_OPTIONS} /></div>
      {chartLoading ? <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div> : <BollingerInteractiveChart data={klineData} period={period} multiplier={multiplier} height={mode === 'free' ? 450 : 400} />}
      {mode === 'preset' && activeCase?.steps && <StepNavigator steps={activeCase.steps} currentStep={currentStep} onStepChange={setCurrentStep} />}
      <div style={{ marginTop: 16 }}>{currentStepData?.content ? <ReactMarkdown>{currentStepData.content}</ReactMarkdown> : mode === 'free' ? <div style={{ color: '#666', fontSize: 13 }}><p>🔍 <strong>自由探索模式</strong> — 布林带已叠加在 K 线图上。调节下方参数观察带宽度变化。</p></div> : null}</div>
      <div style={{ marginTop: 16, padding: '12px 16px', background: '#fafafa', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, fontWeight: 'bold' }}>🎚️ 参数</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ fontSize: 12, color: '#666' }}>周期</span><Slider style={{ width: 100, margin: 0 }} min={5} max={50} value={period} onChange={setPeriod} /><strong style={{ fontSize: 12, minWidth: 20 }}>{period}</strong></div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ fontSize: 12, color: '#666' }}>标准差倍数</span><Slider style={{ width: 100, margin: 0 }} min={1} max={3} step={0.1} value={multiplier} onChange={setMultiplier} /><strong style={{ fontSize: 12, minWidth: 20 }}>{multiplier}</strong></div>
        <Button size="small" icon={<UndoOutlined />} onClick={() => { setPeriod(defaultParams.period); setMultiplier(defaultParams.multiplier); }}>恢复默认</Button>
      </div>
      <Collapse style={{ marginTop: 24 }} size="small" items={[{ key: 'glossary', label: '📖 术语说明', children: (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '12px 24px', fontSize: 13 }}>
          <div><strong>布林带（Bollinger Bands）</strong><p style={{ margin: '4px 0 0', color: '#666' }}>由 John Bollinger 于 1980 年代提出。由上轨、中轨、下轨三条线组成，基于统计学标准差原理。</p></div>
          <div><strong>中轨（橙）</strong><p style={{ margin: '4px 0 0', color: '#666' }}>N 日 SMA，价格趋势的中轴。股价在中轨上方为多头，下方为空头。</p></div>
          <div><strong>上轨 / 下轨（红/绿虚线）</strong><p style={{ margin: '4px 0 0', color: '#666' }}>中轨 ± N 倍标准差。带宽反映波动率：带宽扩大=波动加剧，收窄=波动降低。</p></div>
          <div><strong>触及上轨</strong><p style={{ margin: '4px 0 0', color: '#666' }}>价格触及上轨可能超买，但强趋势中可沿上轨运行。需结合趋势判断。</p></div>
          <div><strong>触及下轨</strong><p style={{ margin: '4px 0 0', color: '#666' }}>价格触及下轨可能超卖反弹。震荡市中上下轨之间的波动较规律。</p></div>
          <div><strong>带宽收窄</strong><p style={{ margin: '4px 0 0', color: '#666' }}>上下轨收窄（Squeeze）预示即将出现大波动，是重要的突破预警信号。</p></div>
        </div>),
      }]} />
    </div>
  );
};
export default InteractiveBollingerPage;
