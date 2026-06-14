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

export interface StrategyExecuteResponse {
  strategy_id: number;
  strategy_name: string;
  cutoff_date: string;
  recommendations: Recommendation[];
  total: number;
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
