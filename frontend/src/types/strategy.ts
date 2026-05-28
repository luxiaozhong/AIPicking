// 策略相关类型定义

export interface Strategy {
  id: number;
  user_id?: number;
  owner_name?: string;
  name: string;
  description?: string;
  file_path: string;
  params_schema?: string;
  tags?: string[];
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface StrategyListResponse {
  items: Strategy[];
  total: number;
  page: number;
  limit: number;
}

export interface StrategyUploadResponse {
  code: number;
  message: string;
  data?: Strategy;
  errors?: string[];
}

export interface StrategyResponse extends Strategy {
  factor_config?: Record<string, unknown>;
  generated_code?: string;
}

export interface StrategyDetailResponse {
  code: number;
  data: Strategy;
  code_content: string;
}
