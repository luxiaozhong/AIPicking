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
  is_published: boolean;
  avg_score?: number | null;
  rating_count?: number;
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

// 发布相关
export interface PublishResponse {
  code: number;
  message: string;
  is_published: boolean;
}

// 评分相关
export interface RatingStats {
  average: number | null;
  count: number;
  distribution: Record<number, number>;
  current_user_score: number | null;
}

export interface RatingSubmitResponse {
  code: number;
  message: string;
  data: {
    id: number;
    score: number;
  };
}

// 评论相关
export interface CommentItem {
  id: number;
  strategy_id: number;
  user_id: number;
  user_name: string | null;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface CommentListResponse {
  items: CommentItem[];
  total: number;
  page: number;
  limit: number;
}

export interface CommentCreateResponse {
  code: number;
  message: string;
  data: {
    id: number;
    content: string;
    user_name: string | null;
    created_at: string;
  };
}
