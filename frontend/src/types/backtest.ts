// 回测相关类型定义（新逻辑）

export interface RecommendationItem {
  ts_code: string;
  name: string;
  score: number;
  signal: string;
  return_0d?: number;
  return_3d?: number;
  return_7d?: number;
  return_15d?: number;
  breakdown?: Record<string, number>;
  details?: Record<string, any>;
}

export interface BacktestSummary {
  total_recommendations: number;
  avg_return_3d: number;
  avg_return_7d: number;
  avg_return_15d: number;
  win_rate_3d: number;
  win_rate_7d: number;
  win_rate_15d: number;
  best_return_15d: number;
  worst_return_15d: number;
  total_qualifying: number;
  base_stock_count: number;
  pick_rate: number;
}

export interface BacktestReport {
  id: number;
  strategy_id: number;
  strategy_name?: string;
  name: string;
  status: string;
  cutoff_date: string;
  config?: string;
  recommendations?: RecommendationItem[];
  summary?: BacktestSummary;
  error_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface BacktestListResponse {
  items: BacktestReport[];
  total: number;
  page: number;
  limit: number;
}

export interface BacktestCreate {
  strategy_id: number;
  cutoff_date: string;
  track_days?: number[];
  config?: Record<string, any>;
}

export interface StrategyExecuteResponse {
  strategy_id: number;
  strategy_name: string;
  cutoff_date: string;
  recommendations: RecommendationItem[];
  total: number;
}

// 批量回测相关类型

export interface DailyResultItem {
  cutoff_date: string;
  status: string;
  input?: { cutoff_date: string; config: Record<string, any> };
  recommendations?: RecommendationItem[];
  summary?: BacktestSummary;
  error_message?: string;
}

export interface BatchBacktestReport {
  id: number;
  strategy_id: number;
  strategy_name?: string;
  name?: string;
  status: string;
  start_date: string;
  end_date: string;
  config?: Record<string, any>;
  total_days: number;
  completed_days: number;
  daily_results?: DailyResultItem[];
  error_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface BatchBacktestCreate {
  strategy_id: number;
  start_date: string;
  end_date: string;
  track_days?: number[];
  name?: string;
  config?: Record<string, any>;
}

export interface BatchBacktestListResponse {
  items: BatchBacktestReport[];
  total: number;
  page: number;
  limit: number;
}
