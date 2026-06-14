/**
 * MACD / RSI 明日预判工具
 * 通过二分搜索计算：明日收盘价到达什么位置会触发金叉/死叉/背离/超买/超卖信号
 */

import { calcEMA, calcMACD, extendEMA } from './indicators';

// ── 类型定义 ──────────────────────────────────────────────

export type PredictionStatus = 'already' | 'imminent' | 'moderate' | 'far';

export interface CrossPrediction {
  type: 'golden_cross' | 'death_cross';
  /** 当前 DIF 与 DEA 的关系 */
  currentState: 'dif_above_dea' | 'dif_below_dea';
  currentDif: number;
  currentDea: number;
  /** 触发交叉所需的收盘价，null=已处于交叉状态 */
  thresholdPrice: number | null;
  /** 所需涨跌幅（小数） */
  thresholdChangePct: number | null;
  status: PredictionStatus;
  description: string;
}

export interface DivergencePrediction {
  type: 'top_divergence' | 'bottom_divergence';
  currentPrice: number;
  lookbackLow: number;
  lookbackLowDIF: number | null;
  thresholdPrice: number | null;
  thresholdChangePct: number | null;
  status: PredictionStatus;
  description: string;
}

export interface RSIPrediction {
  type: 'overbought' | 'oversold';
  currentRSI: number;
  threshold: number;
  thresholdPrice: number | null;
  thresholdChangePct: number | null;
  status: PredictionStatus;
  description: string;
}

export interface IndexPredictions {
  cross: CrossPrediction;
  divergence: { top: DivergencePrediction; bottom: DivergencePrediction };
  rsi: { overbought: RSIPrediction; oversold: RSIPrediction };
}

// ── 工具函数 ──────────────────────────────────────────────

function statusFromPct(absPct: number, already: boolean): PredictionStatus {
  if (already) return 'already';
  if (absPct <= 0.02) return 'imminent';
  if (absPct <= 0.05) return 'moderate';
  return 'far';
}

const BISECTION_STEPS = 80;
const SEARCH_RANGE = 0.12; // ±12%

// ── 核心函数 ──────────────────────────────────────────────

/** 基于现有 closes，计算追加一个 newClose 后的 MACD 瞬时值 */
export function extendMACDWithPrice(
  closes: number[],
  fast: number,
  slow: number,
  signal: number,
  newClose: number
): { dif: number; dea: number; bar: number } {
  // 取得最后有效的 EMA 值
  const emaFast = calcEMA(closes, fast);
  const emaSlow = calcEMA(closes, slow);
  const lastEmaFast = emaFast.filter((x): x is number => x !== null).pop()!;
  const lastEmaSlow = emaSlow.filter((x): x is number => x !== null).pop()!;

  // 递推 EMA
  const newEmaFast = extendEMA(lastEmaFast, newClose, fast);
  const newEmaSlow = extendEMA(lastEmaSlow, newClose, slow);
  const newDif = newEmaFast - newEmaSlow;

  // 递推 DEA
  const { dif, dea } = calcMACD(closes, fast, slow, signal);
  const lastDea = dea.filter((x): x is number => x !== null).pop()!;
  const newDea = extendEMA(lastDea, newDif, signal);
  const newBar = 2 * (newDif - newDea);

  return { dif: newDif, dea: newDea, bar: newBar };
}

/** 基于现有 closes，计算追加一个 newClose 后的 RSI 值 */
export function extendRSIWithPrice(
  closes: number[],
  period: number,
  newClose: number
): number {
  if (closes.length < period + 1) return 50;

  // 重新走一遍 RSI 计算（O(n)，n≈120，够快）
  const extended = [...closes, newClose];
  const gains: number[] = [];
  const losses: number[] = [];
  for (let i = 1; i < extended.length; i++) {
    const diff = extended[i] - extended[i - 1];
    gains.push(diff > 0 ? diff : 0);
    losses.push(diff < 0 ? -diff : 0);
  }

  let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
  let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;

  for (let i = period; i < gains.length; i++) {
    avgGain = (avgGain * (period - 1) + gains[i]) / period;
    avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
  }

  return avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
}

// ── 金叉/死叉预判 ────────────────────────────────────────

