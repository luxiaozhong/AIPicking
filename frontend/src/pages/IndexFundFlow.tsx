import React, { useEffect, useMemo, useCallback, useState } from 'react';
import {
  Card, Row, Col, Tabs, Select, DatePicker, Spin, Empty, Alert,
  Statistic, Typography, Space, Tag, Button, InputNumber, Modal,
} from 'antd';
import {
  DollarOutlined, RiseOutlined, FallOutlined, ReloadOutlined,
  BarChartOutlined, PieChartOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs, { type Dayjs } from 'dayjs';
import { useIndexFundFlowStore } from '@/stores/indexFundFlowStore';
import { indexFundFlowService, type IndexHistoryItem, type RankingTrendData } from '@/services/indexFundFlowService';
import ConstituentTreemap from '@/components/index-fund-flow/ConstituentTreemap';
import BarChartRace from '@/components/index-fund-flow/BarChartRace';
import MultiStockTrendChart from '@/components/index-fund-flow/MultiStockTrendChart';
import IndustrySummaryBar from '@/components/index-fund-flow/IndustrySummaryBar';
import Top10Ranking from '@/components/index-fund-flow/Top10Ranking';
import RankingTrend from '@/components/index-fund-flow/RankingTrend';
import StockFundFlowDetail from '@/components/shared/StockFundFlowDetail';
import StockSearchLookup from '@/components/shared/StockSearchLookup';

const { Title, Text } = Typography;

const RED_COLOR = '#cf1322';
const GREEN_COLOR = '#3f8600';

function fmtYi(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 10000) return (v / 10000).toFixed(2) + ' 万亿';
  if (abs >= 1) return v.toFixed(2) + ' 亿';
  return (v * 10000).toFixed(0) + ' 万';
}

