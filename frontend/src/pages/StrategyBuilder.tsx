import { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Input, Button, Card, Select, message, Modal, Space, Tabs, Tag } from 'antd';
import {
  RobotOutlined,
  CaretUpOutlined,
  CaretDownOutlined,
  SafetyOutlined,
  ThunderboltOutlined,
  FilterOutlined,
  RiseOutlined,
} from '@ant-design/icons';
import type { FactorMeta, FactorItem, ConditionMeta, ConditionItem, FactorConfig } from '@/types/factor';
import { factorService } from '@/services/factorService';
import { strategyService } from '@/services/strategyService';
import { aiService } from '@/services/aiService';
import { useStrategyStore } from '@/stores/strategyStore';
import { isVisualEditable } from '@/types/strategy';
import PageHeader from '@/components/shared/PageHeader';
import FactorCard from '@/components/builder/FactorCard';
import ConditionCard from '@/components/builder/ConditionCard';
import FactorLibrary from '@/components/builder/FactorLibrary';
import AINLAssistant from '@/components/builder/AINLAssistant';

type BuilderMode = 'signal' | 'similarity';

function emptyFactorConfig(): FactorConfig {
  return {
    selection_conditions: { logic: 'AND', conditions: [] },
    scoring_modifiers: [],
    buy_signals: { logic: 'AND', factors: [] },
    sell_signals: { logic: 'OR', factors: [] },
    risk_factors: [],
  };
}