export function predictCross(
  closes: number[],
  macdParams: { fast: number; slow: number; signal: number }
): CrossPrediction {
  const { fast, slow, signal } = macdParams;
  const { dif, dea } = calcMACD(closes, fast, slow, signal);
  const lastDif = dif.filter((x): x is number => x !== null).pop()!;
  const lastDea = dea.filter((x): x is number => x !== null).pop()!;
  const lastClose = closes[closes.length - 1];
  const difAboveDea = lastDif > lastDea;

  const type = difAboveDea ? 'death_cross' : 'golden_cross';
  const currentState = difAboveDea ? 'dif_above_dea' : 'dif_below_dea';

  // 二分搜索找交叉阈值
  let lo = lastClose * (1 - SEARCH_RANGE);
  let hi = lastClose * (1 + SEARCH_RANGE);
  let threshold: number | null = null;

  for (let step = 0; step < BISECTION_STEPS; step++) {
    const mid = (lo + hi) / 2;
    const ext = extendMACDWithPrice(closes, fast, slow, signal, mid);

    let crossed: boolean;
    if (type === 'golden_cross') {
      crossed = ext.dif > ext.dea;
    } else {
      crossed = ext.dif < ext.dea;
    }

    if (crossed) {
      hi = mid;
      threshold = mid;
    } else {
      lo = mid;
    }
  }

  // 检查是否已处于交叉状态（例如当前已金叉中，问何时死叉）
  // 如果 lo ≈ hi 仍是 crossed，说明当前已满足
  const extLo = extendMACDWithPrice(closes, fast, slow, signal, lastClose);
  const alreadyCrossed =
    type === 'golden_cross' ? extLo.dif > extLo.dea : extLo.dif < extLo.dea;

  if (alreadyCrossed && threshold === null) {
    // 当前已是交叉状态，即使二分到底也回不去
    threshold = lastClose; // 近似：今日价就触发
  }

  if (threshold === null) {
    // 二分搜索未找到（波动范围不足）
    return {
      type,
      currentState,
      currentDif: lastDif,
      currentDea: lastDea,
      thresholdPrice: null,
      thresholdChangePct: null,
      status: 'far',
      description: `当前DIF(${lastDif.toFixed(2)})与DEA(${lastDea.toFixed(2)})差距较大，±12%范围内未找到交叉点`,
    };
  }

  const changePct = (threshold - lastClose) / lastClose;
  const already = (type === 'golden_cross' && difAboveDea) || (type === 'death_cross' && !difAboveDea);

  let desc: string;
  const label = type === 'golden_cross' ? '金叉' : '死叉';
  const dir = changePct >= 0 ? '上涨' : '下跌';
  if (already) {
    desc = `当前已处于${label}状态 (DIF${difAboveDea ? '>' : '<'}DEA)`;
  } else {
    desc = `明日收盘${dir}${Math.abs(changePct * 100).toFixed(1)}%至${threshold.toFixed(0)}点，触发${label}`;
  }

  return {
    type,
    currentState,
    currentDif: lastDif,
    currentDea: lastDea,
    thresholdPrice: threshold,
    thresholdChangePct: changePct,
    status: statusFromPct(Math.abs(changePct), already),
    description: desc,
  };
}

// ── 背离预判 ──────────────────────────────────────────────