const IndexFundFlow: React.FC = () => {
  const store = useIndexFundFlowStore();
  const [selectedStock, setSelectedStock] = useState<string | null>(null);
  const [stockSearchValue, setStockSearchValue] = useState('');
  const [kpiHistory, setKpiHistory] = useState<{ title: string; field: string; items: IndexHistoryItem[] } | null>(null);
  const [kpiLoading, setKpiLoading] = useState(false);
  const [rankingTrend, setRankingTrend] = useState<RankingTrendData | null>(null);
  const [rankingTrendLoading, setRankingTrendLoading] = useState(false);

  const fetchRankingTrend = useCallback(async () => {
    if (!store.selectedIndexCode) return;
    setRankingTrendLoading(true);
    try {
      const data = await indexFundFlowService.getRankingTrend(store.selectedIndexCode, 15);
      setRankingTrend(data);
    } catch {
      setRankingTrend(null);
    } finally {
      setRankingTrendLoading(false);
    }
  }, [store.selectedIndexCode]);

  const handleKpiClick = useCallback(async (title: string, field: string) => {
    if (!store.selectedIndexCode) return;
    setKpiLoading(true);
    try {
      const data = await indexFundFlowService.getIndexHistory(store.selectedIndexCode, 30);
      setKpiHistory({ title, field, items: data.items });
    } catch {
      setKpiHistory(null);
    } finally {
      setKpiLoading(false);
    }
  }, [store.selectedIndexCode]);

  // Fetch indices on mount
  useEffect(() => {
    store.fetchIndices();
    return () => {
      store.stopPolling();
    };
  }, []);

  const handleIndexChange = useCallback((code: string) => {
    store.setSelectedIndexCode(code);
  }, [store]);

  const handleDateChange = useCallback((date: Dayjs | null) => {
    store.setSelectedDate(date ? date.format('YYYY-MM-DD') : undefined);
  }, [store]);

  const handleRefreshAll = useCallback(() => {
    store.fetchAllData(store.selectedDate);
  }, [store]);

  const handleStockClick = useCallback((tsCode: string) => {
    setSelectedStock(tsCode);
  }, []);

  const handleTogglePolling = useCallback(() => {
    if (store.isPolling) {
      store.stopPolling();
    } else {
      store.startPolling();
    }
  }, [store.isPolling, store.startPolling, store.stopPolling]);

  // Derived KPIs
  const kpis = useMemo(() => {
    const items = store.constituentFlow;
    if (!items || items.length === 0) return null;
    const totalMainNet = items.reduce((s, i) => s + i.main_net_flow, 0);
    const totalMainNet5d = items.reduce((s, i) => s + (i.main_net_flow_5d || 0), 0);
    const totalJumbo = items.reduce((s, i) => s + i.jumbo_net_flow, 0);
    const totalBlock = items.reduce((s, i) => s + i.block_net_flow, 0);
    const positiveCount = items.filter((i) => i.main_net_flow > 0).length;
    const positivePct = items.length > 0 ? (positiveCount / items.length * 100) : 0;
    const positiveCount5d = items.filter((i) => (i.main_net_flow_5d || 0) > 0).length;
    const positivePct5d = items.length > 0 ? (positiveCount5d / items.length * 100) : 0;
    return { totalMainNet, totalMainNet5d, totalJumbo, totalBlock, positivePct, positiveCount, positivePct5d, total: items.length };
  }, [store.constituentFlow]);

  const selectedIndexName = useMemo(() => {
    const idx = store.indices.find((i) => i.index_code === store.selectedIndexCode);
    return idx ? `${idx.full_name || idx.index_name} (${idx.index_code})` : store.selectedIndexCode || '';
  }, [store.indices, store.selectedIndexCode]);

  const isLoading = Object.values(store.loading).some(Boolean) && store.constituentFlow.length === 0;

  const tabItems = [
    {
      key: 'race',
      label: (
        <span>
          <BarChartOutlined /> 排名竞速
        </span>
      ),
      children: (
        <div>
          <Card
            title="主力净流入 排名竞速"
            size="small"
            extra={
              <Space>
                <Text type="secondary">
                  快照数: {store.snapshots?.snapshots?.length || 0}
                </Text>
                {store.lastUpdated && (
                  <Text type="secondary">最后更新: {store.lastUpdated}</Text>
                )}
              </Space>
            }
            styles={{ body: { padding: 8 } }}
          >
            <BarChartRace
              snapshots={store.snapshots}
              loading={store.loading.snapshots}
              isPolling={store.isPolling}
              onTogglePolling={handleTogglePolling}
              onStockClick={handleStockClick}
            />
          </Card>
        </div>
      ),
    },
    {
      key: 'trend',
      label: (
        <span>
          <RiseOutlined /> 趋势追踪
        </span>
      ),
      children: (
        <div>
          <Card
            title="5日累计排名变化 — 潜力股追踪"
            size="small"
            extra={
              <Space>
                <Text type="secondary">
                  回溯 {rankingTrend?.items?.[0]?.dates?.length || 0} 个交易日
                </Text>
              </Space>
            }
            styles={{ body: { padding: 8 } }}
          >
            <RankingTrend
              data={rankingTrend}
              loading={rankingTrendLoading}
              onStockClick={handleStockClick}
            />
          </Card>
        </div>
      ),
    },
    {
      key: 'dashboard',
      label: (
        <span>
          <PieChartOutlined /> 资金流看板
        </span>
      ),
      children: (
        <div>
          {/* Row 1: Treemap */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={24}>
              <Card title="成分股资金流热力图" size="small" styles={{ body: { padding: 8 } }}>
                <ConstituentTreemap
                  data={store.treemapData}
                  loading={store.loading.treemap}
                  onStockClick={handleStockClick}
                />
              </Card>
            </Col>
          </Row>

          {/* Row 2: Top 10 Ranking */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={24}>
              <Card title="主力资金排名" size="small" styles={{ body: { padding: 8 } }}>
                <Top10Ranking
                  data={store.constituentFlow}
                  loading={store.loading.constituentFlow}
                  onStockClick={handleStockClick}
                />
              </Card>
            </Col>
          </Row>

          {/* Row 2: Multi-Stock Trend */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={24}>
              <Card
                title="主力资金流趋势对比"
                size="small"
                extra={
                  <Space>
                    <Text type="secondary">Top</Text>
                    <InputNumber
                      min={1}
                      max={20}
                      size="small"
                      value={store.trendTopN}
                      onChange={(v) => v && store.setTrendTopN(v)}
                      style={{ width: 60 }}
                    />
                  </Space>
                }
                styles={{ body: { padding: 8 } }}
              >
                <MultiStockTrendChart
                  data={store.multiStockTrend}
                  loading={store.loading.multiStockTrend}
                />
              </Card>
            </Col>
          </Row>

          {/* Row 3: Industry Summary */}
          <Row gutter={16}>
            <Col span={24}>
              <Card title="行业资金流汇总" size="small" styles={{ body: { padding: 8 } }}>
                <IndustrySummaryBar
                  data={store.industrySummary}
                  loading={store.loading.industrySummary}
                />
              </Card>
            </Col>
          </Row>
        </div>
      ),
    },
  ];

  return (
    <div>
      {/* Header Row */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <Space align="center">
          <Title level={4} style={{ margin: 0 }}>指数资金流</Title>
          <Select
            showSearch
            placeholder="选择指数"
            value={store.selectedIndexCode}
            onChange={handleIndexChange}
            loading={store.loading.indices}
            style={{ minWidth: 220 }}
            filterOption={(input, option) =>
              (option?.label as string || '').toLowerCase().includes(input.toLowerCase())
            }
            options={store.indices.map((idx) => ({
              label: `${idx.full_name || idx.index_name} (${idx.index_code})`,
              value: idx.index_code,
            }))}
          />
          <DatePicker
            value={store.selectedDate ? dayjs(store.selectedDate) : null}
            onChange={handleDateChange}
            allowClear
            placeholder="选择日期"
            style={{ width: 140 }}
          />
          <StockSearchLookup
            value={stockSearchValue}
            onChange={setStockSearchValue}
            onSelect={(code) => {
              setSelectedStock(code);
              setStockSearchValue('');
            }}
            placeholder="搜索个股资金流"
            style={{ width: 200 }}
          />
          {selectedStock && (
            <Tag closable onClose={() => setSelectedStock(null)} color="blue">
              已选: {selectedStock}
            </Tag>
          )}
        </Space>
        <Space>
          {store.lastUpdated && (
            <Text type="secondary">更新: {store.lastUpdated}</Text>
          )}
          {store.isPolling && <Tag color="processing">🔄 轮询中</Tag>}
          <Button
            icon={<ReloadOutlined />}
            onClick={handleRefreshAll}
            loading={isLoading}
          >
            刷新
          </Button>
        </Space>
      </div>

      {/* Error */}
      {store.error && (
        <Alert
          message={store.error}
          type="error"
          closable
          onClose={store.clearError}
          style={{ marginBottom: 16 }}
        />
      )}

      {/* KPI Cards */}
      {kpis && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}>
            <Card size="small" hoverable onClick={() => handleKpiClick('主力净流入', 'main_net_yi')}>
              <Statistic
                title="主力净流入"
                value={kpis.totalMainNet / 1e8}
                precision={2}
                suffix="亿"
                prefix={kpis.totalMainNet >= 0 ? <RiseOutlined /> : <FallOutlined />}
                valueStyle={{ color: kpis.totalMainNet >= 0 ? RED_COLOR : GREEN_COLOR, fontSize: 18 }}
              />
              <div style={{ marginTop: 4, fontSize: 12, color: '#888' }}>
                5日累计: <Text style={{ color: kpis.totalMainNet5d >= 0 ? RED_COLOR : GREEN_COLOR, fontWeight: 500 }}>{(kpis.totalMainNet5d / 1e8).toFixed(2)}亿</Text>
              </div>
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small" hoverable onClick={() => handleKpiClick('超大单净流入', 'jumbo_net_yi')}>
              <Statistic
                title="超大单净流入"
                value={kpis.totalJumbo / 1e8}
                precision={2}
                suffix="亿"
                valueStyle={{ color: kpis.totalJumbo >= 0 ? RED_COLOR : GREEN_COLOR, fontSize: 18 }}
              />
              <div style={{ marginTop: 4, fontSize: 12, color: '#888' }}>
                主力占比: <Text style={{ fontWeight: 500 }}>{kpis.totalMainNet !== 0 ? (kpis.totalJumbo / kpis.totalMainNet * 100).toFixed(0) : '-'}%</Text>
              </div>
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small" hoverable onClick={() => handleKpiClick('大单净流入', 'block_net_yi')}>
              <Statistic
                title="大单净流入"
                value={kpis.totalBlock / 1e8}
                precision={2}
                suffix="亿"
                valueStyle={{ color: kpis.totalBlock >= 0 ? RED_COLOR : GREEN_COLOR, fontSize: 18 }}
              />
              <div style={{ marginTop: 4, fontSize: 12, color: '#888' }}>
                主力占比: <Text style={{ fontWeight: 500 }}>{kpis.totalMainNet !== 0 ? (kpis.totalBlock / kpis.totalMainNet * 100).toFixed(0) : '-'}%</Text>
              </div>
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small" hoverable onClick={() => handleKpiClick('资金广度', 'positive_pct')}>
              <Statistic
                title="资金广度"
                value={kpis.positivePct}
                precision={1}
                suffix={`% (${kpis.positiveCount}/${kpis.total})`}
                valueStyle={{ fontSize: 18 }}
              />
              <div style={{ marginTop: 4, fontSize: 12, color: '#888' }}>
                5日前: <Text style={{ fontWeight: 500 }}>{kpis.positivePct5d.toFixed(1)}%</Text>
              </div>
            </Card>
          </Col>
        </Row>
      )}

      {/* Main Content */}
      {!store.selectedIndexCode && store.indices.length === 0 && !store.loading.indices ? (
        <Empty description="暂无可用指数，请先使用 sync_index_constituents.py 导入指数数据" />
      ) : (
        <Tabs
          defaultActiveKey="race"
          items={tabItems}
          onChange={(key) => {
            if (key === 'race') {
              store.fetchSnapshots(store.selectedDate);
            } else {
              store.stopPolling();
            }
            if (key === 'trend') {
              fetchRankingTrend();
            }
          }}
        />
      )}

      {/* 个股资金流详情弹层 */}
      <StockFundFlowDetail
        tsCode={selectedStock}
        onClose={() => setSelectedStock(null)}
      />

      {/* KPI 历史趋势弹窗 */}
      <Modal
        title={<Text strong>近30日 — {kpiHistory?.title}</Text>}
        open={!!kpiHistory}
        onCancel={() => setKpiHistory(null)}
        footer={null}
        width={700}
        destroyOnClose
      >
        {kpiHistory && kpiHistory.items.length > 0 && (
          <ReactECharts
            option={{
              tooltip: { trigger: 'axis' as const },
              grid: { left: 60, right: 20, top: 10, bottom: 30 },
              xAxis: {
                type: 'category' as const,
                data: kpiHistory.items.map((d) => d.trade_date.slice(5)),
                axisLabel: { fontSize: 10, rotate: 45 },
              },
              yAxis: {
                type: 'value' as const,
                axisLabel: {
                  formatter: (v: number) => kpiHistory.field === 'positive_pct' ? v.toFixed(0) + '%' : v.toFixed(1) + '亿',
                },
                splitLine: { lineStyle: { type: 'dashed', color: '#eee' } },
              },
              series: [
                {
                  name: kpiHistory.title,
                  type: kpiHistory.field === 'positive_pct' ? 'line' as const : 'bar' as const,
                  data: kpiHistory.items.map((d) => {
                    const v = (d as any)[kpiHistory.field] || 0;
                    return kpiHistory.field === 'positive_pct'
                      ? v
                      : { value: v, itemStyle: { color: v >= 0 ? RED_COLOR : GREEN_COLOR } };
                  }),
                  ...(kpiHistory.field === 'positive_pct' ? {
                    smooth: true,
                    symbol: 'circle',
                    symbolSize: 4,
                    lineStyle: { color: '#1677ff', width: 2 },
                    areaStyle: { color: 'rgba(22,119,255,0.1)' },
                    markLine: {
                      silent: true,
                      data: [{ yAxis: 50, lineStyle: { color: '#999', type: 'dashed' } }],
                    },
                  } : {}),
                },
              ],
            }}
            style={{ height: 320 }}
            notMerge
          />
        )}
      </Modal>
    </div>
  );
};

export default IndexFundFlow;
