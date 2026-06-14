import api from './api';

export interface RebalanceReport {
  id: number;
  strategy_id: number;
  strategy_name?: string;
  name?: string;
  status: string;
  start_date: string;
  end_date: string;
  config: {
    N: number;
    M: number;
    index_code: string;
    initial_capital: number;
    variant?: string;  // "flow" | "value"
  } | null;
  total_days: number;
  completed_days: number;
  daily_snapshots: DailySnapshot[] | null;
  trades: TradeRecord[] | null;
  summary: RebalanceSummary | null;
  error_message?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
}

export interface DailySnapshot {
  date: string;
  holdings: HoldingItem[];
  cash: number;
  total_value: number;
  daily_return_pct: number;
  action: 'rebalance' | 'hold';
}

export interface HoldingItem {
  ts_code: string;
  name: string;
  shares: number;
  buy_price: number;
  buy_cost: number;
  close_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

export interface TradeRecord {
  date: string;
  ts_code: string;
  name: string;
  action: 'buy' | 'sell';
  price: number;
  shares: number;
  amount: number;
  // 买入字段
  commission?: number;
  total_cost?: number;
  // 卖出字段
  stamp_duty?: number;
  net_proceeds?: number;
  buy_cost?: number;
  pnl?: number;
  pnl_pct?: number;
  reason: string;
}

export interface RebalanceSummary {
  initial_capital: number;
  final_value: number;
  total_return_pct: number;
  annualized_return_pct: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  total_trading_days: number;
  total_trades: number;
  total_buys: number;
  total_sells: number;
  turnover_rate: number;
  avg_daily_return_pct: number;
  win_days: number;
  lose_days: number;
  daily_win_rate: number;
  total_fees_paid: number;
  realized_pnl: number;
  win_trades: number;
  lose_trades: number;
}

export interface RebalanceCreate {
  strategy_id: number;
  start_date: string;   // YYYYMMDD
  end_date: string;     // YYYYMMDD
  name?: string;
  initial_capital: number;
  config?: Record<string, any>;
}

export interface RebalanceListResponse {
  items: RebalanceReport[];
  total: number;
  page: number;
  limit: number;
}

const BASE = '/rebalance';

export const rebalanceService = {
  async create(data: RebalanceCreate): Promise<RebalanceReport> {
    const response = await api.post<RebalanceReport>(BASE, data);
    return response.data;
  },

  async getList(params: {
    page?: number;
    limit?: number;
    strategy_id?: number;
    status?: string;
  } = {}): Promise<RebalanceListResponse> {
    const response = await api.get<RebalanceListResponse>(BASE, { params });
    return response.data;
  },

  async getDetail(id: number): Promise<RebalanceReport> {
    const response = await api.get<RebalanceReport>(`${BASE}/${id}`);
    return response.data;
  },

  async delete(id: number): Promise<void> {
    await api.delete(`${BASE}/${id}`);
  },
};

export default rebalanceService;