export function predictDivergence(
  closes: number[],
  dif: (number | null)[],
  lookback: number = 60
): { top: DivergencePrediction; bottom: DivergencePrediction } {
  const lastClose = closes[closes.length - 1];
  const validDif = dif.filter((d): d is number => d !== null);

  // 在 lookback 窗口内找最低价和对应的 DIF
  const windowStart = Math.max(0, closes.length - lookback);
  let priceLow = Infinity;
  let priceHigh = -Infinity;
  let lowPriceDIF: number | null = null;
  let highPriceDIF: number | null = null;

  for (let i = windowStart; i < closes.length; i++) {
    if (closes[i] < priceLow) {
      priceLow = closes[i];
      lowPriceDIF = dif[i];
    }
    if (closes[i] > priceHigh) {
      priceHigh = closes[i];
      highPriceDIF = dif[i];
    }
  }

  // 底背离：价格需跌破 priceLow，且新 DIF > lowPriceDIF
  const bottom: DivergencePrediction = (() => {
    if (lowPriceDIF === null || lastClose <= priceLow) {
      return {
        type: 'bottom_divergence',
        currentPrice: lastClose,
        lookbackLow: priceLow,
        lookbackLowDIF: lowPriceDIF,
        thresholdPrice: null,
        thresholdChangePct: null,
        status: lastClose <= priceLow ? 'already' : 'not_detectable' as any,
        description: lastClose <= priceLow
          ? `当前价格(${lastClose.toFixed(0)})已创新低，需人工判断背离`
          : '无底背离条件',
      };
    }

    // 检查即使跌到搜索下限，DIF 是否仍高于历史低点 DIF
    const loPrice = lastClose * (1 - SEARCH_RANGE);
    const { dif: loDIF } = extendMACDWithPrice(closes, 12, 26, 9, loPrice);
    if (loDIF > lowPriceDIF! && loPrice < priceLow) {
      // 能找到：二分搜索精确阈值
      let lo = priceLow;
      let hi = lastClose;
      let threshold: number | null = null;
      for (let step = 0; step < BISECTION_STEPS; step++) {
        const mid = (lo + hi) / 2;
        const { dif: newDif } = extendMACDWithPrice(closes, 12, 26, 9, mid);
        if (newDif > lowPriceDIF!) {
          hi = mid;
          threshold = mid;
        } else {
          lo = mid;
        }
      }
      const changePct = threshold ? (threshold - lastClose) / lastClose : 0;
      return {
        type: 'bottom_divergence',
        currentPrice: lastClose,
        lookbackLow: priceLow,
        lookbackLowDIF: lowPriceDIF,
        thresholdPrice: threshold,
        thresholdChangePct: changePct,
        status: statusFromPct(Math.abs(changePct), false),
        description: threshold
          ? `明日收盘跌至${threshold.toFixed(0)}以下（${(changePct * 100).toFixed(1)}%），价格创新低但DIF(${loDIF.toFixed(2)})不破前低DIF(${lowPriceDIF!.toFixed(2)})，形成底背离`
          : '无法触发底背离',
      };
    }

    return {
      type: 'bottom_divergence',
      currentPrice: lastClose,
      lookbackLow: priceLow,
      lookbackLowDIF: lowPriceDIF,
      thresholdPrice: null,
      thresholdChangePct: null,
      status: 'far',
      description: `价格跌破${priceLow.toFixed(0)}后DIF(${loDIF.toFixed(2)})将同步新低，不构成底背离`,
    };
  })();

  // 顶背离：价格需突破 priceHigh，且新 DIF < highPriceDIF
  const top: DivergencePrediction = (() => {
    if (highPriceDIF === null || lastClose >= priceHigh) {
      return {
        type: 'top_divergence',
        currentPrice: lastClose,
        lookbackLow: priceHigh,
        lookbackLowDIF: highPriceDIF,
        thresholdPrice: null,
        thresholdChangePct: null,
        status: lastClose >= priceHigh ? 'already' : 'not_detectable' as any,
        description: lastClose >= priceHigh
          ? `当前价格(${lastClose.toFixed(0)})已创新高，需人工判断背离`
          : '无顶背离条件',
      };
    }

    const hiPrice = lastClose * (1 + SEARCH_RANGE);
    const { dif: hiDIF } = extendMACDWithPrice(closes, 12, 26, 9, hiPrice);
    if (hiDIF < highPriceDIF! && hiPrice > priceHigh) {
      let lo = lastClose;
      let hi = hiPrice;
      let threshold: number | null = null;
      for (let step = 0; step < BISECTION_STEPS; step++) {
        const mid = (lo + hi) / 2;
        const { dif: newDif } = extendMACDWithPrice(closes, 12, 26, 9, mid);
        if (newDif < highPriceDIF!) {
          lo = mid;
          threshold = mid;
        } else {
          hi = mid;
        }
      }
      const changePct = threshold ? (threshold - lastClose) / lastClose : 0;
      return {
        type: 'top_divergence',
        currentPrice: lastClose,
        lookbackLow: priceHigh,
        lookbackLowDIF: highPriceDIF,
        thresholdPrice: threshold,
        thresholdChangePct: changePct,
        status: statusFromPct(Math.abs(changePct), false),
        description: threshold
          ? `明日收盘涨至${threshold.toFixed(0)}以上（+${(changePct * 100).toFixed(1)}%），价格创新高但DIF(${hiDIF.toFixed(2)})不破前高DIF(${highPriceDIF!.toFixed(2)})，形成顶背离`
          : '无法触发顶背离',
      };
    }

    return {
      type: 'top_divergence',
      currentPrice: lastClose,
      lookbackLow: priceHigh,
      lookbackLowDIF: highPriceDIF,
      thresholdPrice: null,
      thresholdChangePct: null,
      status: 'far',
      description: `价格突破${priceHigh.toFixed(0)}后DIF(${hiDIF.toFixed(2)})将同步新高，不构成顶背离`,
    };
  })();

  return { top, bottom };
}

