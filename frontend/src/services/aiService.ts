import api from './api';

export const aiService = {
  async generateStrategy(prompt: string) {
    const response = await api.post('/ai/generate-strategy', { prompt });
    return response.data;
  },

  async analyzeStock(data: {
    ts_code: string;
    date: string;
    model: string;
    prompt: string;
  }) {
    const response = await api.post('/ai/analyze-stock', data);
    return response.data;
  },

  async getAnalysisResult(taskId: string) {
    const response = await api.get(`/ai/analyze-stock/${taskId}`);
    return response.data;
  },

  async getTasks(limit = 20, offset = 0) {
    const response = await api.get('/ai/analyze-stock/tasks', {
      params: { limit, offset },
    });
    return response.data;
  },

  async confirmStrategy(data: {
    task_id: string;
    strategy_name?: string;
    indicators: Record<string, unknown>[];
    buy_logic?: string;
  }) {
    const response = await api.post('/ai/confirm-strategy', data);
    return response.data;
  },
};
