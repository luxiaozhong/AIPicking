import { Input, Collapse, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { FactorMeta } from '@/types/factor';

const { Panel } = Collapse;

const CATEGORY_ICONS: Record<string, string> = {
  '趋势类': 'trend',
  '动量类': 'momentum',
  '量能类': 'volume',
  '形态类': 'pattern',
  '风控类': 'risk',
};

interface FactorLibraryProps {
  allFactors: FactorMeta[];
  categories: string[];
  searchText: string;
  onSearchChange: (value: string) => void;
  onAddFactor: (factor: FactorMeta, target: 'buy' | 'sell' | 'risk') => void;
}

export default function FactorLibrary({
  allFactors,
  categories,
  searchText,
  onSearchChange,
  onAddFactor,
}: FactorLibraryProps) {
  const filteredFactors = searchText
    ? allFactors.filter(
        (f) => f.name.includes(searchText) || f.description.includes(searchText),
      )
    : allFactors;

  return (
    <div style={{ padding: 16, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Input
        placeholder="搜索因子..."
        value={searchText}
        onChange={(e) => onSearchChange(e.target.value)}
        allowClear
        style={{ marginBottom: 12 }}
      />
      <div style={{ flex: 1, overflow: 'auto' }}>
        {categories.map((cat) => {
          const catFactors = filteredFactors.filter((f) => f.category === cat);
          if (catFactors.length === 0) return null;
          return (
            <Collapse key={cat} ghost size="small" style={{ marginBottom: 4 }}>
              <Panel
                header={
                  <span>
                    {cat} <Tag style={{ marginLeft: 8 }}>{catFactors.length}</Tag>
                  </span>
                }
                key={cat}
              >
                {catFactors.map((f) => (
                  <div
                    key={f.id}
                    style={{
                      padding: '8px 8px',
                      cursor: 'pointer',
                      borderBottom: '1px solid #f5f5f5',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                    onClick={() => {
                      if (f.signal_type === 'sell') onAddFactor(f, 'sell');
                      else onAddFactor(f, 'buy');
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 13 }}>{f.name}</div>
                      <div style={{ fontSize: 11, color: '#999' }}>
                        {f.description.slice(0, 36)}...
                      </div>
                    </div>
                    <PlusOutlined style={{ color: '#1677ff' }} />
                  </div>
                ))}
              </Panel>
            </Collapse>
          );
        })}
      </div>
    </div>
  );
}
