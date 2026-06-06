import React, { useEffect, useMemo, useState } from 'react';
import { Row, Col, Card, Tabs, Table, Tag, DatePicker, Alert, Button, Modal, Empty, Spin } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { useMarketHeatStore } from '@/stores/marketHeatStore';
import TemperatureCard from '@/components/market-heat/TemperatureCard';
import SectorTreemap from '@/components/market-heat/SectorTreemap';
import ThemeWordCloud from '@/components/market-heat/ThemeWordCloud';
import SectorDrawer from '@/components/market-heat/SectorDrawer';
import ThemeDrawer from '@/components/market-heat/ThemeDrawer';
import StockKLineModal from '@/components/shared/StockKLineModal';
import KpiDetailModal from '@/components/market-heat/KpiDetailModal';
import type { SectorItem, ThemeItem, HotStockItem, DragonTigerItem, SectorFundHistoryItem } from '@/services/marketHeatService';

/** 纯数字股票代码 → ts_code（6→SH，其他→SZ）；已有后缀则原样返回 */
function toTsCode(code: string): string {
  if (code.includes('.')) return code;
  if (code.startsWith('6') || code.startsWith('9')) return `${code}.SH`;
  return `${code}.SZ`;
}

const MarketHeat: React.FC = () => {
  const store = useMarketHeatStore();
  const [klineStock, setKlineStock] = useState<{ ts_code: string; name: string } | null>(null);
  const [kpiDetail, setKpiDetail] = useState<{
    type: 'northbound' | 'advance_decline' | 'leading_sector' | 'lagging_sector';
    sectorName?: string;
  } | null>(null);
  const [temperatureModalOpen, setTemperatureModalOpen] = useState(false);
  const [boardTempModal, setBoardTempModal] = useState<{
    boardCode: string;
    boardName: string;
  } | null>(null);
  const [sectorFundModalOpen, setSectorFundModalOpen] = useState(false);

  useEffect(() => {
    store.fetchAvailableDates();
    store.fetchTemperatureHistory();
  }, []);

  useEffect(() => {
    if (store.tradeDate) {
      store.fetchOverview();
      store.fetchSectors();
      store.fetchThemes();
      store.fetchHotStocks(1);
      store.fetchDragonTiger(1);
      store.fetchNorthbound();
      store.fetchSectorFundOverview();
    }
  }, [store.tradeDate]);

  const handleRefresh = () => {
    store.fetchOverview();
    store.fetchSectors();
    store.fetchThemes();
    store.fetchHotStocks();
    store.fetchDragonTiger();
    store.fetchNorthbound();
    store.fetchSectorFundOverview();
  };

  const sectorFundHistoryChartOption = useMemo(() => {
    const data = store.sectorFundHistory;
    if (!data.length) return {};
    const dates = data.map((d) => d.trade_date.slice(5));
    const totals = data.map((d) => d.total_net_yi);
    const positiveColor = '#cf1322';
    const negativeColor = '#389e0d';
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const p = params[0];
          if (!p) return '';
          const v = p.value;
          return `<strong>${p.axisValue}</strong><br/>全行业资金净额: <b style="color:${v >= 0 ? positiveColor : negativeColor}">${v > 0 ? '+' : ''}${v.toFixed(1)}亿</b>`;
        },
      },
      grid: { left: 60, right: 30, top: 20, bottom: 40 },
      xAxis: { type: 'category', data: dates, axisLabel: { rotate: 45, fontSize: 10 } },
      yAxis: {
        type: 'value',
        name: '净额(亿)',
        splitLine: { lineStyle: { type: 'dashed' } },
        axisLabel: { formatter: (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(0)}` },
      },
      series: [{
        type: 'bar',
        data: totals,
        itemStyle: {
          color: (params: any) => params.value >= 0 ? '#cf1322' : '#389e0d',
        },
        emphasis: {
          itemStyle: { opacity: 0.8 },
        },
      }],
    };
  }, [store.sectorFundHistory]);

  const handleStockClick = (code: string, name: string) => {
    setKlineStock({ ts_code: toTsCode(code), name });
  };

  const temperatureChartOption = useMemo(() => {
    const data = store.temperatureHistory;
    if (!data.length) return {};
    const dates = data.map((d) => d.trade_date.slice(5));
    const scores = data.map((d) => d.score);
    const levels = data.map((d) => d.level);
    const markAreas: any[] = [
      [{ yAxis: 0, itemStyle: { color: 'rgba(24,144,255,0.08)' } }, { yAxis: 30, label: { show: true, position: 'insideLeft', formatter: '冰点', fontSize: 10 } }],
      [{ yAxis: 30 }, { yAxis: 50, itemStyle: { color: 'rgba(82,196,26,0.06)' }, label: { show: true, position: 'insideLeft', formatter: '偏冷', fontSize: 10 } }],
      [{ yAxis: 50 }, { yAxis: 70, itemStyle: { color: 'rgba(250,173,20,0.06)' } }],
      [{ yAxis: 70 }, { yAxis: 85, itemStyle: { color: 'rgba(255,122,69,0.06)' }, label: { show: true, position: 'insideLeft', formatter: '偏热', fontSize: 10 } }],
      [{ yAxis: 85 }, { yAxis: 100, itemStyle: { color: 'rgba(255,77,79,0.08)' }, label: { show: true, position: 'insideLeft', formatter: '过热', fontSize: 10 } }],
    ];
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const p = params[0];
          if (!p) return '';
          const idx = p.dataIndex;
          const dims = data[idx]?.dimensions;
          if (!dims) return `${p.axisValue}<br/>温度: ${p.value}°`;
          return `<strong>${p.axisValue}</strong><br/>温度: <b>${p.value}°</b> (${levels[idx]})<br/><span style="font-size:11px">资金面:${dims.capital}/20 | 涨跌结构:${dims.breadth}/20<br/>情绪面:${dims.sentiment}/20 | 集中度:${dims.concentration}/20 | 延续:${dims.continuity}/20</span>`;
        },
      },
      grid: { left: 60, right: 30, top: 20, bottom: 40 },
      xAxis: { type: 'category', data: dates, axisLabel: { rotate: 45, fontSize: 10 } },
      yAxis: { type: 'value', min: 0, max: 100, name: '温度', splitLine: { lineStyle: { type: 'dashed' } } },
      series: [{
        type: 'line', data: scores, smooth: true, symbol: 'circle', symbolSize: 6,
        lineStyle: { width: 2.5, color: '#1677ff' }, itemStyle: { color: '#1677ff' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(22,119,255,0.25)' }, { offset: 1, color: 'rgba(22,119,255,0.02)' }] } },
        markArea: { silent: true, data: markAreas },
      }],
    };
  }, [store.temperatureHistory]);

  const boardTemperatureChartOption = useMemo(() => {
    const data = store.boardTemperatureHistory;
    if (!data.length) return {};
    const dates = data.map((d) => d.trade_date.slice(5));
    const scores = data.map((d) => d.score);
    const levels = data.map((d) => d.level);
    const markAreas: any[] = [
      [{ yAxis: 0, itemStyle: { color: 'rgba(24,144,255,0.08)' } }, { yAxis: 30, label: { show: true, position: 'insideLeft', formatter: '冰点', fontSize: 10 } }],
      [{ yAxis: 30 }, { yAxis: 50, itemStyle: { color: 'rgba(82,196,26,0.06)' }, label: { show: true, position: 'insideLeft', formatter: '偏冷', fontSize: 10 } }],
      [{ yAxis: 50 }, { yAxis: 70, itemStyle: { color: 'rgba(250,173,20,0.06)' } }],
      [{ yAxis: 70 }, { yAxis: 85, itemStyle: { color: 'rgba(255,122,69,0.06)' }, label: { show: true, position: 'insideLeft', formatter: '偏热', fontSize: 10 } }],
      [{ yAxis: 85 }, { yAxis: 100, itemStyle: { color: 'rgba(255,77,79,0.08)' }, label: { show: true, position: 'insideLeft', formatter: '过热', fontSize: 10 } }],
    ];
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const p = params[0];
          if (!p) return '';
          const idx = p.dataIndex;
          const dims = data[idx]?.dimensions;
          if (!dims) return `${p.axisValue}<br/>温度: ${p.value}°`;
          return `<strong>${p.axisValue}</strong><br/>温度: <b>${p.value}°</b> (${levels[idx]})<br/><span style="font-size:11px">涨跌结构:${dims.breadth}/40 | 情绪面:${dims.sentiment}/30 | 量能:${dims.volume}/30</span>`;
        },
      },
      grid: { left: 60, right: 30, top: 20, bottom: 40 },
      xAxis: { type: 'category', data: dates, axisLabel: { rotate: 45, fontSize: 10 } },
      yAxis: { type: 'value', min: 0, max: 100, name: '温度', splitLine: { lineStyle: { type: 'dashed' } } },
      series: [{
        type: 'line', data: scores, smooth: true, symbol: 'circle', symbolSize: 6,
        lineStyle: { width: 2.5, color: '#1677ff' }, itemStyle: { color: '#1677ff' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(22,119,255,0.25)' }, { offset: 1, color: 'rgba(22,119,255,0.02)' }] } },
        markArea: { silent: true, data: markAreas },
      }],
    };
  }, [store.boardTemperatureHistory]);

  /** 可点击的股票名链接 */
  const stockNameLink = (code: string, name: string) => (
    <a onClick={(e) => { e.stopPropagation(); handleStockClick(code, name); }}>
      {name}
    </a>
  );

  const hotStockColumns = [
    {
      title: '股票', dataIndex: 'stock_name', key: 'stock_name', width: 100,
      render: (_: string, r: HotStockItem) => stockNameLink(r.stock_code, r.stock_name),
    },
    {
      title: '涨幅',
      dataIndex: 'change_pct',
      key: 'change_pct',
      width: 80,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#cf1322' : '#389e0d', fontWeight: 600 }}>
          {v != null ? `${v > 0 ? '+' : ''}${v.toFixed(2)}%` : '-'}
        </span>
      ),
    },
    {
      title: '换手率', dataIndex: 'turnover_pct', key: 'turnover_pct', width: 80,
      render: (v: number) => v != null ? `${v.toFixed(2)}%` : '-',
    },
    {
      title: '收盘价', dataIndex: 'close', key: 'close', width: 80,
      render: (v: number) => v != null ? v.toFixed(2) : '-',
    },
    {
      title: '上涨原因', dataIndex: 'reason', key: 'reason',
      render: (v: string) => (v || '').split('+').map((tag: string, i: number) => (
        <Tag key={i} color="blue" style={{ marginBottom: 2 }}>{tag.trim()}</Tag>
      )),
    },
  ];

  const dragonColumns = [
    {
      title: '股票', dataIndex: 'stock_name', key: 'stock_name', width: 100,
      render: (_: string, r: DragonTigerItem) => stockNameLink(r.stock_code, r.stock_name),
    },
    {
      title: '涨幅', dataIndex: 'change_pct', key: 'change_pct', width: 80,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#cf1322' : '#389e0d', fontWeight: 600 }}>
          {v != null ? `${v > 0 ? '+' : ''}${v.toFixed(2)}%` : '-'}
        </span>
      ),
    },
    {
      title: '净买入(万)', dataIndex: 'net_buy_wan', key: 'net_buy_wan', width: 100,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#cf1322' : '#389e0d', fontWeight: 600 }}>
          {v != null ? `${v > 0 ? '+' : ''}${v.toFixed(0)}` : '-'}
        </span>
      ),
    },
    { title: '上榜原因', dataIndex: 'reason', key: 'reason', ellipsis: true },
  ];

  const tabItems = [
    {
      key: 'hot-stocks',
      label: '热门股票',
      children: (
        <Table
          dataSource={store.hotStocks}
          columns={hotStockColumns}
          rowKey="stock_code"
          size="small"
          loading={store.hotStocksLoading}
          pagination={{
            current: store.hotStocksPage,
            total: store.hotStocksTotal,
            pageSize: 20,
            onChange: (p) => store.fetchHotStocks(p),
            showSizeChanger: false,
          }}
        />
      ),
    },
    {
      key: 'dragon-tiger',
      label: '龙虎榜',
      children: (
        <Table
          dataSource={store.dragonTiger}
          columns={dragonColumns}
          rowKey="stock_code"
          size="small"
          loading={store.dragonTigerLoading}
          expandable={{
            expandedRowRender: (record: DragonTigerItem) => (
              <Table
                dataSource={record.seats || []}
                columns={[
                  { title: '席位', dataIndex: 'seat_name', key: 'seat_name' },
                  {
                    title: '类型',
                    dataIndex: 'seat_type',
                    key: 'seat_type',
                    render: (v: string) => v === 'buy' ? '买入' : '卖出',
                  },
                  { title: '买入(万)', dataIndex: 'buy_amt_wan', key: 'buy_amt_wan', render: (v: number) => v?.toFixed(0) },
                  { title: '卖出(万)', dataIndex: 'sell_amt_wan', key: 'sell_amt_wan', render: (v: number) => v?.toFixed(0) },
                  {
                    title: '净额(万)',
                    dataIndex: 'net_amt_wan',
                    key: 'net_amt_wan',
                    render: (v: number) => (
                      <span style={{ color: v >= 0 ? '#cf1322' : '#389e0d' }}>{v?.toFixed(0)}</span>
                    ),
                  },
                  {
                    title: '机构',
                    dataIndex: 'is_institution',
                    key: 'is_institution',
                    render: (v: boolean) => v ? <Tag color="volcano">机构</Tag> : null,
                  },
                ]}
                rowKey={(r: any) => `${r.seat_type}-${r.rank}`}
                size="small"
                pagination={false}
              />
            ),
          }}
          pagination={{
            current: store.dragonTigerPage,
            total: store.dragonTigerTotal,
            pageSize: 20,
            onChange: (p) => store.fetchDragonTiger(p),
            showSizeChanger: false,
          }}
        />
      ),
    },
  ];

  return (
    <div>
      {/* 顶部栏：日期选择 + 刷新 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>市场热度</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <DatePicker
            value={store.tradeDate ? dayjs(store.tradeDate) : null}
            onChange={(d) => d && store.setTradeDate(d.format('YYYY-MM-DD'))}
            allowClear={false}
            format="YYYY-MM-DD"
            disabledDate={(d) => {
              if (!store.availableDates.length) return false;
              return !store.availableDates.includes(d.format('YYYY-MM-DD'));
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={handleRefresh}>刷新</Button>
        </div>
      </div>

      {store.error && (
        <Alert message={store.error} type="error" closable style={{ marginBottom: 16 }} onClose={store.clearError} />
      )}

      {/* 第一层: KPI 卡片 */}
      <div style={{ marginBottom: 16 }}>
        <TemperatureCard
          overview={store.overview}
          loading={store.overviewLoading}
          sectorFundTotalYI={store.sectorFundOverview?.total_net_yi ?? null}
          sectorFundLoading={store.sectorFundOverviewLoading}
          onTemperatureClick={() => setTemperatureModalOpen(true)}
          onNorthboundClick={() => setKpiDetail({ type: 'northbound' })}
          onAdvanceDeclineClick={() => setKpiDetail({ type: 'advance_decline' })}
          onLeadingSectorClick={(name) => setKpiDetail({
            type: 'leading_sector',
            sectorName: name,
          })}
          onLaggingSectorClick={(name) => setKpiDetail({
            type: 'lagging_sector',
            sectorName: name,
          })}
          onBoardTemperatureClick={(boardCode, boardName) => {
            setBoardTempModal({ boardCode, boardName });
            store.fetchBoardTemperatureHistory(boardCode);
          }}
          onSectorFundClick={() => {
            setSectorFundModalOpen(true);
            store.fetchSectorFundHistory();
          }}
        />
      </div>

      {/* 第二层: 可视化 + 明细 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={16}>
          <SectorTreemap
            sectors={store.sectors}
            sectorType={store.sectorType}
            loading={store.sectorsLoading}
            onSectorTypeChange={store.setSectorType}
            onSectorClick={(s: SectorItem) => store.openDrawer('sector', s.sector_code, s.sector_name)}
          />
        </Col>
        <Col xs={24} lg={8}>
          <ThemeWordCloud
            themes={store.themes}
            loading={store.themesLoading}
            onThemeClick={(t: ThemeItem) => store.openDrawer('theme', t.theme_name, t.theme_name)}
          />
          <Card style={{ marginTop: 16 }}>
            <Tabs items={tabItems} />
          </Card>
        </Col>
      </Row>

      {/* 抽屉 */}
      <SectorDrawer
        open={store.drawer.open && store.drawer.type === 'sector'}
        sectorCode={store.drawer.code}
        sectorName={store.drawer.name}
        tradeDate={store.tradeDate}
        onClose={store.closeDrawer}
        onStockClick={handleStockClick}
      />
      <ThemeDrawer
        open={store.drawer.open && store.drawer.type === 'theme'}
        themeName={store.drawer.name}
        tradeDate={store.tradeDate}
        onClose={store.closeDrawer}
        onStockClick={handleStockClick}
      />

      {/* K线弹窗 */}
      <StockKLineModal
        ts_code={klineStock?.ts_code ?? ''}
        name={klineStock?.name}
        open={!!klineStock}
        onClose={() => setKlineStock(null)}
      />

      {/* KPI 详情弹窗 */}
      <KpiDetailModal
        open={!!kpiDetail}
        type={kpiDetail?.type ?? null}
        tradeDate={store.tradeDate}
        sectorName={kpiDetail?.sectorName}
        onClose={() => setKpiDetail(null)}
        onStockClick={handleStockClick}
      />

      <Modal
        title="市场温度 · 近 60 日趋势"
        open={temperatureModalOpen}
        onCancel={() => setTemperatureModalOpen(false)}
        footer={null}
        width={800}
        destroyOnClose
      >
        {store.temperatureHistoryLoading ? (
          <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
        ) : store.temperatureHistory.length > 0 ? (
          <ReactECharts option={temperatureChartOption} style={{ height: 400 }} />
        ) : (
          <Empty description="暂无历史温度数据" />
        )}
      </Modal>

      <Modal
        title={`${boardTempModal?.boardName ?? ''} 板块温度 · 近 60 日趋势`}
        open={!!boardTempModal}
        onCancel={() => setBoardTempModal(null)}
        footer={null}
        width={800}
        destroyOnClose
      >
        {store.boardTemperatureHistoryLoading ? (
          <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
        ) : store.boardTemperatureHistory.length > 0 ? (
          <ReactECharts option={boardTemperatureChartOption} style={{ height: 400 }} />
        ) : (
          <Empty description={`暂无${boardTempModal?.boardName ?? ''}板块温度历史数据`} />
        )}
      </Modal>

      <Modal
        title="板块资金流 · 近 3 个月趋势"
        open={sectorFundModalOpen}
        onCancel={() => setSectorFundModalOpen(false)}
        footer={null}
        width={900}
        destroyOnClose
      >
        {store.sectorFundHistoryLoading ? (
          <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
        ) : store.sectorFundHistory.length > 0 ? (
          <ReactECharts option={sectorFundHistoryChartOption} style={{ height: 420 }} />
        ) : (
          <Empty description="暂无板块资金流历史数据" />
        )}
        {store.sectorFundHistory.length > 0 && (
          <div style={{ marginTop: 12, fontSize: 12, color: '#666', textAlign: 'center' }}>
            近 90 个交易日全行业资金净额合计 · 红柱为净流入，绿柱为净流出
          </div>
        )}
      </Modal>
    </div>
  );
};

export default MarketHeat;
