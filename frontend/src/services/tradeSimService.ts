import api from './api';
import type {
  TradeSimReport,
  TradeSimListResponse,
  TradeSimCreate,
  StopFactorMeta,
  BatchTradeSimCreate,
  BatchTradeSimReport,
} from '@/types/tradeSim';

const BASE = '/trade-sims';

export const tradeSimService = {
  async create(data: TradeSimCreate): Promise<TradeSimReport> {
    const response = await api.post<TradeSimReport>(BASE, data);
    return response.data;
  },

  async getList(params: {
    page?: number;
    limit?: number;
    strategy_id?: number;
    status?: string;
  } = {}): Promise<TradeSimListResponse> {
    const response = await api.get<TradeSimListResponse>(BASE, { params });
    return response.data;
  },

  async getDetail(id: number): Promise<TradeSimReport> {
    const response = await api.get<TradeSimReport>(`${BASE}/${id}`);
    return response.data;
  },

  async delete(id: number): Promise<void> {
    await api.delete(`${BASE}/${id}`);
  },

  async getStopFactors(): Promise<Record<string, StopFactorMeta>> {
    const response = await api.get<Record<string, StopFactorMeta>>(`${BASE}/factors`);
    return response.data;
  },

  async createBatch(data: BatchTradeSimCreate): Promise<BatchTradeSimReport> {
    const response = await api.post<BatchTradeSimReport>(`${BASE}/batch`, data);
    return response.data;
  },

  async getBatchList(params: {
    page?: number; limit?: number; strategy_id?: number;
  } = {}): Promise<{ items: BatchTradeSimReport[]; total: number; page: number; limit: number }> {
    const response = await api.get<{ items: BatchTradeSimReport[]; total: number; page: number; limit: number }>(`${BASE}/batch`, { params });
    return response.data;
  },

  async getBatchDetail(id: number): Promise<BatchTradeSimReport> {
    const response = await api.get<BatchTradeSimReport>(`${BASE}/batch/${id}`);
    return response.data;
  },

  async deleteBatch(id: number): Promise<void> {
    await api.delete(`${BASE}/batch/${id}`);
  },
};

export default tradeSimService;
