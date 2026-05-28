import axios from 'axios';
import type { FactorMeta, FactorCategory } from '@/types/factor';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 10000,
});

export const factorService = {
  // 获取因子列表（按分类）
  async getFactors(category?: string) {
    const response = await api.get<{
      code: number;
      data: {
        factors: FactorMeta[];
        categories: string[];
      };
    }>('/factors', { params: { category } });
    return response.data;
  },

  // 获取单个因子详情
  async getFactorDetail(factorId: string) {
    const response = await api.get<{
      code: number;
      data: FactorMeta;
    }>(`/factors/${factorId}`);
    return response.data;
  },
};
