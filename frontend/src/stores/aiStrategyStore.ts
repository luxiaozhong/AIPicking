import { create } from 'zustand';
import { aiService, connectAnalysisSSE } from '@/services/aiService';
import strategyService from '@/services/strategyService';
import type {
  AnalysisPhase,
  AnalysisResult,
  AnalysisTask,
  GenerationProgress,
  IndicatorItem,
} from '@/types/aiStrategy';

// 模块级变量存储 SSE 连接 abort 函数
let _sseAbort: (() => void) | null = null;

function _disconnectSSE() {
  if (_sseAbort) {
    _sseAbort();
    _sseAbort = null;
  }
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
  connectAndListen: (taskId: string) => void;
  cancelPolling: () => void;
  clearAnalysis: () => void;
  updateIndicator: (index: number, field: string, value: unknown) => void;
  removeIndicator: (index: number) => void;
  addIndicator: (indicator: IndicatorItem) => void;
  setBuyLogic: (logic: 'AND' | 'OR') => void;
  confirmAndGenerate: (strategyName?: string) => Promise<number>;
  deleteTask: (taskId: string) => Promise<void>;
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
        get().connectAndListen(taskId);
      } else {
        set({ phase: 'idle', error: res.message || '提交失败' });
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({ phase: 'failed', error: err.response?.data?.message || '提交分析失败' });
    }
  },

  /** 通过 SSE 连接监听任务状态变化 */
  connectAndListen: (taskId: string) => {
    _disconnectSSE();

    _sseAbort = connectAnalysisSSE(
      taskId,
      // onEvent: 收到 SSE 推送
      (data) => {
        const status = data.status as string;

        if (status === 'completed' || status === 'review') {
          if (data.strategy_id) {
            set({
              phase: 'completed',
              generatedStrategyId: data.strategy_id as number,
              progress: null,
            });
          } else {
            set({
              phase: 'review',
              result: data as unknown as AnalysisResult,
              indicators: (data.indicators as IndicatorItem[]) || [],
              error: null,
              progress: null,
            });
          }
          _disconnectSSE();
          get().fetchTasks();
        } else if (status === 'failed') {
          set({
            phase: 'failed',
            error: (data.error_message as string) || '任务执行失败',
            progress: null,
          });
          _disconnectSSE();
          get().fetchTasks();
        } else if (status === 'generating') {
          set({ phase: 'generating' });
          if (data.progress) {
            set({ progress: data.progress as GenerationProgress });
          }
        }
        // processing → 保持 analyzing 状态，不做额外操作
      },
      // onDone: SSE 流结束
      () => {
        _disconnectSSE();
      },
      // onError: 连接异常
      () => {
        _disconnectSSE();
      },
    );
  },

  cancelPolling: () => {
    _disconnectSSE();
  },

  clearAnalysis: () => {
    _disconnectSSE();
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
          _disconnectSSE();

          _sseAbort = connectAnalysisSSE(
            taskId!,
            (data) => {
              const status = data.status as string;

              if (data.progress) {
                set({ progress: data.progress as GenerationProgress });
              }

              if (
                (status === 'completed' || status === 'review') &&
                data.strategy_id
              ) {
                const sid = data.strategy_id as number;
                // 验证策略存在
                strategyService.getStrategy(sid).then(() => {
                  set({
                    generatedStrategyId: sid,
                    phase: 'completed',
                    progress: null,
                  });
                  _disconnectSSE();
                  resolve(sid);
                }).catch(() => {
                  // 策略尚未就绪，SSE 会继续推送
                });
              } else if (status === 'failed') {
                set({
                  phase: 'failed',
                  error: (data.error_message as string) || '生成失败',
                  progress: null,
                });
                _disconnectSSE();
                reject(new Error(data.error_message as string));
              }
            },
            () => { _disconnectSSE(); },
            () => { _disconnectSSE(); },
          );
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

  deleteTask: async (taskId: string) => {
    try {
      await aiService.deleteTask(taskId);
      // 如果删除的是当前任务，重置状态
      if (get().taskId === taskId) {
        _disconnectSSE();
        set({
          taskId: null,
          phase: 'idle',
          error: null,
          result: null,
          indicators: [],
          progress: null,
        });
      }
      // 刷新列表
      get().fetchTasks();
    } catch {
      // silent
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
      // silent — 非关键路径
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
        get().connectAndListen(taskId);
      } else if (data.status === 'generating') {
        set({ phase: 'generating', progress: data.progress || null });
        get().connectAndListen(taskId);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      set({ phase: 'failed', error: err.response?.data?.message || '加载任务失败' });
    }
  },

  resumeInProgressTask: async () => {
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

      // 恢复 stale 状态
      const { taskId, phase } = get();
      if ((phase === 'analyzing' || phase === 'generating') && taskId) {
        const currentTask = tasks.find((t) => t.task_id === taskId);
        if (currentTask?.status === 'completed' || currentTask?.status === 'review') {
          get().loadTask(taskId);
        } else if (currentTask?.status === 'failed') {
          set({ phase: 'failed', error: '任务执行失败' });
        } else if (!currentTask) {
          set({ phase: 'idle', taskId: null, error: null });
        }
      }
    } catch {
      // silent
    }
  },
}));