export default function StrategyBuilder() {

  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const editId = searchParams.get('id');
  const isEditMode = !!editId;

  const {
    currentStrategy,
    error: storeError,
    fetchStrategy,
    updateFactorConfig,
    createFromFactorConfig,
  } = useStrategyStore();

  const [builderMode, setBuilderMode] = useState<BuilderMode>('signal');
  const [strategyName, setStrategyName] = useState('');
  const [strategyDesc, setStrategyDesc] = useState('');
  const [factorConfig, setFactorConfig] = useState<FactorConfig>(emptyFactorConfig);
  const [allFactors, setAllFactors] = useState<FactorMeta[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [allConditions, setAllConditions] = useState<ConditionMeta[]>([]);
  const [conditionCategories, setConditionCategories] = useState<string[]>([]);
  const [searchText, setSearchText] = useState('');
  const [loading, setLoading] = useState(false);
  const [aiPanelOpen, setAiPanelOpen] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiLoading, setAiLoading] = useState(false);

  const [isDirty, setIsDirty] = useState(false);
  const [editLoaded, setEditLoaded] = useState(false);
  const editLoadedRef = useRef(false);

  // Reset dirty-flag guard when entering edit mode
  useEffect(() => {
    if (isEditMode) {
      editLoadedRef.current = false;
    }
  }, [isEditMode]);

  // Track changes after initial edit load
  useEffect(() => {
    if (editLoaded && editLoadedRef.current) {
      setIsDirty(true);
    }
  }, [factorConfig, strategyName, strategyDesc, editLoaded]);

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);

  // 加载因子 + 条件
  const loadData = useCallback(async () => {
    try {
      const [factorRes, condRes] = await Promise.all([
        factorService.getFactors(),
        factorService.getConditions(),
      ]);
      if (factorRes.code === 0) {
        setAllFactors(factorRes.data.factors);
        setCategories(factorRes.data.categories);
      }
      if (condRes.code === 0) {
        setAllConditions(condRes.data.conditions);
        setConditionCategories(condRes.data.categories);
      }
    } catch {
      message.error('加载因子/条件列表失败');
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 编辑模式：加载策略数据
  useEffect(() => {
    if (!editId) return;
    const id = parseInt(editId, 10);
    if (isNaN(id)) {
      message.warning('无效的策略 ID');
      navigate('/strategies');
      return;
    }
    fetchStrategy(id);
  }, [editId, fetchStrategy, navigate]);

  // 处理获取策略时的错误
  useEffect(() => {
    if (storeError && isEditMode) {
      message.error(storeError);
      navigate('/strategies');
    }
  }, [storeError, isEditMode, navigate]);

  // 编辑模式：currentStrategy 加载完成后填充表单
  useEffect(() => {
    if (!isEditMode || editLoaded || !currentStrategy) return;

    if (!isVisualEditable(currentStrategy.factor_config)) {
      message.warning('该策略不支持可视化编辑（AI 参考选股策略）');
      navigate('/strategies');
      return;
    }

    setStrategyName(currentStrategy.name);
    setStrategyDesc(currentStrategy.description || '');

    const fc = currentStrategy.factor_config as FactorConfig;
    if (fc) {
      setFactorConfig({
        ...emptyFactorConfig(),
        ...fc,
        selection_conditions: {
          logic: fc.selection_conditions?.logic || 'AND',
          conditions: fc.selection_conditions?.conditions || [],
        },
        buy_signals: {
          logic: fc.buy_signals?.logic || 'AND',
          factors: fc.buy_signals?.factors || [],
        },
        sell_signals: {
          logic: fc.sell_signals?.logic || 'OR',
          factors: fc.sell_signals?.factors || [],
        },
        scoring_modifiers: fc.scoring_modifiers || [],
        risk_factors: fc.risk_factors || [],
      });
    }
    setEditLoaded(true);
    // Defer ref to avoid marking dirty on initial load
    setTimeout(() => { editLoadedRef.current = true; }, 0);
  }, [isEditMode, currentStrategy, editLoaded, navigate]);

  // ── K 线因子 操作 ──
  const addFactor = (factor: FactorMeta, target: 'buy' | 'sell' | 'risk') => {
    const newItem: FactorItem = {
      factor_id: factor.id,
      params: factor.params.reduce(
        (acc, p) => {
          acc[p.name] = p.default;
          return acc;
        },
        {} as Record<string, number | boolean | string>,
      ),
    };

    setFactorConfig((prev) => {
      if (target === 'risk') {
        return { ...prev, risk_factors: [...prev.risk_factors, newItem] };
      }
      const key = target === 'buy' ? 'buy_signals' : 'sell_signals';
      return {
        ...prev,
        [key]: { ...prev[key], factors: [...prev[key].factors, newItem] },
      };
    });
    message.success(`已添加: ${factor.name}`);
  };

  const removeFactor = (target: 'buy' | 'sell' | 'risk', index: number) => {
    setFactorConfig((prev) => {
      if (target === 'risk') {
        const f = [...prev.risk_factors];
        f.splice(index, 1);
        return { ...prev, risk_factors: f };
      }
      const key = target === 'buy' ? 'buy_signals' : 'sell_signals';
      const f = [...prev[key].factors];
      f.splice(index, 1);
      return { ...prev, [key]: { ...prev[key], factors: f } };
    });
  };

  const updateFactorParams = (
    target: 'buy' | 'sell' | 'risk',
    index: number,
    paramName: string,
    value: number | boolean | string,
  ) => {
    setFactorConfig((prev) => {
      if (target === 'risk') {
        const f = [...prev.risk_factors];
        f[index] = { ...f[index], params: { ...f[index].params, [paramName]: value } };
        return { ...prev, risk_factors: f };
      }
      const key = target === 'buy' ? 'buy_signals' : 'sell_signals';
      const f = [...prev[key].factors];
      f[index] = { ...f[index], params: { ...f[index].params, [paramName]: value } };
      return { ...prev, [key]: { ...prev[key], factors: f } };
    });
  };

  // ── Tier 2 条件 操作 ──
  const addCondition = (condition: ConditionMeta, target: 'selection' | 'scoring') => {
    const newItem: ConditionItem = {
      condition_id: condition.id,
      params: condition.params.reduce(
        (acc, p) => {
          acc[p.name] = p.default;
          return acc;
        },
        {} as Record<string, number | boolean | string>,
      ),
    };

    setFactorConfig((prev) => {
      if (target === 'scoring') {
        return { ...prev, scoring_modifiers: [...prev.scoring_modifiers, newItem] };
      }
      return {
        ...prev,
        selection_conditions: {
          ...prev.selection_conditions,
          conditions: [...prev.selection_conditions.conditions, newItem],
        },
      };
    });
    message.success(`已添加: ${condition.name}`);
  };

  const removeCondition = (target: 'selection' | 'scoring', index: number) => {
    setFactorConfig((prev) => {
      if (target === 'scoring') {
        const f = [...prev.scoring_modifiers];
        f.splice(index, 1);
        return { ...prev, scoring_modifiers: f };
      }
      const f = [...prev.selection_conditions.conditions];
      f.splice(index, 1);
      return { ...prev, selection_conditions: { ...prev.selection_conditions, conditions: f } };
    });
  };

  const updateConditionParams = (
    target: 'selection' | 'scoring',
    index: number,
    paramName: string,
    value: number | boolean | string,
  ) => {
    setFactorConfig((prev) => {
      if (target === 'scoring') {
        const f = [...prev.scoring_modifiers];
        f[index] = { ...f[index], params: { ...f[index].params, [paramName]: value } };
        return { ...prev, scoring_modifiers: f };
      }
      const f = [...prev.selection_conditions.conditions];
      f[index] = { ...f[index], params: { ...f[index].params, [paramName]: value } };
      return { ...prev, selection_conditions: { ...prev.selection_conditions, conditions: f } };
    });
  };

  // ── 保存 ──
  const handleSave = async () => {
    if (!strategyName.trim()) {
      message.warning('请输入策略名称');
      return;
    }
    setLoading(true);
    try {
      const res = await strategyService.createStrategyWithFactors({
        name: strategyName,
        description: strategyDesc,
        factor_config: factorConfig,
      });
      if (res.code === 0 && res.data) {
        message.success('策略创建成功！');
      } else {
        message.error(res.message || '创建失败');
      }
    } catch (err: unknown) {
      message.error((err as Error)?.message || '创建失败');
    } finally {
      setLoading(false);
    }
  };

  // 编辑模式：更新策略
  const handleUpdate = async () => {
    if (!strategyName.trim()) {
      message.warning('请输入策略名称');
      return;
    }
    if (!editId) return;
    setLoading(true);
    try {
      await updateFactorConfig(parseInt(editId, 10), factorConfig as any, {
        name: strategyName,
        description: strategyDesc,
      });
      message.success('策略更新成功！');
      setIsDirty(false);
    } catch (err: unknown) {
      message.error((err as Error)?.message || '更新失败');
    } finally {
      setLoading(false);
    }
  };

  // 编辑模式：另存为新策略
  const [saveAsModalOpen, setSaveAsModalOpen] = useState(false);
  const [saveAsName, setSaveAsName] = useState('');

  const handleSaveAs = async () => {
    if (!saveAsName.trim()) {
      message.warning('请输入新策略名称');
      return;
    }
    setLoading(true);
    try {
      const newStrategy = await createFromFactorConfig(
        factorConfig as any,
        saveAsName,
        strategyDesc,
      );
      message.success('新策略创建成功！');
      setSaveAsModalOpen(false);
      if (newStrategy) {
        navigate(`/strategies/${newStrategy.id}`);
      }
    } catch (err: unknown) {
      message.error((err as Error)?.message || '另存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleAIGenerate = async () => {
    if (!aiPrompt.trim()) {
      message.warning('请输入策略描述');
      return;
    }
    setAiLoading(true);
    try {
      const res = await aiService.generateStrategy(aiPrompt);
      if (res.code === 0) {
        const { name, description, factor_config, explanation } = res.data;
        setStrategyName(name || 'AI生成的策略');
        setStrategyDesc(description || '');
        if (factor_config) {
          setFactorConfig({
            ...emptyFactorConfig(),
            ...factor_config,
          });
        }
        message.success(explanation || 'AI 已生成策略配置');
        setAiPanelOpen(false);
      } else {
        message.error(res.message || 'AI 生成失败');
      }
    } catch (err: unknown) {
      message.error((err as Error)?.message || 'AI 生成失败');
    } finally {
      setAiLoading(false);
    }
  };

  const getMeta = (factorId: string) => allFactors.find((f) => f.id === factorId);
  const getCondMeta = (condId: string) => allConditions.find((c) => c.id === condId);

  const handleNLGenerated = (strategyId: number) => {
    message.success(`策略生成成功！ID: ${strategyId}`);
  };

  const selConditions = factorConfig.selection_conditions.conditions;
  const scorers = factorConfig.scoring_modifiers;

  return (
    <>
      <PageHeader
        title={isEditMode ? `编辑策略：${strategyName || '加载中...'}` : '可视化构建策略'}
        breadcrumb={[
          { title: '策略管理', path: '/strategies' },
          ...(isEditMode
            ? [
                { title: strategyName || '策略详情', path: editId ? `/strategies/${editId}` : '/strategies' },
                { title: '编辑' },
              ]
            : [{ title: '可视化构建' }]),
        ]}
      />

      {!isEditMode && (
        <Tabs
          activeKey={builderMode}
          onChange={(key) => {
            if (builderMode === 'similarity' && key === 'signal') {
              Modal.confirm({
                title: '切换模式',
                content: '切换将丢失当前 AI 分析结果，是否继续？',
                onOk: () => setBuilderMode(key as BuilderMode),
              });
            } else {
              setBuilderMode(key as BuilderMode);
            }
          }}
          items={[
            {
              key: 'signal',
              label: (
                <span>
                  <CaretUpOutlined style={{ color: '#52c41a' }} /> 信号策略
                </span>
              ),
            },
            {
              key: 'similarity',
              label: (
                <span>
                  <ThunderboltOutlined style={{ color: '#1677ff' }} /> 相似度匹配{' '}
                  <Tag color="green" style={{ fontSize: 10, lineHeight: '16px', marginLeft: 2 }}>NEW</Tag>
                </span>
              ),
            },
          ]}
          style={{ marginBottom: 16 }}
        />
      )}

      {builderMode === 'similarity' && !isEditMode ? (
        /* === 相似度匹配模式 === */
        <div style={{ maxWidth: 800, margin: '0 auto' }}>
          <AINLAssistant onStrategyGenerated={handleNLGenerated} />
        </div>
      ) : null}

      {(builderMode === 'signal' || isEditMode) ? (
        /* === 信号策略模式 === */
        <>
          {/* Toolbar */}
          <div
            style={{
              marginBottom: 16,
              display: 'flex',
              gap: 12,
              alignItems: 'center',
              flexWrap: 'wrap',
            }}
          >
            <Input
              placeholder="策略名称"
              value={strategyName}
              onChange={(e) => setStrategyName(e.target.value)}
              style={{ width: 200 }}
            />
            <Input
              placeholder="策略描述"
              value={strategyDesc}
              onChange={(e) => setStrategyDesc(e.target.value)}
              style={{ width: 280 }}
            />
            <Button icon={<RobotOutlined />} onClick={() => setAiPanelOpen(!aiPanelOpen)}>
              AI 助手
            </Button>
            {isEditMode ? (
              <Space>
                <Button type="primary" onClick={handleUpdate} loading={loading}>
                  更新策略
                </Button>
                <Button onClick={() => {
                  setSaveAsName(strategyName ? `${strategyName} - 副本` : '');
                  setSaveAsModalOpen(true);
                }}>
                  另存为新策略
                </Button>
              </Space>
            ) : (
              <Button type="primary" onClick={handleSave} loading={loading}>
                保存策略
              </Button>
            )}
          </div>

          {/* AI Assistant Panel */}
          {aiPanelOpen && (
            <Card size="small" style={{ marginBottom: 16 }}>
              <p style={{ marginBottom: 8, color: '#666' }}>
                用自然语言描述你的策略想法，AI 会帮你配置因子：
              </p>
              <Input.TextArea
                rows={3}
                placeholder="例如：5日均线上穿20日均线时买入，跌破买入价5%止损"
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                style={{ marginBottom: 8 }}
              />
              <Button type="primary" onClick={handleAIGenerate} loading={aiLoading}>
                生成策略
              </Button>
              <span style={{ marginLeft: 12, color: '#999', fontSize: 12 }}>
                MVP 版本支持关键词识别（均线、MACD、RSI、止损、止盈等）
              </span>
            </Card>
          )}

          {/* Main layout: factor library + canvas */}
          <div style={{ display: 'flex', gap: 16, minHeight: 'calc(100vh - 280px)' }}>
            {/* Left: Factor & Condition Library */}
            <div
              style={{
                width: 300,
                minWidth: 280,
                background: '#fff',
                borderRadius: 8,
                border: '1px solid #f0f0f0',
                maxHeight: 'calc(100vh - 280px)',
                overflow: 'auto',
              }}
            >
              <FactorLibrary
                allFactors={allFactors}
                categories={categories}
                allConditions={allConditions}
                conditionCategories={conditionCategories}
                searchText={searchText}
                onSearchChange={setSearchText}
                onAddFactor={addFactor}
                onAddCondition={addCondition}
              />
            </div>

            {/* Right: Strategy Canvas */}
            <div style={{ flex: 1, minWidth: 0 }}>
              {/* ── 选股条件（Tier 2 pre_filter）── */}
              {selConditions.length === 0 ? (
                <div style={{
                  marginBottom: 16, padding: '8px 12px',
                  border: '1px dashed #d9d9d9', borderRadius: 8,
                  color: '#999', fontSize: 13,
                }}>
                  <Space><FilterOutlined style={{ color: '#1677ff' }} />选股条件 — 从左侧点击添加</Space>
                </div>
              ) : (
                <Card
                  title={
                    <Space>
                      <FilterOutlined style={{ color: '#1677ff' }} />
                      选股条件
                      <Select
                        size="small"
                        value={factorConfig.selection_conditions.logic}
                        style={{ width: 80 }}
                        onChange={(v) =>
                          setFactorConfig((prev) => ({
                            ...prev,
                            selection_conditions: {
                              ...prev.selection_conditions,
                              logic: v,
                            },
                          }))
                        }
                        options={[
                          { label: 'AND', value: 'AND' },
                          { label: 'OR', value: 'OR' },
                        ]}
                      />
                    </Space>
                  }
                  style={{ marginBottom: 16 }}
                >
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                    {selConditions.map((item, i) => {
                      const meta = getCondMeta(item.condition_id);
                      if (!meta) return null;
                      return (
                        <ConditionCard
                          key={`sel-${i}`}
                          item={item}
                          meta={meta}
                          onRemove={() => removeCondition('selection', i)}
                          onParamChange={(p, v) => updateConditionParams('selection', i, p, v)}
                        />
                      );
                    })}
                  </div>
                </Card>
              )}

              {/* ── 评分修正（Tier 2 score_modifier）── */}
              {scorers.length === 0 ? (
                <div style={{
                  marginBottom: 16, padding: '8px 12px',
                  border: '1px dashed #d9d9d9', borderRadius: 8,
                  color: '#999', fontSize: 13,
                }}>
                  <Space><RiseOutlined style={{ color: '#fa8c16' }} />评分修正 — 从左侧点击添加</Space>
                </div>
              ) : (
                <Card
                  title={
                    <Space>
                      <RiseOutlined style={{ color: '#fa8c16' }} />
                      评分修正
                    </Space>
                  }
                  style={{ marginBottom: 16 }}
                >
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                    {scorers.map((item, i) => {
                      const meta = getCondMeta(item.condition_id);
                      if (!meta) return null;
                      return (
                        <ConditionCard
                          key={`scr-${i}`}
                          item={item}
                          meta={meta}
                          onRemove={() => removeCondition('scoring', i)}
                          onParamChange={(p, v) => updateConditionParams('scoring', i, p, v)}
                        />
                      );
                    })}
                  </div>
                </Card>
              )}

              {/* Buy Signals */}
              {factorConfig.buy_signals.factors.length === 0 ? (
                <div style={{
                  marginBottom: 16, padding: '8px 12px',
                  border: '1px dashed #d9d9d9', borderRadius: 8,
                  color: '#999', fontSize: 13,
                }}>
                  <Space><CaretUpOutlined style={{ color: '#52c41a' }} />买入信号因子 — 从左侧点击添加</Space>
                </div>
              ) : (
                <Card
                  title={
                    <Space>
                      <CaretUpOutlined style={{ color: '#52c41a' }} />
                      买入信号因子
                      <Select
                        size="small"
                        value={factorConfig.buy_signals.logic}
                        style={{ width: 80 }}
                        onChange={(v) =>
                          setFactorConfig((prev) => ({
                            ...prev,
                            buy_signals: { ...prev.buy_signals, logic: v },
                          }))
                        }
                        options={[
                          { label: 'AND', value: 'AND' },
                          { label: 'OR', value: 'OR' },
                        ]}
                      />
                    </Space>
                  }
                  style={{ marginBottom: 16 }}
                >
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                    {factorConfig.buy_signals.factors.map((item, i) => {
                      const meta = getMeta(item.factor_id);
                      if (!meta) return null;
                      return (
                        <FactorCard
                          key={`buy-${i}`}
                          item={item}
                          meta={meta}
                          target="buy"
                          onRemove={() => removeFactor('buy', i)}
                          onParamChange={(p, v) => updateFactorParams('buy', i, p, v)}
                        />
                      );
                    })}
                  </div>
                </Card>
              )}

              {/* Sell Signals */}
              {factorConfig.sell_signals.factors.length === 0 ? (
                <div style={{
                  marginBottom: 16, padding: '8px 12px',
                  border: '1px dashed #d9d9d9', borderRadius: 8,
                  color: '#999', fontSize: 13,
                }}>
                  <Space><CaretDownOutlined style={{ color: '#ff4d4f' }} />卖出信号因子 — 从左侧点击添加</Space>
                </div>
              ) : (
                <Card
                  title={
                    <Space>
                      <CaretDownOutlined style={{ color: '#ff4d4f' }} />
                      卖出信号因子
                    </Space>
                  }
                  style={{ marginBottom: 16 }}
                >
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                    {factorConfig.sell_signals.factors.map((item, i) => {
                      const meta = getMeta(item.factor_id);
                      if (!meta) return null;
                      return (
                        <FactorCard
                          key={`sell-${i}`}
                          item={item}
                          meta={meta}
                          target="sell"
                          onRemove={() => removeFactor('sell', i)}
                          onParamChange={(p, v) => updateFactorParams('sell', i, p, v)}
                        />
                      );
                    })}
                  </div>
                </Card>
              )}

              {/* Risk Factors */}
              {factorConfig.risk_factors.length === 0 ? (
                <div style={{
                  marginBottom: 16, padding: '8px 12px',
                  border: '1px dashed #d9d9d9', borderRadius: 8,
                  color: '#999', fontSize: 13,
                }}>
                  <Space><SafetyOutlined style={{ color: '#faad14' }} />风控因子（始终生效）— 从左侧点击添加</Space>
                </div>
              ) : (
                <Card
                  title={
                    <Space>
                      <SafetyOutlined style={{ color: '#faad14' }} />
                      风控因子（始终生效）
                    </Space>
                  }
                >
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                    {factorConfig.risk_factors.map((item, i) => {
                      const meta = getMeta(item.factor_id);
                      if (!meta) return null;
                      return (
                        <FactorCard
                          key={`risk-${i}`}
                          item={item}
                          meta={meta}
                          target="risk"
                          onRemove={() => removeFactor('risk', i)}
                          onParamChange={(p, v) => updateFactorParams('risk', i, p, v)}
                        />
                      );
                    })}
                  </div>
                </Card>
              )}
            </div>
          </div>
        </>
      ) : null}

      <Modal
        title="另存为新策略"
        open={saveAsModalOpen}
        onOk={handleSaveAs}
        onCancel={() => setSaveAsModalOpen(false)}
        confirmLoading={loading}
        okText="创建"
        cancelText="取消"
      >
        <p style={{ marginBottom: 12, color: '#666' }}>将当前因子配置保存为一个新策略：</p>
        <Input
          placeholder="请输入新策略名称"
          value={saveAsName}
          onChange={(e) => setSaveAsName(e.target.value)}
        />
      </Modal>
    </>
  );
}
