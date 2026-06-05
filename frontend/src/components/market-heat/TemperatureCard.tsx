import React from 'react';
import { Card, Spin, theme } from 'antd';
import type { OverviewData } from '@/services/marketHeatService';

interface Props {
  overview: OverviewData | null;
  loading: boolean;
}

const TEMP_COLORS: Record<string, [string, string]> = {
  '冰点': ['#1890ff', '#096dd9'],
  '偏冷': ['#52c41a', '#389e0d'],
  '中性': ['#faad14', '#d48806'],
  '偏热': ['#ff7a45', '#fa541c'],
  '过热': ['#ff4d4f', '#cf1322'],
};

const TemperatureCard: React.FC<Props> = ({ overview, loading }) => {
  const { token } = theme.useToken();

  if (loading) {
    return (
      <Card><Spin /><div style={{ textAlign: 'center', marginTop: 8 }}>加载中...</div></Card>
    );
  }

  if (!overview?.temperature) {
    return <Card><div style={{ textAlign: 'center', color: '#999' }}>暂无数据</div></Card>;
  }

  const t = overview.temperature;
  const [startColor, endColor] = TEMP_COLORS[t.level] || TEMP_COLORS['中性'];

  const cards = [
    {
      label: '🔥 市场温度',
      value: `${t.score}°`,
      sub: t.level,
      gradient: `linear-gradient(135deg, ${startColor}, ${endColor})`,
    },
    {
      label: '💰 北向资金',
      value: overview.northbound
        ? `${overview.northbound.total_net_yi > 0 ? '+' : ''}${overview.northbound.total_net_yi.toFixed(1)}亿`
        : '--',
      sub: overview.northbound?.total_net_yi
        ? (overview.northbound.total_net_yi > 0 ? '净流入' : '净流出')
        : '无数据',
      gradient: 'linear-gradient(135deg, #1677ff, #0958d9)',
    },
    {
      label: '📊 涨跌比',
      value: overview.advance_decline && overview.advance_decline.total > 0
        ? `${(overview.advance_decline.up_count / overview.advance_decline.total * 100).toFixed(0)}%`
        : '--',
      sub: overview.advance_decline
        ? `涨 ${overview.advance_decline.up_count} · 跌 ${overview.advance_decline.down_count}`
        : '--',
      gradient: 'linear-gradient(135deg, #52c41a, #389e0d)',
    },
    {
      label: '🏆 领涨板块',
      value: overview.leading_sector?.sector_name || '--',
      sub: overview.leading_sector
        ? `${overview.leading_sector.change_pct > 0 ? '+' : ''}${overview.leading_sector.change_pct.toFixed(1)}% · 净流入 ${overview.leading_sector.main_net_yi.toFixed(1)}亿`
        : '--',
      gradient: 'linear-gradient(135deg, #722ed1, #531dab)',
    },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
      {cards.map((card) => (
        <div
          key={card.label}
          style={{
            background: card.gradient,
            borderRadius: token.borderRadius,
            padding: '16px 20px',
            color: '#fff',
          }}
        >
          <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 4 }}>{card.label}</div>
          <div style={{ fontSize: 24, fontWeight: 700, marginBottom: 2 }}>{card.value}</div>
          <div style={{ fontSize: 11, opacity: 0.75 }}>{card.sub}</div>
        </div>
      ))}
    </div>
  );
};

export default TemperatureCard;
