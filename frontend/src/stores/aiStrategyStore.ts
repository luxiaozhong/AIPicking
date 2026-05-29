import { create } from 'zustand';
import { aiService } from '@/services/aiService';
import type {
  AnalysisResult,
  AnalysisTask,
  IndicatorItem,
} from '@/types/aiStrategy';

interface AIStrategyState {
  taskId: string | null;
  status: 'idle' | 'submitting' | 'polling' | 'completed' | 'failed';
  error: string | null;
  result: AnalysisResult | null;

  indicators: IndicatorItem[];
  buyLogic: 'AND' | 'OR';

  tasks: AnalysisTask[];
  tasksLoading: boolean;

  submitting: boolean;
  generatedStrategyId: number | null;

  submitAnalysis: (
    tsCode: string,
    date: string,
    model: string,
    prompt: string
  ) => Promise<void>;
  pollResult: (taskId: string) => Promise<void>;
  clearAnalysis: () => void;
  updateIndicator: (index: number, field: string, value: unknown) => void;
  removeIndicator: (index: number) => void;
  addIndicator: (indicator: IndicatorItem) => void;
  setBuyLogic: (logic: 'AND' | 'OR') => void;
  confirmAndGenerate: (strategyName?: string) => Promise<number>;
  fetchTasks: () => Promise<void>;
  loadTask: (taskId: string) => Promise<void>;
}

export const useAIStrategyStore = create<AIStrategyState>((set, get) => ({
  taskId: null,
  status: 'idle',
  error: null,
  result: null,
  indicators: [],
  buyLogic: 'OR',
  tasks: [],
  tasksLoading: false,
  submitting: false,
  generatedStrategyId: null,

  submitAnalysis: async (tsCode, date, model, prompt) => {
    set({ status: 'submitting', error: null });
    try {
      const res = await aiService.analyzeStock({
        ts_code: tsCode,
        date,
        model,
        prompt,
      });
      if (res.code === 0) {
        const taskId = res.data.task_id;
        set({ taskId, status: 'polling' });
        get().pollResult(taskId);
      } else {
        set({
          status: 'idle',
          error: res.message || '提交失败',
        });
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({
        status: 'failed',
        error: err.response?.data?.message || '提交分析失败',
      });
    }
  },

  pollResult: async (taskId: string) => {
    const poll = async () => {
      try {
        const res = await aiService.getAnalysisResult(taskId);
        if (res.code !== 0) return;

        const data = res.data;
        if (data.status === 'completed') {
          set({
            status: 'completed',
            result: data,
            indicators: data.indicators || [],
            error: null,
          });
          get().fetchTasks();
        } else if (data.status === 'failed') {
          set({
            status: 'failed',
            error: data.error_message || '分析失败',
          });
          get().fetchTasks();
        } else {
          setTimeout(poll, 2000);
        }
      } catch {
        setTimeout(poll, 3000);
      }
    };
    setTimeout(poll, 2000);
  },

  clearAnalysis: () =>
    set({
      taskId: null,
      status: 'idle',
      error: null,
      result: null,
      indicators: [],
    }),

  updateIndicator: (index, field, value) => {
    const indicators = [...get().indicators];
    indicators[index] = { ...indicators[index], [field]: value };
    set({ indicators });
  },

  removeIndicator: (index) => {
    set({ indicators: get().indicators.filter((_, i) => i !== index) });
  },

  addIndicator: (indicator) => {
    set({ indicators: [...get().indicators, indicator] });
  },

  setBuyLogic: (buyLogic) => set({ buyLogic }),

  confirmAndGenerate: async (strategyName) => {
    const { taskId, indicators, buyLogic } = get();
    set({ submitting: true });
    try {
      const res = await aiService.confirmStrategy({
        task_id: taskId!,
        strategy_name: strategyName,
        indicators: indicators as unknown as Record<string, unknown>[],
        buy_logic: buyLogic,
      });

      if (res.code === 0) {
        set({
          generatedStrategyId: res.data.strategy_id,
          submitting: false,
        });
        return res.data.strategy_id;
      } else {
        set({ submitting: false, error: res.message || '生成策略失败' });
        throw new Error(res.message);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({
        submitting: false,
        error: err.response?.data?.message || '生成策略失败',
      });
      throw e;
    }
  },

  fetchTasks: async () => {
    set({ tasksLoading: true });
    try {
      const res = await aiService.getTasks();
      if (res.code === 0) {
        set({ tasks: res.data.tasks || [] });
      }
    } catch {
      // silent
    } finally {
      set({ tasksLoading: false });
    }
  },

  loadTask: async (taskId: string) => {
    set({ taskId, status: 'completed' });
    try {
      const res = await aiService.getAnalysisResult(taskId);
      if (res.code === 0 && res.data.status === 'completed') {
        set({
          result: res.data,
          indicators: res.data.indicators || [],
          error: null,
        });
      } else if (res.data.status === 'failed') {
        set({ status: 'failed', error: res.data.error_message });
      } else if (res.data.status === 'processing') {
        set({ status: 'polling' });
        get().pollResult(taskId);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({ status: 'failed', error: err.response?.data?.message || '加载任务失败' });
    }
  },
}));
