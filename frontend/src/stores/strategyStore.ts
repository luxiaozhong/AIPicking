import { create } from 'zustand';
import type { Strategy, StrategyListResponse, StrategyUploadResponse } from '@/types/strategy';
import strategyService from '@/services/strategyService';

interface StrategyState {
  // 状态
  strategies: Strategy[];
  total: number;
  page: number;
  limit: number;
  loading: boolean;
  error: string | null;

  // 当前策略详情
  currentStrategy: Strategy | null;
  codeContent: string;

  // 操作方法
  fetchStrategies: (params?: {
    page?: number;
    limit?: number;
    search?: string;
    status?: string;
    scope?: string;
  }) => Promise<void>;


  fetchStrategy: (id: number) => Promise<void>;

  downloadStrategy: (id: number, fileName: string) => Promise<void>;

  updateStrategy: (id: number, data: {
    name?: string;
    description?: string;
    params_schema?: string;
    tags?: string[];
    status?: string;
  }) => Promise<Strategy>;

  updateStrategyCode: (id: number, file?: File, code?: string) => Promise<StrategyUploadResponse>;

  deleteStrategy: (id: number) => Promise<void>;

  permanentDeleteStrategy: (id: number) => Promise<void>;

  updateFactorConfig: (id: number, config: Record<string, unknown>, meta?: {
    name?: string;
    description?: string;
    tags?: string[];
  }) => Promise<void>;

  createFromFactorConfig: (config: Record<string, unknown>, name: string, description?: string) => Promise<Strategy>;

  publishStrategy: (id: number) => Promise<void>;
  unpublishStrategy: (id: number) => Promise<void>;
  rateStrategy: (id: number, score: number) => Promise<void>;
  fetchRatings: (id: number) => Promise<import('@/types/strategy').RatingStats | null>;
  addComment: (id: number, content: string) => Promise<void>;
  fetchComments: (id: number, page?: number) => Promise<import('@/types/strategy').CommentListResponse | null>;
  deleteComment: (strategyId: number, commentId: number) => Promise<void>;

  clearError: () => void;
}

