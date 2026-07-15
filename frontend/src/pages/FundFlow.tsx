import React, { useEffect, useMemo, useState } from 'react';
import {
  Card, Row, Col, Statistic, Spin, Empty, Alert, DatePicker, Segmented,
  Table, Tag, Typography, Space, Select, Drawer,
} from 'antd';
import {
  RiseOutlined, FallOutlined, DollarOutlined, PieChartOutlined,
  ArrowUpOutlined, ArrowDownOutlined, CloseCircleOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs, { type Dayjs } from 'dayjs';
import { useFundFlowStore } from '@/stores/fundFlowStore';
import type { StockFlowItem } from '@/services/fundFlowService';
import { fundFlowService } from '@/services/fundFlowService';
import type { ColumnsType } from 'antd/es/table';
import StockSearchLookup from '@/components/shared/StockSearchLookup';
import StockFundFlowDetail from '@/components/shared/StockFundFlowDetail';
import SectorFlowLineChart from '@/components/fund-flow/SectorFlowLineChart';
import RankingTrend from '@/components/index-fund-flow/RankingTrend';

const { Title, Text } = Typography;

// ── 颜色常量 ──
const RED_COLOR = '#cf1322';
const GREEN_COLOR = '#3f8600';
const BOARD_COLORS: Record<string, string> = {
  sh_main: '#cf1322',
  sh_star: '#fa8c16',
  sz_main: '#1677ff',
  sz_chi: '#722ed1',
};

// ── 格式化 ──
function fmtYi(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 10000) return (v / 10000).toFixed(2) + ' 万亿';
  if (abs >= 1) return v.toFixed(2) + ' 亿';
  return (v * 10000).toFixed(0) + ' 万';
}

function fmtYiShort(v: number): string {
  const sign = v >= 0 ? '+' : '';
  return sign + v.toFixed(1) + '亿';
}

function posColor(v: number): string {
  return v >= 0 ? RED_COLOR : GREEN_COLOR;
}

// ── 工具 ──
function formatDate(d: string): string {
  if (!d) return '';
  return d.length >= 10 ? d.slice(0, 10) : d;
}

function pivotBoardHistory(
  data: { trade_date: string; board_code: string; main_net_yi: number }[]
) {
  const dates = [...new Set(data.map((d) => d.trade_date))].sort();
  const codes = ['sh_main', 'sh_star', 'sz_main', 'sz_chi'];
  return {
    dates,
    series: codes.map((code) => ({
      code,
      name: { sh_main: '上证主板', sh_star: '科创板', sz_main: '深证主板', sz_chi: '创业板' }[code],
      data: dates.map((date) => {
        const row = data.find((r) => r.trade_date === date && r.board_code === code);
        return row ? row.main_net_yi : null;
      }),
    })),
  };
}

// ═══════════════════════════════════════════════════════════════
// FundFlow Page
// ═══════════════════════════════════════════════════════════════

