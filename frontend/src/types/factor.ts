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
  factor_type?: 'kline' | 'fundamental';
  usage_modes?: ('scoring' | 'screening')[];
}

export interface FactorItem {
  factor_id: string;
  params: Record<string, number | boolean | string>;
}

export interface SignalGroup {
  logic: 'AND' | 'OR';
  factors: FactorItem[];
}

// Tier 2 — 选股条件 & 评分修正

/** 条件类型：pre_filter = 预筛选，score_modifier = 评分修正 */
export type ConditionType = 'pre_filter' | 'score_modifier';

export interface ConditionMeta {
  id: string;
  name: string;
  category: string;
  type: ConditionType;
  description: string;
  params: FactorParam[];
  usage_modes?: ('scoring' | 'screening')[];
}

export interface ConditionItem {
  condition_id: string;
  params: Record<string, number | boolean | string>;
}

export interface SelectionGroup {
  logic: 'AND' | 'OR';
  conditions: ConditionItem[];
}

export interface FactorConfig {
  selection_conditions: SelectionGroup;
  scoring_modifiers: ConditionItem[];
  buy_signals: SignalGroup;
  sell_signals: SignalGroup;
  risk_factors: FactorItem[];
}

export interface FactorCategory {
  name: string;
  factors: FactorMeta[];
}
