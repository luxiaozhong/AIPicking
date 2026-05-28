import api from './api';
import type { BacktestReport, BacktestListResponse, BacktestCreate, StrategyExecuteResponse, BatchBacktestReport, BatchBacktestListResponse, BatchBacktestCreate } from '@/types/backtest';

// 回测管理服务
export const backtestService = {
  // 获取回测报告列表
  async getBacktests(params: {
    page?: number;
    limit?: number;
    strategy_id?: number;
    status?: string;
    stock?: string;
  } = {}) {
    const response = await api.get<BacktestListResponse>('/backtests', {
      params,
    });
    return response.data;
  },

  // 获取回测报告详情
  async getBacktest(id: number) {
    const response = await api.get<BacktestReport>(`/backtests/${id}`);
    return response.data;
  },

  // 提交回测任务
  async createBacktest(data: BacktestCreate) {
    const response = await api.post<BacktestReport>('/backtests', data);
    return response.data;
  },

  // 执行策略（同步，立即返回推荐结果）
  async executeStrategy(strategyId: number, cutoffDate?: string, tsCode?: string) {
    const params: Record<string, string> = {};
    if (cutoffDate) params.cutoff_date = cutoffDate;
    if (tsCode) params.ts_code = tsCode;
    const response = await api.post<StrategyExecuteResponse>(
      `/backtests/execute/${strategyId}`,
      null,
      { params }
    );
    return response.data;
  },

  // 删除回测报告
  async deleteBacktest(id: number) {
    await api.delete(`/backtests/${id}`);
  },

  // 批量回测
  async getBatchBacktests(params: {
    page?: number;
    limit?: number;
    strategy_id?: number;
  } = {}) {
    const response = await api.get<BatchBacktestListResponse>('/backtests/batch', { params });
    return response.data;
  },

  async getBatchBacktest(id: number) {
    const response = await api.get<BatchBacktestReport>(`/backtests/batch/${id}`);
    return response.data;
  },

  async createBatchBacktest(data: BatchBacktestCreate) {
    const response = await api.post<BatchBacktestReport>('/backtests/batch', data);
    return response.data;
  },

  async deleteBatchBacktest(id: number) {
    await api.delete(`/backtests/batch/${id}`);
  },
};

export default backtestService;
