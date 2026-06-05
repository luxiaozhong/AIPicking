import api from './api';

export interface OverviewData {
  trade_date: string | null;
  temperature: {
    score: number;
    level: string;
    dimensions: Record<string, number>;
  } | null;
  northbound: {
    trade_date: string;
    hgt_net_yi: number;
    sgt_net_yi: number;
    total_net_yi: number;
  } | null;
  advance_decline: {
    total: number;
    up_count: number;
    down_count: number;
  } | null;
  leading_sector: {
    sector_name: string;
    change_pct: number;
    main_net_yi: number;
  } | null;
}

export interface SectorItem {
  trade_date: string;
  sector_type: string;
  sector_code: string;
  sector_name: string;
  change_pct: number;
  up_count: number;
  down_count: number;
  leader_stock: string;
  leader_change: number;
  main_net_yi: number;
  net_inflow: number;
  rank: number;
}

export interface SectorDetail {
  info: SectorItem | null;
  trend: SectorItem[];
  stocks: { ts_code: string; name: string; close: number; open: number }[];
}

export interface ThemeItem {
  trade_date: string;
  theme_name: string;
  stock_count: number;
}

export interface HotStockItem {
  trade_date: string;
  stock_code: string;
  stock_name: string;
  close: number;
  change_pct: number;
  turnover_pct: number;
  reason: string;
  dde_net: number;
  sort_order: number;
}

export interface DragonTigerItem {
  trade_date: string;
  stock_code: string;
  stock_name: string;
  reason: string;
  close: number;
  change_pct: number;
  turnover_pct: number;
  net_buy_wan: number;
  buy_wan: number;
  sell_wan: number;
  seats: {
    seat_type: string;
    rank: number;
    seat_name: string;
    buy_amt_wan: number;
    sell_amt_wan: number;
    net_amt_wan: number;
    is_institution: boolean;
  }[];
}

export interface NorthboundItem {
  trade_date: string;
  hgt_net_yi: number;
  sgt_net_yi: number;
  total_net_yi: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
}

export const marketHeatService = {
  async getOverview(tradeDate?: string) {
    const response = await api.get<{ code: number; data: OverviewData }>(
      '/market-heat/overview',
      { params: { trade_date: tradeDate } },
    );
    return response.data.data;
  },

  async getSectors(tradeDate?: string, sectorType: 'industry' | 'concept' = 'industry') {
    const response = await api.get<{ code: number; data: SectorItem[] }>(
      '/market-heat/sectors',
      { params: { trade_date: tradeDate, sector_type: sectorType } },
    );
    return response.data.data;
  },

  async getSectorDetail(sectorCode: string, tradeDate?: string, days: number = 10) {
    const response = await api.get<{ code: number; data: SectorDetail }>(
      `/market-heat/sectors/${sectorCode}`,
      { params: { trade_date: tradeDate, days } },
    );
    return response.data.data;
  },

  async getThemes(tradeDate?: string, limit: number = 20) {
    const response = await api.get<{ code: number; data: ThemeItem[] }>(
      '/market-heat/themes',
      { params: { trade_date: tradeDate, limit } },
    );
    return response.data.data;
  },

  async getThemeDetail(themeName: string, tradeDate?: string) {
    const response = await api.get<{ code: number; data: HotStockItem[] }>(
      `/market-heat/themes/${encodeURIComponent(themeName)}`,
      { params: { trade_date: tradeDate } },
    );
    return response.data.data;
  },

  async getHotStocks(tradeDate?: string, page: number = 1, pageSize: number = 20) {
    const response = await api.get<{ code: number; data: PaginatedResponse<HotStockItem> }>(
      '/market-heat/hot-stocks',
      { params: { trade_date: tradeDate, page, page_size: pageSize } },
    );
    return response.data.data;
  },

  async getDragonTiger(tradeDate?: string, page: number = 1, pageSize: number = 20) {
    const response = await api.get<{ code: number; data: PaginatedResponse<DragonTigerItem> }>(
      '/market-heat/dragon-tiger',
      { params: { trade_date: tradeDate, page, page_size: pageSize } },
    );
    return response.data.data;
  },

  async getNorthbound(days: number = 30) {
    const response = await api.get<{ code: number; data: NorthboundItem[] }>(
      '/market-heat/northbound',
      { params: { days } },
    );
    return response.data.data;
  },

  async getAvailableDates(days: number = 20) {
    const response = await api.get<{ code: number; data: string[] }>(
      '/market-heat/available-dates',
      { params: { days } },
    );
    return response.data.data;
  },

  async getChangeDistribution(tradeDate?: string) {
    const response = await api.get<{ code: number; data: ChangeBucket[] }>(
      '/market-heat/change-distribution',
      { params: { trade_date: tradeDate } },
    );
    return response.data.data;
  },

  async getLeadingSectorStocks(sectorName: string, tradeDate?: string) {
    const response = await api.get<{ code: number; data: LeadingStock[] }>(
      '/market-heat/leading-sector-stocks',
      { params: { sector_name: sectorName, trade_date: tradeDate } },
    );
    return response.data.data;
  },
};

export interface ChangeBucket {
  label: string;
  lo: number;
  hi: number;
  count: number;
}

export interface LeadingStock {
  ts_code: string;
  name: string;
  close: number;
  open: number;
  change_pct: number | null;
}

export default marketHeatService;
