import { describe, it, expect } from 'vitest';
import { calcEMA, calcMACD, detectCrosses } from '../indicators';

describe('calcEMA', () => {
  it('calculates EMA for simple sequence', () => {
    const data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    const result = calcEMA(data, 5);
    // First 4 values (period-1) should be null
    expect(result[0]).toBeNull();
    expect(result[3]).toBeNull();
    expect(result[4]).not.toBeNull();
    expect(result[9]).not.toBeNull();
  });

  it('returns all null for empty input', () => {
    expect(calcEMA([], 5)).toEqual([]);
  });

  it('returns nulls for data shorter than period', () => {
    const result = calcEMA([1, 2, 3], 5);
    expect(result.length).toBe(3);
    expect(result.every((v) => v === null)).toBe(true);
  });
});

describe('calcMACD', () => {
  it('returns dif, dea, bar arrays of same length', () => {
    const closes = Array.from({ length: 100 }, (_, i) => 10 + Math.sin(i * 0.1) * 2);
    const { dif, dea, bar } = calcMACD(closes, 12, 26, 9);
    expect(dif.length).toBe(100);
    expect(dea.length).toBe(100);
    expect(bar.length).toBe(100);
  });

  it('has valid values after warm-up period', () => {
    const closes = Array.from({ length: 60 }, (_, i) => 10 + i * 0.1);
    const { dif, dea, bar } = calcMACD(closes, 12, 26, 9);
    // After slow(26) + signal(9) - 1 = 34, values should be valid
    const validStart = 34;
    expect(dif[validStart]).not.toBeNull();
    expect(dea[validStart]).not.toBeNull();
    expect(bar[validStart]).not.toBeNull();
  });

  it('bar equals 2 * (dif - dea)', () => {
    const closes = Array.from({ length: 100 }, (_, i) => 10 + Math.sin(i * 0.1) * 2);
    const { dif, dea, bar } = calcMACD(closes, 12, 26, 9);
    for (let i = 40; i < 100; i++) {
      if (dif[i] !== null && dea[i] !== null && bar[i] !== null) {
        expect(Math.abs(bar[i]! - 2 * (dif[i]! - dea[i]!))).toBeLessThan(0.001);
      }
    }
  });
});

describe('detectCrosses', () => {
  it('detects golden cross', () => {
    const dates = ['2020-01-01', '2020-01-02', '2020-01-03'];
    const dif = [null, -0.5, 0.5];
    const dea = [null, -0.2, -0.1];
    const crosses = detectCrosses(dates, dif, dea);
    expect(crosses.length).toBe(1);
    expect(crosses[0].type).toBe('golden');
    expect(crosses[0].date).toBe('2020-01-03');
  });

  it('detects death cross', () => {
    const dates = ['2020-01-01', '2020-01-02', '2020-01-03'];
    const dif = [null, 0.5, -0.5];
    const dea = [null, 0.2, 0.1];
    const crosses = detectCrosses(dates, dif, dea);
    expect(crosses.length).toBe(1);
    expect(crosses[0].type).toBe('death');
  });

  it('returns empty when no crosses', () => {
    const dates = ['2020-01-01', '2020-01-02', '2020-01-03'];
    const dif = [null, 1, 2];
    const dea = [null, 0.5, 1];
    const crosses = detectCrosses(dates, dif, dea);
    expect(crosses.length).toBe(0);
  });

  it('handles null values in arrays', () => {
    const dates = ['2020-01-01', '2020-01-02', '2020-01-03', '2020-01-04'];
    const dif = [null, null, -0.5, 0.5];
    const dea = [null, null, -0.1, -0.2];
    const crosses = detectCrosses(dates, dif, dea);
    // Both index 2 and 3 have valid values, dif[2] < dea[2], dif[3] > dea[3] -> golden
    expect(crosses.length).toBe(1);
    expect(crosses[0].type).toBe('golden');
  });
});
