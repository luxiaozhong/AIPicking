import React, { useEffect } from 'react';
import { Row, Col, Card, Tabs, Table, Tag, DatePicker, Alert, Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useMarketHeatStore } from '@/stores/marketHeatStore';
import TemperatureCard from '@/components/market-heat/TemperatureCard';
import SectorTreemap from '@/components/market-heat/SectorTreemap';
import ThemeWordCloud from '@/components/market-heat/ThemeWordCloud';
import SectorDrawer from '@/components/market-heat/SectorDrawer';
import ThemeDrawer from '@/components/market-heat/ThemeDrawer';
import type { SectorItem, ThemeItem, HotStockItem, DragonTigerItem } from '@/services/marketHeatService';

const MarketHeat: React.FC = () => {
  const store = useMarketHeatStore();

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

  const hotStockColumns = [
    { title: '股票', dataIndex: 'stock_name', key: 'stock_name', width: 100 },
    {
      title: '涨幅',
      dataIndex: 'change_pct',
      key: 'change_pct',
      width: 80,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#cf1322' : '#389e0d', fontWeight: 600 }}>
          {v > 0 ? '+' : ''}{v?.toFixed(2)}%
        </span>
      ),
    },
    {
      title: '换手率', dataIndex: 'turnover_pct', key: 'turnover_pct', width: 80,
      render: (v: number) => `${v?.toFixed(2)}%`,
    },
    { title: '收盘价', dataIndex: 'close', key: 'close', width: 80, render: (v: number) => v?.toFixed(2) },
    {
      title: '上涨原因', dataIndex: 'reason', key: 'reason',
      render: (v: string) => (v || '').split('+').map((tag: string, i: number) => (
        <Tag key={i} color="blue" style={{ marginBottom: 2 }}>{tag.trim()}</Tag>
      )),
    },
  ];

  const dragonColumns = [
    { title: '股票', dataIndex: 'stock_name', key: 'stock_name', width: 100 },
    {
      title: '涨幅', dataIndex: 'change_pct', key: 'change_pct', width: 80,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#cf1322' : '#389e0d', fontWeight: 600 }}>
          {v > 0 ? '+' : ''}{v?.toFixed(2)}%
        </span>
      ),
    },
    {
      title: '净买入(万)', dataIndex: 'net_buy_wan', key: 'net_buy_wan', width: 100,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#cf1322' : '#389e0d', fontWeight: 600 }}>
          {v > 0 ? '+' : ''}{v?.toFixed(0)}
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
          onRow={(record: HotStockItem) => ({
            style: { cursor: 'pointer' },
            onClick: () => window.open(`/strategies/${record.stock_code}`, '_blank'),
          })}
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
            value={store.tradeDate ? dayjs(store.tradeDate, 'YYYYMMDD') : null}
            onChange={(d) => d && store.setTradeDate(d.format('YYYYMMDD'))}
            allowClear={false}
            format="YYYY-MM-DD"
            disabledDate={(d) => {
              if (!store.availableDates.length) return false;
              return !store.availableDates.includes(d.format('YYYYMMDD'));
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
        <TemperatureCard overview={store.overview} loading={store.overviewLoading} />
      </div>

      {/* 第二层: 可视化 */}
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
        </Col>
      </Row>

      {/* 第三层: 明细列表 */}
      <Card>
        <Tabs items={tabItems} />
      </Card>

      {/* 抽屉 */}
      <SectorDrawer
        open={store.drawer.open && store.drawer.type === 'sector'}
        sectorCode={store.drawer.code}
        sectorName={store.drawer.name}
        tradeDate={store.tradeDate}
        onClose={store.closeDrawer}
      />
      <ThemeDrawer
        open={store.drawer.open && store.drawer.type === 'theme'}
        themeName={store.drawer.name}
        tradeDate={store.tradeDate}
        onClose={store.closeDrawer}
      />
    </div>
  );
};

export default MarketHeat;
