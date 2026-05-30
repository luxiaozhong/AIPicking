import React from 'react';
import { Select, AutoComplete, Button } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { MACDCase } from '@/services/educationService';

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

  const handleSearch = () => {
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
        style={{ width: 160 }}
        value={searchValue}
        onChange={setSearchValue}
        placeholder="输入股票代码..."
      />
      <Button
        type="primary"
        icon={<SearchOutlined />}
        onClick={handleSearch}
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
