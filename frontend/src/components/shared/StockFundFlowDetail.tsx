import React, { useEffect, useState, useCallback } from 'react';
import { Card, Row, Col, Spin, Empty, Space, Tag, Typography, Modal } from 'antd';
import ReactECharts from 'echarts-for-react';
import { fundFlowService } from '@/services/fundFlowService';
import type { StockTrend, StockTrendDay, StockIntraday } from '@/services/fundFlowService';
import stockService from '@/services/stockService';
import type { KLineItem } from '@/types/stock';

const { Text, Title } = Typography;

const RED_COLOR = '#cf1322';
const GREEN_COLOR = '#3f8600';

function fmtYiShort(v: number): string {
  const sign = v >= 0 ? '+' : '';
  return sign + v.toFixed(2) + '亿';
}

function posColor(v: number): string {
  return v >= 0 ? RED_COLOR : GREEN_COLOR;
}

function buildOrderFlowChart(days: StockTrendDay[]) {
  const dates = days.map((d) => d.trade_date);
  return {
    tooltip: { trigger: 'axis' as const },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    grid: { left: 60, right: 20, top: 10, bottom: 75 },
    xAxis: { type: 'category' as const, data: dates, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { type: 'value' as const, axisLabel: { formatter: (v: number) => (v / 1e8).toFixed(0) + '亿' } },
    series: [
      { name: '超大单', type: 'bar' as const, data: days.map((d) => d.jumbo_net_flow), itemStyle: { color: '#cf1322' } },
      { name: '大单', type: 'bar' as const, data: days.map((d) => d.block_net_flow), itemStyle: { color: '#fa8c16' } },
      { name: '中单', type: 'bar' as const, data: days.map((d) => d.mid_net_flow), itemStyle: { color: '#1677ff' } },
      { name: '小单', type: 'bar' as const, data: days.map((d) => d.small_net_flow), itemStyle: { color: '#3f8600' } },
    ],
  };
}

function buildCumTrendChart(days: StockTrendDay[]) {
  const dates = days.map((d) => d.trade_date);
  return {
    tooltip: { trigger: 'axis' as const },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    grid: { left: 60, right: 20, top: 10, bottom: 75 },
    xAxis: { type: 'category' as const, data: dates, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { type: 'value' as const, axisLabel: { formatter: (v: number) => (v / 1e8).toFixed(0) + '亿' } },
    series: [
      { name: '5日累计', type: 'line' as const, smooth: true, symbol: 'none' as const, data: days.map((d) => d.main_net_flow_5d), itemStyle: { color: '#fa8c16' }, lineStyle: { color: '#fa8c16', width: 1.5 } },
      { name: '10日累计', type: 'line' as const, smooth: true, symbol: 'none' as const, data: days.map((d) => d.main_net_flow_10d), itemStyle: { color: '#1677ff' }, lineStyle: { color: '#1677ff', width: 1.5 } },
      { name: '20日累计', type: 'line' as const, smooth: true, symbol: 'none' as const, data: days.map((d) => d.main_net_flow_20d), itemStyle: { color: '#722ed1' }, lineStyle: { color: '#722ed1', width: 1.5 } },
    ],
  };
}

function buildMainFlowTrendChart(days: StockTrendDay[], klineDays: KLineItem[] = []) {
  const dates = days.map((d) => d.trade_date);

  // 构建日期→K线数据映射
  const klineMap: Record<string, KLineItem> = {};
  for (const k of klineDays) {
    klineMap[k.trade_date] = k;
  }

  // 为每个日期匹配 K 线数据（[open, close, low, high]）
  const klineData: (number[] | null)[] = dates.map((d) => {
    const k = klineMap[d];
    return k ? [k.open, k.close, k.low, k.high] : null;
  });

  const hasKline = klineData.some((k) => k !== null);

  const series: any[] = [
    {
      name: '主力净流入', type: 'bar' as const,
      data: days.map((d) => ({ value: d.main_net_flow, itemStyle: { color: d.main_net_flow >= 0 ? RED_COLOR : GREEN_COLOR } })),
    },
    { name: '主力流入', type: 'line' as const, smooth: true, symbol: 'none' as const, data: days.map((d) => d.main_in_flow), itemStyle: { color: RED_COLOR }, lineStyle: { color: RED_COLOR, width: 1, type: 'dashed' as const } },
    { name: '主力流出', type: 'line' as const, smooth: true, symbol: 'none' as const, data: days.map((d) => d.main_out_flow), itemStyle: { color: GREEN_COLOR }, lineStyle: { color: GREEN_COLOR, width: 1, type: 'dashed' as const } },
  ];

  // yAxis：有K线时双轴，无K线时保持原始对象格式（向后兼容）
  const yAxis: any = hasKline
    ? [
        { type: 'value' as const, axisLabel: { formatter: (v: number) => (v / 1e8).toFixed(0) + '亿' }, splitLine: { lineStyle: { type: 'dashed', color: '#eee' } } },
        { type: 'value' as const, name: '股价(元)', nameTextStyle: { fontSize: 10 }, axisLabel: { formatter: (v: number) => v.toFixed(1) }, splitLine: { show: false }, scale: true },
      ]
    : { type: 'value' as const, axisLabel: { formatter: (v: number) => (v / 1e8).toFixed(0) + '亿' }, splitLine: { lineStyle: { type: 'dashed', color: '#eee' } } };

  if (hasKline) {
    series.push({
      name: 'K线',
      type: 'candlestick' as const,
      yAxisIndex: 1,
      data: klineData,
      itemStyle: {
        color: RED_COLOR,
        color0: GREEN_COLOR,
        borderColor: RED_COLOR,
        borderColor0: GREEN_COLOR,
      },
      barWidth: '60%',
    });
  }

  // tooltip formatter：防御性包装，避免渲染崩溃
  const tooltipFormatter = (params: any) => {
    try {
      const paramList = Array.isArray(params) ? params : [params];
      if (paramList.length === 0) return '';
      const date = paramList[0]?.axisValue || '';
      let html = `<strong>${date}</strong><br/>`;
      for (const p of paramList) {
        if (!p) continue;
        if (p.seriesName === 'K线') {
          const k = Array.isArray(p.data) ? p.data : [];
          if (k.length >= 4) {
            const chg = k[1] - k[0];
            const pct = k[0] !== 0 ? ((chg / k[0]) * 100).toFixed(2) : '0.00';
            const sign = chg >= 0 ? '+' : '';
            html += `📈 开${k[0]} 收${k[1]} 低${k[2]} 高${k[3]} 涨跌 <span style="color:${chg >= 0 ? RED_COLOR : GREEN_COLOR}">${sign}${chg.toFixed(2)}(${sign}${pct}%)</span><br/>`;
          }
        } else {
          const val = typeof p.value === 'number' ? p.value : (p.value?.value ?? 0);
          if (typeof val === 'number' && !isNaN(val)) {
            html += `${p.marker} ${p.seriesName}: ${(val / 1e8).toFixed(2)}亿<br/>`;
          }
        }
      }
      return html;
    } catch {
      return '';
    }
  };

  return {
    tooltip: {
      trigger: 'axis' as const,
      ...(hasKline ? { axisPointer: { type: 'cross' as const } } : {}),
      ...(hasKline ? { formatter: tooltipFormatter } : {}),
    },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    grid: { left: 60, right: hasKline ? 60 : 20, top: 10, bottom: 75 },
    xAxis: { type: 'category' as const, data: dates, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis,
    series,
  };
}

// ── Props ──

export interface StockFundFlowDetailProps {
  tsCode: string | null;
  stockName?: string;
  onClose: () => void;
  days?: number;
}

const StockFundFlowDetail: React.FC<StockFundFlowDetailProps> = ({
  tsCode,
  stockName: extName,
  onClose,
  days = 30,
}) => {
  const [data, setData] = useState<StockTrend | null>(null);
  const [intraday, setIntraday] = useState<StockIntraday | null>(null);
  const [klineData, setKlineData] = useState<KLineItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchTrend = useCallback(async () => {
    if (!tsCode) return;
    setLoading(true);
    try {
      const [trendResult, intradayResult, klineResult] = await Promise.all([
        fundFlowService.getStockTrend(tsCode, days),
        fundFlowService.getStockIntraday(tsCode),
        stockService.getKLine(tsCode, days).then((d) => d.items).catch(() => [] as KLineItem[]),
      ]);
      setData(trendResult);
      setIntraday(intradayResult);
      setKlineData(klineResult);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [tsCode, days]);

  useEffect(() => {
    if (tsCode) {
      fetchTrend();
    } else {
      setData(null);
      setIntraday(null);
    }
  }, [tsCode, fetchTrend]);

  const displayName = extName || data?.stock_name || tsCode || '';

  // 雪球个股链接
  const xueqiuCode = tsCode ? tsCode.replace(/^(\d+)\.(SH|SZ|BJ)$/, '$2$1') : '';
  const xueqiuUrl = xueqiuCode ? `https://xueqiu.com/S/${xueqiuCode}` : '#';

  const open = !!tsCode;

  return (
    <Modal
      title={
        <Space>
          <Tag color="blue">{tsCode}</Tag>
          <a
            href={xueqiuUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: 16, fontWeight: 'bold' }}
          >
            {displayName}
          </a>
          {data?.indices && data.indices.length > 0 && (
            <Text type="secondary" style={{ fontSize: 13 }}>
              · {data.indices.map((idx) => idx.index_name).join(', ')}
            </Text>
          )}
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={960}
      destroyOnClose
      styles={{ body: { maxHeight: '75vh', overflow: 'auto', padding: '16px 24px' } }}
    >
      {loading ? (
        <Spin style={{ display: 'block', padding: 40 }} tip="加载资金流数据..." />
      ) : data && data.days.length > 0 ? (
        <>
          {/* ── 指标卡片行 ── */}
          <Row gutter={[8, 8]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" styles={{ body: { padding: '8px 12px' } }}>
                <Text type="secondary" style={{ fontSize: 11 }}>主力净流入 (最新)</Text>
                <br />
                <Text strong style={{ fontSize: 16, color: posColor(data.days[data.days.length - 1].main_net_flow) }}>
                  {fmtYiShort(data.days[data.days.length - 1].main_net_flow / 1e8)}
                </Text>
              </Card>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" styles={{ body: { padding: '8px 12px' } }}>
                <Text type="secondary" style={{ fontSize: 11 }}>超大单</Text>
                <br />
                <Text strong style={{ fontSize: 15, color: posColor(data.days[data.days.length - 1].jumbo_net_flow) }}>
                  {fmtYiShort(data.days[data.days.length - 1].jumbo_net_flow / 1e8)}
                </Text>
              </Card>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" styles={{ body: { padding: '8px 12px' } }}>
                <Text type="secondary" style={{ fontSize: 11 }}>大单</Text>
                <br />
                <Text strong style={{ fontSize: 15, color: posColor(data.days[data.days.length - 1].block_net_flow) }}>
                  {fmtYiShort(data.days[data.days.length - 1].block_net_flow / 1e8)}
                </Text>
              </Card>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" styles={{ body: { padding: '8px 12px' } }}>
                <Text type="secondary" style={{ fontSize: 11 }}>5日 / 10日 / 20日累计</Text>
                <br />
                <Text strong style={{ fontSize: 13, color: posColor(data.days[data.days.length - 1].main_net_flow_5d) }}>
                  {fmtYiShort(data.days[data.days.length - 1].main_net_flow_5d / 1e8)}
                </Text>
                <Text style={{ fontSize: 11, marginLeft: 6, color: posColor(data.days[data.days.length - 1].main_net_flow_10d) }}>
                  {fmtYiShort(data.days[data.days.length - 1].main_net_flow_10d / 1e8)}
                </Text>
                <Text style={{ fontSize: 11, marginLeft: 6, color: posColor(data.days[data.days.length - 1].main_net_flow_20d) }}>
                  {fmtYiShort(data.days[data.days.length - 1].main_net_flow_20d / 1e8)}
                </Text>
              </Card>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" styles={{ body: { padding: '8px 12px' } }}>
                <Text type="secondary" style={{ fontSize: 11 }}>最新收盘价</Text>
                <br />
                <Text strong style={{ fontSize: 16 }}>
                  {data.days[data.days.length - 1].close_price?.toFixed(2) || '-'}
                </Text>
              </Card>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Card size="small" styles={{ body: { padding: '8px 12px' } }}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {(() => {
                    const last = data.days[data.days.length - 1];
                    const total = last.main_in_flow + last.retail_in_flow;
                    const mainPct = total > 0 ? (last.main_in_flow / total * 100).toFixed(1) : '-';
                    return `主力占比 ${mainPct}%`;
                  })()}
                </Text>
                <br />
                <Text strong style={{ fontSize: 13, color: RED_COLOR }}>
                  主买 {fmtYiShort(data.days[data.days.length - 1].main_in_flow / 1e8)}
                </Text>
                <Text style={{ fontSize: 11, marginLeft: 4, color: GREEN_COLOR }}>
                  主卖 {fmtYiShort(data.days[data.days.length - 1].main_out_flow / 1e8)}
                </Text>
              </Card>
            </Col>
          </Row>

          {/* ── 盘中资金流变化 ── */}
          {intraday && intraday.snapshots.length >= 2 && (
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={24}>
                <Card size="small" title="盘中主力资金流变化">
                  <ReactECharts
                    option={{
                      tooltip: { trigger: 'axis' as const },
                      grid: { left: 60, right: 20, top: 10, bottom: 30 },
                      xAxis: {
                        type: 'category' as const,
                        data: intraday.snapshots.map((s) => {
                          try {
                            const t = new Date(s.snapshot_time);
                            return t.getHours().toString().padStart(2, '0') + ':' +
                                   t.getMinutes().toString().padStart(2, '0');
                          } catch { return s.snapshot_time.slice(11, 16); }
                        }),
                        axisLabel: { fontSize: 10 },
                      },
                      yAxis: {
                        type: 'value' as const,
                        axisLabel: { formatter: (v: number) => (v / 1e8).toFixed(1) + '亿' },
                        splitLine: { lineStyle: { type: 'dashed', color: '#eee' } },
                      },
                      series: [
                        {
                          name: '主力净流入',
                          type: 'line' as const,
                          smooth: true,
                          symbol: 'circle',
                          symbolSize: 6,
                          data: intraday.snapshots.map((s) => ({
                            value: s.main_net_flow,
                            itemStyle: { color: s.main_net_flow >= 0 ? RED_COLOR : GREEN_COLOR },
                          })),
                          lineStyle: { color: '#fa8c16', width: 2 },
                          areaStyle: {
                            color: {
                              type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
                              colorStops: [
                                { offset: 0, color: 'rgba(207,19,34,0.15)' },
                                { offset: 1, color: 'rgba(63,134,0,0.15)' },
                              ],
                            },
                          },
                          markLine: {
                            silent: true,
                            data: [{ yAxis: 0, lineStyle: { color: '#999', type: 'dashed' } }],
                          },
                        },
                      ],
                    }}
                    style={{ height: 250 }}
                  />
                </Card>
              </Col>
            </Row>
          )}

          {/* ── 主力资金流趋势（默认展示） ── */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={24}>
              <Card size="small" title="主力资金流趋势">
                <ReactECharts option={buildMainFlowTrendChart(data.days, klineData)} style={{ height: 360 }} />
              </Card>
            </Col>
          </Row>

          {/* ── 四类订单 + 累计趋势 ── */}
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Card size="small" title="四类订单净流入（超大/大/中/小）" style={{ marginBottom: 12 }}>
                <ReactECharts option={buildOrderFlowChart(data.days)} style={{ height: 250 }} />
              </Card>
            </Col>
            <Col xs={24} md={12}>
              <Card size="small" title="多日累计趋势">
                <ReactECharts option={buildCumTrendChart(data.days)} style={{ height: 250 }} />
              </Card>
            </Col>
          </Row>
        </>
      ) : (
        <Empty description="暂无该股票资金流数据" />
      )}
    </Modal>
  );
};

export default StockFundFlowDetail;
export { buildOrderFlowChart, buildCumTrendChart, buildMainFlowTrendChart, fmtYiShort, posColor };
