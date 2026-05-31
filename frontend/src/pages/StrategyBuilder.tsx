import { useState, useEffect, useCallback } from 'react';
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
        title="可视化构建策略"
        breadcrumb={[
          { title: '策略管理', path: '/strategies' },
          { title: '可视化构建' },
        ]}
      />

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

      {builderMode === 'similarity' ? (
        /* === 相似度匹配模式 === */
        <div style={{ maxWidth: 800, margin: '0 auto' }}>
          <AINLAssistant onStrategyGenerated={handleNLGenerated} />
        </div>
      ) : (
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
            <Button type="primary" onClick={handleSave} loading={loading}>
              保存策略
            </Button>
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
      )}

    </>
  );
}
