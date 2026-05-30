import { useState, useCallback, useRef, useEffect } from 'react';
import { AutoComplete, Spin, Typography } from 'antd';
import stockService from '@/services/stockService';
import type { StockItem } from '@/types/stock';

const { Text } = Typography;

interface StockSearchLookupProps {
  value: string;
  onChange: (code: string) => void;
  placeholder?: string;
  style?: React.CSSProperties;
}

export default function StockSearchLookup({
  value,
  onChange,
  placeholder = '输入股票代码或名称搜索',
  style,
}: StockSearchLookupProps) {
  const [options, setOptions] = useState<{ value: string; label: React.ReactNode }[]>([]);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handleSearch = useCallback((keyword: string) => {
    if (!keyword) {
      setOptions([]);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const items: StockItem[] = await stockService.search(keyword);
        setOptions(
          items.map((s) => ({
            value: s.ts_code,
            label: (
              <span>
                {s.ts_code} <Text type="secondary">{s.name}</Text>
              </span>
            ),
          }))
        );
      } catch (err) {
        console.error('Stock search failed:', err);
        setOptions([]);
      } finally {
        setSearching(false);
      }
    }, 300);
  }, []);

  return (
    <AutoComplete
      value={value}
      options={options}
      onSearch={handleSearch}
      onSelect={(val: string) => onChange(val)}
      onChange={(val: string) => onChange(val)}
      placeholder={placeholder}
      allowClear
      style={style}
      notFoundContent={searching ? <Spin size="small" /> : null}
    />
  );
}
