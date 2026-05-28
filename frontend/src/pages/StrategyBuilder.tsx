import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Input, Button, Card, Select, message, Modal, Space, Empty, Collapse } from 'antd';
import {
  RobotOutlined,
  CodeOutlined,
  CaretUpOutlined,
  CaretDownOutlined,
  SafetyOutlined,
} from '@ant-design/icons';
import type { FactorMeta, FactorItem, FactorConfig } from '@/types/factor';
import { factorService } from '@/services/factorService';
import { strategyService } from '@/services/strategyService';
import { aiService } from '@/services/aiService';
import PageHeader from '@/components/shared/PageHeader';
import FactorCard from '@/components/builder/FactorCard';
import FactorLibrary from '@/components/builder/FactorLibrary';

export default function StrategyBuilder() {
  const navigate = useNavigate();

  const [strategyName, setStrategyName] = useState('');
  const [strategyDesc, setStrategyDesc] = useState('');
  const [factorConfig, setFactorConfig] = useState<FactorConfig>({
    buy_signals: { logic: 'AND', factors: [] },
    sell_signals: { logic: 'OR', factors: [] },
    risk_factors: [],
  });
  const [allFactors, setAllFactors] = useState<FactorMeta[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [searchText, setSearchText] = useState('');
  const [loading, setLoading] = useState(false);
  const [codePreviewVisible, setCodePreviewVisible] = useState(false);
  const [generatedCode, setGeneratedCode] = useState('');
  const [aiPanelOpen, setAiPanelOpen] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiLoading, setAiLoading] = useState(false);

  const loadFactors = useCallback(async () => {
    try {
      const res = await factorService.getFactors();
      if (res.code === 0) {
        setAllFactors(res.data.factors);
        setCategories(res.data.categories);
      }
    } catch {
      message.error('加载因子列表失败');
    }
  }, []);

  useEffect(() => {
    loadFactors();
  }, [loadFactors]);

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
        setGeneratedCode(res.data.generated_code || '');
        setCodePreviewVisible(true);
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
        if (factor_config) setFactorConfig(factor_config);
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

  return (
    <>
      <PageHeader
        title="可视化构建策略"
        breadcrumb={[
          { title: '策略管理', path: '/strategies' },
          { title: '可视化构建' },
        ]}
      />

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
        <Button
          icon={<CodeOutlined />}
          onClick={() => setCodePreviewVisible(true)}
          disabled={!generatedCode}
        >
          预览代码
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
        {/* Left: Factor Library */}
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
            searchText={searchText}
            onSearchChange={setSearchText}
            onAddFactor={addFactor}
          />
        </div>

        {/* Right: Strategy Canvas */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Buy Signals */}
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
            {factorConfig.buy_signals.factors.length === 0 ? (
              <Empty description="从左侧因子库点击添加买入因子" />
            ) : (
              factorConfig.buy_signals.factors.map((item, i) => {
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
              })
            )}
          </Card>

          {/* Sell Signals */}
          <Card
            title={
              <Space>
                <CaretDownOutlined style={{ color: '#ff4d4f' }} />
                卖出信号因子
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
            {factorConfig.sell_signals.factors.length === 0 ? (
              <Empty description="从左侧因子库点击添加卖出因子" />
            ) : (
              factorConfig.sell_signals.factors.map((item, i) => {
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
              })
            )}
          </Card>

          {/* Risk Factors */}
          <Card
            title={
              <Space>
                <SafetyOutlined style={{ color: '#faad14' }} />
                风控因子（始终生效）
              </Space>
            }
          >
            {factorConfig.risk_factors.length === 0 ? (
              <Empty description="从左侧因子库点击添加风控因子" />
            ) : (
              factorConfig.risk_factors.map((item, i) => {
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
              })
            )}
          </Card>
        </div>
      </div>

      {/* Code Preview Modal */}
      <Modal
        title="生成的策略代码"
        open={codePreviewVisible}
        onCancel={() => setCodePreviewVisible(false)}
        footer={
          <Button type="primary" onClick={() => { setCodePreviewVisible(false); navigate('/strategies'); }}>
            返回策略列表
          </Button>
        }
        width={800}
      >
        <pre
          style={{
            background: '#1e1e1e',
            color: '#d4d4d4',
            padding: 16,
            borderRadius: 8,
            maxHeight: 500,
            overflow: 'auto',
            whiteSpace: 'pre-wrap',
            fontSize: 13,
          }}
        >
          {generatedCode}
        </pre>
      </Modal>
    </>
  );
}
