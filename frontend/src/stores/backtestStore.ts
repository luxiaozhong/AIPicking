import { create } from 'zustand';
import type { BacktestReport, BacktestListResponse, BacktestCreate } from '@/types/backtest';
import backtestService from '@/services/backtestService';

let pollingTimer: ReturnType<typeof setInterval> | null = null;

interface BacktestState {
  // 状态
  backtests: BacktestReport[];
  total: number;
  page: number;
  limit: number;
  loading: boolean;
  error: string | null;

  // 当前回测报告详情
  currentBacktest: BacktestReport | null;

  // 策略执行结果（同步返回）
  executeResult: any | null;

  // 操作方法
  fetchBacktests: (params?: {
    page?: number;
    limit?: number;
    strategy_id?: number;
    status?: string;
    stock?: string;
  }) => Promise<void>;

  fetchBacktest: (id: number) => Promise<void>;

  createBacktest: (data: BacktestCreate) => Promise<BacktestReport>;

  executeStrategy: (strategyId: number, cutoffDate?: string, tsCode?: string) => Promise<any>;

  deleteBacktest: (id: number) => Promise<void>;

  clearError: () => void;

  startPolling: () => void;
  stopPolling: () => void;
}

export const useBacktestStore = create<BacktestState>((set, get) => ({
  // 初始状态
  backtests: [],
  total: 0,
  page: 1,
  limit: 20,
  loading: false,
  error: null,

  currentBacktest: null,
  executeResult: null,

  // 获取回测报告列表
  fetchBacktests: async (params = {}) => {
    set({ loading: true, error: null });

    try {
      const response = await backtestService.getBacktests({
        page: params.page || get().page,
        limit: params.limit || get().limit,
        strategy_id: params.strategy_id,
        status: params.status,
        stock: params.stock,
      });

      set({
        backtests: response.items,
        total: response.total,
        page: response.page,
        limit: response.limit,
        loading: false,
      });
    } catch (error: any) {
      set({
        loading: false,
        error: error.response?.data?.message || '获取回测报告列表失败',
      });
    }
  },

  // 获取回测报告详情
  fetchBacktest: async (id: number) => {
    set({ loading: true, error: null });

    try {
      const response = await backtestService.getBacktest(id);

      set({
        currentBacktest: response,
        loading: false,
      });
    } catch (error: any) {
      set({
        loading: false,
        error: error.response?.data?.message || '获取回测报告详情失败',
      });
    }
  },

  // 提交回测任务
  createBacktest: async (data) => {
    set({ loading: true, error: null });

    try {
      const response = await backtestService.createBacktest(data);

      set({ loading: false });

      // 刷新列表
      get().fetchBacktests();

      return response;
    } catch (error: any) {
      set({
        loading: false,
        error: error.response?.data?.message || '提交回测任务失败',
      });

      throw error;
    }
  },

  // 执行策略（同步，立即返回推荐结果）
  executeStrategy: async (strategyId: number, cutoffDate?: string, tsCode?: string) => {
    set({ loading: true, error: null });

    try {
      const response = await backtestService.executeStrategy(strategyId, cutoffDate, tsCode);

      set({
        loading: false,
        executeResult: response,
      });

      return response;
    } catch (error: any) {
      set({
        loading: false,
        error: error.response?.data?.message || '执行策略失败',
      });

      throw error;
    }
  },

  // 删除回测报告
  deleteBacktest: async (id: number) => {
    set({ loading: true, error: null });

    try {
      await backtestService.deleteBacktest(id);

      set({ loading: false });

      // 刷新列表
      get().fetchBacktests();
    } catch (error: any) {
      set({
        loading: false,
        error: error.response?.data?.message || '删除回测报告失败',
      });

      throw error;
    }
  },

  // 清除错误
  clearError: () => {
    set({ error: null });
  },

  // 开始轮询：检测是否有未完成的任务，有则自动刷新列表
  startPolling: () => {
    if (pollingTimer) return;
    pollingTimer = setInterval(() => {
      const state = get();
      const hasActive = state.backtests.some(
        (b) => b.status === 'pending' || b.status === 'running',
      );
      if (hasActive) {
        state.fetchBacktests();
      }
    }, 3000);
  },

  // 停止轮询
  stopPolling: () => {
    if (pollingTimer) {
      clearInterval(pollingTimer);
      pollingTimer = null;
    }
  },
}));
