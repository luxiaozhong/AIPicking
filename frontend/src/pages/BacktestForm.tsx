import { useState, useEffect } from 'react';
import { Card, Form, DatePicker, Checkbox, Button, message, Typography, Spin, Input, InputNumber, Radio, Space } from 'antd';
import dayjs from 'dayjs';
import { useParams, useNavigate } from 'react-router-dom';
import { useStrategyStore } from '@/stores/strategyStore';
import { useBacktestStore } from '@/stores/backtestStore';
import PageHeader from '@/components/shared/PageHeader';
import StockSearchLookup from '@/components/shared/StockSearchLookup';
import backtestService from '@/services/backtestService';
import tradeSimService from '@/services/tradeSimService';
import type { TradeSimCreate, BatchTradeSimCreate } from '@/types/tradeSim';

const { Text } = Typography;
const { Group: CheckboxGroup } = Checkbox;

function boardFilterToPrefixes(selected: string[]): string[] {
  const map: Record<string, string[]> = {
    '60': ['60'],
    '00': ['00'],
    '688/689': ['688', '689'],
    '300/301': ['300', '301'],
  };
  return selected.flatMap(k => map[k] || []);
}

const TRACK_DAY_OPTIONS = [
  { label: '3天', value: 3 },
  { label: '7天', value: 7 },
  { label: '15天', value: 15 },
];

