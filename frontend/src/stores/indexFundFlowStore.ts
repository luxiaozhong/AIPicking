import { create } from 'zustand';
import { indexFundFlowService } from '@/services/indexFundFlowService';
import type {
  IndexInfo,
  ConstituentFlowItem,
  MultiStockTrend,
  IndustrySummaryItem,
  TreemapItem,
  SnapshotData,
} from '@/services/indexFundFlowService';

// ── 交易时段判断 ──

function isInMarketHours(): boolean {
  const now = new Date();
  const day = now.getDay(); // 0 = Sunday, 6 = Saturday
  if (day === 0 || day === 6) return false;
  const hour = now.getHours();
  const minute = now.getMinutes();
  const totalMinutes = hour * 60 + minute;
  // 9:30 - 15:00
  return totalMinutes >= 9 * 60 + 30 && totalMinutes <= 15 * 60;
}

interface IndexFundFlowState {
  // ── 指数选择 ──
  selectedIndexCode: string | null;
  indices: IndexInfo[];

  // ── D 看板数据 ──
  constituentFlow: ConstituentFlowItem[];
  constituentFlowDate: string | null;
  multiStockTrend: MultiStockTrend | null;
  industrySummary: IndustrySummaryItem[];
  treemapData: TreemapItem[];

  // ── B 竞速数据 ──
  snapshots: SnapshotData | null;

  // ── UI 状态 ──
  loading: Record<string, boolean>;
  error: string | null;
  selectedDate: string | undefined;
  sortField: string;
  trendTopN: number;

  // ── 轮询 ──
  pollIntervalId: ReturnType<typeof setInterval> | null;
  isPolling: boolean;
  lastUpdated: string | null;

  // ── Actions ──
  setSelectedIndexCode: (code: string) => void;
  setSelectedDate: (date: string | undefined) => void;
  setSortField: (sort: string) => void;
  setTrendTopN: (n: number) => void;

  fetchIndices: () => Promise<void>;
  fetchConstituentFlow: (date?: string, sort?: string) => Promise<void>;
  fetchMultiStockTrend: (days?: number, topN?: number) => Promise<void>;
  fetchIndustrySummary: (date?: string) => Promise<void>;
  fetchTreemap: (date?: string) => Promise<void>;
  fetchSnapshots: (date?: string) => Promise<void>;
  fetchAllData: (date?: string) => Promise<void>;

  startPolling: () => void;
  stopPolling: () => void;
  clearError: () => void;
}

