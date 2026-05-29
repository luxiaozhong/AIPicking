export interface AnalyzeStockRequest {
  ts_code: string;
  date: string;
  model: 'deepseek-chat' | 'deepseek-reasoner';
  prompt: string;
}

export interface IndicatorItem {
  name: string;
  category: string;
  description: string;
  signal_type: 'buy' | 'sell' | 'both';
  reason: string;
  params: Record<string, number>;
  code_required: boolean;
  matched_factor_id: string | null;
  code_reference?: string;
}

export interface AnalysisResult {
  status: 'processing' | 'completed' | 'failed';
  summary?: string;
  indicators?: IndicatorItem[];
  kline_summary?: {
    start_date: string;
    end_date: string;
    trading_days: number;
  };
  error_message?: string;
}

export interface AnalysisTask {
  task_id: string;
  ts_code: string;
  date: string;
  status: string;
  created_at: string;
}

export interface ConfirmStrategyResponse {
  strategy_id: number;
  factor_config: Record<string, unknown>;
  generated_factors: string[];
  failed_factors: { name: string; error: string }[];
}