export default function BacktestForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { currentStrategy, fetchStrategy, loading: strategyLoading, error: strategyError, clearError: clearStrategyError } = useStrategyStore();
  const { createBacktest, loading: backtestLoading, error: backtestError, clearError: clearBacktestError } = useBacktestStore();

  const [cutoffDate, setCutoffDate] = useState<dayjs.Dayjs | null>(null);
  const [trackDays, setTrackDays] = useState<number[]>([3, 7, 15]);
  const [stockCode, setStockCode] = useState('');
  const [mode, setMode] = useState<'single' | 'batch'>('single');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [batchName, setBatchName] = useState('');

  const [backtestMode, setBacktestMode] = useState<'simple' | 'trade-sim'>('simple');
  const [tradeSimMode, setTradeSimMode] = useState<'single' | 'batch'>('single');

  // 交易模拟字段
  const [totalAmount, setTotalAmount] = useState<number>(100000);
  const [topN, setTopN] = useState<number>(5);
  const [maxHoldDays, setMaxHoldDays] = useState<number>(60);
  const [stopFactors, setStopFactors] = useState<Array<{ id: string; enabled: boolean; params: Record<string, number> }>>([
    { id: 'stop_prev_low', enabled: true, params: { ref_days: 20 } },
    { id: 'stop_ma10_cross', enabled: false, params: { coefficient: 0.93, buffer_days: 2 } },
    { id: 'take_profit_pct', enabled: true, params: { profit_pct: 5.0 } },
  ]);

  const BOARD_OPTIONS = [
    { label: '上证', value: '60' },
    { label: '深圳', value: '00' },
    { label: '科创', value: '688/689' },
    { label: '创业', value: '300/301' },
  ];

  const [boardFilter, setBoardFilter] = useState<string[]>(['60', '00', '688/689', '300/301']);

  const [availableFactors, setAvailableFactors] = useState<Record<string, any>>({});

  useEffect(() => {
    tradeSimService.getStopFactors().then(setAvailableFactors).catch(() => {});
  }, []);

  useEffect(() => {
    if (id) fetchStrategy(parseInt(id));
  }, [id, fetchStrategy]);

  useEffect(() => {
    if (strategyError) {
      message.error(strategyError);
      clearStrategyError();
    }
  }, [strategyError, clearStrategyError]);

  useEffect(() => {
    if (backtestError) {
      message.error(backtestError);
      clearBacktestError();
    }
  }, [backtestError, clearBacktestError]);

  const handleSubmit = async () => {
    if (!currentStrategy) {
      message.error('策略不存在');
      return;
    }

    // 交易模拟模式
    if (backtestMode === 'trade-sim') {
      // 交易模拟批量模式
      if (tradeSimMode === 'batch') {
        if (!dateRange || !dateRange[0] || !dateRange[1]) {
          message.error('请选择起始和结束日期');
          return;
        }
        if (!totalAmount || totalAmount <= 0) {
          message.error('请输入投资总额');
          return;
        }
        const enabled = stopFactors.filter(sf => sf.enabled);
        if (enabled.length === 0) {
          message.error('请至少启用一个止损止盈条件');
          return;
        }

        try {
          const payload: BatchTradeSimCreate = {
            strategy_id: currentStrategy.id,
            start_date: dateRange[0].format('YYYYMMDD'),
            end_date: dateRange[1].format('YYYYMMDD'),
            name: batchName.trim() || undefined,
            total_amount: totalAmount,
            top_n: topN,
            max_hold_days: maxHoldDays,
            stop_factors: stopFactors,
          };
          const result = await tradeSimService.createBatch(payload);
          message.success('批量交易模拟已提交');
          navigate(`/backtests/trade-sim/batch/${result.id}`);
        } catch (err: any) {
          message.error(err.response?.data?.detail || '提交失败');
        }
        return;
      }

      // 交易模拟单日模式
      if (!cutoffDate) {
        message.error('请选择截止日');
        return;
      }
      if (!totalAmount || totalAmount <= 0) {
        message.error('请输入投资总额');
        return;
      }
      const enabled = stopFactors.filter(sf => sf.enabled);
      if (enabled.length === 0) {
        message.error('请至少启用一个止损止盈条件');
        return;
      }

      try {
        const payload: TradeSimCreate = {
          strategy_id: currentStrategy.id,
          cutoff_date: cutoffDate.format('YYYY-MM-DD'),
          total_amount: totalAmount,
          top_n: topN,
          max_hold_days: maxHoldDays,
          stop_factors: stopFactors,
        };
        const result = await tradeSimService.create(payload);
        message.success('交易模拟回测已提交');
        navigate(`/backtests/trade-sim/${result.id}`);
      } catch (err: any) {
        message.error(err.response?.data?.detail || '提交失败');
      }
      return;
    }

    if (mode === 'batch') {
      if (!dateRange || !dateRange[0] || !dateRange[1]) {
        message.error('请选择起始和结束日期');
        return;
      }
      if (trackDays.length === 0) {
        message.error('请至少选择一个追踪天数');
        return;
      }
      try {
        const payload: any = {
          strategy_id: currentStrategy.id,
          start_date: dateRange[0].format('YYYYMMDD'),
          end_date: dateRange[1].format('YYYYMMDD'),
          track_days: trackDays,
        };
        if (batchName.trim()) {
          payload.name = batchName.trim();
        }
        if (stockCode.trim()) {
          payload.config = { ts_code: stockCode.trim(), board_filter: boardFilterToPrefixes(boardFilter) };
        } else {
          payload.config = { board_filter: boardFilterToPrefixes(boardFilter) };
        }
        const result = await backtestService.createBatchBacktest(payload);
        message.success('批量回测任务已提交');
        navigate(`/backtests/batch/${result.id}`);
      } catch (err: any) {
        message.error(err.response?.data?.detail || '提交批量回测失败');
      }
      return;
    }

    if (!cutoffDate) {
      message.error('请选择截止日');
      return;
    }
    if (trackDays.length === 0) {
      message.error('请至少选择一个追踪天数');
      return;
    }

    try {
      const payload: any = {
        strategy_id: currentStrategy.id,
        cutoff_date: cutoffDate.format('YYYYMMDD'),
        track_days: trackDays,
      };
      if (stockCode.trim()) {
        payload.config = { ts_code: stockCode.trim(), board_filter: boardFilterToPrefixes(boardFilter) };
      } else {
        payload.config = { board_filter: boardFilterToPrefixes(boardFilter) };
      }
      const result = await createBacktest(payload);
      message.success('回测任务已提交');
      navigate(`/backtests/${result.id}`);
    } catch {
      // error handled in store
    }
  };

  if (strategyLoading) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  }

  if (!currentStrategy) {
    return <div>策略不存在</div>;
  }

  return (
    <>
      <PageHeader
        title={`运行回测 - ${currentStrategy.name}`}
        breadcrumb={[
          { title: '策略管理', path: '/strategies' },
          { title: currentStrategy.name, path: `/strategies/${currentStrategy.id}` },
          { title: '运行回测' },
        ]}
      />

      <Card style={{ maxWidth: 600 }}>
        <Form layout="vertical" onFinish={handleSubmit}>
          <Form.Item label="回测类型">
            <Radio.Group value={backtestMode} onChange={(e) => setBacktestMode(e.target.value)}>
              <Radio.Button value="simple">简单回测</Radio.Button>
              <Radio.Button value="trade-sim">交易模拟</Radio.Button>
            </Radio.Group>
          </Form.Item>

          {backtestMode === 'simple' ? (
            <>
              <Card size="small" style={{ marginBottom: 16, background: '#fafafa' }}>
                <Text strong>{currentStrategy.name}</Text>
                <br />
                <Text type="secondary">{currentStrategy.description || '无描述'}</Text>
              </Card>

              <Form.Item label="回测模式">
                <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)}>
                  <Radio.Button value="single">单日回测</Radio.Button>
                  <Radio.Button value="batch">批量回测</Radio.Button>
                </Radio.Group>
              </Form.Item>

              {mode === 'single' ? (
                <Form.Item label="截止日" required>
                  <DatePicker
                    value={cutoffDate}
                    onChange={setCutoffDate}
                    style={{ width: '100%' }}
                    placeholder="策略将用此日及之前的数据选股"
                    presets={[
                      { label: '昨天', value: () => dayjs().subtract(1, 'day') },
                      { label: '上周五', value: () => dayjs().subtract(1, 'week').endOf('week').subtract(1, 'day') },
                      { label: '本月1日', value: () => dayjs().startOf('month') },
                    ]}
                  />
                </Form.Item>
              ) : (
                <>
                  <Form.Item label="日期范围" required>
                    <DatePicker.RangePicker
                      value={dateRange as any}
                      onChange={(v) => setDateRange(v as [dayjs.Dayjs, dayjs.Dayjs])}
                      style={{ width: '100%' }}
                      placeholder={['起始日期', '结束日期']}
                    />
                  </Form.Item>
                  <Form.Item label="报告名称（可选）">
                    <Input
                      placeholder="如：4月回测"
                      value={batchName}
                      onChange={(e) => setBatchName(e.target.value)}
                      allowClear
                    />
                  </Form.Item>
                </>
              )}

              <Form.Item label="追踪天数" required>
                <CheckboxGroup
                  options={TRACK_DAY_OPTIONS}
                  value={trackDays}
                  onChange={(values) => setTrackDays(values as number[])}
                />
                <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
                  追踪推荐股票在截止日后的涨跌表现
                </Text>
              </Form.Item>

              <Form.Item label="目标股票（可选）">
                <StockSearchLookup
                  value={stockCode}
                  onChange={setStockCode}
                  placeholder="输入股票代码或名称搜索（留空则全市场选股）"
                />
              </Form.Item>

              <Form.Item label="基础板块" required>
                <CheckboxGroup
                  options={BOARD_OPTIONS}
                  value={boardFilter}
                  onChange={(values) => {
                    if (values.length > 0) {
                      setBoardFilter(values as string[]);
                    }
                  }}
                />
                <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
                  用于计算入选率的分母，至少选一个
                </Text>
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item label="回测模式">
                <Radio.Group value={tradeSimMode} onChange={(e) => setTradeSimMode(e.target.value)}>
                  <Radio.Button value="single">单日</Radio.Button>
                  <Radio.Button value="batch">批量</Radio.Button>
                </Radio.Group>
              </Form.Item>

              {tradeSimMode === 'single' ? (
                <Form.Item label="截止日" required>
                  <DatePicker
                    value={cutoffDate}
                    onChange={setCutoffDate}
                    style={{ width: '100%' }}
                    placeholder="策略将用此日及之前的数据选股"
                    presets={[
                      { label: '昨天', value: () => dayjs().subtract(1, 'day') },
                      { label: '上周五', value: () => dayjs().subtract(1, 'week').endOf('week').subtract(1, 'day') },
                      { label: '本月1日', value: () => dayjs().startOf('month') },
                    ]}
                  />
                </Form.Item>
              ) : (
                <>
                  <Form.Item label="日期范围" required>
                    <DatePicker.RangePicker
                      value={dateRange as any}
                      onChange={(v) => setDateRange(v as [dayjs.Dayjs, dayjs.Dayjs])}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                  <Form.Item label="报告名称（可选）">
                    <Input placeholder="如：5月交易模拟" value={batchName} onChange={(e) => setBatchName(e.target.value)} allowClear />
                  </Form.Item>
                </>
              )}

              <Form.Item label="投资总额（元）" required>
                <InputNumber
                  value={totalAmount}
                  onChange={(v) => setTotalAmount(v || 0)}
                  min={1}
                  style={{ width: '100%' }}
                  placeholder="如 100000"
                />
              </Form.Item>

              <Form.Item label="持仓股票数 N">
                <InputNumber
                  value={topN}
                  onChange={(v) => setTopN(v || 5)}
                  min={1}
                  max={20}
                  style={{ width: '100%' }}
                  placeholder="取分数最高的前N只"
                />
              </Form.Item>

              <Form.Item label="强制平仓天数">
                <InputNumber
                  value={maxHoldDays}
                  onChange={(v) => setMaxHoldDays(v || 60)}
                  min={1}
                  max={365}
                  style={{ width: '100%' }}
                  placeholder="超过此天数未触发则强制平仓"
                />
              </Form.Item>

              <Form.Item label="止损止盈条件" required>
                <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                  任一条件触发即平仓（OR 关系），按顺序检查
                </Text>
                {stopFactors.map((sf, idx) => {
                  const meta = availableFactors[sf.id];
                  const factorName = meta?.name || sf.id;
                  return (
                    <Card key={sf.id} size="small" style={{ marginBottom: 8 }}>
                      <Space>
                        <Checkbox
                          checked={sf.enabled}
                          onChange={(e) => {
                            const next = [...stopFactors];
                            next[idx] = { ...next[idx], enabled: e.target.checked };
                            setStopFactors(next);
                          }}
                        >
                          {factorName}
                        </Checkbox>
                      </Space>
                      {sf.enabled && meta && (
                        <div style={{ marginTop: 8, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                          {meta.params.map((param: any) => (
                            <div key={param.name}>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                {param.description}:
                              </Text>
                              <InputNumber
                                size="small"
                                value={sf.params[param.name] ?? param.default}
                                onChange={(v) => {
                                  const next = [...stopFactors];
                                  next[idx] = {
                                    ...next[idx],
                                    params: { ...next[idx].params, [param.name]: v ?? param.default },
                                  };
                                  setStopFactors(next);
                                }}
                                step={param.type === 'float' ? 0.01 : 1}
                                style={{ width: 100, marginLeft: 4 }}
                              />
                            </div>
                          ))}
                        </div>
                      )}
                    </Card>
                  );
                })}
              </Form.Item>

              <Form.Item label="基础板块" required>
                <CheckboxGroup
                  options={BOARD_OPTIONS}
                  value={boardFilter}
                  onChange={(values) => {
                    if (values.length > 0) {
                      setBoardFilter(values as string[]);
                    }
                  }}
                />
                <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
                  用于计算入选率的分母，至少选一个
                </Text>
              </Form.Item>
            </>
          )}

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={backtestLoading} size="large" style={{ marginRight: 8 }}>
              提交回测
            </Button>
            <Button onClick={() => navigate(-1)} size="large">
              取消
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </>
  );
}
