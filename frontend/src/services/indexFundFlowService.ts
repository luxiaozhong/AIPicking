import api from './api';

// ── 指数信息 ──

export interface IndexInfo {
  index_code: string;
  index_name: string;
  full_name: string;
  publisher: string;
  constituent_count: number;
}

// ── 成分股资金流 ──

export interface ConstituentFlowItem {
  ts_code: string;
  stock_name: string;
  industry_name: string;
  weight: number;
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
  pct_change: number;
}

export interface ConstituentFlowRanking {
  trade_date: string | null;
  items: ConstituentFlowItem[];
}

// ── 多股趋势 ──

export interface TrendDay {
  trade_date: string;
  main_net_flow: number;
  jumbo_net_flow: number;
  block_net_flow: number;
  mid_net_flow: number;
  small_net_flow: number;
  close_price: number;
}

export interface StockTrendSeries {
  ts_code: string;
  stock_name: string;
  days: TrendDay[];
}

export interface MultiStockTrend {
  trade_date: string;
  days: number;
  stocks: StockTrendSeries[];
}

// ── 行业汇总 ──

export interface IndustrySummaryItem {
  industry_name: string;
  main_net_yi: number;
  jumbo_net_yi: number;
  block_net_yi: number;
  positive_pct: number;
  stock_count: number;
}

export interface IndustrySummary {
  trade_date: string | null;
  items: IndustrySummaryItem[];
}

// ── Treemap ──

export interface IndexHistoryItem {
  trade_date: string;
  main_net_yi: number;
  jumbo_net_yi: number;
  block_net_yi: number;
  positive_pct: number;
  stock_count: number;
}

export interface RankingTrendItem {
  ts_code: string;
  stock_name: string;
  dates: string[];
  ranks: number[];
  flows5d: number[];
  flows15d: number[];
  flows: number[];
  improvement: number;
  current_rank: number;
  current_flow_5d: number;
  current_flow_15d: number;
  current_flow: number;
}

export interface RankingTrendData {
  items: RankingTrendItem[];
}

export interface IndexHistory {
  items: IndexHistoryItem[];
}

export interface TreemapItem {
  ts_code: string;
  stock_name: string;
  industry_name: string;
  weight: number;
  main_net_flow: number;
  jumbo_net_flow: number;
  block_net_flow: number;
  mid_net_flow: number;
  small_net_flow: number;
}

export interface TreemapData {
  trade_date: string | null;
  items: TreemapItem[];
}

// ── 盘中快照（Bar Chart Race） ──

export interface SnapshotStock {
  ts_code: string;
  stock_name: string;
  main_net_flow: number;
  jumbo_net_flow: number;
  block_net_flow: number;
  main_net_flow_5d: number;
  main_net_flow_3d: number;
}

export interface SnapshotFrame {
  snapshot_time: string;
  stocks: SnapshotStock[];
}

export interface SnapshotData {
  trade_date: string | null;
  snapshots: SnapshotFrame[];
}

// ── Service ──

export const indexFundFlowService = {
  async getIndices() {
    const { data } = await api.get<{ code: number; data: IndexInfo[] }>(
      '/fund-flow/index/indices'
    );
    return data.data;
  },

  async getConstituentFlow(
    indexCode: string,
    tradeDate?: string,
    sort: string = 'main_net',
    limit: number = 100
  ) {
    const { data } = await api.get<{ code: number; data: ConstituentFlowRanking }>(
      `/fund-flow/index/${encodeURIComponent(indexCode)}/stocks`,
      { params: { trade_date: tradeDate, sort, limit } }
    );
    return data.data;
  },

  async getMultiStockTrend(indexCode: string, days: number = 30, topN: number = 5) {
    const { data } = await api.get<{ code: number; data: MultiStockTrend }>(
      `/fund-flow/index/${encodeURIComponent(indexCode)}/trend`,
      { params: { days, top_n: topN } }
    );
    return data.data;
  },

  async getIndustrySummary(indexCode: string, tradeDate?: string) {
    const { data } = await api.get<{ code: number; data: IndustrySummary }>(
      `/fund-flow/index/${encodeURIComponent(indexCode)}/industry`,
      { params: { trade_date: tradeDate } }
    );
    return data.data;
  },

  async getTreemap(indexCode: string, tradeDate?: string) {
    const { data } = await api.get<{ code: number; data: TreemapData }>(
      `/fund-flow/index/${encodeURIComponent(indexCode)}/treemap`,
      { params: { trade_date: tradeDate } }
    );
    return data.data;
  },

  async getRankingTrend(indexCode: string, days: number = 10) {
    const { data } = await api.get<{ code: number; data: RankingTrendData }>(
      `/fund-flow/index/${encodeURIComponent(indexCode)}/ranking-trend`,
      { params: { days } }
    );
    return data.data;
  },

  async getIndexHistory(indexCode: string, days: number = 30) {
    const { data } = await api.get<{ code: number; data: IndexHistory }>(
      `/fund-flow/index/${encodeURIComponent(indexCode)}/history`,
      { params: { days } }
    );
    return data.data;
  },

  async getSnapshots(indexCode: string, tradeDate?: string) {
    const { data } = await api.get<{ code: number; data: SnapshotData }>(
      `/fund-flow/index/${encodeURIComponent(indexCode)}/snapshots`,
      { params: { trade_date: tradeDate } }
    );
    return data.data;
  },
};
