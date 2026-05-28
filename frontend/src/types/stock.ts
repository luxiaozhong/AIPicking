export interface StockItem {
  ts_code: string;
  symbol: string;
  name: string;
  market: string;
}

export interface StockSearchResponse {
  items: StockItem[];
  total: number;
}
