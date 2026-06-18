import api from './api';

export interface WatchlistStock {
  raw_code: string;
  stock_name: string;
  ts_code: string;
  symbol: string;
  eff_date: string;
  weight: number | null;
}

export interface WatchlistIndexInfo {
  index_code: string;
  index_name: string;
  full_name: string;
  publisher: string;
  constituent_count: number;
  last_sync_date: string;
}

export interface WatchlistData {
  stocks: WatchlistStock[];
  index_info: WatchlistIndexInfo | null;
}

const watchlistService = {
  async getWatchlist(): Promise<WatchlistData> {
    const res = await api.get('/watchlist');
    return res.data.data;
  },

  async addStocks(tsCodes: string[]): Promise<{ added: number; ts_codes: string[] }> {
    const res = await api.post('/watchlist/stocks', { ts_codes: tsCodes });
    return res.data.data;
  },

  async removeStock(tsCode: string): Promise<{ removed: boolean; ts_code: string }> {
    const res = await api.delete(`/watchlist/stocks/${encodeURIComponent(tsCode)}`);
    return res.data.data;
  },
};

export default watchlistService;
