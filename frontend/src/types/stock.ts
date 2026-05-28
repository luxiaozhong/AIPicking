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

export interface KLineItem {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  vol: number;
  amount: number;
}

export interface KLineData {
  ts_code: string;
  name: string;
  items: KLineItem[];
}
