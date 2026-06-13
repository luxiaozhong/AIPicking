import { create } from 'zustand';
import { fundFlowService } from '@/services/fundFlowService';
import type {
  FundFlowOverview,
  FundFlowHistoryItem,
  BoardHistoryItem,
  BreadthHistoryItem,
  IndustryFlowItem,
  ConceptFlowItem,
  HeatmapData,
  StockFlowItem,
  StockTrend,
} from '@/services/fundFlowService';

interface FundFlowState {
  // ── Data ──
  overview: FundFlowOverview | null;
  history: FundFlowHistoryItem[];
  boardHistory: BoardHistoryItem[];
  breadthHistory: BreadthHistoryItem[];
  industries: IndustryFlowItem[];
  concepts: ConceptFlowItem[];
  heatmap: HeatmapData | null;
  stockRanking: StockFlowItem[];
  stockTrend: StockTrend | null;
  availableDates: string[];

  // ── UI state ──
  loading: Record<string, boolean>;
  error: string | null;
  selectedDate: string | undefined;
  selectedStock: string | null;
  sectorType: 'industry' | 'concept';

  // ── Actions ──
  setSelectedDate: (date: string | undefined) => void;
  setSelectedStock: (tsCode: string | null) => void;
  setSectorType: (type: 'industry' | 'concept') => void;

  fetchAvailableDates: () => Promise<void>;
  fetchOverview: (date?: string) => Promise<void>;
  fetchHistory: (days?: number) => Promise<void>;
  fetchBoardHistory: (days?: number) => Promise<void>;
  fetchBreadthHistory: (days?: number) => Promise<void>;
  fetchIndustryFlow: (date?: string) => Promise<void>;
  fetchConceptFlow: (date?: string) => Promise<void>;
  fetchHeatmap: (days?: number, type?: 'industry' | 'concept') => Promise<void>;
  fetchStockRanking: (date?: string, sort?: string) => Promise<void>;
  fetchStockTrend: (tsCode: string, days?: number) => Promise<void>;

  clearError: () => void;
}