export const useStrategyStore = create<StrategyState>((set, get) => ({
  // 初始状态
  strategies: [],
  total: 0,
  page: 1,
  limit: 20,
  loading: false,
  error: null,

  currentStrategy: null,
  codeContent: '',

  // 获取策略列表
  fetchStrategies: async (params = {}) => {
    set({ loading: true, error: null });

    try {
      const response = await strategyService.getStrategies({
        page: params.page || get().page,
        limit: params.limit || get().limit,
        search: params.search,
        status: params.status,
        scope: params.scope,
      });

      set({
        strategies: response.items,
        total: response.total,
        page: response.page,
        limit: response.limit,
        loading: false,
      });
    } catch (error: any) {
      set({
        loading: false,
        error: error.response?.data?.message || '获取策略列表失败',
      });
    }
  },


  // 获取策略详情
  fetchStrategy: async (id: number) => {
    set({ loading: true, error: null });

    try {
      const response = await strategyService.getStrategy(id);

      set({
        currentStrategy: response.data,
        codeContent: response.code_content,
        loading: false,
      });
    } catch (error: any) {
      set({
        loading: false,
        error: error.response?.data?.message || '获取策略详情失败',
      });
    }
  },

  // 下载策略
  downloadStrategy: async (id: number, fileName: string) => {
    try {
      await strategyService.downloadStrategy(id, fileName);
    } catch (error: any) {
      set({
        error: error.response?.data?.message || '下载策略失败',
      });
    }
  },

  // 更新策略元数据
  updateStrategy: async (id: number, data: {
    name?: string;
    description?: string;
    params_schema?: string;
    tags?: string[];
    status?: string;
  }) => {
    set({ loading: true, error: null });

    try {
      const response = await strategyService.updateStrategy(id, data);

      set({
        currentStrategy: response,
        loading: false,
      });

      return response;
    } catch (error: any) {
      set({
        loading: false,
        error: error.response?.data?.message || '更新策略失败',
      });

      throw error;
    }
  },

  // 更新策略代码
  updateStrategyCode: async (id: number, file?: File, code?: string) => {
    set({ loading: true, error: null });

    try {
      const formData = new FormData();

      if (file) {
        formData.append('file', file);
      }

      if (code) {
        formData.append('code', code);
      }

      const response = await strategyService.updateStrategyCode(id, formData);

      // 刷新策略详情
      await get().fetchStrategy(id);

      set({ loading: false });

      return response;
    } catch (error: any) {
      set({
        loading: false,
        error: error.response?.data?.message || '更新策略代码失败',
      });

      throw error;
    }
  },

  // 删除策略（软删除）
  deleteStrategy: async (id: number) => {
    set({ loading: true, error: null });

    try {
      await strategyService.deleteStrategy(id);

      set({ loading: false });

      // 刷新列表
      get().fetchStrategies();
    } catch (error: any) {
      set({
        loading: false,
        error: error.response?.data?.message || '删除策略失败',
      });

      throw error;
    }
  },

  // 彻底删除策略（硬删除，同时删除关联的回测报告）
  permanentDeleteStrategy: async (id: number) => {
    set({ loading: true, error: null });

    try {
      await strategyService.permanentDeleteStrategy(id);

      set({ loading: false });

      // 刷新列表
      get().fetchStrategies();
    } catch (error: any) {
      set({
        loading: false,
        error: error.response?.data?.message || '彻底删除策略失败',
      });

      throw error;
    }
  },

  // 更新策略因子配置（重新生成代码）
  updateFactorConfig: async (id: number, config: Record<string, unknown>, meta?: {
    name?: string;
    description?: string;
    tags?: string[];
  }) => {
    set({ loading: true, error: null });
    try {
      // 先更新元数据（如有变化）
      if (meta && (meta.name || meta.description !== undefined || meta.tags)) {
        await strategyService.updateStrategy(id, {
          name: meta.name,
          description: meta.description,
          tags: meta.tags,
        });
      }
      // 更新因子配置
      await strategyService.updateStrategyFactors(id, config as any);
      // 刷新数据
      await get().fetchStrategy(id);
      set({ loading: false });
    } catch (error: any) {
      set({ loading: false, error: error.response?.data?.message || '更新因子配置失败' });
      throw error;
    }
  },

  // 基于因子配置创建新策略（另存为）
  createFromFactorConfig: async (config: Record<string, unknown>, name: string, description?: string) => {
    set({ loading: true, error: null });
    try {
      const res = await strategyService.createStrategyWithFactors({
        name,
        description,
        factor_config: config as any,
      });
      if (res.code === 0 && res.data) {
        set({ loading: false });
        return res.data;
      }
      throw new Error(res.message || '创建失败');
    } catch (error: any) {
      set({ loading: false, error: error.response?.data?.message || error.message || '创建失败' });
      throw error;
    }
  },

  // 发布策略
  publishStrategy: async (id: number) => {
    set({ loading: true, error: null });
    try {
      await strategyService.publishStrategy(id);
      await get().fetchStrategies();
      if (get().currentStrategy?.id === id) {
        await get().fetchStrategy(id);
      }
      set({ loading: false });
    } catch (error: any) {
      set({ loading: false, error: error.response?.data?.message || '发布失败' });
      throw error;
    }
  },

  // 取消发布
  unpublishStrategy: async (id: number) => {
    set({ loading: true, error: null });
    try {
      await strategyService.unpublishStrategy(id);
      await get().fetchStrategies();
      if (get().currentStrategy?.id === id) {
        await get().fetchStrategy(id);
      }
      set({ loading: false });
    } catch (error: any) {
      set({ loading: false, error: error.response?.data?.message || '取消发布失败' });
      throw error;
    }
  },

  // 评分
  rateStrategy: async (id: number, score: number) => {
    try {
      await strategyService.rateStrategy(id, score);
    } catch (error: any) {
      set({ error: error.response?.data?.message || '评分失败' });
      throw error;
    }
  },

  // 获取评分统计
  fetchRatings: async (id: number) => {
    try {
      return await strategyService.getStrategyRatings(id);
    } catch {
      return null;
    }
  },

  // 发表评论
  addComment: async (id: number, content: string) => {
    try {
      await strategyService.addComment(id, content);
    } catch (error: any) {
      set({ error: error.response?.data?.message || '评论失败' });
      throw error;
    }
  },

  // 获取评论列表
  fetchComments: async (id: number, page = 1) => {
    try {
      return await strategyService.getComments(id, page);
    } catch {
      return null;
    }
  },

  // 删除评论
  deleteComment: async (strategyId: number, commentId: number) => {
    try {
      await strategyService.deleteComment(strategyId, commentId);
    } catch (error: any) {
      set({ error: error.response?.data?.message || '删除评论失败' });
      throw error;
    }
  },

  // 清除错误
  clearError: () => {
    set({ error: null });
  },
}));
