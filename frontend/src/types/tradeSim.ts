export interface StopFactorMeta {
  name: string;
  params: Array<{
    name: string;
    type: 'int' | 'float';
    default: number;
    description: string;
  }>;
}

export interface StopFactorConfig {
  id: string;
  enabled: boolean;
  params: Record<string, number>;
}

export interface TradeSimCreate {
  strategy_id: number;
  cutoff_date: string;        // YYYY-MM-DD
  total_amount: number;
  top_n: number;              // default 5
  max_hold_days: number;      // default 60
  stop_factors: StopFactorConfig[];
}

export interface DailyTrackingItem {
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  ma10: number | null;
  prev_low_ref: number | null;
  ma10_stop_line: number | null;
  ma60_stop_line: number | null;
  trailing_stop_line: number | null;
  prev_high_target: number | null;
  return_pct: number;
  status: 'holding' | 'stopped' | 'take_profit' | 'force_close';
}

export interface TradeItem {
  ts_code: string;
  name: string;
  score: number;
  allocated_amount: number;
  shares: number;
  buy_price: number;
  buy_date: string;
  sell_price: number | null;
  sell_date: string | null;
  sell_reason: string | null;
  hold_days: number | null;
  return_pct: number | null;
  high_price: number | null;
  low_price: number | null;
  max_drawdown: number | null;
  daily_tracking: DailyTrackingItem[];
}

export interface ReturnDistribution {
  'lt_-10': number;
  '-10_0': number;
  '0_5': number;
  '5_10': number;
  'gt_10': number;
}

export interface TradeSimSummary {
  total_trades: number;
  win_count: number;
  lose_count: number;
  win_rate: number;
  avg_return: number;
  avg_win: number;
  avg_loss: number;
  profit_loss_ratio: number;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  total_pnl: number;
  total_qualifying: number;
  base_stock_count: number;
  pick_rate: number;
  return_distribution: ReturnDistribution;
}

export interface TradeSimReport {
  id: number;
  strategy_id: number;
  strategy_name?: string;
  cutoff_date: string;
  config: TradeSimCreate | null;
  trades: TradeItem[] | null;
  summary: TradeSimSummary | null;
  status: string;
  error_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface TradeSimListResponse {
  items: TradeSimReport[];
  total: number;
  page: number;
  limit: number;
}

export interface BatchTradeSimCreate {
  strategy_id: number;
  start_date: string;       // YYYYMMDD
  end_date: string;         // YYYYMMDD
  name?: string;
  total_amount: number;
  top_n: number;
  max_hold_days: number;
  stop_factors: StopFactorConfig[];
}

export interface BatchDailyResult {
  cutoff_date: string;
  status: string;
  trades?: TradeItem[] | null;
  summary?: TradeSimSummary | null;
  error_message?: string;
}

export interface BatchTradeSimReport {
  id: number;
  strategy_id: number;
  strategy_name?: string;
  name?: string;
  status: string;
  start_date: string;
  end_date: string;
  config: { total_amount: number; top_n: number; max_hold_days: number; stop_factors: StopFactorConfig[] } | null;
  total_days: number;
  completed_days: number;
  daily_results?: BatchDailyResult[] | null;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  created_at?: string;
}
