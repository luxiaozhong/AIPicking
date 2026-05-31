import { Input, Collapse, Tag, Divider } from 'antd';
import { PlusOutlined, FilterOutlined, RiseOutlined } from '@ant-design/icons';
import type { FactorMeta, ConditionMeta } from '@/types/factor';

const CATEGORY_COLORS: Record<string, string> = {
  '龙虎榜': 'volcano',
  '板块资金流': 'cyan',
  '热门题材': 'orange',
  '热门股': 'magenta',
};

interface FactorLibraryProps {
  allFactors: FactorMeta[];
  categories: string[];
  allConditions: ConditionMeta[];
  conditionCategories: string[];
  searchText: string;
  onSearchChange: (value: string) => void;
  onAddFactor: (factor: FactorMeta, target: 'buy' | 'sell' | 'risk') => void;
  onAddCondition: (condition: ConditionMeta, target: 'selection' | 'scoring') => void;
}

export default function FactorLibrary({
  allFactors,
  categories,
  allConditions,
  conditionCategories,
  searchText,
  onSearchChange,
  onAddFactor,
  onAddCondition,
}: FactorLibraryProps) {
  const filteredFactors = searchText
    ? allFactors.filter(
        (f) => f.name.includes(searchText) || f.description.includes(searchText),
      )
    : allFactors;

  const filteredConditions = searchText
    ? allConditions.filter(
        (c) => c.name.includes(searchText) || c.description.includes(searchText),
      )
    : allConditions;

  const hasConditions = conditionCategories.length > 0;

  return (
    <div style={{ padding: 16, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Input
        placeholder="搜索因子或条件..."
        value={searchText}
        onChange={(e) => onSearchChange(e.target.value)}
        allowClear
        style={{ marginBottom: 12 }}
      />
      <div style={{ flex: 1, overflow: 'auto' }}>
        {/* Tier 2 选股条件 */}
        {hasConditions && filteredConditions.length > 0 && (
          <>
            <Divider plain style={{ fontSize: 12, margin: '8px 0' }}>
              <FilterOutlined /> 选股条件 & 评分
            </Divider>
            {conditionCategories.map((cat) => {
              const catConditions = filteredConditions.filter((c) => c.category === cat);
              if (catConditions.length === 0) return null;
              return (
                <Collapse key={`cond-${cat}`} ghost size="small" style={{ marginBottom: 4 }}>
                  <Collapse.Panel
                    header={
                      <span>
                        <Tag color={CATEGORY_COLORS[cat] || 'default'} style={{ marginRight: 4 }}>
                          {cat}
                        </Tag>
                        {catConditions.length}
                      </span>
                    }
                    key={cat}
                  >
                    {catConditions.map((c) => (
                      <div
                        key={c.id}
                        style={{
                          padding: '8px 8px',
                          cursor: 'pointer',
                          borderBottom: '1px solid #f5f5f5',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                        }}
                        onClick={() => {
                          onAddCondition(
                            c,
                            c.type === 'score_modifier' ? 'scoring' : 'selection',
                          );
                        }}
                      >
                        <div>
                          <div style={{ fontSize: 13 }}>
                            {c.name}
                            <Tag
                              color={c.type === 'score_modifier' ? 'orange' : 'blue'}
                              style={{ marginLeft: 6, fontSize: 10, lineHeight: '16px' }}
                            >
                              {c.type === 'score_modifier' ? '加分' : '筛选'}
                            </Tag>
                          </div>
                          <div style={{ fontSize: 11, color: '#999' }}>
                            {c.description.slice(0, 36)}...
                          </div>
                        </div>
                        <PlusOutlined style={{ color: '#1677ff' }} />
                      </div>
                    ))}
                  </Collapse.Panel>
                </Collapse>
              );
            })}

            <Divider plain style={{ fontSize: 12, margin: '8px 0' }}>
              <RiseOutlined /> K线技术因子
            </Divider>
          </>
        )}

        {/* K 线因子 */}
        {categories.map((cat) => {
          const catFactors = filteredFactors.filter((f) => f.category === cat);
          if (catFactors.length === 0) return null;
          return (
            <Collapse key={cat} ghost size="small" style={{ marginBottom: 4 }}>
              <Collapse.Panel
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
              </Collapse.Panel>
            </Collapse>
          );
        })}
      </div>
    </div>
  );
}
