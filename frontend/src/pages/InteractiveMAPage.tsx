import React, { useEffect, useState, useCallback } from 'react';
import { Spin, Radio, Slider, Button } from 'antd';
import { UndoOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import educationService from '@/services/educationService';
import { stockService } from '@/services/stockService';
import type { KLineItem } from '@/types/stock';
import CaseSelector from '@/components/education/CaseSelector';
import MAInteractiveChart from '@/components/education/MAInteractiveChart';
import StepNavigator from '@/components/education/StepNavigator';

const P = [{ label: '1月', value: 1 }, { label: '3月', value: 3 }, { label: '6月', value: 6 }, { label: '1年', value: 12 }, { label: '2年', value: 24 }];

const InteractiveMAPage: React.FC = () => {
  const [data, setData] = useState<any>(null); const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<'preset'|'free'>('preset'); const [caseId, setCaseId] = useState<string|null>(null);
  const [kl, setKl] = useState<KLineItem[]>([]); const [cl, setCl] = useState(false);
  const [fast, setFast] = useState(5); const [slow, setSlow] = useState(20);
  const [step, setStep] = useState(1); const [pm, setPm] = useState(6);

  useEffect(() => { educationService.getMACases().then(d => { setData(d); if(d.cases.length>0)setCaseId(d.cases[0].id); setLoading(false); }).catch(()=>setLoading(false)); }, []);
  const ac = data?.cases?.find((c:any)=>c.id===caseId);
  const dp: any = data?.default_params || { fast: 5, slow: 20 };
  const load = useCallback(async (ts:string,st:string,en:string) => { setCl(true); try { const s=st.replace(/-/g,''),e=en.replace(/-/g,''); const r=await stockService.getKLine(ts,Math.min(365,Math.ceil((new Date(en).getTime()-new Date(st).getTime())/86400000)+30)); const i=r.items||[]; setKl(i.filter((x:KLineItem)=>x.trade_date>=s&&x.trade_date<=e)); } finally { setCl(false); } }, []);
  useEffect(() => { if(!ac)return; setFast(dp.fast); setSlow(dp.slow); setStep(1); setMode('preset'); const e=new Date(ac.date_range.end); const s=new Date(e); s.setMonth(s.getMonth()-pm); load(ac.stock.ts_code,s.toISOString().slice(0,10),ac.date_range.end); }, [caseId]);
  useEffect(() => { if(mode==='free'){const t=new Date();const s=new Date(t);s.setMonth(s.getMonth()-pm);load('',s.toISOString().slice(0,10),t.toISOString().slice(0,10));return} if(!ac)return; const e=new Date(ac.date_range.end);const s=new Date(e);s.setMonth(s.getMonth()-pm);load(ac.stock.ts_code,s.toISOString().slice(0,10),ac.date_range.end); }, [pm]);
  const cs = ac?.steps?.find((s:any)=>s.step===step);
  if(loading)return <div style={{textAlign:'center',padding:80}}><Spin size="large"/></div>;
  return <div style={{maxWidth:1100,margin:'0 auto'}}>
    <h2 style={{marginBottom:8}}>均线金叉死叉 交互学习</h2>
    <CaseSelector cases={data?.cases||[]} activeCaseId={caseId} mode={mode} onSelectCase={setCaseId} onSearchStock={code=>{setMode('free');setCaseId(null);setStep(1);const t=new Date();const s=new Date(t);s.setMonth(s.getMonth()-pm);load(code,s.toISOString().slice(0,10),t.toISOString().slice(0,10));}}/>
    <div style={{display:'flex',alignItems:'center',gap:8,padding:'4px 0'}}><span style={{fontSize:12,color:'#666'}}>📅 周期：</span><Radio.Group value={pm} onChange={e=>setPm(e.target.value)} size="small" optionType="button" buttonStyle="solid" options={P}/></div>
    {cl?<div style={{textAlign:'center',padding:60}}><Spin size="large"/></div>:<MAInteractiveChart data={kl} fast={fast} slow={slow} height={mode==='free'?450:400}/>}
    {mode==='preset'&&ac?.steps&&<StepNavigator steps={ac.steps} currentStep={step} onStepChange={setStep}/>}
    <div style={{marginTop:16}}>{cs?.content?<ReactMarkdown>{cs.content}</ReactMarkdown>:mode==='free'?<div style={{color:'#666',fontSize:13}}><p>🔍 <strong>自由探索模式</strong> — 金叉死叉信号已在图上标注。调节下方参数切换均线组合。</p></div>:null}</div>
    <div style={{marginTop:16,padding:'12px 16px',background:'#fafafa',borderRadius:8,display:'flex',alignItems:'center',gap:24,flexWrap:'wrap'}}>
      <span style={{fontSize:13,fontWeight:'bold'}}>🎚️ 参数</span>
      <div style={{display:'flex',alignItems:'center',gap:8}}><span style={{fontSize:12,color:'#666'}}>快线</span><Slider style={{width:100,margin:0}} min={2} max={50} value={fast} onChange={setFast}/><strong style={{fontSize:12,minWidth:20}}>{fast}</strong></div>
      <div style={{display:'flex',alignItems:'center',gap:8}}><span style={{fontSize:12,color:'#666'}}>慢线</span><Slider style={{width:100,margin:0}} min={5} max={120} value={slow} onChange={setSlow}/><strong style={{fontSize:12,minWidth:20}}>{slow}</strong></div>
      <Button size="small" icon={<UndoOutlined />} onClick={()=>{setFast(dp.fast);setSlow(dp.slow);}}>恢复默认</Button>
    </div>
  </div>;
};
export default InteractiveMAPage;
