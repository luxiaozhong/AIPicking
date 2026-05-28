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
  }) => Promise<void>;
  
  uploadStrategy: (file: File, name?: string, description?: string, tags?: string) => Promise<StrategyUploadResponse>;
  
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
  
  // 上传策略
  uploadStrategy: async (file: File, name?: string, description?: string, tags?: string) => {
    set({ loading: true, error: null });
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      if (name) {
        formData.append('name', name);
      }
      
      if (description) {
        formData.append('description', description);
      }
      
      if (tags) {
        formData.append('tags', tags);
      }
      
      const response = await strategyService.uploadStrategy(formData);
      
      set({ loading: false });
      
      // 刷新列表
      get().fetchStrategies();
      
      return response;
    } catch (error: any) {
      set({
        loading: false,
        error: error.response?.data?.message || '上传策略失败',
      });
      
      throw error;
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
  
  // 删除策略
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
  
  // 清除错误
  clearError: () => {
    set({ error: null });
  },
}));
