import api from './api';

// ── Types ────────────────────────────────────────────────────

export interface HoldingItem {
  ts_code: string;
  stock_name: string;
  shares: number;
  buy_price: number;
}

export interface SaveHoldingsRequest {
  strategy_id: number;
  date: string;
  holdings: HoldingItem[];
  cash?: number;
}

export interface HoldingRecord {
  id: number;
  strategy_id: number;
  date: string;
  ts_code: string;
  stock_name: string;
  shares: number;
  buy_price: number;
  created_at?: string;
}

export interface HoldingsByDate {
  [date: string]: HoldingRecord[];
}

export interface NavPoint {
  date: string;
  holdings_value: number;
  cash: number;
  total_value: number;
}

export interface RecommendationsResponse {
  strategy_id: number;
  strategy_name: string;
  requested_date: string;
  trade_date: string;
  cached: boolean;
  recommendations: Recommendation[];
  total: number;
  message?: string;
}

export interface Recommendation {
  ts_code: string;
  name: string;
  score: number;
  signal: string;
}

// ── Service ──────────────────────────────────────────────────

const BASE = '/strategy-tracker';

export const strategyTrackerService = {
  // 获取策略每日推荐（带缓存 + 交易日回退）
  async getRecommendations(
    strategyId: number,
    date?: string,
    forceRefresh?: boolean,
    m?: number,
    n?: number,
  ): Promise<RecommendationsResponse> {
    const response = await api.get<RecommendationsResponse>(
      `${BASE}/recommendations`,
      { params: { strategy_id: strategyId, date, force_refresh: forceRefresh, m, n } },
    );
    return response.data;
  },

  // 获取最近交易日
  async getLatestTradingDay(date?: string): Promise<{
    requested_date: string;
    trade_date: string;
    is_trading_day: boolean;
  }> {
    const response = await api.get<{
      requested_date: string;
      trade_date: string;
      is_trading_day: boolean;
    }>(`${BASE}/latest-trading-day`, { params: { date } });
    return response.data;
  },

  // 保存持仓
  async saveHoldings(data: SaveHoldingsRequest): Promise<{ message: string; count: number }> {
    const response = await api.post<{ message: string; count: number }>(
      `${BASE}/holdings`,
      data,
    );
    return response.data;
  },

  // 查询持仓历史
  async getHoldings(
    strategyId: number,
    startDate?: string,
    endDate?: string,
  ): Promise<{ items: HoldingsByDate; total_dates: number }> {
    const response = await api.get<{ items: HoldingsByDate; total_dates: number }>(
      `${BASE}/holdings`,
      { params: { strategy_id: strategyId, start_date: startDate, end_date: endDate } },
    );
    return response.data;
  },

  // 计算净值历史
  async getNav(
    strategyId: number,
    startDate?: string,
    endDate?: string,
  ): Promise<{ nav: NavPoint[]; count: number; message?: string }> {
    const response = await api.get<{ nav: NavPoint[]; count: number; message?: string }>(
      `${BASE}/nav`,
      { params: { strategy_id: strategyId, start_date: startDate, end_date: endDate } },
    );
    return response.data;
  },
};

export default strategyTrackerService;
