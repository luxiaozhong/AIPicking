import { useEffect, useState, useCallback, useRef } from 'react';
import { Card, Button, Descriptions, Tag, Space, message, Popconfirm, Tabs, Table, Input, AutoComplete, Spin, Typography } from 'antd';
import {
  EditOutlined,
  DownloadOutlined,
  DeleteOutlined,
  BarChartOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import { useStrategyStore } from '@/stores/strategyStore';
import { useBacktestStore } from '@/stores/backtestStore';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import CodeBlock from '@/components/shared/CodeBlock';
import LoadingSkeleton from '@/components/shared/LoadingSkeleton';
import StockKLineModal from '@/components/shared/StockKLineModal';
import type { RecommendationItem } from '@/types/backtest';
import stockService from '@/services/stockService';
import type { StockItem } from '@/types/stock';

export default function StrategyDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const {
    currentStrategy,
    codeContent,
    loading,
    error,
    fetchStrategy,
    downloadStrategy,
    deleteStrategy,
    clearError,
  } = useStrategyStore();

  const { executeStrategy, loading: executeLoading } = useBacktestStore();
  const [stockCode, setStockCode] = useState('');
  const [stockOptions, setStockOptions] = useState<{ value: string; label: React.ReactNode }[]>([]);
  const [stockSearching, setStockSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);
  const [executeResult, setExecuteResult] = useState<{
    strategy_name: string;
    cutoff_date: string;
    total: number;
    recommendations: RecommendationItem[];
  } | null>(null);
  const [selectedStock, setSelectedStock] = useState<RecommendationItem | null>(null);

  useEffect(() => {
    if (id) fetchStrategy(parseInt(id));
  }, [id, fetchStrategy]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

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
          label: <span>{s.ts_code}  <Typography.Text type="secondary">{s.name}</Typography.Text></span>,
        })));
      } catch (err) {
        console.error('Stock search failed:', err);
        setStockOptions([]);
      } finally {
        setStockSearching(false);
      }
    }, 300);
  }, []);

  const handleExecute = async () => {
    if (!currentStrategy) return;
    const tsCode = stockCode.trim() || undefined;
    try {
      const result = await executeStrategy(currentStrategy.id, undefined, tsCode);
      setExecuteResult(result);
    } catch {
      // error handled in store
    }
  };

  const handleDownload = async () => {
    if (!currentStrategy) return;
    try {
      await downloadStrategy(currentStrategy.id, `${currentStrategy.name}.py`);
      message.success('下载成功');
    } catch {
      message.error('下载失败');
    }
  };

  const handleDelete = async () => {
    if (!currentStrategy) return;
    try {
      await deleteStrategy(currentStrategy.id);
      message.success('删除成功');
      navigate('/strategies');
    } catch {
      message.error('删除失败');
    }
  };

  if (loading) return <LoadingSkeleton type="detail" />;
  if (!currentStrategy) return <div>策略不存在</div>;

  const actions = (
    <>
      <Button icon={<EditOutlined />} onClick={() => navigate(`/strategies/${currentStrategy.id}/edit`)}>
        编辑
      </Button>
      <Button icon={<DownloadOutlined />} onClick={handleDownload}>
        下载
      </Button>
      <Button icon={<BarChartOutlined />} onClick={() => navigate(`/strategies/${currentStrategy.id}/backtest`)}>
        运行回测
      </Button>
      <AutoComplete
        value={stockCode}
        options={stockOptions}
        onSearch={handleStockSearch}
        onSelect={(value: string) => setStockCode(value)}
        onChange={(value: string) => setStockCode(value)}
        placeholder="股票代码（可选）"
        style={{ width: 200 }}
        allowClear
        notFoundContent={stockSearching ? <Spin size="small" /> : null}
      />
      <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleExecute} loading={executeLoading}>
        执行策略
      </Button>
      <Popconfirm title="确定删除？" onConfirm={handleDelete} okText="确定" cancelText="取消">
        <Button danger icon={<DeleteOutlined />}>删除</Button>
      </Popconfirm>
    </>
  );

  const tabItems = [
    {
      key: 'info',
      label: '基本信息',
      children: (
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="策略名称">{currentStrategy.name}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <StatusTag status={currentStrategy.status} />
          </Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>
            {currentStrategy.description || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="标签" span={2}>
            {currentStrategy.tags?.length
              ? currentStrategy.tags.map((tag) => (
                  <Tag key={tag}>{tag}</Tag>
                ))
              : '—'}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">{currentStrategy.created_at}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{currentStrategy.updated_at}</Descriptions.Item>
          <Descriptions.Item label="版本">{currentStrategy.version}</Descriptions.Item>
        </Descriptions>
      ),
    },
    {
      key: 'code',
      label: '策略代码',
      children: (
        <CodeBlock code={codeContent} maxHeight={500} onCopy={() => message.success('已复制')} />
      ),
    },
    {
      key: 'execute',
      label: '执行结果',
      children: (
        <>
          <Space style={{ marginBottom: 16 }}>
            <AutoComplete
              value={stockCode}
              options={stockOptions}
              onSearch={handleStockSearch}
              onSelect={(value: string) => setStockCode(value)}
              onChange={(value: string) => setStockCode(value)}
              placeholder="输入股票代码或名称搜索（留空则全市场扫描）"
              style={{ width: 280 }}
              allowClear
              notFoundContent={stockSearching ? <Spin size="small" /> : null}
            />
            <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleExecute} loading={executeLoading}>
              {executeResult ? '重新执行' : '执行策略'}
            </Button>
          </Space>
          {executeResult ? (
            <>
              <Descriptions column={3} size="small" style={{ marginBottom: 16 }}>
                <Descriptions.Item label="策略名称">{executeResult.strategy_name}</Descriptions.Item>
                <Descriptions.Item label="截止日">{executeResult.cutoff_date}</Descriptions.Item>
                <Descriptions.Item label="推荐数量">{executeResult.total} 只</Descriptions.Item>
              </Descriptions>
              <Table
                dataSource={executeResult.recommendations}
                columns={[
                  { title: '排名', width: 60, render: (_: unknown, __: unknown, i: number) => i + 1 },
                  {
                    title: '股票代码',
                    dataIndex: 'ts_code',
                    width: 110,
                    render: (code: string, record: RecommendationItem) => (
                      <a onClick={() => setSelectedStock(record)}>{code}</a>
                    ),
                  },
                  { title: '股票名称', dataIndex: 'name', width: 100 },
                  { title: '得分', dataIndex: 'score', width: 80, sorter: (a: RecommendationItem, b: RecommendationItem) => a.score - b.score },
                  { title: '信号说明', dataIndex: 'signal' },
                ]}
                rowKey="ts_code"
                size="small"
                pagination={false}
                scroll={{ x: 500 }}
                expandable={{
                  rowExpandable: (r: RecommendationItem) => !!r.breakdown,
                  expandedRowRender: (r: RecommendationItem) => {
                    const bd = r.breakdown;
                    const dt = r.details;
                    if (!bd) return null;
                    return (
                      <Descriptions column={5} size="small" bordered>
                        {bd.trend !== undefined && <Descriptions.Item label="趋势">{bd.trend}/25</Descriptions.Item>}
                        {bd.momentum !== undefined && <Descriptions.Item label="动量">{bd.momentum}/25</Descriptions.Item>}
                        {bd.volume !== undefined && <Descriptions.Item label="量能">{bd.volume}/20</Descriptions.Item>}
                        {bd.pattern !== undefined && <Descriptions.Item label="形态">{bd.pattern}/15</Descriptions.Item>}
                        {bd.flow !== undefined && <Descriptions.Item label="资金流">{bd.flow}/15</Descriptions.Item>}
                        {dt?.ma_status && <Descriptions.Item label="均线">{dt.ma_status}</Descriptions.Item>}
                        {dt?.macd_signal && <Descriptions.Item label="MACD">{dt.macd_signal}</Descriptions.Item>}
                        {dt?.rsi !== undefined && <Descriptions.Item label="RSI">{dt.rsi}</Descriptions.Item>}
                        {dt?.kdj_signal && <Descriptions.Item label="KDJ">{dt.kdj_signal}</Descriptions.Item>}
                        {dt?.vol_status && <Descriptions.Item label="量能">{dt.vol_status}</Descriptions.Item>}
                        {dt?.divergence && <Descriptions.Item label="背离">{dt.divergence}</Descriptions.Item>}
                        {dt?.td_signal && <Descriptions.Item label="九转">{dt.td_signal}</Descriptions.Item>}
                        {dt?.sr_status && <Descriptions.Item label="支撑阻力">{dt.sr_status}</Descriptions.Item>}
                        {dt?.best_sector && <Descriptions.Item label="资金板块">{dt.best_sector}</Descriptions.Item>}
                      </Descriptions>
                    );
                  },
                }}
              />
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
              点击上方按钮执行策略，获取当前市场推荐
            </div>
          )}
        </>
      ),
    },
    {
      key: 'backtests',
      label: '回测报告',
      children: (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <p style={{ color: '#999', marginBottom: 16 }}>暂无回测报告</p>
          <Button type="primary" icon={<BarChartOutlined />} onClick={() => navigate(`/strategies/${currentStrategy.id}/backtest`)}>
            运行回测
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="策略详情"
        breadcrumb={[
          { title: '策略管理', path: '/strategies' },
          { title: currentStrategy.name },
        ]}
        extra={actions}
      />
      <Tabs defaultActiveKey="info" items={tabItems} />
      <StockKLineModal
        ts_code={selectedStock?.ts_code ?? ''}
        name={selectedStock?.name}
        open={!!selectedStock}
        onClose={() => setSelectedStock(null)}
      />
    </>
  );
}