export const useIndexFundFlowStore = create<IndexFundFlowState>((set, get) => ({
  // ── Initial state ──
  selectedIndexCode: null,
  indices: [],
  constituentFlow: [],
  constituentFlowDate: null,
  multiStockTrend: null,
  industrySummary: [],
  treemapData: [],
  snapshots: null,
  loading: {},
  error: null,
  selectedDate: undefined,
  sortField: 'main_net',
  trendTopN: 5,
  pollIntervalId: null,
  isPolling: false,
  lastUpdated: null,

  // ── Setters ──

  setSelectedIndexCode: (code) => {
    set({ selectedIndexCode: code, error: null });
    if (code) {
      // Persist to URL param and localStorage
      const params = new URLSearchParams(window.location.search);
      params.set('index', code);
      window.history.replaceState(null, '', `?${params.toString()}`);
      localStorage.setItem('indexFundFlow_selectedIndex', code);

      const state = get();
      get().fetchAllData(state.selectedDate);
    }
  },

  setSelectedDate: (date) => {
    set({ selectedDate: date, error: null });
    const state = get();
    if (state.selectedIndexCode) {
      get().fetchAllData(date);
    }
  },

  setSortField: (sort) => {
    set({ sortField: sort });
    const state = get();
    if (state.selectedIndexCode) {
      get().fetchConstituentFlow(state.selectedDate, sort);
    }
  },

  setTrendTopN: (n) => {
    set({ trendTopN: n });
    const state = get();
    if (state.selectedIndexCode) {
      get().fetchMultiStockTrend(30, n);
    }
  },

  // ── Fetchers ──

  fetchIndices: async () => {
    set((s) => ({ loading: { ...s.loading, indices: true }, error: null }));
    try {
      const data = await indexFundFlowService.getIndices();
      set({ indices: data, loading: { ...get().loading, indices: false } });
      // Auto-select from URL param → localStorage → default 980080
      if (!get().selectedIndexCode && data.length > 0) {
        const params = new URLSearchParams(window.location.search);
        const urlIndex = params.get('index');
        const savedIndex = localStorage.getItem('indexFundFlow_selectedIndex');
        const preferred = urlIndex || savedIndex;
        const defaultIdx = (preferred && data.find((d) => d.index_code === preferred))
          || data.find((d) => d.index_code === '980080')
          || data[0];
        get().setSelectedIndexCode(defaultIdx.index_code);
      }
    } catch (e: any) {
      set({
        error: e?.response?.data?.message || e?.message || '获取指数列表失败',
        loading: { ...get().loading, indices: false },
      });
    }
  },

  fetchConstituentFlow: async (date, sort) => {
    const code = get().selectedIndexCode;
    if (!code) return;
    set((s) => ({ loading: { ...s.loading, constituentFlow: true }, error: null }));
    try {
      const data = await indexFundFlowService.getConstituentFlow(
        code, date, sort || get().sortField, 100
      );
      set({
        constituentFlow: data.items,
        constituentFlowDate: data.trade_date || null,
        lastUpdated: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        loading: { ...get().loading, constituentFlow: false },
      });
    } catch (e: any) {
      set({
        error: e?.response?.data?.message || e?.message || '获取成分股资金流失败',
        loading: { ...get().loading, constituentFlow: false },
      });
    }
  },

  fetchMultiStockTrend: async (days = 30, topN) => {
    const code = get().selectedIndexCode;
    if (!code) return;
    set((s) => ({ loading: { ...s.loading, multiStockTrend: true } }));
    try {
      const data = await indexFundFlowService.getMultiStockTrend(
        code, days, topN || get().trendTopN
      );
      set({
        multiStockTrend: data,
        loading: { ...get().loading, multiStockTrend: false },
      });
    } catch (e: any) {
      set({
        loading: { ...get().loading, multiStockTrend: false },
      });
    }
  },

  fetchIndustrySummary: async (date) => {
    const code = get().selectedIndexCode;
    if (!code) return;
    set((s) => ({ loading: { ...s.loading, industrySummary: true } }));
    try {
      const data = await indexFundFlowService.getIndustrySummary(code, date);
      set({
        industrySummary: data.items,
        loading: { ...get().loading, industrySummary: false },
      });
    } catch (e: any) {
      set({
        loading: { ...get().loading, industrySummary: false },
      });
    }
  },

  fetchTreemap: async (date) => {
    const code = get().selectedIndexCode;
    if (!code) return;
    set((s) => ({ loading: { ...s.loading, treemap: true } }));
    try {
      const data = await indexFundFlowService.getTreemap(code, date);
      set({
        treemapData: data.items,
        loading: { ...get().loading, treemap: false },
      });
    } catch (e: any) {
      set({
        loading: { ...get().loading, treemap: false },
      });
    }
  },

  fetchSnapshots: async (date) => {
    const code = get().selectedIndexCode;
    if (!code) return;
    set((s) => ({ loading: { ...s.loading, snapshots: true } }));
    try {
      const data = await indexFundFlowService.getSnapshots(code, date);
      set({
        snapshots: data,
        lastUpdated: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        loading: { ...get().loading, snapshots: false },
      });
    } catch (e: any) {
      set({
        loading: { ...get().loading, snapshots: false },
      });
    }
  },

  fetchAllData: async (date) => {
    await Promise.all([
      get().fetchConstituentFlow(date),
      get().fetchMultiStockTrend(30),
      get().fetchIndustrySummary(date),
      get().fetchTreemap(date),
      get().fetchSnapshots(date),
    ]);
  },

  // ── Polling ──

  startPolling: () => {
    const state = get();
    if (state.pollIntervalId) return; // already polling

    // Fetch immediately on start
    get().fetchSnapshots(get().selectedDate);

    const id = setInterval(() => {
      if (isInMarketHours()) {
        get().fetchSnapshots(get().selectedDate);
      } else {
        get().stopPolling();
      }
    }, 60_000); // 60s polling

    set({ pollIntervalId: id, isPolling: true });
  },

  stopPolling: () => {
    const state = get();
    if (state.pollIntervalId) {
      clearInterval(state.pollIntervalId);
    }
    set({ pollIntervalId: null, isPolling: false });
  },

  clearError: () => set({ error: null }),
}));
