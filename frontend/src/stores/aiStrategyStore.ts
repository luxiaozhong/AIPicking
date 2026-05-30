import { create } from 'zustand';
import { aiService } from '@/services/aiService';
import strategyService from '@/services/strategyService';
import type {
  AnalysisPhase,
  AnalysisResult,
  AnalysisTask,
  GenerationProgress,
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
  phase: AnalysisPhase;
  error: string | null;
  result: AnalysisResult | null;

  indicators: IndicatorItem[];
  buyLogic: 'AND' | 'OR';

  tasks: AnalysisTask[];
  tasksLoading: boolean;

  generatedStrategyId: number | null;
  progress: GenerationProgress | null;

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
  phase: 'idle',
  error: null,
  result: null,
  indicators: [],
  buyLogic: 'OR',
  tasks: [],
  tasksLoading: false,
  generatedStrategyId: null,
  progress: null,

  submitAnalysis: async (tsCode, date, model, prompt) => {
    set({ phase: 'submitting', error: null });
    try {
      const res = await aiService.analyzeStock({
        ts_code: tsCode,
        date,
        model,
        prompt,
      });
      if (res.code === 0) {
        const taskId = res.data.task_id;
        set({ taskId, phase: 'analyzing' });
        get().pollResult(taskId);
      } else {
        set({ phase: 'idle', error: res.message || '提交失败' });
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({ phase: 'failed', error: err.response?.data?.message || '提交分析失败' });
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
        if (data.status === 'completed' || data.status === 'review') {
          // 有 strategy_id → 策略已生成；否则 → 分析完成等待确认（review）
          if (data.strategy_id) {
            set({ phase: 'completed', generatedStrategyId: data.strategy_id });
          } else {
            set({
              phase: 'review',
              result: data,
              indicators: data.indicators || [],
              error: null,
            });
          }
          get().fetchTasks();
        } else if (data.status === 'failed') {
          set({ phase: 'failed', error: data.error_message || '分析失败' });
          get().fetchTasks();
        } else if (data.status === 'generating') {
          // 正在生成策略代码，更新进度
          set({ phase: 'generating' });
          if (data.progress) {
            set({ progress: data.progress });
          }
          _schedulePoll(poll, 2000);
        } else {
          // processing → 仍在分析 K 线
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
  },

  clearAnalysis: () => {
    _clearPollTimer();
    set({
      taskId: null,
      phase: 'idle',
      error: null,
      result: null,
      indicators: [],
      progress: null,
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
    set({ phase: 'generating', progress: null });
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
              // 更新进度
              if (r.data.progress) {
                set({ progress: r.data.progress });
              }
              if (r.data.status === 'completed' && r.data.strategy_id) {
                const sid = r.data.strategy_id;
                try {
                  await strategyService.getStrategy(sid);
                } catch {
                  _schedulePoll(poll, 1500);
                  return;
                }
                set({ generatedStrategyId: sid, phase: 'completed', progress: null });
                resolve(sid);
              } else if (r.data.status === 'failed') {
                set({ phase: 'failed', error: r.data.error_message || '生成失败', progress: null });
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
        set({ generatedStrategyId: res.data.strategy_id, phase: 'completed' });
        return res.data.strategy_id;
      } else {
        set({ phase: 'failed', error: res.message || '生成策略失败' });
        throw new Error(res.message);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({ phase: 'failed', error: err.response?.data?.message || '生成策略失败', progress: null });
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
      // silent — 非关键路径，静默失败
    } finally {
      set({ tasksLoading: false });
    }
  },

  loadTask: async (taskId: string) => {
    set({ taskId });
    try {
      const res = await aiService.getAnalysisResult(taskId);
      const data = res.data;
      if (res.code === 0 && (data.status === 'completed' || data.status === 'review')) {
        if (data.strategy_id) {
          set({ phase: 'completed', generatedStrategyId: data.strategy_id });
        } else {
          set({
            phase: 'review',
            result: data,
            indicators: data.indicators || [],
            error: null,
          });
        }
      } else if (data.status === 'failed') {
        set({ phase: 'failed', error: data.error_message });
      } else if (data.status === 'processing') {
        set({ phase: 'analyzing' });
        get().pollResult(taskId);
      } else if (data.status === 'generating') {
        set({ phase: 'generating', progress: data.progress || null });
        get().pollResult(taskId);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({ phase: 'failed', error: err.response?.data?.message || '加载任务失败' });
    }
  },

  resumeInProgressTask: async () => {
    // 页面加载时，检查是否有进行中的任务并自动恢复轮询；
    // 同时处理导航离开后 store 残留的 stale 状态。
    try {
      const res = await aiService.getTasks();
      if (res.code !== 0) return;
      const tasks: AnalysisTask[] = res.data.tasks || [];
      const inProgress = tasks.find(
        (t) => t.status === 'processing' || t.status === 'generating'
      );
      if (inProgress) {
        get().loadTask(inProgress.task_id);
        return;
      }

      // 没有进行中的任务，但如果 store 仍处于 analyzing/generating
      // 且 taskId 对应的任务已 completed，自动加载结果（恢复 stale 状态）
      const { taskId, phase } = get();
      if ((phase === 'analyzing' || phase === 'generating') && taskId) {
        const currentTask = tasks.find((t) => t.task_id === taskId);
        if (currentTask?.status === 'completed') {
          get().loadTask(taskId);
        } else if (currentTask?.status === 'failed') {
          set({ phase: 'failed', error: '任务执行失败' });
        } else if (!currentTask) {
          set({ phase: 'idle', taskId: null, error: null });
        }
        // 如果仍在 processing/generating，上面的 inProgress 已处理
      }
    } catch {
      // silent
    }
  },
}));
