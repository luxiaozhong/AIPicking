import api from './api';
import type { StrategyResponse, StrategyListResponse, StrategyUploadResponse } from '@/types/strategy';
import type { FactorConfig } from '@/types/factor';

// 策略管理服务
export const strategyService = {
  // 获取策略列表
  async getStrategies(params: {
    page?: number;
    limit?: number;
    search?: string;
    status?: string;
    scope?: string;
  } = {}) {
    const response = await api.get<StrategyListResponse>('/strategies', {
      params,
    });
    return response.data;
  },


  // 通过因子配置创建策略（新方式）
  async createStrategyWithFactors(data: {
    name: string;
    description?: string;
    tags?: string[];
    factor_config: FactorConfig;
  }) {
    const response = await api.post<{ code: number; message: string; data?: StrategyResponse }>('/strategies', data);
    return response.data;
  },

  // 获取策略详情
  async getStrategy(id: number) {
    const response = await api.get<{ code: number; data: StrategyResponse; code_content: string }>(`/strategies/${id}`);
    return response.data;
  },

  // 下载策略脚本
  async downloadStrategy(id: number, fileName: string) {
    const response = await api.get(`/strategies/${id}/download`, {
      responseType: 'blob',
    });

    // 创建下载链接
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', fileName);
    document.body.appendChild(link);
    link.click();
    link.parentNode?.removeChild(link);
  },

  // 更新策略元数据
  async updateStrategy(id: number, data: {
    name?: string;
    description?: string;
    params_schema?: string;
    tags?: string[];
    status?: string;
  }) {
    const response = await api.put<StrategyResponse>(`/strategies/${id}`, data);
    return response.data;
  },

  // 更新策略因子配置
  async updateStrategyFactors(id: number, factor_config: FactorConfig) {
    const response = await api.put(`/strategies/${id}/factors`, factor_config);
    return response.data;
  },

  // 获取策略生成的代码
  async getStrategyCode(id: number) {
    const response = await api.get<{ code: number; data: { generated_code: string; factor_config: FactorConfig } }>(`/strategies/${id}/code`);
    return response.data;
  },

  // 更新策略代码
  async updateStrategyCode(id: number, formData: FormData) {
    const response = await api.put<StrategyUploadResponse>(`/strategies/${id}/code`, formData);
    return response.data;
  },

  // 删除策略（软删除）
  async deleteStrategy(id: number) {
    await api.delete(`/strategies/${id}`);
  },

  // 彻底删除策略（硬删除，同时删除关联的回测报告）
  async permanentDeleteStrategy(id: number) {
    await api.delete(`/strategies/${id}/permanent`);
  },

  // 发布策略
  async publishStrategy(id: number) {
    const response = await api.put<{ code: number; message: string; is_published: boolean }>(`/strategies/${id}/publish`);
    return response.data;
  },

  // 取消发布策略
  async unpublishStrategy(id: number) {
    const response = await api.put<{ code: number; message: string; is_published: boolean }>(`/strategies/${id}/unpublish`);
    return response.data;
  },

  // 评分
  async rateStrategy(id: number, score: number) {
    const response = await api.post<{ code: number; message: string; data: { id: number; score: number } }>(`/strategies/${id}/ratings`, { score });
    return response.data;
  },

  // 获取评分统计
  async getStrategyRatings(id: number) {
    const response = await api.get<{ average: number | null; count: number; distribution: Record<number, number>; current_user_score: number | null }>(`/strategies/${id}/ratings`);
    return response.data;
  },

  // 发表评论
  async addComment(id: number, content: string) {
    const response = await api.post<{ code: number; message: string; data: { id: number; content: string; user_name: string | null; created_at: string } }>(`/strategies/${id}/comments`, { content });
    return response.data;
  },

  // 获取评论列表
  async getComments(id: number, page = 1, limit = 20) {
    const response = await api.get<{ items: import('@/types/strategy').CommentItem[]; total: number; page: number; limit: number }>(`/strategies/${id}/comments`, { params: { page, limit } });
    return response.data;
  },

  // 删除评论
  async deleteComment(strategyId: number, commentId: number) {
    const response = await api.delete<{ code: number; message: string }>(`/strategies/${strategyId}/comments/${commentId}`);
    return response.data;
  },
};

export default strategyService;
