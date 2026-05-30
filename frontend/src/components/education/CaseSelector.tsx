import React, { useCallback, useRef } from 'react';
import { Select, AutoComplete, Button } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { MACDCase } from '@/services/educationService';
import { stockService } from '@/services/stockService';

interface CaseSelectorProps {
  cases: MACDCase[];
  activeCaseId: string | null;
  mode: 'preset' | 'free';
  onSelectCase: (caseId: string) => void;
  onSearchStock: (tsCode: string) => void;
}

const CaseSelector: React.FC<CaseSelectorProps> = ({
  cases,
  activeCaseId,
  mode,
  onSelectCase,
  onSearchStock,
}) => {
  const [searchValue, setSearchValue] = React.useState('');
  const [options, setOptions] = React.useState<{ value: string; label: React.ReactNode }[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleSearch = useCallback((val: string) => {
    setSearchValue(val);
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!val.trim()) {
      setOptions([]);
      return;
    }
    timerRef.current = setTimeout(async () => {
      try {
        const items = await stockService.search(val.trim());
        setOptions(
          items.map((s) => ({
            value: s.ts_code,
            label: (
              <span>
                <strong>{s.ts_code}</strong>
                <span style={{ color: '#999', marginLeft: 8, fontSize: 12 }}>{s.name}</span>
              </span>
            ),
          }))
        );
      } catch {
        setOptions([]);
      }
    }, 300);
  }, []);

  const handleSelect = (value: string) => {
    setSearchValue(value);
    onSearchStock(value);
  };

  const handleClick = () => {
    const trimmed = searchValue.trim();
    if (trimmed) onSearchStock(trimmed);
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0' }}>
      <span style={{ fontWeight: 'bold', fontSize: 13, whiteSpace: 'nowrap' }}>📋 案例</span>
      <Select
        style={{ minWidth: 240 }}
        value={mode === 'preset' ? activeCaseId : undefined}
        placeholder="选择预置案例..."
        onChange={onSelectCase}
        options={cases.map((c) => ({
          value: c.id,
          label: c.title,
        }))}
        allowClear={false}
      />
      <span style={{ color: '#999', fontSize: 12 }}>或</span>
      <AutoComplete
        style={{ width: 200 }}
        value={searchValue}
        options={options}
        onSearch={handleSearch}
        onSelect={handleSelect}
        placeholder="输入股票代码或名称..."
      />
      <Button
        type="primary"
        icon={<SearchOutlined />}
        onClick={handleClick}
        size="small"
      >
        查看
      </Button>
      {mode === 'free' && (
        <span style={{ fontSize: 11, color: '#fa8c16', marginLeft: 8 }}>
          自选模式 — 无步骤引导，自由探索
        </span>
      )}
    </div>
  );
};

export default CaseSelector;
