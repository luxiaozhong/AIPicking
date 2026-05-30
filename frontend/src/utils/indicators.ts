/** 技术指标计算工具 */

export interface CrossPoint {
  index: number;
  date: string;
  type: 'golden' | 'death'; // 金叉 / 死叉
}

export interface DivergencePoint {
  index: number;
  date: string;
  type: 'top' | 'bottom'; // 顶背离 / 底背离
}

/** MA 均线配置 */
export const MA_LINES = [
  { period: 5, name: 'MA5', color: '#757575' },
  { period: 10, name: 'MA10', color: '#f5a623' },
  { period: 20, name: 'MA20', color: '#e040fb' },
  { period: 60, name: 'MA60', color: '#1e88e5' },
] as const;

/** 计算 SMA（简单移动平均） */
export function calcMA(data: number[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    sum += data[i];
    if (i >= period) {
      sum -= data[i - period];
    }
    result.push(i >= period - 1 ? sum / period : null);
  }
  return result;
}

/** 计算 EMA 序列 */
export function calcEMA(data: number[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  if (data.length === 0) return result;
  const k = 2 / (period + 1);
  // 首个有效值为 SMA
  let sum = 0;
  for (let i = 0; i < period && i < data.length; i++) sum += data[i];
  let ema = sum / Math.min(period, data.length);
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null);
    } else if (i === period - 1) {
      result.push(ema);
    } else {
      ema = data[i] * k + ema * (1 - k);
      result.push(ema);
    }
  }
  return result;
}

/** 计算 MACD */
export function calcMACD(
  closes: number[],
  fast: number,
  slow: number,
  signal: number
): { dif: (number | null)[]; dea: (number | null)[]; bar: (number | null)[] } {
  const emaFast = calcEMA(closes, fast);
  const emaSlow = calcEMA(closes, slow);
  const dif: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (emaFast[i] === null || emaSlow[i] === null) {
      dif.push(null);
    } else {
      dif.push(emaFast[i]! - emaSlow[i]!);
    }
  }
  // DIF 的有效数据起始索引 = Math.max(fast, slow) - 1
  const difStart = Math.max(fast, slow) - 1;
  const difValid: number[] = [];
  for (let i = difStart; i < dif.length; i++) {
    if (dif[i] !== null) difValid.push(dif[i]!);
  }
  const deaRaw = calcEMA(difValid, signal);
  const dea: (number | null)[] = new Array(difStart).fill(null);
  for (let i = 0; i < deaRaw.length; i++) {
    dea.push(deaRaw[i]);
  }
  // 补齐尾部
  while (dea.length < closes.length) dea.push(null);
  const bar: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (dif[i] !== null && dea[i] !== null) {
      bar.push(2 * (dif[i]! - dea[i]!));
    } else {
      bar.push(null);
    }
  }
  return { dif, dea, bar };
}

/** 检测金叉死叉 */
export function detectCrosses(dates: string[], dif: (number | null)[], dea: (number | null)[]): CrossPoint[] {
  const crosses: CrossPoint[] = [];
  for (let i = 1; i < dates.length; i++) {
    if (dif[i] === null || dea[i] === null || dif[i - 1] === null || dea[i - 1] === null) continue;
    if (dif[i - 1]! <= dea[i - 1]! && dif[i]! > dea[i]!) {
      crosses.push({ index: i, date: dates[i], type: 'golden' });
    } else if (dif[i - 1]! >= dea[i - 1]! && dif[i]! < dea[i]!) {
      crosses.push({ index: i, date: dates[i], type: 'death' });
    }
  }
  return crosses;
}

