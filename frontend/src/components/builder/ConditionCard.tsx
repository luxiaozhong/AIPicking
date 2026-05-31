import { Card, Tag, Space, InputNumber, Switch, Select, Typography, Button } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import type { ConditionMeta, ConditionItem } from '@/types/factor';

const { Text } = Typography;

interface ConditionCardProps {
  item: ConditionItem;
  meta: ConditionMeta;
  onRemove: () => void;
  onParamChange: (paramName: string, value: number | boolean | string) => void;
}

const typeColors: Record<string, string> = {
  pre_filter: 'blue',
  score_modifier: 'orange',
};

const typeLabels: Record<string, string> = {
  pre_filter: '筛选',
  score_modifier: '加分',
};

export default function ConditionCard({ item, meta, onRemove, onParamChange }: ConditionCardProps) {
  return (
    <Card
      size="small"
      style={{ marginBottom: 8 }}
      title={
        <Space>
          <span>{meta.name}</span>
          <Tag color={typeColors[meta.type] || 'default'}>
            {typeLabels[meta.type] || meta.type}
          </Tag>
        </Space>
      }
      extra={
        <Button type="text" danger size="small" icon={<DeleteOutlined />} onClick={onRemove} />
      }
    >
      {meta.params.map((p) => (
        <div key={p.name} style={{ marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Text style={{ width: 120, fontSize: 12 }}>{p.label}:</Text>
          {p.type === 'enum' && p.options ? (
            <Select
              size="small"
              style={{ width: 120 }}
              value={item.params[p.name] as string}
              onChange={(v) => onParamChange(p.name, v)}
              options={p.options}
            />
          ) : p.type === 'int' || p.type === 'float' ? (
            <InputNumber
              size="small"
              style={{ width: 100 }}
              value={item.params[p.name] as number}
              min={p.min}
              max={p.max}
              step={p.type === 'int' ? 1 : 0.1}
              onChange={(v) => onParamChange(p.name, v as number)}
            />
          ) : p.type === 'bool' ? (
            <Switch
              size="small"
              checked={item.params[p.name] as boolean}
              onChange={(v) => onParamChange(p.name, v)}
            />
          ) : null}
        </div>
      ))}
    </Card>
  );
}
