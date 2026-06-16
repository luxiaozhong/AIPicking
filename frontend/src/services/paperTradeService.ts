import api from './api';

// ── Types ────────────────────────────────────────────────────

export interface PaperTradeRecord {
  id: number;
  action: 'buy' | 'sell';
  exec_date: string;
  rec_date: string;
  ts_code: string;
  stock_name: string;
  shares: number;
  price: number;
  amount: number;
  commission: number;
  stamp_duty: number;
  net_amount: number;
}

export interface PaperHolding {
  ts_code: string;
  stock_name: string;
  shares: number;
  avg_cost: number;
  cost_basis: number;
  last_price: number | null;
  market_value: number;
  unrealized_pnl: number;
}

export interface PaperStatus {
  strategy_id: number;
  initial_capital: number;
  cash: number;
  holdings: PaperHolding[];
  total_market_value: number;
  total_cost_basis: number;
  total_nav: number;
  total_return_pct: number;
  last_exec_date: string | null;
  last_rec_date: string | null;
  trade_count: number;
}

export interface ExecuteSummary {
  cash_before: number;
  cash_after: number;
  holdings_before: number;
  holdings_after: number;
  sell_count: number;
  buy_count: number;
  keep_count: number;
  total_buy_amount: number;
  total_sell_amount: number;
  total_commission: number;
  total_stamp_duty: number;
  additional_capital_added: number;
}

export interface ExecuteResult {
  executed: boolean;
  rec_date: string;
  exec_date: string;
  trades: PaperTradeRecord[];
  summary: ExecuteSummary;
}

export interface NavPoint {
  date: string;
  cash: number;
  holdings_value: number;
  total_value: number;
  return_pct: number;
}

export interface NavResponse {
  strategy_id: number;
  initial_capital: number;
  nav: NavPoint[];
  count: number;
  message?: string;
}

export interface TradeListResponse {
  strategy_id: number;
  trades: PaperTradeRecord[];
  total: number;
  page: number;
  page_size: number;
}

// ── Service ──────────────────────────────────────────────────

const BASE = '/paper-trade';

export const paperTradeService = {
  /** 初始化或更新本金 */
  async start(strategyId: number, initialCapital: number): Promise<{
    strategy_id: number;
    initial_capital: number;
    message: string;
  }> {
    const response = await api.post(`${BASE}/start`, {
      strategy_id: strategyId,
      initial_capital: initialCapital,
    });
    return response.data;
  },

  /** 获取当前账户状态 */
  async getStatus(strategyId: number): Promise<PaperStatus> {
    const response = await api.get<PaperStatus>(`${BASE}/status`, {
      params: { strategy_id: strategyId },
    });
    return response.data;
  },

  /** 执行一次调仓（灵活模式） */
  async execute(payload: {
    strategy_id: number;
    date?: string;
    sells: { ts_code: string; shares: number }[];
    buys: { ts_code: string; shares: number; stock_name?: string }[];
    additional_capital?: number;
    exec_date?: string;
  }): Promise<ExecuteResult> {
    const response = await api.post<ExecuteResult>(`${BASE}/execute`, payload);
    return response.data;
  },

  /** 获取净值历史 */
  async getNav(
    strategyId: number,
    startDate?: string,
    endDate?: string,
  ): Promise<NavResponse> {
    const response = await api.get<NavResponse>(`${BASE}/nav`, {
      params: {
        strategy_id: strategyId,
        start_date: startDate,
        end_date: endDate,
      },
    });
    return response.data;
  },

  /** 获取交易历史（分页） */
  async getTrades(
    strategyId: number,
    page = 1,
    pageSize = 20,
  ): Promise<TradeListResponse> {
    const response = await api.get<TradeListResponse>(`${BASE}/trades`, {
      params: {
        strategy_id: strategyId,
        page,
        page_size: pageSize,
      },
    });
    return response.data;
  },

  /** 重置模拟盘（清空所有交易） */
  async reset(strategyId: number): Promise<{
    strategy_id: number;
    message: string;
    deleted_count: number;
  }> {
    const response = await api.delete(`${BASE}/reset`, {
      params: { strategy_id: strategyId },
    });
    return response.data;
  },
};

export default paperTradeService;
