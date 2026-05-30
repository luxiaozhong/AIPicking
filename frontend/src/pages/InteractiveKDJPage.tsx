import React, { useEffect, useState, useCallback } from 'react';
import { Spin, Radio, Collapse, Slider, Button } from 'antd';
import { UndoOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import educationService from '@/services/educationService';
import { stockService } from '@/services/stockService';
import type { MACDCase, MACDCasesData } from '@/services/educationService';
import type { KLineItem } from '@/types/stock';
import CaseSelector from '@/components/education/CaseSelector';
import KDJInteractiveChart from '@/components/education/KDJInteractiveChart';
import StepNavigator from '@/components/education/StepNavigator';

const PERIOD_OPTIONS = [
  { label: '1月', value: 1 }, { label: '3月', value: 3 }, { label: '6月', value: 6 },
  { label: '1年', value: 12 }, { label: '2年', value: 24 },
];

const InteractiveKDJPage: React.FC = () => {
  const [casesData, setCasesData] = useState<MACDCasesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<'preset' | 'free'>('preset');
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);
  const [klineData, setKlineData] = useState<KLineItem[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [period, setPeriod] = useState(9);
  const [currentStep, setCurrentStep] = useState(1);
  const [periodMonths, setPeriodMonths] = useState<number>(6);

  useEffect(() => {
    educationService.getKDJCases().then((data) => {
      setCasesData(data);
      if (data.cases.length > 0) setActiveCaseId(data.cases[0].id);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const activeCase = casesData?.cases.find((c) => c.id === activeCaseId);
  const defaultParams: any = casesData?.default_params || { period: 9 };

  const loadKline = useCallback(async (tsCode: string, start: string, end: string) => {
    setChartLoading(true);
    try {
      const s = start.replace(/-/g, ''); const e = end.replace(/-/g, '');
      const days = Math.ceil((new Date(end).getTime() - new Date(start).getTime()) / 86400000) + 30;
      const result = await stockService.getKLine(tsCode, Math.min(days, 365));
      const items = result.items || [];
      const filtered = items.filter((item) => item.trade_date >= s && item.trade_date <= e);
      setKlineData(filtered.length > 0 ? filtered : items);
    } finally { setChartLoading(false); }
  }, []);

  useEffect(() => {
    if (!activeCase) return;
    setPeriod(defaultParams.period); setCurrentStep(1); setMode('preset');
    const end = new Date(activeCase.date_range.end);
    const start = new Date(end); start.setMonth(start.getMonth() - periodMonths);
    loadKline(activeCase.stock.ts_code, start.toISOString().slice(0, 10), activeCase.date_range.end);
  }, [activeCaseId]);

  useEffect(() => {
    if (mode === 'free') { const t = new Date(); const s = new Date(t); s.setMonth(s.getMonth() - periodMonths); loadKline(activeCase?.stock.ts_code || '', s.toISOString().slice(0, 10), t.toISOString().slice(0, 10)); return; }
    if (!activeCase) return;
    const end = new Date(activeCase.date_range.end); const start = new Date(end); start.setMonth(start.getMonth() - periodMonths);
    loadKline(activeCase.stock.ts_code, start.toISOString().slice(0, 10), activeCase.date_range.end);
  }, [periodMonths]);

  const currentStepData = activeCase?.steps?.find((s) => s.step === currentStep);
  if (loading) return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>;

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <h2 style={{ marginBottom: 8 }}>KDJ 交互学习</h2>
      <CaseSelector cases={casesData?.cases || []} activeCaseId={activeCaseId} mode={mode}
        onSelectCase={setActiveCaseId}
        onSearchStock={(code) => { setMode('free'); setActiveCaseId(null); setCurrentStep(1); const t = new Date(); const s = new Date(t); s.setMonth(s.getMonth() - periodMonths); loadKline(code, s.toISOString().slice(0, 10), t.toISOString().slice(0, 10)); }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
        <span style={{ fontSize: 12, color: '#666' }}>📅 K 线周期：</span>
        <Radio.Group value={periodMonths} onChange={(e) => setPeriodMonths(e.target.value)} size="small" optionType="button" buttonStyle="solid" options={PERIOD_OPTIONS} />
      </div>
      {chartLoading ? <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div> :
        <KDJInteractiveChart data={klineData} period={period} height={mode === 'free' ? 450 : 400} />}
      {mode === 'preset' && activeCase?.steps && <StepNavigator steps={activeCase.steps} currentStep={currentStep} onStepChange={setCurrentStep} />}
      {/* Content */}
      <div style={{ marginTop: 16 }}>
        {currentStepData?.content ? <ReactMarkdown>{currentStepData.content}</ReactMarkdown> :
         mode === 'free' ? <div style={{ color: '#666', fontSize: 13 }}><p>🔍 <strong>自由探索模式</strong> — K/D/J 线及超买超卖区已在图中标注。调节下方参数观察 KDJ 变化。</p></div> : null}
      </div>

      {/* Parameter Panel — horizontal below content */}
      <div style={{ marginTop: 16, padding: '12px 16px', background: '#fafafa', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, fontWeight: 'bold', whiteSpace: 'nowrap' }}>🎚️ 参数</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, border: currentStepData?.highlight_params === 'period' ? '2px solid #1677ff' : '2px solid transparent', borderRadius: 6, padding: '2px 6px' }}>
          <span style={{ fontSize: 12, color: '#666' }}>周期</span>
          <Slider style={{ width: 100, margin: 0 }} min={2} max={30} value={period} onChange={setPeriod} />
          <strong style={{ fontSize: 12, minWidth: 20 }}>{period}</strong>
        </div>
        <Button size="small" icon={<UndoOutlined />} onClick={() => setPeriod(defaultParams.period)}>恢复默认</Button>
      </div>
      <Collapse style={{ marginTop: 24 }} size="small" items={[{
        key: 'glossary', label: '📖 术语说明', children: (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '12px 24px', fontSize: 13 }}>
            <div><strong>KDJ（随机指标）</strong><p style={{ margin: '4px 0 0', color: '#666' }}>通过比较收盘价在近期价格范围中的位置来衡量动量。由 K、D、J 三条线组成。</p></div>
            <div><strong>K 线（蓝）</strong><p style={{ margin: '4px 0 0', color: '#666' }}>快速线，对价格变化最敏感。K 线上穿 D 线为金叉买入信号。</p></div>
            <div><strong>D 线（橙）</strong><p style={{ margin: '4px 0 0', color: '#666' }}>慢速线，K 线的平滑版本。更稳定但信号稍滞后。</p></div>
            <div><strong>J 线（紫）</strong><p style={{ margin: '4px 0 0', color: '#666' }}>J = 3K - 2D，波动最大，常领先于 K/D 线。J 值可超过 100 或低于 0。</p></div>
            <div><strong>超买区（&gt;80）</strong><p style={{ margin: '4px 0 0', color: '#666' }}>K/D 值超过 80 为超买，价格短期过热。J 值超 100 为极端超买。</p></div>
            <div><strong>超卖区（&lt;20）</strong><p style={{ margin: '4px 0 0', color: '#666' }}>K/D 值低于 20 为超卖，价格短期过冷。J 值低于 0 为极端超卖。</p></div>
          </div>),
      }]} />
    </div>
  );
};

export default InteractiveKDJPage;
