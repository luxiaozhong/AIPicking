// 因子相关类型定义

export interface FactorParam {
  name: string;
  label: string;
  type: 'int' | 'float' | 'enum' | 'bool' | 'date';
  default: number | boolean | string;
  min?: number;
  max?: number;
  options?: { label: string; value: string }[];
}

export interface FactorMeta {
  id: string;
  name: string;
  category: string;
  description: string;
  params: FactorParam[];
  signal_type: 'buy' | 'sell' | 'both';
}

export interface FactorItem {
  factor_id: string;
  params: Record<string, number | boolean | string>;
}

export interface SignalGroup {
  logic: 'AND' | 'OR';
  factors: FactorItem[];
}

export interface FactorConfig {
  buy_signals: SignalGroup;
  sell_signals: SignalGroup;
  risk_factors: FactorItem[];
}

export interface FactorCategory {
  name: string;
  factors: FactorMeta[];
}
