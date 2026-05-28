import { Card, Tag, Space, InputNumber, Switch, Typography, Button } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import type { FactorMeta, FactorItem } from '@/types/factor';

const { Text } = Typography;

interface FactorCardProps {
  item: FactorItem;
  meta: FactorMeta;
  target: 'buy' | 'sell' | 'risk';
  onRemove: () => void;
  onParamChange: (paramName: string, value: number | boolean | string) => void;
}

const signalColors: Record<string, string> = {
  buy: 'green',
  sell: 'red',
  both: 'blue',
};

const signalLabels: Record<string, string> = {
  buy: '买入',
  sell: '卖出',
  both: '双向',
};

export default function FactorCard({ item, meta, target, onRemove, onParamChange }: FactorCardProps) {
  return (
    <Card
      size="small"
      style={{ marginBottom: 8 }}
      title={
        <Space>
          <span>{meta.name}</span>
          <Tag color={signalColors[meta.signal_type] || 'blue'}>
            {signalLabels[meta.signal_type] || meta.signal_type}
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
          {p.type === 'int' || p.type === 'float' ? (
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
