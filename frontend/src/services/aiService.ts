import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
});

export const aiService = {
  // 自然语言生成策略配置
  async generateStrategy(prompt: string) {
    const response = await api.post<{
      code: number;
      message?: string;
      data: {
        name: string;
        description: string;
        factor_config: any;
        explanation: string;
      };
    }>('/ai/generate-strategy', { prompt });
    return response.data;
  },
};
