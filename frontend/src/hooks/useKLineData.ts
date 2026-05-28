import { useState, useEffect, useRef } from 'react';
import stockService from '@/services/stockService';
import type { KLineItem } from '@/types/stock';

const MAX_CACHE_SIZE = 50;
const cache = new Map<string, { name: string; items: KLineItem[] }>();
const cacheKeys: string[] = [];

interface KLineDataState {
  name: string;
  items: KLineItem[];
}

export function useKLineData(tsCode: string | null, days: number = 365) {
  const [data, setData] = useState<KLineDataState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!tsCode) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }

    const key = `${tsCode}:${days}`;
    const cached = cache.get(key);
    if (cached) {
      setData(cached);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    stockService
      .getKLine(tsCode, days)
      .then((result) => {
        if (cancelled) return;
        const value = { name: result.name, items: result.items };
        cacheKeys.push(key);
        if (cacheKeys.length > MAX_CACHE_SIZE) {
          const oldest = cacheKeys.shift()!;
          cache.delete(oldest);
        }
        cache.set(key, value);
        setData(value);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.response?.data?.message || '获取 K 线数据失败');
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [tsCode, days]);

  return { data, loading, error };
}