// ── RSI 超买超卖预判 ─────────────────────────────────────

export function predictRSI(
  closes: number[],
  period: number,
  threshold: number,
  type: 'overbought' | 'oversold'
): RSIPrediction {
  const lastClose = closes[closes.length - 1];
  const currentRSI = extendRSIWithPrice(closes.slice(0, -1), period, lastClose);

  const isOverbought = type === 'overbought';
  const alreadyInZone = isOverbought ? currentRSI >= threshold : currentRSI <= threshold;

  if (alreadyInZone) {
    return {
      type,
      currentRSI,
      threshold,
      thresholdPrice: null,
      thresholdChangePct: null,
      status: 'already',
      description: `当前RSI(${currentRSI.toFixed(1)})已处于${isOverbought ? '超买' : '超卖'}区域(阈值${threshold})`,
    };
  }

  // 二分搜索：找到使 RSI 突破阈值的价格
  let lo: number, hi: number;
  if (isOverbought) {
    // 需要上涨才能超买
    lo = lastClose;
    hi = lastClose * (1 + SEARCH_RANGE);
  } else {
    // 需要下跌才能超卖
    lo = lastClose * (1 - SEARCH_RANGE);
    hi = lastClose;
  }

  let thresholdPrice: number | null = null;

  for (let step = 0; step < BISECTION_STEPS; step++) {
    const mid = (lo + hi) / 2;
    const rsi = extendRSIWithPrice(closes.slice(0, -1), period, mid);

    const crossed = isOverbought ? rsi >= threshold : rsi <= threshold;

    if (crossed) {
      if (isOverbought) {
        hi = mid;
      } else {
        lo = mid;
      }
      thresholdPrice = mid;
    } else {
      if (isOverbought) {
        lo = mid;
      } else {
        hi = mid;
      }
    }
  }

  if (thresholdPrice === null) {
    return {
      type,
      currentRSI,
      threshold,
      thresholdPrice: null,
      thresholdChangePct: null,
      status: 'far',
      description: `当前RSI(${currentRSI.toFixed(1)})距${isOverbought ? '超买' : '超卖'}线(${threshold})较远，±12%范围内无法触发`,
    };
  }

  const changePct = (thresholdPrice - lastClose) / lastClose;
  const dir = changePct >= 0 ? '上涨' : '下跌';

  return {
    type,
    currentRSI,
    threshold,
    thresholdPrice,
    thresholdChangePct: changePct,
    status: statusFromPct(Math.abs(changePct), false),
    description: `明日收盘${dir}${Math.abs(changePct * 100).toFixed(1)}%至${thresholdPrice.toFixed(0)}点，RSI达到${threshold}(${isOverbought ? '超买' : '超卖'})`,
  };
}

// ── 聚合函数 ──────────────────────────────────────────────

export function computeAllPredictions(
  closes: number[],
  macdParams: { fast: number; slow: number; signal: number },
  rsiPeriod: number,
  overbought: number,
  oversold: number,
  lookback: number = 60
): IndexPredictions {
  const { dif } = calcMACD(closes, macdParams.fast, macdParams.slow, macdParams.signal);
  return {
    cross: predictCross(closes, macdParams),
    divergence: predictDivergence(closes, dif, lookback),
    rsi: {
      overbought: predictRSI(closes, rsiPeriod, overbought, 'overbought'),
      oversold: predictRSI(closes, rsiPeriod, oversold, 'oversold'),
    },
  };
}
