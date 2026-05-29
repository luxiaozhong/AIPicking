import { create } from 'zustand';
import { aiService } from '@/services/aiService';
import strategyService from '@/services/strategyService';
import type {
  AnalysisResult,
  AnalysisTask,
  IndicatorItem,
} from '@/types/aiStrategy';

// 模块级变量存储 poll timer，避免 Zustand 不支持 ref 的问题
let _pollTimer: ReturnType<typeof setTimeout> | null = null;

function _clearPollTimer() {
  if (_pollTimer) {
    clearTimeout(_pollTimer);
    _pollTimer = null;
  }
}

function _schedulePoll(fn: () => void, delay: number) {
  _clearPollTimer();
  _pollTimer = setTimeout(fn, delay);
}

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
  cancelPolling: () => void;
  clearAnalysis: () => void;
  updateIndicator: (index: number, field: string, value: unknown) => void;
  removeIndicator: (index: number) => void;
  addIndicator: (indicator: IndicatorItem) => void;
  setBuyLogic: (logic: 'AND' | 'OR') => void;
  confirmAndGenerate: (strategyName?: string) => Promise<number>;
  fetchTasks: () => Promise<void>;
  loadTask: (taskId: string) => Promise<void>;
  resumeInProgressTask: () => Promise<void>;
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
        set({ status: 'idle', error: res.message || '提交失败' });
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({ status: 'failed', error: err.response?.data?.message || '提交分析失败' });
    }
  },

  pollResult: async (taskId: string) => {
    const poll = async () => {
      try {
        const res = await aiService.getAnalysisResult(taskId);
        if (res.code !== 0) {
          _schedulePoll(poll, 2000);
          return;
        }

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
          set({ status: 'failed', error: data.error_message || '分析失败' });
          get().fetchTasks();
        } else {
          _schedulePoll(poll, 2000);
        }
      } catch {
        _schedulePoll(poll, 3000);
      }
    };
    _schedulePoll(poll, 2000);
  },

  cancelPolling: () => {
    _clearPollTimer();
    // 不重置 status, 这样回到页面时可以恢复
  },

  clearAnalysis: () => {
    _clearPollTimer();
    set({
      taskId: null,
      status: 'idle',
      error: null,
      result: null,
      indicators: [],
    });
  },

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
    set({ submitting: true, status: 'polling' });
    try {
      const res = await aiService.confirmStrategy({
        task_id: taskId!,
        strategy_name: strategyName,
        indicators: indicators as unknown as Record<string, unknown>[],
      });

      if (res.code === 0 && res.data.status === 'generating') {
        return new Promise<number>((resolve, reject) => {
          const poll = async () => {
            try {
              const r = await aiService.getAnalysisResult(taskId!);
              if (r.data.status === 'completed' && r.data.strategy_id) {
                const sid = r.data.strategy_id;
                try {
                  await strategyService.getStrategy(sid);
                } catch {
                  _schedulePoll(poll, 1500);
                  return;
                }
                set({ generatedStrategyId: sid, submitting: false, status: 'completed' });
                resolve(sid);
              } else if (r.data.status === 'failed') {
                set({ submitting: false, status: 'failed', error: r.data.error_message || '生成失败' });
                reject(new Error(r.data.error_message));
              } else {
                _schedulePoll(poll, 2000);
              }
            } catch {
              _schedulePoll(poll, 3000);
            }
          };
          _schedulePoll(poll, 2000);
        });
      } else if (res.code === 0 && res.data.strategy_id) {
        set({ generatedStrategyId: res.data.strategy_id, submitting: false });
        return res.data.strategy_id;
      } else {
        set({ submitting: false, error: res.message || '生成策略失败' });
        throw new Error(res.message);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({ submitting: false, error: err.response?.data?.message || '生成策略失败' });
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
    set({ taskId });
    try {
      const res = await aiService.getAnalysisResult(taskId);
      const data = res.data;
      if (res.code === 0 && data.status === 'completed') {
        set({ status: 'completed', result: data, indicators: data.indicators || [], error: null });
      } else if (data.status === 'failed') {
        set({ status: 'failed', error: data.error_message });
      } else if (data.status === 'processing' || data.status === 'generating') {
        set({ status: 'polling' });
        get().pollResult(taskId);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({ status: 'failed', error: err.response?.data?.message || '加载任务失败' });
    }
  },

  resumeInProgressTask: async () => {
    // 页面加载时，检查是否有进行中的任务并自动恢复轮询
    try {
      const res = await aiService.getTasks();
      if (res.code !== 0) return;
      const tasks: AnalysisTask[] = res.data.tasks || [];
      const inProgress = tasks.find(
        (t) => t.status === 'processing' || t.status === 'generating'
      );
      if (inProgress) {
        get().loadTask(inProgress.task_id);
      }
    } catch {
      // silent
    }
  },
}));
