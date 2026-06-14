import React, { useEffect, useMemo, useState } from 'react';
import {
  Card, Row, Col, Statistic, Spin, Empty, Alert, DatePicker, Segmented,
  Table, Tag, Typography, Space, Select,
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

// ── 图表 option 构建（复用） ──
function buildOrderFlowChart(days: Array<{
  trade_date: string;
  jumbo_net_flow: number;
  block_net_flow: number;
  mid_net_flow: number;
  small_net_flow: number;
}>) {
  const dates = days.map((d) => d.trade_date);
  return {
    tooltip: { trigger: 'axis' as const },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    grid: { left: 60, right: 20, top: 10, bottom: 35 },
    xAxis: { type: 'category' as const, data: dates, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { type: 'value' as const, name: '元', axisLabel: { formatter: (v: number) => (v / 1e8).toFixed(0) + '亿' } },
    series: [
      {
        name: '超大单', type: 'bar' as const,
        data: days.map((d) => d.jumbo_net_flow),
        itemStyle: { color: '#cf1322' },
      },
      {
        name: '大单', type: 'bar' as const,
        data: days.map((d) => d.block_net_flow),
        itemStyle: { color: '#fa8c16' },
      },
      {
        name: '中单', type: 'bar' as const,
        data: days.map((d) => d.mid_net_flow),
        itemStyle: { color: '#1677ff' },
      },
      {
        name: '小单', type: 'bar' as const,
        data: days.map((d) => d.small_net_flow),
        itemStyle: { color: '#3f8600' },
      },
    ],
  };
}

function buildCumTrendChart(days: Array<{ trade_date: string; main_net_flow_5d: number; main_net_flow_10d: number; main_net_flow_20d: number }>) {
  const dates = days.map((d) => d.trade_date);
  return {
    tooltip: { trigger: 'axis' as const },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    grid: { left: 60, right: 20, top: 10, bottom: 35 },
    xAxis: { type: 'category' as const, data: dates, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { type: 'value' as const, name: '元', axisLabel: { formatter: (v: number) => (v / 1e8).toFixed(0) + '亿' } },
    series: [
      {
        name: '5日累计', type: 'line' as const, smooth: true, symbol: 'none' as const,
        data: days.map((d) => d.main_net_flow_5d),
        lineStyle: { color: '#fa8c16', width: 1.5 },
      },
      {
        name: '10日累计', type: 'line' as const, smooth: true, symbol: 'none' as const,
        data: days.map((d) => d.main_net_flow_10d),
        lineStyle: { color: '#1677ff', width: 1.5 },
      },
      {
        name: '20日累计', type: 'line' as const, smooth: true, symbol: 'none' as const,
        data: days.map((d) => d.main_net_flow_20d),
        lineStyle: { color: '#722ed1', width: 1.5 },
      },
    ],
  };
}

// ═══════════════════════════════════════════════════════════════
// FundFlow Page
// ═══════════════════════════════════════════════════════════════

const FundFlow: React.FC = () => {
  const store = useFundFlowStore();

  // 个股搜索
  const [stockSearchValue, setStockSearchValue] = useState('');
  const [searchedStock, setSearchedStock] = useState<string | null>(null);  // ts_code

  const handleStockSelect = (tsCode: string) => {
    if (!tsCode) return;
    setSearchedStock(tsCode);
    setStockSearchValue(tsCode);
    store.fetchStockTrend(tsCode, 30);
  };

  const handleClearStock = () => {
    setSearchedStock(null);
    setStockSearchValue('');
    store.setSelectedStock(null);
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
    store.fetchHeatmap(20, 'industry');
    store.fetchStockRanking();
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
      grid: { left: 60, right: 20, top: 10, bottom: 35 },
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
      grid: { left: 50, right: 20, top: 10, bottom: 35 },
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

  // ── Layer 2: 热力图 ──

  const heatmapOption = useMemo(() => {
    if (!store.heatmap?.rows.length) return {};
    const rows = store.heatmap.rows;
    const dates = [...new Set(rows.map((r) => r.trade_date))].sort();
    const sectors = [...new Set(rows.map((r) => r.sector_name))];

    // 取近 20 日主力净流入总和最大的 20 个板块
    const sectorTotals: Record<string, number> = {};
    rows.forEach((r) => {
      sectorTotals[r.sector_name] = (sectorTotals[r.sector_name] || 0) + r.main_net_yi;
    });
    const topSectors = Object.entries(sectorTotals)
      .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
      .slice(0, 25)
      .map(([name]) => name)
      .reverse();

    const maxAbs = Math.max(...rows.map((r) => Math.abs(r.main_net_yi)), 0.1);
    const data = rows
      .filter((r) => topSectors.includes(r.sector_name))
      .map((r) => [dates.indexOf(r.trade_date), topSectors.indexOf(r.sector_name), r.main_net_yi]);

    return {
      tooltip: {
        formatter: (params: any) => {
          const [di, si, v] = params.value || [0, 0, 0];
          return `${dates[di]}<br/>${topSectors[si]}<br/>主力净流入: ${fmtYiShort(v)}`;
        },
      },
      grid: { left: 90, right: 40, top: 10, bottom: 50 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { rotate: 45, fontSize: 10 },
        position: 'bottom',
      },
      yAxis: {
        type: 'category',
        data: topSectors,
        axisLabel: { fontSize: 10 },
      },
      visualMap: {
        min: -maxAbs,
        max: maxAbs,
        inRange: { color: [GREEN_COLOR, '#f5f5f5', RED_COLOR] },
        show: false,
      },
      series: [
        {
          type: 'heatmap',
          data,
          label: { show: false },
          emphasis: {
            itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' },
          },
        },
      ],
    };
  }, [store.heatmap]);

  // ── Layer 3: 个股表格 ──

  const stockColumns: ColumnsType<StockFlowItem> = [
    {
      title: '排名',
      key: 'rank',
      width: 50,
      render: (_: any, __: any, idx: number) => idx + 1,
      sorter: false,
    },
    {
      title: '代码',
      dataIndex: 'ts_code',
      width: 100,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: '名称',
      dataIndex: 'stock_name',
      width: 80,
    },
    {
      title: '行业',
      dataIndex: 'industry_name',
      width: 80,
      ellipsis: true,
    },
    {
      title: '主力净流入(元)',
      dataIndex: 'main_net_flow',
      width: 140,
      align: 'right',
      sorter: (a, b) => a.main_net_flow - b.main_net_flow,
      render: (v: number) => (
        <span style={{ color: posColor(v), fontWeight: 500 }}>
          {(v / 1e8).toFixed(2)} 亿
        </span>
      ),
    },
    {
      title: '超大单',
      dataIndex: 'jumbo_net_flow',
      width: 110,
      align: 'right',
      render: (v: number) => <span style={{ color: posColor(v) }}>{(v / 1e8).toFixed(2)} 亿</span>,
    },
    {
      title: '大单',
      dataIndex: 'block_net_flow',
      width: 100,
      align: 'right',
      render: (v: number) => <span style={{ color: posColor(v) }}>{(v / 1e8).toFixed(2)} 亿</span>,
    },
    {
      title: '中单',
      dataIndex: 'mid_net_flow',
      width: 100,
      align: 'right',
      render: (v: number) => <span style={{ color: posColor(v) }}>{(v / 1e8).toFixed(2)} 亿</span>,
    },
    {
      title: '占流通市值',
      dataIndex: 'main_inflow_circ_rate',
      width: 90,
      align: 'right',
      sorter: (a, b) => a.main_inflow_circ_rate - b.main_inflow_circ_rate,
      render: (v: number) => v > 0 ? `${v.toFixed(2)}%` : '-',
    },
    {
      title: '5日累计',
      dataIndex: 'main_net_flow_5d',
      width: 110,
      align: 'right',
      render: (v: number) => <span style={{ color: posColor(v) }}>{(v / 1e8).toFixed(1)} 亿</span>,
    },
  ];

  // ── 个股展开：趋势图（按股票缓存，避免多行展开时数据串扰） ──
  const [trendCache, setTrendCache] = useState<Record<string, typeof store.stockTrend>>({});

  const handleExpand = (expanded: boolean, record: StockFlowItem) => {
    if (expanded) {
      if (!trendCache[record.ts_code]) {
        // 异步获取后写入缓存
        fundFlowService.getStockTrend(record.ts_code, 30).then((trend) => {
          setTrendCache((prev) => ({ ...prev, [record.ts_code]: trend }));
        }).catch(() => {});
      }
    }
  };

  const expandedRowRender = (record: StockFlowItem) => {
    const trend = trendCache[record.ts_code];
    if (!trend?.days?.length) {
      return <Spin style={{ display: 'block', padding: 20 }} />;
    }
    const days = trend.days;
    return (
      <Row gutter={16}>
        <Col span={12}>
          <Card size="small" title="四类订单净流入（超大/大/中/小）">
            <ReactECharts option={buildOrderFlowChart(days)} style={{ height: 250 }} />
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title="多日累计趋势">
            <ReactECharts option={buildCumTrendChart(days)} style={{ height: 250 }} />
          </Card>
        </Col>
      </Row>
    );
  };

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
        </Space>
      </div>

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
                style={{ borderLeft: `3px solid ${BOARD_COLORS[b.board_code] || '#666'}` }}
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

      {/* Heatmap */}
      <Card size="small" title={`${store.sectorType === 'industry' ? '行业' : '题材'}资金流热力图（近 20 日）`} style={{ marginBottom: 16 }}>
        {loading.heatmap ? (
          <Spin style={{ display: 'block', padding: 60 }} />
        ) : store.heatmap?.rows.length ? (
          <ReactECharts option={heatmapOption} style={{ height: 500 }} />
        ) : (
          <Empty description="暂无热力图数据" />
        )}
      </Card>

      {/* ═════════════════════════════════════════════╗
          ║  Layer 3: 个股资金流                          ║
          ╚════════════════════════════════════════════╝ */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <Title level={4} style={{ margin: 0 }}>
          <FallOutlined /> 个股资金流
        </Title>
        <Space>
          <StockSearchLookup
            value={stockSearchValue}
            onChange={setStockSearchValue}
            onSelect={handleStockSelect}
            placeholder="搜索个股代码或名称"
            style={{ width: 220 }}
          />
          {searchedStock && (
            <Tag
              closable
              onClose={handleClearStock}
              color="blue"
              style={{ cursor: 'default' }}
            >
              已选: {searchedStock}
            </Tag>
          )}
          <Select
            value="main_net"
            style={{ width: 140 }}
            onChange={(v) => store.fetchStockRanking(store.selectedDate, v)}
            options={[
              { label: '主力净流入↓', value: 'main_net' },
              { label: '主力净流出↑', value: 'main_net_asc' },
              { label: '占流通市值比', value: 'inflow_rate' },
              { label: '超大单', value: 'jumbo' },
              { label: '大单', value: 'block' },
            ]}
          />
        </Space>
      </div>

      {/* ── 个股搜索详情面板 ── */}
      {searchedStock && (
        <Card
          size="small"
          style={{ marginBottom: 12 }}
          title={
            <Space>
              <Tag color="blue">{searchedStock}</Tag>
              <Text strong>{store.stockTrend?.stock_name || ''}</Text>
            </Space>
          }
          extra={
            <Tag
              closable
              onClose={handleClearStock}
              style={{ cursor: 'pointer' }}
            >
              关闭
            </Tag>
          }
        >
          {store.loading.stockTrend ? (
            <Spin style={{ display: 'block', padding: 20 }} />
          ) : store.stockTrend && store.stockTrend.days.length > 0 ? (
            (() => {
              const latest = store.stockTrend.days[store.stockTrend.days.length - 1];
              return (
                <>
                  {/* 指标卡片 */}
                  <Row gutter={[8, 8]} style={{ marginBottom: 12 }}>
                    <Col xs={12} sm={6} md={3}>
                      <Card size="small" bodyStyle={{ padding: '8px 12px' }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>主力净流入</Text>
                        <br />
                        <Text strong style={{ fontSize: 16, color: posColor(latest.main_net_flow) }}>
                          {fmtYiShort(latest.main_net_flow / 1e8)}
                        </Text>
                      </Card>
                    </Col>
                    <Col xs={12} sm={6} md={3}>
                      <Card size="small" bodyStyle={{ padding: '8px 12px' }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>超大单</Text>
                        <br />
                        <Text strong style={{ fontSize: 16, color: posColor(latest.jumbo_net_flow) }}>
                          {fmtYiShort(latest.jumbo_net_flow / 1e8)}
                        </Text>
                      </Card>
                    </Col>
                    <Col xs={12} sm={6} md={3}>
                      <Card size="small" bodyStyle={{ padding: '8px 12px' }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>大单</Text>
                        <br />
                        <Text strong style={{ fontSize: 16, color: posColor(latest.block_net_flow) }}>
                          {fmtYiShort(latest.block_net_flow / 1e8)}
                        </Text>
                      </Card>
                    </Col>
                    <Col xs={12} sm={6} md={3}>
                      <Card size="small" bodyStyle={{ padding: '8px 12px' }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>中单 / 小单</Text>
                        <br />
                        <Text strong style={{ fontSize: 14, color: posColor(latest.mid_net_flow) }}>
                          {fmtYiShort(latest.mid_net_flow / 1e8)}
                        </Text>
                        <Text style={{ fontSize: 12, marginLeft: 8, color: posColor(latest.small_net_flow) }}>
                          {fmtYiShort(latest.small_net_flow / 1e8)}
                        </Text>
                      </Card>
                    </Col>
                    <Col xs={12} sm={6} md={3}>
                      <Card size="small" bodyStyle={{ padding: '8px 12px' }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>5日 / 10日 / 20日累计</Text>
                        <br />
                        <Text strong style={{ fontSize: 14, color: posColor(latest.main_net_flow_5d) }}>
                          {fmtYiShort(latest.main_net_flow_5d / 1e8)}
                        </Text>
                        <Text style={{ fontSize: 12, marginLeft: 8, color: posColor(latest.main_net_flow_10d) }}>
                          {fmtYiShort(latest.main_net_flow_10d / 1e8)}
                        </Text>
                        <Text style={{ fontSize: 12, marginLeft: 8, color: posColor(latest.main_net_flow_20d) }}>
                          {fmtYiShort(latest.main_net_flow_20d / 1e8)}
                        </Text>
                      </Card>
                    </Col>
                    <Col xs={12} sm={6} md={3}>
                      <Card size="small" bodyStyle={{ padding: '8px 12px' }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>收盘价</Text>
                        <br />
                        <Text strong style={{ fontSize: 16 }}>
                          {latest.close_price?.toFixed(2) || '-'}
                        </Text>
                      </Card>
                    </Col>
                  </Row>

                  {/* 趋势图表 */}
                  <Row gutter={16}>
                    <Col span={12}>
                      <Card size="small" title="四类订单净流入（超大/大/中/小）">
                        <ReactECharts
                          option={buildOrderFlowChart(store.stockTrend.days)}
                          style={{ height: 250 }}
                        />
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title="多日累计趋势">
                        <ReactECharts
                          option={buildCumTrendChart(store.stockTrend.days)}
                          style={{ height: 250 }}
                        />
                      </Card>
                    </Col>
                  </Row>
                </>
              );
            })()
          ) : (
            <Empty description="暂无该股票资金流数据" />
          )}
        </Card>
      )}

      <Card size="small">
        {loading.stockRanking ? (
          <Spin style={{ display: 'block', padding: 60 }} />
        ) : (
          <Table
            columns={stockColumns}
            dataSource={store.stockRanking}
            rowKey="ts_code"
            size="small"
            scroll={{ x: 1000 }}
            pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
            expandable={{
              expandedRowRender,
              onExpand: handleExpand,
              rowExpandable: () => true,
            }}
          />
        )}
      </Card>
    </div>
  );
};

export default FundFlow;
