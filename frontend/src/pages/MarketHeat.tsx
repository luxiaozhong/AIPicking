import React, { useEffect, useState } from 'react';
import { Row, Col, Card, Tabs, Table, Tag, DatePicker, Alert, Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useMarketHeatStore } from '@/stores/marketHeatStore';
import TemperatureCard from '@/components/market-heat/TemperatureCard';
import SectorTreemap from '@/components/market-heat/SectorTreemap';
import ThemeWordCloud from '@/components/market-heat/ThemeWordCloud';
import SectorDrawer from '@/components/market-heat/SectorDrawer';
import ThemeDrawer from '@/components/market-heat/ThemeDrawer';
import StockKLineModal from '@/components/shared/StockKLineModal';
import KpiDetailModal from '@/components/market-heat/KpiDetailModal';
import type { SectorItem, ThemeItem, HotStockItem, DragonTigerItem } from '@/services/marketHeatService';

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

  useEffect(() => {
    store.fetchAvailableDates();
  }, []);

  useEffect(() => {
    if (store.tradeDate) {
      store.fetchOverview();
      store.fetchSectors();
      store.fetchThemes();
      store.fetchHotStocks(1);
      store.fetchDragonTiger(1);
      store.fetchNorthbound();
    }
  }, [store.tradeDate]);

  const handleRefresh = () => {
    store.fetchOverview();
    store.fetchSectors();
    store.fetchThemes();
    store.fetchHotStocks();
    store.fetchDragonTiger();
    store.fetchNorthbound();
  };

  const handleStockClick = (code: string, name: string) => {
    setKlineStock({ ts_code: toTsCode(code), name });
  };

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
    </div>
  );
};

export default MarketHeat;
