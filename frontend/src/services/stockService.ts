import api from './api';
import type { StockSearchResponse, KLineData } from '@/types/stock';

export const stockService = {
  async search(q: string, limit = 10) {
    const response = await api.get<{ code: number; data: StockSearchResponse }>('/stocks/search', {
      params: { q, limit },
    });
    return response.data.data.items;
  },

  async getKLine(tsCode: string, days: number = 365): Promise<KLineData> {
    const response = await api.get<{ code: number; data: KLineData }>('/stocks/kline', {
      params: { ts_code: tsCode, days },
    });
    return response.data.data;
  },
};

export default stockService;
