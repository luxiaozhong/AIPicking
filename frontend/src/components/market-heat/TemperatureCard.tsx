import React from 'react';
import { Spin, theme } from 'antd';
import type { OverviewData } from '@/services/marketHeatService';

interface Props {
  overview: OverviewData | null;
  loading: boolean;
  onNorthboundClick?: () => void;
  onAdvanceDeclineClick?: () => void;
  onLeadingSectorClick?: (sectorName: string) => void;
}

const TEMP_COLORS: Record<string, [string, string]> = {
  '冰点': ['#1890ff', '#096dd9'],
  '偏冷': ['#52c41a', '#389e0d'],
  '中性': ['#faad14', '#d48806'],
  '偏热': ['#ff7a45', '#fa541c'],
  '过热': ['#ff4d4f', '#cf1322'],
};

const TemperatureCard: React.FC<Props> = ({
  overview, loading, onNorthboundClick, onAdvanceDeclineClick, onLeadingSectorClick,
}) => {
  const { token } = theme.useToken();

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 40 }}><Spin /><div style={{ marginTop: 8 }}>加载中...</div></div>;
  }

  if (!overview?.temperature) {
    return <div style={{ textAlign: 'center', color: '#999', padding: 40 }}>暂无数据</div>;
  }

  const t = overview.temperature;
  const [startColor, endColor] = TEMP_COLORS[t.level] || TEMP_COLORS['中性'];

  const cards = [
    {
      label: '🔥 市场温度',
      value: `${t.score}°`,
      sub: t.level,
      gradient: `linear-gradient(135deg, ${startColor}, ${endColor})`,
      onClick: undefined,
    },
    {
      label: '💰 北向(深股通)',
      value: overview.northbound
        ? `${overview.northbound.total_net_yi > 0 ? '+' : ''}${overview.northbound.total_net_yi.toFixed(1)}亿`
        : '--',
      sub: overview.northbound?.total_net_yi
        ? (overview.northbound.total_net_yi > 0 ? '净流入' : '净流出')
        : '无数据',
      gradient: 'linear-gradient(135deg, #1677ff, #0958d9)',
      onClick: onNorthboundClick,
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
      onClick: onAdvanceDeclineClick,
    },
    // 领涨板块 Top 3 — 三个独立卡片
    ...(overview.leading_sectors || []).map((s, i) => ({
      label: `🏆 领涨${['一','二','三'][i]}`,
      value: s.sector_name,
      sub: `${s.change_pct > 0 ? '+' : ''}${s.change_pct.toFixed(1)}% · 净流入 ${s.main_net_yi.toFixed(1)}亿`,
      gradient: ['linear-gradient(135deg, #722ed1, #531dab)', 'linear-gradient(135deg, #9254de, #722ed1)', 'linear-gradient(135deg, #b37feb, #9254de)'][i],
      onClick: () => onLeadingSectorClick?.(s.sector_name),
    })),
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
      {cards.map((card) => (
        <div
          key={card.label}
          onClick={card.onClick}
          style={{
            background: card.gradient,
            borderRadius: token.borderRadius,
            padding: '16px 20px',
            color: '#fff',
            cursor: card.onClick ? 'pointer' : 'default',
            transition: 'transform 0.15s',
          }}
          onMouseEnter={(e) => { if (card.onClick) e.currentTarget.style.transform = 'scale(1.02)'; }}
          onMouseLeave={(e) => { if (card.onClick) e.currentTarget.style.transform = 'scale(1)'; }}
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
