import api from './api';

// ── 市场总览 ──

export interface FundFlowSummary {
  main_net_yi: number;
  jumbo_net_yi: number;
  block_net_yi: number;
  mid_net_yi: number;
  small_net_yi: number;
  retail_net_yi: number;
  main_in_yi: number;
  main_out_yi: number;
}

export interface BoardItem {
  board_code: string;
  board_name: string;
  main_net_yi: number;
  jumbo_net_yi: number;
  positive_pct: number;
  stock_count: number;
}

export interface BreadthInfo {
  positive_count: number;
  total_count: number;
  positive_pct: number;
}

export interface FundFlowOverview {
  trade_date: string | null;
  summary: FundFlowSummary | null;
  boards: BoardItem[];
  breadth: BreadthInfo | null;
}

// ── 历史时间序列 ──

export interface FundFlowHistoryItem {
  trade_date: string;
  main_net_yi: number;
  jumbo_net_yi: number;
  block_net_yi: number;
  mid_net_yi: number;
  small_net_yi: number;
  retail_net_yi: number;
}

export interface BoardHistoryItem {
  trade_date: string;
  board_code: string;
  board_name: string;
  main_net_yi: number;
}

export interface BreadthHistoryItem {
  trade_date: string;
  positive_pct: number;
  positive_count: number;
  total_count: number;
}

// ── 行业/题材 ──

export interface IndustryFlowItem {
  industry_name: string;
  main_net_yi: number;
  jumbo_net_yi: number;
  block_net_yi: number;
  mid_net_yi: number;
  small_net_yi: number;
  avg_inflow_rate: number;
  positive_pct: number;
  stock_count: number;
}

export interface ConceptFlowItem {
  concept_name: string;
  main_net_yi: number;
  block_net_yi: number;
  mid_net_yi: number;
  small_net_yi: number;
  positive_pct: number;
  stock_count: number;
}

export interface IndustryFlowData {
  trade_date: string | null;
  items: IndustryFlowItem[];
}

export interface ConceptFlowData {
  trade_date: string | null;
  items: ConceptFlowItem[];
}

// ── 热力图 ──

export interface HeatmapRow {
  trade_date: string;
  sector_name: string;
  main_net_yi: number;
}

export interface HeatmapData {
  type: string;
  days: number;
  rows: HeatmapRow[];
}

// ── 个股 ──

export interface StockFlowItem {
  ts_code: string;
  stock_name: string;
  industry_name: string;
  main_net_flow: number;
  jumbo_net_flow: number;
  block_net_flow: number;
  mid_net_flow: number;
  small_net_flow: number;
  main_in_flow: number;
  main_out_flow: number;
  retail_in_flow: number;
  retail_out_flow: number;
  main_net_flow_5d: number;
  main_net_flow_10d: number;
  main_net_flow_20d: number;
  main_inflow_circ_rate: number;
  main_inflow_rank: number | null;
  close_price: number;
}

export interface StockFlowRanking {
  trade_date: string | null;
  items: StockFlowItem[];
}

export interface StockTrendDay {
  trade_date: string;
  main_net_flow: number;
  jumbo_net_flow: number;
  block_net_flow: number;
  mid_net_flow: number;
  small_net_flow: number;
  main_in_flow: number;
  main_out_flow: number;
  retail_in_flow: number;
  retail_out_flow: number;
  main_net_flow_5d: number;
  main_net_flow_10d: number;
  main_net_flow_20d: number;
  close_price: number;
}

export interface IntradaySnapshot {
  snapshot_time: string;
  main_net_flow: number;
  jumbo_net_flow: number;
  block_net_flow: number;
  main_net_flow_5d: number;
}

export interface StockIntraday {
  ts_code: string;
  trade_date: string | null;
  snapshots: IntradaySnapshot[];
}

export interface IndexInfo {
  index_code: string;
  index_name: string;
}

export interface StockTrend {
  ts_code: string;
  stock_name: string;
  indices: IndexInfo[];
  days: StockTrendDay[];
}

// ── Service ──

export const fundFlowService = {
  async getOverview(tradeDate?: string) {
    const { data } = await api.get<{ code: number; data: FundFlowOverview }>(
      '/fund-flow/overview',
      { params: { trade_date: tradeDate } }
    );
    return data.data;
  },

  async getHistory(days: number = 30) {
    const { data } = await api.get<{ code: number; data: FundFlowHistoryItem[] }>(
      '/fund-flow/history',
      { params: { days } }
    );
    return data.data;
  },

  async getBoardHistory(days: number = 30) {
    const { data } = await api.get<{ code: number; data: BoardHistoryItem[] }>(
      '/fund-flow/board-history',
      { params: { days } }
    );
    return data.data;
  },

  async getIndustryFlow(tradeDate?: string, sort: string = 'net', limit: number = 50) {
    const { data } = await api.get<{ code: number; data: IndustryFlowData }>(
      '/fund-flow/industry',
      { params: { trade_date: tradeDate, sort, limit } }
    );
    return data.data;
  },

  async getConceptFlow(tradeDate?: string, sort: string = 'net', limit: number = 50) {
    const { data } = await api.get<{ code: number; data: ConceptFlowData }>(
      '/fund-flow/concept',
      { params: { trade_date: tradeDate, sort, limit } }
    );
    return data.data;
  },

  async getHeatmap(days: number = 20, sectorType: 'industry' | 'concept' = 'industry') {
    const { data } = await api.get<{ code: number; data: HeatmapData }>(
      '/fund-flow/heatmap',
      { params: { days, sector_type: sectorType } }
    );
    return data.data;
  },

  async getStockRanking(tradeDate?: string, sort: string = 'main_net', limit: number = 100, board?: string) {
    const { data } = await api.get<{ code: number; data: StockFlowRanking }>(
      '/fund-flow/stocks',
      { params: { trade_date: tradeDate, sort, limit, board } }
    );
    return data.data;
  },

  async getStockTrend(tsCode: string, days: number = 30) {
    const { data } = await api.get<{ code: number; data: StockTrend }>(
      `/fund-flow/stocks/${encodeURIComponent(tsCode)}/trend`,
      { params: { days } }
    );
    return data.data;
  },

  async getBreadthHistory(days: number = 30) {
    const { data } = await api.get<{ code: number; data: BreadthHistoryItem[] }>(
      '/fund-flow/breadth-history',
      { params: { days } }
    );
    return data.data;
  },

  async getStockIntraday(tsCode: string, tradeDate?: string) {
    const { data } = await api.get<{ code: number; data: StockIntraday }>(
      `/fund-flow/stocks/${encodeURIComponent(tsCode)}/intraday`,
      { params: { trade_date: tradeDate } }
    );
    return data.data;
  },

  async getAvailableDates(days: number = 60) {
    const { data } = await api.get<{ code: number; data: string[] }>(
      '/fund-flow/available-dates',
      { params: { days } }
    );
    return data.data;
  },
};