const FundFlow: React.FC = () => {
  const store = useFundFlowStore();

  // 折线图 / 趋势追踪 交互状态
  const [lineTopN, setLineTopN] = useState<number>(15);
  const [lineMode, setLineMode] = useState<'daily' | 'cum'>('cum');

  // Drawer 个股搜索（顶部）
  const [drawerStock, setDrawerStock] = useState<string | null>(null);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [drawerSearchValue, setDrawerSearchValue] = useState('');

  const handleTopStockSelect = (tsCode: string) => {
    if (!tsCode) return;
    store.fetchStockTrend(tsCode, 30);
    setDrawerStock(tsCode);
    setDrawerVisible(true);
    setDrawerSearchValue('');
  };

  const handleCloseDrawer = () => {
    setDrawerVisible(false);
    setDrawerStock(null);
  };

  // 板块个股排行 Drawer
  const [selectedBoard, setSelectedBoard] = useState<string | null>(null);
  const [boardInflow, setBoardInflow] = useState<StockFlowItem[]>([]);
  const [boardOutflow, setBoardOutflow] = useState<StockFlowItem[]>([]);
  const [boardDrawerLoading, setBoardDrawerLoading] = useState(false);

  const handleBoardClick = async (boardCode: string) => {
    setSelectedBoard(boardCode);
    setBoardDrawerLoading(true);
    try {
      const [inflow, outflow] = await Promise.all([
        fundFlowService.getStockRanking(store.selectedDate, 'main_net', 10, boardCode),
        fundFlowService.getStockRanking(store.selectedDate, 'main_net_asc', 10, boardCode),
      ]);
      setBoardInflow(inflow.items);
      setBoardOutflow(outflow.items);
    } catch {
      setBoardInflow([]);
      setBoardOutflow([]);
    } finally {
      setBoardDrawerLoading(false);
    }
  };

  const handleCloseBoardDrawer = () => {
    setSelectedBoard(null);
    setBoardInflow([]);
    setBoardOutflow([]);
  };

  // ── 板块（行业/题材）个股排行 Drawer ──
  const [selectedSector, setSelectedSector] = useState<string | null>(null);
  const [sectorStocks, setSectorStocks] = useState<StockFlowItem[]>([]);
  const [sectorDrawerLoading, setSectorDrawerLoading] = useState(false);

  const handleSectorClick = async (sectorName: string) => {
    setSelectedSector(sectorName);
    setSectorDrawerLoading(true);
    try {
      const result = await fundFlowService.getSectorStocks(
        sectorName,
        store.sectorType,
        store.selectedDate,
        'main_net',
        20,
      );
      setSectorStocks(result.items);
    } catch {
      setSectorStocks([]);
    } finally {
      setSectorDrawerLoading(false);
    }
  };

  const handleCloseSectorDrawer = () => {
    setSelectedSector(null);
    setSectorStocks([]);
  };

  // 初始化
  useEffect(() => {
    store.fetchAvailableDates();
    store.fetchOverview();
    store.fetchHistory(30);
    store.fetchBoardHistory(30);
    store.fetchBreadthHistory(30);
    store.fetchIndustryFlow();
    store.fetchConceptFlow();
    store.fetchHeatmap(30, 'industry');
    store.fetchSectorRankingTrend(30, 'industry');
  }, []);

  // ── Layer 1: 市场总览图表 options ──

  const boardHistoryOption = useMemo(() => {
    const pivoted = pivotBoardHistory(store.boardHistory);
    if (!pivoted.dates.length) return {};
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          let html = `<b>${params[0]?.axisValue || ''}</b><br/>`;
          params.forEach((p: any) => {
            html += `${p.marker} ${p.seriesName}: ${fmtYiShort(p.value ?? 0)}<br/>`;
          });
          return html;
        },
      },
      legend: { bottom: 0, textStyle: { fontSize: 11 } },
      grid: { left: 60, right: 20, top: 10, bottom: 75 },
      xAxis: {
        type: 'category',
        data: pivoted.dates,
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        name: '亿',
        splitLine: { lineStyle: { type: 'dashed', color: '#eee' } },
      },
      series: pivoted.series.map((s) => ({
        name: s.name,
        type: 'line',
        data: s.data,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.5 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: (BOARD_COLORS[s.code] || '#666') + '44' },
              { offset: 1, color: (BOARD_COLORS[s.code] || '#666') + '08' },
            ],
          },
        },
        itemStyle: { color: BOARD_COLORS[s.code] || '#666' },
      })),
    };
  }, [store.boardHistory]);

  const breadthOption = useMemo(() => {
    if (!store.breadthHistory.length) return {};
    const dates = store.breadthHistory.map((d) => d.trade_date);
    const pcts = store.breadthHistory.map((d) => d.positive_pct);
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) =>
          `${params[0]?.axisValue}<br/>主力净流入为正: ${params[0]?.value}%`,
      },
      grid: { left: 50, right: 20, top: 10, bottom: 75 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        name: '%',
        min: 0,
        max: 100,
        splitLine: { lineStyle: { type: 'dashed', color: '#eee' } },
      },
      series: [
        {
          type: 'line',
          data: pcts,
          smooth: true,
          symbol: 'none',
          areaStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: RED_COLOR + '44' },
                { offset: 1, color: RED_COLOR + '08' },
              ],
            },
          },
          lineStyle: { color: RED_COLOR, width: 1.5 },
          markLine: {
            silent: true,
            data: [{ yAxis: 50, lineStyle: { color: '#999', type: 'dashed' }, label: { formatter: '50%' } }],
          },
        },
      ],
    };
  }, [store.breadthHistory]);

  // ── Layer 2: 行业排名图表 ──

  const sectorRankOption = useMemo(() => {
    const items = store.sectorType === 'industry' ? store.industries : store.concepts;
    const nameKey = store.sectorType === 'industry' ? 'industry_name' : 'concept_name';
    if (!items.length) return {};

    const sorted = [...items].sort((a, b) => (b as any).main_net_yi - (a as any).main_net_yi);
    const topIn = sorted.slice(0, 10).reverse();
    const topOut = sorted.slice(-10).reverse();

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: any) => {
          const p = params[0];
          return `${p?.name}<br/>主力净流入: ${fmtYiShort(p?.value ?? 0)}`;
        },
      },
      grid: [
        { left: '5%', top: 10, width: '42%', bottom: 80 },
        { left: '55%', top: 10, width: '42%', bottom: 80 },
      ],
      xAxis: [
        { type: 'value', gridIndex: 0, name: '亿' },
        { type: 'value', gridIndex: 1, name: '亿', inverse: true },
      ],
      yAxis: [
        {
          type: 'category', gridIndex: 0,
          data: topIn.map((i: any) => i[nameKey]),
          axisLabel: { fontSize: 10 },
          position: 'left',
        },
        {
          type: 'category', gridIndex: 1,
          data: topOut.map((i: any) => i[nameKey]),
          axisLabel: { fontSize: 10 },
          position: 'right',
        },
      ],
      series: [
        {
          type: 'bar', xAxisIndex: 0, yAxisIndex: 0,
          data: topIn.map((i: any) => ({
            value: i.main_net_yi,
            itemStyle: { color: i.main_net_yi >= 0 ? RED_COLOR : GREEN_COLOR },
          })),
          label: { show: true, position: 'right', fontSize: 10, formatter: (p: any) => fmtYiShort(p.value) },
        },
        {
          type: 'bar', xAxisIndex: 1, yAxisIndex: 1,
          data: topOut.map((i: any) => ({
            value: i.main_net_yi,
            itemStyle: { color: i.main_net_yi >= 0 ? RED_COLOR : GREEN_COLOR },
          })),
          label: { show: true, position: 'left', fontSize: 10, formatter: (p: any) => fmtYiShort(p.value) },
        },
      ],
    };
  }, [store.industries, store.concepts, store.sectorType]);

  // ── 板块个股排行 Drawer 表格列（精简版）──
  const boardStockColumns: ColumnsType<StockFlowItem> = [
    {
      title: '#',
      key: 'rank',
      width: 36,
      render: (_: any, __: any, idx: number) => idx + 1,
    },
    {
      title: '代码',
      dataIndex: 'ts_code',
      width: 90,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: '名称',
      dataIndex: 'stock_name',
      width: 72,
      render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: '行业',
      dataIndex: 'industry_name',
      width: 72,
      ellipsis: true,
      render: (v: string) => <Text type="secondary" style={{ fontSize: 11 }}>{v}</Text>,
    },
    {
      title: '主力净流入',
      dataIndex: 'main_net_flow',
      width: 110,
      align: 'right',
      render: (v: number) => (
        <span style={{ color: posColor(v), fontWeight: 500, fontSize: 12 }}>
          {(v / 1e8).toFixed(2)} 亿
        </span>
      ),
    },
  ];

  // ── Render ──

  const overview = store.overview;
  const loading = store.loading;

  return (
    <div style={{ padding: '0 0 24px 0' }}>
      {/* Header */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <Title level={3} style={{ margin: 0 }}>
          <DollarOutlined /> 资金流向
        </Title>
        <Space>
          {store.availableDates.length > 0 && (
            <Select
              style={{ width: 160 }}
              placeholder="选择日期"
              value={store.selectedDate || overview?.trade_date || undefined}
              onChange={(v) => store.setSelectedDate(v)}
              options={store.availableDates.slice(0, 30).map((d) => ({ label: d, value: d }))}
              allowClear
            />
          )}
          <DatePicker
            value={store.selectedDate ? dayjs(store.selectedDate) : null}
            onChange={(d: Dayjs | null) => store.setSelectedDate(d?.format('YYYY-MM-DD'))}
            placeholder="选择日期"
            allowClear
          />
          <StockSearchLookup
            value={drawerSearchValue}
            onChange={setDrawerSearchValue}
            onSelect={handleTopStockSelect}
            placeholder="搜索个股资金流"
            style={{ width: 200 }}
          />
          {drawerStock && (
            <Tag closable onClose={handleCloseDrawer} color="blue">
              已选: {drawerStock}
            </Tag>
          )}
        </Space>
      </div>

      {/* ── 个股资金流 Drawer ── */}
      <Drawer
        title={
          <Space>
            <Tag color="blue">{drawerStock}</Tag>
            <Text strong>{store.stockTrend?.stock_name || ''}</Text>
          </Space>
        }
        open={drawerVisible}
        onClose={handleCloseDrawer}
        width={960}
        destroyOnClose
      >
        {drawerStock && (
          <StockFundFlowDetail
            tsCode={drawerStock}
            stockName={store.stockTrend?.stock_name}
            onClose={handleCloseDrawer}
          />
        )}
      </Drawer>

      {/* ── 板块个股排行 Drawer ── */}
      <Drawer
        title={
          <Space>
            <Tag color={BOARD_COLORS[selectedBoard || ''] || '#666'}>
              {selectedBoard && overview?.boards?.find(b => b.board_code === selectedBoard)?.board_name}
            </Tag>
            <Text strong>个股资金流 Top 10</Text>
          </Space>
        }
        open={!!selectedBoard}
        onClose={handleCloseBoardDrawer}
        width={900}
        destroyOnClose
      >
        {boardDrawerLoading ? (
          <Spin style={{ display: 'block', padding: 60 }} />
        ) : (
          <Row gutter={16}>
            <Col span={12}>
              <Card size="small" title={<span style={{ color: RED_COLOR }}>🔴 主力净流入 Top 10</span>}>
                <Table
                  dataSource={boardInflow}
                  rowKey="ts_code"
                  columns={boardStockColumns}
                  size="small"
                  pagination={false}
                  scroll={{ x: 400 }}
                  onRow={(record) => ({
                    onClick: () => handleTopStockSelect(record.ts_code),
                    style: { cursor: 'pointer' },
                  })}
                />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small" title={<span style={{ color: GREEN_COLOR }}>🟢 主力净流出 Top 10</span>}>
                <Table
                  dataSource={boardOutflow}
                  rowKey="ts_code"
                  columns={boardStockColumns}
                  size="small"
                  pagination={false}
                  scroll={{ x: 400 }}
                  onRow={(record) => ({
                    onClick: () => handleTopStockSelect(record.ts_code),
                    style: { cursor: 'pointer' },
                  })}
                />
              </Card>
            </Col>
          </Row>
        )}
      </Drawer>

      {/* ── 板块个股排行 Drawer（行业/题材点击）── */}
      <Drawer
        title={
          <Space>
            <Tag color="blue">{selectedSector}</Tag>
            <Text strong>{store.sectorType === 'industry' ? '行业' : '题材'}个股资金流</Text>
          </Space>
        }
        open={!!selectedSector}
        onClose={handleCloseSectorDrawer}
        width={700}
        destroyOnClose
      >
        {sectorDrawerLoading ? (
          <Spin style={{ display: 'block', padding: 60 }} />
        ) : (
          <Table
            dataSource={sectorStocks}
            rowKey="ts_code"
            columns={[
              { title: '#', key: 'rank', width: 40, render: (_: any, __: any, idx: number) => idx + 1 },
              {
                title: '代码',
                dataIndex: 'ts_code',
                width: 90,
                render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text>,
              },
              {
                title: '名称',
                dataIndex: 'stock_name',
                width: 80,
                render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text>,
              },
              {
                title: '涨跌幅',
                dataIndex: 'pct_change',
                width: 80,
                align: 'right',
                sorter: (a, b) => a.pct_change - b.pct_change,
                render: (v: number) => (
                  <Text style={{ color: v >= 0 ? RED_COLOR : GREEN_COLOR, fontWeight: 500, fontSize: 12 }}>
                    {v > 0 ? '+' : ''}{v.toFixed(2)}%
                  </Text>
                ),
              },
              {
                title: '主力净流入',
                dataIndex: 'main_net_flow',
                width: 110,
                align: 'right',
                sorter: (a, b) => a.main_net_flow - b.main_net_flow,
                render: (v: number) => (
                  <span style={{ color: posColor(v), fontWeight: 500, fontSize: 12 }}>
                    {(v / 1e8).toFixed(2)} 亿
                  </span>
                ),
              },
              {
                title: '超大单',
                dataIndex: 'jumbo_net_flow',
                width: 90,
                align: 'right',
                render: (v: number) => <span style={{ color: posColor(v), fontSize: 12 }}>{(v / 1e8).toFixed(2)} 亿</span>,
              },
              {
                title: '占流通市值',
                dataIndex: 'main_inflow_circ_rate',
                width: 80,
                align: 'right',
                render: (v: number) => <Text style={{ fontSize: 12 }}>{v > 0 ? `${v.toFixed(2)}%` : '-'}</Text>,
              },
            ]}
            size="small"
            pagination={false}
            scroll={{ x: 560 }}
            onRow={(record) => ({
              onClick: () => handleTopStockSelect(record.ts_code),
              style: { cursor: 'pointer' },
            })}
          />
        )}
      </Drawer>

      {store.error && (
        <Alert message={store.error} type="error" closable onClose={store.clearError} style={{ marginBottom: 16 }} />
      )}

      {/* ═════════════════════════════════════════════╗
          ║  Layer 1: 市场总览                          ║
          ╚════════════════════════════════════════════╝ */}
      <Title level={4} style={{ marginBottom: 12 }}>
        <PieChartOutlined /> 市场总览
      </Title>

      {/* KPI Cards */}
      {loading.overview ? (
        <Spin style={{ display: 'block', padding: 40 }} />
      ) : overview?.summary ? (
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title="主力净流入"
                value={overview.summary.main_net_yi}
                precision={1}
                suffix="亿"
                valueStyle={{ color: posColor(overview.summary.main_net_yi), fontSize: 22 }}
                prefix={overview.summary.main_net_yi >= 0 ? <RiseOutlined /> : <FallOutlined />}
              />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title="超大单净流入"
                value={overview.summary.jumbo_net_yi}
                precision={1}
                suffix="亿"
                valueStyle={{ color: posColor(overview.summary.jumbo_net_yi), fontSize: 22 }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title="大单净流入"
                value={overview.summary.block_net_yi}
                precision={1}
                suffix="亿"
                valueStyle={{ color: posColor(overview.summary.block_net_yi), fontSize: 22 }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title="散户净流入"
                value={overview.summary.retail_net_yi}
                precision={1}
                suffix="亿"
                valueStyle={{ color: posColor(overview.summary.retail_net_yi), fontSize: 22 }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title="资金广度"
                value={overview.breadth?.positive_pct}
                precision={0}
                suffix="%"
                valueStyle={{
                  color: (overview.breadth?.positive_pct || 0) >= 50 ? RED_COLOR : GREEN_COLOR,
                  fontSize: 22,
                }}
                prefix={(overview.breadth?.positive_pct || 0) >= 50 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {overview.breadth?.positive_count}/{overview.breadth?.total_count} 只
              </Text>
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title="主力流入/流出"
                value={overview.summary.main_in_yi}
                precision={0}
                suffix={`亿 / ${overview.summary.main_out_yi.toFixed(0)}亿`}
                valueStyle={{ fontSize: 16 }}
              />
            </Card>
          </Col>
        </Row>
      ) : (
        <Empty description="暂无数据" />
      )}

      {/* Board Cards */}
      {(overview?.boards?.length ?? 0) > 0 && overview && (
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          {overview.boards.map((b) => (
            <Col xs={12} sm={6} key={b.board_code}>
              <Card
                size="small"
                hoverable
                style={{ borderLeft: `3px solid ${BOARD_COLORS[b.board_code] || '#666'}`, cursor: 'pointer' }}
                onClick={() => handleBoardClick(b.board_code)}
              >
                <Text strong>{b.board_name}</Text>
                <br />
                <Text style={{ color: posColor(b.main_net_yi), fontSize: 18, fontWeight: 600 }}>
                  {fmtYiShort(b.main_net_yi)}
                </Text>
                <br />
                <Text type="secondary" style={{ fontSize: 11 }}>
                  广度 {b.positive_pct}% · {b.stock_count} 只
                </Text>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      {/* Board History Chart */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={14}>
          <Card size="small" title="四大指数主力净流入趋势（近 30 日）">
            {loading.boardHistory ? (
              <Spin style={{ display: 'block', padding: 60 }} />
            ) : store.boardHistory.length > 0 ? (
              <ReactECharts option={boardHistoryOption} style={{ height: 320 }} />
            ) : (
              <Empty description="暂无历史数据" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card size="small" title="资金广度趋势（主力净流入为正占比）">
            {loading.breadthHistory ? (
              <Spin style={{ display: 'block', padding: 60 }} />
            ) : store.breadthHistory.length > 0 ? (
              <ReactECharts option={breadthOption} style={{ height: 320 }} />
            ) : (
              <Empty description="暂无广度数据" />
            )}
          </Card>
        </Col>
      </Row>

      {/* ═════════════════════════════════════════════╗
          ║  Layer 2: 板块 / 题材轮动                    ║
          ╚════════════════════════════════════════════╝ */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>
          <RiseOutlined /> 板块/题材轮动
        </Title>
        <Segmented
          options={[
            { label: '行业', value: 'industry' },
            { label: '题材', value: 'concept' },
          ]}
          value={store.sectorType}
          onChange={(v) => store.setSectorType(v as 'industry' | 'concept')}
        />
      </div>

      {/* Sector Ranking Bar Chart */}
      <Card size="small" title="主力净流入 Top 10 ↑ / ↓" style={{ marginBottom: 16 }}>
        {loading.industries || loading.concepts ? (
          <Spin style={{ display: 'block', padding: 60 }} />
        ) : (
          <ReactECharts option={sectorRankOption} style={{ height: 350 }} />
        )}
      </Card>

      {/* 板块主力资金流趋势（折线图） */}
      <Card
        size="small"
        title="板块主力资金流趋势"
        style={{ marginBottom: 16 }}
        extra={
          <Space size="small">
            <Segmented
              options={[
                { label: '每日净流入', value: 'daily' },
                { label: '累计净流入', value: 'cum' },
              ]}
              value={lineMode}
              onChange={(v) => setLineMode(v as 'daily' | 'cum')}
            />
            <Select
              value={lineTopN}
              style={{ width: 110 }}
              onChange={(v) => setLineTopN(v)}
              options={[
                { label: 'Top 10', value: 10 },
                { label: 'Top 15', value: 15 },
                { label: 'Top 20', value: 20 },
              ]}
            />
          </Space>
        }
      >
        <SectorFlowLineChart
          rows={store.heatmap?.rows || []}
          topN={lineTopN}
          mode={lineMode}
          loading={loading.heatmap}
        />
      </Card>

      {/* 趋势追踪（潜力板块） */}
      <Card
        size="small"
        title={`趋势追踪 · 潜力${store.sectorType === 'industry' ? '行业' : '题材'}（按 5 日累计净流入排名变化）`}
      >
        <RankingTrend
          data={{ items: store.sectorRankingTrend }}
          loading={loading.sectorRankingTrend}
          nameField="sector_name"
          onItemClick={handleSectorClick}
        />
      </Card>
    </div>
  );
};

export default FundFlow;
