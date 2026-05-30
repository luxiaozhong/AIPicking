import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Card, Form, Input, DatePicker, Select, Button, Typography, Alert, AutoComplete,
  Table, InputNumber, Space, Row, Col, Spin, Tag, message,
} from 'antd';
import {
  RobotOutlined, PlusOutlined, DeleteOutlined, CheckCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useAIStrategyStore } from '@/stores/aiStrategyStore';
import stockService from '@/services/stockService';
import TaskHistoryPanel from '@/components/TaskHistoryPanel';
import type { IndicatorItem } from '@/types/aiStrategy';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const CATEGORY_OPTIONS = [
  { label: '趋势类', value: '趋势类' },
  { label: '动量类', value: '动量类' },
  { label: '量能类', value: '量能类' },
  { label: '形态类', value: '形态类' },
  { label: '风控类', value: '风控类' },
];

const SIGNAL_OPTIONS = [
  { label: '买入', value: 'buy' },
  { label: '卖出', value: 'sell' },
  { label: '双向', value: 'both' },
];

const AIStrategyBuilder: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [form] = Form.useForm();
  const [stockCode, setStockCode] = useState('');
  const [stockOptions, setStockOptions] = useState<
    { value: string; label: React.ReactNode }[]
  >([]);
  const [stockSearching, setStockSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);

  const {
    phase, error, result, indicators, buyLogic,
    taskId, tasks, tasksLoading, generatedStrategyId, progress,
    submitAnalysis, updateIndicator, removeIndicator, addIndicator,
    setBuyLogic, confirmAndGenerate, fetchTasks, loadTask, clearAnalysis,
    cancelPolling, resumeInProgressTask,
  } = useAIStrategyStore();

  const [addingNew, setAddingNew] = useState(false);
  const [newIndicatorForm] = Form.useForm();

  useEffect(() => {
    fetchTasks();
    resumeInProgressTask();
    return () => {
      cancelPolling();
    };
  }, []);

  useEffect(() => {
    const tid = searchParams.get('task_id');
    if (tid) {
      loadTask(tid);
    }
  }, [searchParams]);

  useEffect(() => {
    if (generatedStrategyId) {
      navigate(`/strategies/${generatedStrategyId}`);
    }
  }, [generatedStrategyId]);

  const handleStockSearch = useCallback((keyword: string) => {
    if (!keyword) {
      setStockOptions([]);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setStockSearching(true);
      try {
        const items = await stockService.search(keyword);
        setStockOptions(
          items.map((s: { ts_code: string; name: string }) => ({
            value: s.ts_code,
            label: <span>{s.ts_code}  <Text type="secondary">{s.name}</Text></span>,
          }))
        );
      } catch {
        setStockOptions([]);
      } finally {
        setStockSearching(false);
      }
    }, 300);
  }, []);

  const handleSubmit = async (values: {
    date: dayjs.Dayjs;
    model: string;
    prompt?: string;
  }) => {
    if (!stockCode) {
      message.warning('请选择股票');
      return;
    }
    await submitAnalysis(
      stockCode,
      values.date.format('YYYY-MM-DD'),
      values.model,
      values.prompt || ''
    );
  };

  const handleConfirm = async () => {
    try {
      const strategyName = form.getFieldValue('strategy_name');
      const strategyId = await confirmAndGenerate(strategyName);
      message.success('策略生成成功！');
      navigate(`/strategies/${strategyId}`);
    } catch {
      message.error('生成策略失败');
    }
  };

  const handleAddIndicator = () => {
    const values = newIndicatorForm.getFieldsValue();
    const newInd: IndicatorItem = {
      name: values.name || '',
      category: values.category || '动量类',
      description: values.description || '',
      signal_type: values.signal_type || 'buy',
      reason: '用户手动添加',
      params: values.params || {},
      code_required: true,
      matched_factor_id: null,
    };
    addIndicator(newInd);
    newIndicatorForm.resetFields();
    setAddingNew(false);
  };

  const columns = [
    {
      title: '',
      width: 40,
      render: () => (
        <CheckCircleOutlined style={{ color: '#52c41a' }} />
      ),
    },
    {
      title: '指标名称',
      dataIndex: 'name',
      width: 140,
    },
    {
      title: '类别',
      dataIndex: 'category',
      width: 90,
      render: (v: string, _: IndicatorItem, i: number) => (
        <Select
          value={v}
          size="small"
          style={{ width: 80 }}
          options={CATEGORY_OPTIONS}
          onChange={(val: string) => updateIndicator(i, 'category', val)}
        />
      ),
    },
    {
      title: '信号',
      dataIndex: 'signal_type',
      width: 80,
      render: (v: string, _: IndicatorItem, i: number) => (
        <Select
          value={v}
          size="small"
          style={{ width: 70 }}
          options={SIGNAL_OPTIONS}
          onChange={(val: string) => updateIndicator(i, 'signal_type', val)}
        />
      ),
    },
    {
      title: '参数',
      dataIndex: 'params',
      width: 200,
      render: (params: Record<string, number>, _: IndicatorItem, i: number) => (
        <Space size={4} wrap>
          {Object.entries(params || {}).map(([k, v]) => (
            <InputNumber
              key={k}
              size="small"
              style={{ width: 85 }}
              addonBefore={k}
              value={v}
              onChange={(val: number | null) => {
                const newParams = { ...params, [k]: val ?? 0 };
                updateIndicator(i, 'params', newParams);
              }}
            />
          ))}
        </Space>
      ),
    },
    {
      title: '匹配',
      dataIndex: 'matched_factor_id',
      width: 100,
      render: (v: string | null) =>
        v ? (
          <Tag color="green">{v}</Tag>
        ) : (
          <Tag color="orange">需生成</Tag>
        ),
    },
    {
      title: '依据',
      dataIndex: 'reason',
      ellipsis: true,
      width: 200,
    },
    {
      title: '',
      width: 50,
      render: (_: unknown, __: unknown, i: number) => (
        <Button
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={() => removeIndicator(i)}
        />
      ),
    },
  ];

  // === Phase: idle / submitting / failed ===
  if (phase === 'idle' || phase === 'submitting' || phase === 'failed') {
    return (
      <Row gutter={24}>
        <Col span={16}>
          <Card title={<><RobotOutlined /> 参考个股选股策略</>}>
            {error && (
              <Alert
                message={error}
                type="error"
                style={{ marginBottom: 16 }}
                closable
              />
            )}
            <Form form={form} layout="vertical" onFinish={handleSubmit}>
              <Form.Item label="股票代码" required>
                <AutoComplete
                  value={stockCode}
                  options={stockOptions}
                  onSearch={handleStockSearch}
                  onSelect={(value: string) => setStockCode(value)}
                  onChange={(value: string) => setStockCode(value)}
                  placeholder="输入股票代码或名称搜索"
                  allowClear
                  notFoundContent={stockSearching ? <Spin size="small" /> : null}
                />
              </Form.Item>

              <Form.Item
                label="时间点（分析截止日期）"
                name="date"
                rules={[{ required: true, message: '请选择日期' }]}
              >
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>

              <Form.Item
                label="大模型"
                name="model"
                initialValue="deepseek-chat"
              >
                <Select
                  options={[
                    {
                      label: 'DeepSeek Chat（快速分析）',
                      value: 'deepseek-chat',
                    },
                    {
                      label: 'DeepSeek Reasoner（深度推理）',
                      value: 'deepseek-reasoner',
                    },
                  ]}
                />
              </Form.Item>

              <Form.Item label="分析提示（可选）" name="prompt">
                <TextArea
                  rows={3}
                  placeholder="例如：重点关注底部反转信号、偏好趋势突破类指标"
                />
              </Form.Item>

              <Button
                type="primary"
                htmlType="submit"
                loading={phase === 'submitting'}
                icon={<RobotOutlined />}
                size="large"
                block
              >
                提交 AI 分析
              </Button>
            </Form>
          </Card>
        </Col>

        <Col span={8}>
          <TaskHistoryPanel
            tasks={tasks}
            loading={tasksLoading}
            currentTaskId={taskId}
            onTaskClick={loadTask}
          />
        </Col>
      </Row>
    );
  }

  // === Phase: analyzing (DeepSeek 正在分析 K 线) ===
  if (phase === 'analyzing') {
    return (
      <Row gutter={24}>
        <Col span={16}>
          <Card>
            <div style={{ textAlign: 'center', padding: '80px 0' }}>
              <Spin size="large" />
              <Paragraph style={{ marginTop: 24, fontSize: 16 }}>
                <RobotOutlined style={{ marginRight: 8 }} />
                DeepSeek 正在分析 K 线数据，识别量化指标...
              </Paragraph>
              <Text type="secondary">最长可能需要 60 秒，请耐心等待</Text>
            </div>
          </Card>
        </Col>
        <Col span={8}>
          <TaskHistoryPanel
            tasks={tasks}
            loading={tasksLoading}
            currentTaskId={taskId}
            onTaskClick={loadTask}
          />
        </Col>
      </Row>
    );
  }

  // === Phase: generating (DeepSeek 正在生成策略代码) ===
  if (phase === 'generating') {
    return (
      <Row gutter={24}>
        <Col span={16}>
          <Card>
            <div style={{ textAlign: 'center', padding: '80px 0' }}>
              <Spin size="large" />
              <Paragraph style={{ marginTop: 24, fontSize: 16 }}>
                <RobotOutlined style={{ marginRight: 8 }} />
                DeepSeek 正在生成策略代码...
              </Paragraph>
              {progress && progress.total > 0 ? (
                <Text type="secondary">
                  正在生成第 {Math.min(progress.completed + 1, progress.total)}/
                  {progress.total} 个指标的计算代码...
                </Text>
              ) : (
                <Text type="secondary">
                  正在为每个指标生成计算代码，最长可能需要 2-3 分钟
                </Text>
              )}
            </div>
          </Card>
        </Col>
        <Col span={8}>
          <TaskHistoryPanel
            tasks={tasks}
            loading={tasksLoading}
            currentTaskId={taskId}
            onTaskClick={loadTask}
          />
        </Col>
      </Row>
    );
  }

  // === Phase: review (确认量化指标) ===
  return (
    <Row gutter={24}>
      <Col span={16}>
        <Card
          title="确认量化指标"
          extra={
            <Space>
              <Button onClick={clearAnalysis}>返回重新分析</Button>
              <Button
                type="primary"
                icon={<RobotOutlined />}
                onClick={handleConfirm}
              >
                确认并生成策略
              </Button>
            </Space>
          }
        >
          {result?.summary && (
            <Alert
              type="info"
              message="AI 分析总结"
              description={result.summary}
              style={{ marginBottom: 16 }}
            />
          )}

          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={12}>
              <Form.Item label="买入逻辑" style={{ marginBottom: 0 }}>
                <Select value={buyLogic} onChange={setBuyLogic} style={{ width: '100%' }}>
                  <Select.Option value="AND">AND（全部满足）</Select.Option>
                  <Select.Option value="OR">OR（任一满足）</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="策略名称" style={{ marginBottom: 0 }}>
                <Input
                  placeholder="自定义策略名称（可选）"
                  onChange={(e) =>
                    form.setFieldValue('strategy_name', e.target.value)
                  }
                />
              </Form.Item>
            </Col>
          </Row>

          <Table
            rowKey={(record, index) => `${record.name}-${index}`}
            columns={columns}
            dataSource={indicators}
            pagination={false}
            size="small"
            scroll={{ x: 950 }}
            footer={() =>
              addingNew ? (
                <Form
                  form={newIndicatorForm}
                  layout="inline"
                  onFinish={handleAddIndicator}
                >
                  <Form.Item name="name" rules={[{ required: true }]}>
                    <Input placeholder="指标名称" style={{ width: 120 }} />
                  </Form.Item>
                  <Form.Item name="category" initialValue="动量类">
                    <Select options={CATEGORY_OPTIONS} style={{ width: 90 }} />
                  </Form.Item>
                  <Form.Item name="signal_type" initialValue="buy">
                    <Select options={SIGNAL_OPTIONS} style={{ width: 70 }} />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" icon={<PlusOutlined />}>
                      添加
                    </Button>
                  </Form.Item>
                  <Form.Item>
                    <Button onClick={() => setAddingNew(false)}>取消</Button>
                  </Form.Item>
                </Form>
              ) : (
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={() => setAddingNew(true)}
                  block
                >
                  手动添加指标
                </Button>
              )
            }
          />
        </Card>
      </Col>

      <Col span={8}>
        <TaskHistoryPanel
          tasks={tasks}
          loading={tasksLoading}
          currentTaskId={taskId}
          onTaskClick={loadTask}
        />
      </Col>
    </Row>
  );
};

export default AIStrategyBuilder;
