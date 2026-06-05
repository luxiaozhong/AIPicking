import api from './api';
import type { StockSearchResponse, KLineData, ValuationData } from '@/types/stock';

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

  async getValuation(tsCode: string): Promise<ValuationData | null> {
    const response = await api.get<{ code: number; data: ValuationData[] }>(
      `/v1/valuation/${tsCode}`,
      { params: { days: 1 } },
    );
    const data = response.data.data;
    return data?.[0] ?? null;
  },
};

export default stockService;
