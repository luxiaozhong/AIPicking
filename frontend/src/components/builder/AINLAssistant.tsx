import { useState, useEffect } from 'react';
import { Input, Button, Card, Tag, Space, message, Spin, Progress } from 'antd';
import {
  SendOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  BulbOutlined,
  DeleteOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { aiService, connectNLSSE } from '@/services/aiService';
import type { IndicatorItem, NLClassified, GenerationProgress } from '@/types/aiStrategy';

interface Props {
  onStrategyGenerated: (strategyId: number) => void;
  onPhaseChange?: (phase: NLPhase) => void;
}

type NLPhase = 'idle' | 'analyzing' | 'review' | 'generating' | 'completed' | 'failed';

export default function AINLAssistant({ onStrategyGenerated, onPhaseChange }: Props) {
  const [prompt, setPrompt] = useState('');
  const [phase, setPhase] = useState<NLPhase>('idle');

  useEffect(() => {
    onPhaseChange?.(phase);
  }, [phase, onPhaseChange]);

  const [taskId, setTaskId] = useState<string | null>(null);
  const [summary, setSummary] = useState('');
  const [indicators, setIndicators] = useState<IndicatorItem[]>([]);
  const [classified, setClassified] = useState<NLClassified | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<GenerationProgress | null>(null);
  const [strategyName, setStrategyName] = useState('');
  const [sseAbort, setSseAbort] = useState<(() => void) | null>(null);
  const [saving, setSaving] = useState(false);

  const cleanup = () => {
    if (sseAbort) {
      sseAbort();
      setSseAbort(null);
    }
  };

  const handleSubmit = async () => {
    const trimmed = prompt.trim();
    if (!trimmed || trimmed.length < 5) {
      message.warning('请至少输入5个字符描述你的策略思路');
      return;
    }

    cleanup();
    setPhase('analyzing');
    setError(null);
    setSummary('');
    setIndicators([]);
    setClassified(null);
    setProgress(null);

    try {
      const res = await aiService.analyzeNL({ prompt: trimmed });
      if (res.code === 0) {
        const id = res.data.task_id;
        setTaskId(id);

        const abort = connectNLSSE(
          id,
          (data) => {
            const status = data.status as string;

            if (status === 'review') {
              setSummary((data.summary as string) || '');
              setIndicators((data.indicators as IndicatorItem[]) || []);
              setClassified((data.classified as NLClassified) || { matched: [], new: [] });
              setPhase('review');
              setError(null);
              cleanup();
            } else if (status === 'generating') {
              setPhase('generating');
              if (data.progress) setProgress(data.progress as GenerationProgress);
            } else if (status === 'completed') {
              if (data.strategy_id) {
                setPhase('completed');
                setProgress(null);
                onStrategyGenerated(data.strategy_id as number);
                cleanup();
              }
            } else if (status === 'failed') {
              setPhase('failed');
              setError((data.error_message as string) || '分析失败');
              cleanup();
            }
          },
          () => cleanup(),
          () => { cleanup(); setPhase('failed'); setError('连接异常，请重试'); },
        );
        setSseAbort(() => abort);
      } else {
        setPhase('failed');
        setError(res.message || '提交失败');
      }
    } catch (e: unknown) {
      setPhase('failed');
      setError((e as Error)?.message || '提交分析失败');
    }
  };

  const handleConfirm = async () => {
    if (!taskId) return;
    setSaving(true);
    setPhase('generating');
    setProgress(null);

    try {
      const res = await aiService.confirmNLStrategy({
        task_id: taskId,
        strategy_name: strategyName.trim() || undefined,
        indicators: indicators as unknown as Record<string, unknown>[],
      });

      if (res.code === 0 && res.data.status === 'generating') {
        const abort = connectNLSSE(
          taskId,
          (data) => {
            const status = data.status as string;
            if (data.progress) setProgress(data.progress as GenerationProgress);

            if (status === 'completed' && data.strategy_id) {
              setPhase('completed');
              setProgress(null);
              onStrategyGenerated(data.strategy_id as number);
              cleanup();
            } else if (status === 'failed') {
              setPhase('failed');
              setError((data.error_message as string) || '生成失败');
              cleanup();
            }
          },
          () => cleanup(),
          () => { cleanup(); setPhase('failed'); setError('连接异常'); },
        );
        setSseAbort(() => abort);
      }
    } catch (e: unknown) {
      setSseAbort(null);
      const err = e as { response?: { data?: { message?: string } } };
      setPhase('failed');
      setError(err.response?.data?.message || '生成策略失败');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    cleanup();
    setPhase('idle');
    setTaskId(null);
    setSummary('');
    setIndicators([]);
    setClassified(null);
    setError(null);
    setProgress(null);
    setStrategyName('');
  };

  const handleEditRefValue = (index: number, value: string) => {
    const updated = [...indicators];
    const num = parseFloat(value);
    if (!isNaN(num)) {
      updated[index] = { ...updated[index], ref_value: num };
      setIndicators(updated);
    }
  };

  const handleRemoveIndicator = (index: number) => {
    setIndicators(indicators.filter((_, i) => i !== index));
  };

  // Analyzing state
  if (phase === 'analyzing') {
    return (
      <Card style={{ borderColor: '#1677ff' }}>
        <div style={{ textAlign: 'center', padding: '24px 0' }}>
          <Spin size="large" />
          <p style={{ marginTop: 12, color: '#888' }}>
            <ThunderboltOutlined /> DeepSeek 正在分析你的策略描述...
          </p>
        </div>
      </Card>
    );
  }

  // Generating state
  if (phase === 'generating') {
    return (
      <Card style={{ borderColor: '#1677ff' }}>
        <div style={{ textAlign: 'center', padding: '24px 0' }}>
          <Spin size="large" />
          <p style={{ marginTop: 12, color: '#888' }}>
            ⚙️ 正在生成策略代码...
          </p>
          {progress && (
            <Progress
              percent={Math.round((progress.completed / progress.total) * 100)}
              format={() => `${progress.completed}/${progress.total}`}
              style={{ maxWidth: 300, margin: '12px auto' }}
            />
          )}
        </div>
      </Card>
    );
  }

  // Review state - show factors
  if (phase === 'review') {
    return (
      <Card
        title={
          <Space>
            <BulbOutlined style={{ color: '#1677ff' }} />
            DeepSeek 识别结果
          </Space>
        }
        extra={
          <Button icon={<ReloadOutlined />} size="small" onClick={handleReset}>
            重新输入
          </Button>
        }
        style={{ borderColor: '#1677ff' }}
      >
        {/* Summary */}
        {summary && (
          <div style={{
            background: '#f0f5ff',
            padding: '8px 12px',
            borderRadius: 6,
            marginBottom: 16,
            fontSize: 13,
            color: '#1d39c4',
          }}>
            「{summary}」
          </div>
        )}

        {/* Factor list */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>
            识别到的因子（可编辑参考值）：
          </div>

          {indicators.map((ind, i) => {
            const isMatched = classified?.matched?.some(
              (m) => m.name === ind.name
            );
            return (
              <div
                key={i}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 10px',
                  background: isMatched ? '#f6ffed' : '#fffbe6',
                  borderRadius: 4,
                  marginBottom: 4,
                  border: `1px solid ${isMatched ? '#b7eb8f' : '#ffe58f'}`,
                  fontSize: 12,
                }}
              >
                <Tag color={isMatched ? 'green' : 'gold'} style={{ fontSize: 10, margin: 0 }}>
                  {isMatched ? '✓ 已有' : '🆕 生成'}
                </Tag>
                <span style={{ flex: 1, fontWeight: 500 }}>{ind.name}</span>
                <span style={{ color: '#888', fontSize: 11 }}>{ind.category}</span>
                <span>参考值：</span>
                <Input
                  size="small"
                  style={{ width: 70 }}
                  value={ind.ref_value !== undefined
                    ? String(ind.ref_value)
                    : ''}
                  onChange={(e) => handleEditRefValue(i, e.target.value)}
                />
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => handleRemoveIndicator(i)}
                  style={{ minWidth: 24 }}
                />
              </div>
            );
          })}
        </div>

        {/* Strategy name + actions */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Input
            placeholder="策略名称（可选）"
            value={strategyName}
            onChange={(e) => setStrategyName(e.target.value)}
            style={{ flex: 1 }}
            size="small"
          />
          <Button
            type="primary"
            icon={<CheckCircleOutlined />}
            onClick={handleConfirm}
            loading={saving}
            disabled={indicators.length === 0}
          >
            确认 → 生成策略
          </Button>
        </div>
      </Card>
    );
  }

  // Failed state
  if (phase === 'failed') {
    return (
      <Card style={{ borderColor: '#ff4d4f' }}>
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <p style={{ color: '#ff4d4f' }}>分析失败：{error || '未知错误'}</p>
          <Button onClick={handleReset}>重新输入</Button>
        </div>
      </Card>
    );
  }

  // Completed - brief summary
  if (phase === 'completed') {
    return (
      <Card style={{ borderColor: '#52c41a' }}>
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <CheckCircleOutlined style={{ fontSize: 24, color: '#52c41a' }} />
          <p style={{ color: '#52c41a', marginTop: 4 }}>策略已生成！</p>
          <Space>
            <Button onClick={handleReset}>创建新策略</Button>
          </Space>
        </div>
      </Card>
    );
  }

  // Idle state - input form
  return (
    <Card
      title={
        <Space>
          <BulbOutlined style={{ color: '#1677ff' }} />
          AI 助手 — 用自然语言描述你想要的股票特征
        </Space>
      }
    >
      <p style={{ marginBottom: 8, color: '#888', fontSize: 12 }}>
        描述技术指标或交易思路，如「底部放量反弹、MACD金叉、RSI低于30」
      </p>
      <Input.TextArea
        rows={3}
        placeholder="例如：寻找底部放量反弹的股票，MACD金叉，RSI低于30表示超卖..."
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onPressEnter={(e) => {
          if (e.metaKey || e.ctrlKey) handleSubmit();
        }}
        style={{ marginBottom: 8 }}
      />
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSubmit}
          loading={(phase as NLPhase) === 'analyzing'}
          disabled={prompt.trim().length < 5}
        >
          分析
        </Button>
      </div>
      <div style={{ marginTop: 8, fontSize: 11, color: '#bbb' }}>
        Cmd/Ctrl+Enter 快速提交
      </div>
    </Card>
  );
}
