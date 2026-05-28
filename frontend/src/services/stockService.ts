import api from './api';
import type { StockSearchResponse } from '@/types/stock';

export const stockService = {
  async search(q: string, limit = 10) {
    const response = await api.get<{ code: number; data: StockSearchResponse }>('/stocks/search', {
      params: { q, limit },
    });
    return response.data.data.items;
  },
};

export default stockService;