export const useFundFlowStore = create<FundFlowState>((set, get) => ({
  // ── Initial state ──
  overview: null,
  history: [],
  boardHistory: [],
  breadthHistory: [],
  industries: [],
  concepts: [],
  heatmap: null,
  stockRanking: [],
  stockTrend: null,
  availableDates: [],
  loading: {},
  error: null,
  selectedDate: undefined,
  selectedStock: null,
  sectorType: 'industry',

  // ── Simple setters ──
  setSelectedDate: (date) => {
    set({ selectedDate: date, error: null });
    // Trigger dependent fetches
    get().fetchOverview(date);
    get().fetchIndustryFlow(date);
    get().fetchConceptFlow(date);
    get().fetchStockRanking(date);
  },

  setSelectedStock: (tsCode) => {
    set({ selectedStock: tsCode });
    if (tsCode) {
      get().fetchStockTrend(tsCode);
    }
  },

  setSectorType: (type) => {
    set({ sectorType: type });
    get().fetchHeatmap(20, type);
  },

  // ── Async fetches ──
  fetchAvailableDates: async () => {
    set((s) => ({ loading: { ...s.loading, availableDates: true }, error: null }));
    try {
      const dates = await fundFlowService.getAvailableDates();
      set({ availableDates: dates, loading: { ...get().loading, availableDates: false } });
    } catch (e: any) {
      set({
        error: e.response?.data?.message || '获取可用日期失败',
        loading: { ...get().loading, availableDates: false },
      });
    }
  },

  fetchOverview: async (date?: string) => {
    set((s) => ({ loading: { ...s.loading, overview: true }, error: null }));
    try {
      const overview = await fundFlowService.getOverview(date);
      set({ overview, loading: { ...get().loading, overview: false } });
    } catch (e: any) {
      set({
        error: e.response?.data?.message || '获取资金流总览失败',
        loading: { ...get().loading, overview: false },
      });
    }
  },

  fetchHistory: async (days?: number) => {
    set((s) => ({ loading: { ...s.loading, history: true }, error: null }));
    try {
      const history = await fundFlowService.getHistory(days);
      set({ history, loading: { ...get().loading, history: false } });
    } catch (e: any) {
      set({
        error: e.response?.data?.message || '获取资金流历史失败',
        loading: { ...get().loading, history: false },
      });
    }
  },

  fetchBoardHistory: async (days?: number) => {
    set((s) => ({ loading: { ...s.loading, boardHistory: true }, error: null }));
    try {
      const boardHistory = await fundFlowService.getBoardHistory(days);
      set({ boardHistory, loading: { ...get().loading, boardHistory: false } });
    } catch (e: any) {
      set({
        error: e.response?.data?.message || '获取指数资金流失败',
        loading: { ...get().loading, boardHistory: false },
      });
    }
  },

  fetchBreadthHistory: async (days?: number) => {
    set((s) => ({ loading: { ...s.loading, breadthHistory: true }, error: null }));
    try {
      const breadthHistory = await fundFlowService.getBreadthHistory(days);
      set({ breadthHistory, loading: { ...get().loading, breadthHistory: false } });
    } catch (e: any) {
      set({
        error: e.response?.data?.message || '获取资金广度失败',
        loading: { ...get().loading, breadthHistory: false },
      });
    }
  },

  fetchIndustryFlow: async (date?: string) => {
    set((s) => ({ loading: { ...s.loading, industries: true }, error: null }));
    try {
      const data = await fundFlowService.getIndustryFlow(date);
      set({ industries: data.items, loading: { ...get().loading, industries: false } });
    } catch (e: any) {
      set({
        error: e.response?.data?.message || '获取行业资金流失败',
        loading: { ...get().loading, industries: false },
      });
    }
  },

  fetchConceptFlow: async (date?: string) => {
    set((s) => ({ loading: { ...s.loading, concepts: true }, error: null }));
    try {
      const data = await fundFlowService.getConceptFlow(date);
      set({ concepts: data.items, loading: { ...get().loading, concepts: false } });
    } catch (e: any) {
      set({
        error: e.response?.data?.message || '获取题材资金流失败',
        loading: { ...get().loading, concepts: false },
      });
    }
  },

  fetchHeatmap: async (days?: number, type?: 'industry' | 'concept') => {
    set((s) => ({ loading: { ...s.loading, heatmap: true }, error: null }));
    try {
      const heatmap = await fundFlowService.getHeatmap(days, type);
      set({ heatmap, loading: { ...get().loading, heatmap: false } });
    } catch (e: any) {
      set({
        error: e.response?.data?.message || '获取热力图数据失败',
        loading: { ...get().loading, heatmap: false },
      });
    }
  },

  fetchStockRanking: async (date?: string, sort?: string) => {
    set((s) => ({ loading: { ...s.loading, stockRanking: true }, error: null }));
    try {
      const data = await fundFlowService.getStockRanking(date, sort);
      set({ stockRanking: data.items, loading: { ...get().loading, stockRanking: false } });
    } catch (e: any) {
      set({
        error: e.response?.data?.message || '获取个股排名失败',
        loading: { ...get().loading, stockRanking: false },
      });
    }
  },

  fetchStockTrend: async (tsCode: string, days?: number) => {
    set((s) => ({ loading: { ...s.loading, stockTrend: true }, error: null }));
    try {
      const stockTrend = await fundFlowService.getStockTrend(tsCode, days);
      set({ stockTrend, loading: { ...get().loading, stockTrend: false } });
    } catch (e: any) {
      set({
        error: e.response?.data?.message || '获取个股趋势失败',
        loading: { ...get().loading, stockTrend: false },
      });
    }
  },

  clearError: () => set({ error: null }),
}));