/** 检测背离（简单版：比较相邻极值点） */
export function detectDivergences(
  dates: string[],
  closes: number[],
  dif: (number | null)[],
  lookback: number = 60
): DivergencePoint[] {
  const divergences: DivergencePoint[] = [];
  for (let i = lookback; i < dates.length; i++) {
    const windowCloses = closes.slice(i - lookback, i + 1);
    const windowDif = dif.slice(i - lookback, i + 1);
    const validDif = windowDif.filter((d): d is number => d !== null);
    if (validDif.length < lookback / 2) continue;
    const priceMax = Math.max(...windowCloses);
    const priceMin = Math.min(...windowCloses);
    const difMax = Math.max(...validDif);
    const difMin = Math.min(...validDif);
    const priceMaxIdx = windowCloses.lastIndexOf(priceMax);
    const priceMinIdx = windowCloses.lastIndexOf(priceMin);
    const difMaxIdx = validDif.lastIndexOf(difMax);
    const difMinIdx = validDif.lastIndexOf(difMin);
    // 顶背离：价格新高但 DIF 未新高
    if (priceMaxIdx > lookback * 0.5 && difMaxIdx < lookback * 0.5) {
      divergences.push({ index: i - lookback + priceMaxIdx, date: dates[i - lookback + priceMaxIdx], type: 'top' });
    }
    // 底背离：价格新低但 DIF 未新低
    if (priceMinIdx > lookback * 0.5 && difMinIdx < lookback * 0.5) {
      divergences.push({ index: i - lookback + priceMinIdx, date: dates[i - lookback + priceMinIdx], type: 'bottom' });
    }
  }
  return divergences;
}

/** 计算 RSI（相对强弱指数） */
export function calcRSI(closes: number[], period: number = 14): (number | null)[] {
  const result: (number | null)[] = [];
  if (closes.length < period + 1) {
    for (let i = 0; i < closes.length; i++) result.push(null);
    return result;
  }
  // 计算涨跌
  const gains: number[] = [];
  const losses: number[] = [];
  for (let i = 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    gains.push(diff > 0 ? diff : 0);
    losses.push(diff < 0 ? -diff : 0);
  }
  // 首个平均值
  let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
  let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;
  // 前 period 个值
  for (let i = 0; i <= period; i++) result.push(null);
  result[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  // 后续使用平滑算法
  for (let i = period; i < gains.length; i++) {
    avgGain = (avgGain * (period - 1) + gains[i]) / period;
    avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
    result.push(avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss));
  }
  return result;
}

/** 计算 KDJ（随机指标） */
export function calcKDJ(
  highs: number[], lows: number[], closes: number[],
  period: number = 9
): { k: (number | null)[]; d: (number | null)[]; j: (number | null)[] } {
  const n = closes.length;
  const k: (number | null)[] = new Array(n).fill(null);
  const d: (number | null)[] = new Array(n).fill(null);
  const j: (number | null)[] = new Array(n).fill(null);
  if (n < period) return { k, d, j };
  let prevK = 50, prevD = 50;
  for (let i = period - 1; i < n; i++) {
    let h = -Infinity, l = Infinity;
    for (let t = i - period + 1; t <= i; t++) {
      if (highs[t] > h) h = highs[t];
      if (lows[t] < l) l = lows[t];
    }
    const rsv = h === l ? 50 : ((closes[i] - l) / (h - l)) * 100;
    const curK = (2 / 3) * prevK + (1 / 3) * rsv;
    const curD = (2 / 3) * prevD + (1 / 3) * curK;
    const curJ = 3 * curK - 2 * curD;
    k[i] = curK;
    d[i] = curD;
    j[i] = curJ;
    prevK = curK;
    prevD = curD;
  }
  return { k, d, j };
}

/** 计算布林带 */
export function calcBollinger(
  closes: number[], period: number = 20, multiplier: number = 2
): { middle: (number | null)[]; upper: (number | null)[]; lower: (number | null)[] } {
  const n = closes.length;
  const middle = calcMA(closes, period);
  const upper: (number | null)[] = new Array(n).fill(null);
  const lower: (number | null)[] = new Array(n).fill(null);
  for (let i = period - 1; i < n; i++) {
    if (middle[i] === null) continue;
    let sumSq = 0;
    for (let j = i - period + 1; j <= i; j++) sumSq += Math.pow(closes[j] - middle[i]!, 2);
    const std = Math.sqrt(sumSq / period);
    upper[i] = middle[i]! + multiplier * std;
    lower[i] = middle[i]! - multiplier * std;
  }
  return { middle, upper, lower };
}
