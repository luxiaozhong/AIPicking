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
  pre_close: number | null;
  vol: number;
  amount: number;
}

export interface KLineData {
  ts_code: string;
  name: string;
  items: KLineItem[];
}

export interface ValuationData {
  ts_code: string;
  trade_date: string;
  pe_ttm: number | null;
  pe_static: number | null;
  pb: number | null;
  market_cap: number | null;
  circ_market_cap: number | null;
  dividend_yield: number | null;
}
