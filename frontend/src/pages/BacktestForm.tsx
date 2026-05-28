import { useState, useEffect, useCallback, useRef } from 'react';
import { Card, Form, DatePicker, Checkbox, Button, message, Typography, Spin, Input, Radio, AutoComplete } from 'antd';
import dayjs from 'dayjs';
import { useParams, useNavigate } from 'react-router-dom';
import { useStrategyStore } from '@/stores/strategyStore';
import { useBacktestStore } from '@/stores/backtestStore';
import PageHeader from '@/components/shared/PageHeader';
import backtestService from '@/services/backtestService';
import stockService from '@/services/stockService';
import type { StockItem } from '@/types/stock';

const { Text } = Typography;
const { Group: CheckboxGroup } = Checkbox;

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
  const [stockOptions, setStockOptions] = useState<{ value: string; label: React.ReactNode }[]>([]);
  const [stockSearching, setStockSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);

  const handleStockSearch = useCallback((keyword: string) => {
    if (!keyword) {
      setStockOptions([]);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setStockSearching(true);
      try {
        const items: StockItem[] = await stockService.search(keyword);
        setStockOptions(items.map((s) => ({
          value: s.ts_code,
          label: <span>{s.ts_code}  <Text type="secondary">{s.name}</Text></span>,
        })));
      } catch {
        setStockOptions([]);
      } finally {
        setStockSearching(false);
      }
    }, 300);
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
          payload.config = { ts_code: stockCode.trim() };
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
        payload.config = { ts_code: stockCode.trim() };
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
            <AutoComplete
              value={stockCode}
              options={stockOptions}
              onSearch={handleStockSearch}
              onSelect={(value: string) => setStockCode(value)}
              onChange={(value: string) => setStockCode(value)}
              placeholder="输入股票代码或名称搜索（留空则全市场选股）"
              allowClear
              notFoundContent={stockSearching ? <Spin size="small" /> : null}
            />
          </Form.Item>

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
