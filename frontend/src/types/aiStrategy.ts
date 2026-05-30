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
  signal_type?: 'buy' | 'sell' | 'both';
  reason?: string;
  ref_value?: number;
  params: Record<string, number>;
  code_required?: boolean;
  matched_factor_id: string | null;
  code_reference?: string;
}

export interface AnalysisResult {
  status: 'processing' | 'completed' | 'failed' | 'generating';
  summary?: string;
  indicators?: IndicatorItem[];
  kline_summary?: {
    start_date: string;
    end_date: string;
    trading_days: number;
  };
  error_message?: string;
  strategy_id?: number;
  generated_factors?: string[];
  failed_factors?: { name: string; error: string }[];
  progress?: GenerationProgress;
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

/** 前端状态机 phase 枚举 */
export type AnalysisPhase =
  | 'idle'
  | 'submitting'
  | 'analyzing'
  | 'review'
  | 'generating'
  | 'completed'
  | 'failed';

/** 策略生成进度 */
export interface GenerationProgress {
  completed: number;
  total: number;
}

/** NL 分类指示器 */
export interface NLClassified {
  matched: IndicatorItem[];
  new: IndicatorItem[];
}

/** NL 分析请求 */
export interface AnalyzeNLRequest {
  prompt: string;
  model?: string;
}

/** NL 分析结果 */
export interface NLAnalysisResult {
  status: string;
  summary?: string;
  indicators?: IndicatorItem[];
  classified?: NLClassified;
  strategy_id?: number;
  generated_factors?: string[];
  failed_factors?: { name: string; error: string }[];
  error_message?: string;
  progress?: GenerationProgress;
}

/** NL 确认请求 */
export interface ConfirmNLStrategyRequest {
  task_id: string;
  strategy_name?: string;
  indicators: Record<string, unknown>[];
}
