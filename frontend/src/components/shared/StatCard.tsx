import { Card } from 'antd';

interface StatCardProps {
  title: string;
  value: string | number;
  color?: string;
  suffix?: string;
}

export default function StatCard({ title, value, color = '#1677ff', suffix }: StatCardProps) {
  return (
    <Card size="small" style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 13, color: '#999', marginBottom: 8 }}>{title}</div>
      <div style={{ fontSize: 24, fontWeight: 600, color }}>
        {value}
        {suffix && (
          <span style={{ fontSize: 14, fontWeight: 400, marginLeft: 4 }}>{suffix}</span>
        )}
      </div>
    </Card>
  );
}
