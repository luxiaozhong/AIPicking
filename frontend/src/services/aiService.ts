import api from './api';
import authService from './authService';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

/**
 * SSE 连接：监听任务状态变化
 * 返回 abort 函数用于取消连接
 */
export function connectAnalysisSSE(
  taskId: string,
  onEvent: (data: Record<string, unknown>) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): () => void {
  const controller = new AbortController();
  const token = authService.getToken();

  (async () => {
    try {
      const response = await fetch(
        `${API_BASE}/ai/analyze-stock/${taskId}/stream`,
        {
          headers: {
            Authorization: token ? `Bearer ${token}` : '',
          },
          signal: controller.signal,
        },
      );

      if (!response.ok) {
        throw new Error(`SSE connection failed: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const raw = line.slice(6).trim();
            if (!raw) continue;
            try {
              const data = JSON.parse(raw);
              if (data.type === 'done') {
                onDone();
                return;
              }
              onEvent(data);
            } catch {
              // skip malformed JSON
            }
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      onError(err as Error);
    }
  })();

  return () => controller.abort();
}

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
  }) {
    const response = await api.post('/ai/confirm-strategy', data);
    return response.data;
  },
};
