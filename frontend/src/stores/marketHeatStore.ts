import { create } from 'zustand';
import marketHeatService, {
  type OverviewData,
  type SectorItem,
  type ThemeItem,
  type HotStockItem,
  type DragonTigerItem,
  type NorthboundItem,
  type TemperatureHistoryItem,
  type BoardTemperatureHistoryItem,
  type SectorFundOverview,
  type SectorFundHistoryItem,
} from '@/services/marketHeatService';

interface MarketHeatState {
  tradeDate: string | undefined;
  availableDates: string[];
  overview: OverviewData | null;
  overviewLoading: boolean;
  sectorType: 'industry' | 'concept';
  sectors: SectorItem[];
  sectorsLoading: boolean;
  themes: ThemeItem[];
  themesLoading: boolean;
  hotStocks: HotStockItem[];
  hotStocksTotal: number;
  hotStocksPage: number;
  hotStocksLoading: boolean;
  dragonTiger: DragonTigerItem[];
  dragonTigerTotal: number;
  dragonTigerPage: number;
  dragonTigerLoading: boolean;
  northbound: NorthboundItem[];
  northboundLoading: boolean;
  temperatureHistory: TemperatureHistoryItem[];
  temperatureHistoryLoading: boolean;
  boardTemperatureHistory: BoardTemperatureHistoryItem[];
  boardTemperatureHistoryLoading: boolean;
  sectorFundOverview: SectorFundOverview | null;
  sectorFundOverviewLoading: boolean;
  sectorFundHistory: SectorFundHistoryItem[];
  sectorFundHistoryLoading: boolean;
  drawer: {
    open: boolean;
    type: 'sector' | 'theme' | null;
    code: string | null;
    name: string | null;
  };
  error: string | null;

  setTradeDate: (date: string) => void;
  setSectorType: (type: 'industry' | 'concept') => void;
  fetchAvailableDates: () => Promise<void>;
  fetchOverview: () => Promise<void>;
  fetchSectors: () => Promise<void>;
  fetchThemes: () => Promise<void>;
  fetchHotStocks: (page?: number) => Promise<void>;
  fetchDragonTiger: (page?: number) => Promise<void>;
  fetchNorthbound: () => Promise<void>;
  fetchTemperatureHistory: () => Promise<void>;
  fetchBoardTemperatureHistory: (boardCode: string) => Promise<void>;
  fetchSectorFundOverview: () => Promise<void>;
  fetchSectorFundHistory: () => Promise<void>;
  openDrawer: (type: 'sector' | 'theme', code: string, name: string) => void;
  closeDrawer: () => void;
  clearError: () => void;
}

export const useMarketHeatStore = create<MarketHeatState>((set, get) => ({
  tradeDate: undefined,
  availableDates: [],
  overview: null,
  overviewLoading: false,
  sectorType: 'industry',
  sectors: [],
  sectorsLoading: false,
  themes: [],
  themesLoading: false,
  hotStocks: [],
  hotStocksTotal: 0,
  hotStocksPage: 1,
  hotStocksLoading: false,
  dragonTiger: [],
  dragonTigerTotal: 0,
  dragonTigerPage: 1,
  dragonTigerLoading: false,
  northbound: [],
  northboundLoading: false,
  temperatureHistory: [],
  temperatureHistoryLoading: false,
  boardTemperatureHistory: [],
  boardTemperatureHistoryLoading: false,
  sectorFundOverview: null,
  sectorFundOverviewLoading: false,
  sectorFundHistory: [],
  sectorFundHistoryLoading: false,
  drawer: { open: false, type: null, code: null, name: null },
  error: null,

  setTradeDate: (date: string) => {
    set({ tradeDate: date });
    get().fetchOverview();
    get().fetchSectors();
    get().fetchThemes();
    get().fetchHotStocks(1);
    get().fetchDragonTiger(1);
  },

  setSectorType: (type: 'industry' | 'concept') => {
    set({ sectorType: type });
    get().fetchSectors();
  },

  fetchAvailableDates: async () => {
    try {
      const dates = await marketHeatService.getAvailableDates();
      set({ availableDates: dates, tradeDate: dates[0] });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取日期失败' });
    }
  },

  fetchOverview: async () => {
    set({ overviewLoading: true, error: null });
    try {
      const data = await marketHeatService.getOverview(get().tradeDate);
      set({ overview: data, overviewLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取概览失败', overviewLoading: false });
    }
  },

  fetchSectors: async () => {
    set({ sectorsLoading: true, error: null });
    try {
      const data = await marketHeatService.getSectors(get().tradeDate, get().sectorType);
      set({ sectors: data, sectorsLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取板块失败', sectorsLoading: false });
    }
  },

  fetchThemes: async () => {
    set({ themesLoading: true, error: null });
    try {
      const data = await marketHeatService.getThemes(get().tradeDate);
      set({ themes: data, themesLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取主题失败', themesLoading: false });
    }
  },

  fetchHotStocks: async (page?: number) => {
    const p = page ?? get().hotStocksPage;
    set({ hotStocksLoading: true, hotStocksPage: p, error: null });
    try {
      const data = await marketHeatService.getHotStocks(get().tradeDate, p);
      set({ hotStocks: data.items, hotStocksTotal: data.total, hotStocksLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取热门股失败', hotStocksLoading: false });
    }
  },

  fetchDragonTiger: async (page?: number) => {
    const p = page ?? get().dragonTigerPage;
    set({ dragonTigerLoading: true, dragonTigerPage: p, error: null });
    try {
      const data = await marketHeatService.getDragonTiger(get().tradeDate, p);
      set({ dragonTiger: data.items, dragonTigerTotal: data.total, dragonTigerLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取龙虎榜失败', dragonTigerLoading: false });
    }
  },

  fetchNorthbound: async () => {
    set({ northboundLoading: true, error: null });
    try {
      const data = await marketHeatService.getNorthbound();
      set({ northbound: data, northboundLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取北向资金失败', northboundLoading: false });
    }
  },

  fetchTemperatureHistory: async () => {
    set({ temperatureHistoryLoading: true, error: null });
    try {
      const data = await marketHeatService.getTemperatureHistory(60);
      set({ temperatureHistory: data, temperatureHistoryLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取温度历史失败', temperatureHistoryLoading: false });
    }
  },

  fetchBoardTemperatureHistory: async (boardCode: string) => {
    set({ boardTemperatureHistoryLoading: true, error: null });
    try {
      const data = await marketHeatService.getBoardTemperatureHistory(boardCode, 60);
      set({ boardTemperatureHistory: data, boardTemperatureHistoryLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取板块温度历史失败', boardTemperatureHistoryLoading: false });
    }
  },

  fetchSectorFundOverview: async () => {
    set({ sectorFundOverviewLoading: true, error: null });
    try {
      const data = await marketHeatService.getSectorFundOverview(get().tradeDate);
      set({ sectorFundOverview: data, sectorFundOverviewLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取板块资金流失败', sectorFundOverviewLoading: false });
    }
  },

  fetchSectorFundHistory: async () => {
    set({ sectorFundHistoryLoading: true, error: null });
    try {
      const data = await marketHeatService.getSectorFundHistory(90);
      set({ sectorFundHistory: data, sectorFundHistoryLoading: false });
    } catch (err: any) {
      set({ error: err.response?.data?.message || '获取板块资金流历史失败', sectorFundHistoryLoading: false });
    }
  },

  openDrawer: (type, code, name) =>
    set({ drawer: { open: true, type, code, name } }),

  closeDrawer: () =>
    set({ drawer: { open: false, type: null, code: null, name: null } }),

  clearError: () => set({ error: null }),
}));
