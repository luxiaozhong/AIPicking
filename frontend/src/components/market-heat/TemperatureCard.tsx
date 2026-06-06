import React from 'react';
import { Spin, theme } from 'antd';
import type { OverviewData } from '@/services/marketHeatService';

interface Props {
  overview: OverviewData | null;
  loading: boolean;
  onNorthboundClick?: () => void;
  onAdvanceDeclineClick?: () => void;
  onLeadingSectorClick?: (sectorName: string) => void;
  onLaggingSectorClick?: (sectorName: string) => void;
}

const TEMP_COLORS: Record<string, [string, string]> = {
  '冰点': ['#1890ff', '#096dd9'],
  '偏冷': ['#52c41a', '#389e0d'],
  '中性': ['#faad14', '#d48806'],
  '偏热': ['#ff7a45', '#fa541c'],
  '过热': ['#ff4d4f', '#cf1322'],
};

/** 组合卡片内单个板块子项的样式 */
const sectorSubItemStyle: React.CSSProperties = {
  flex: 1,
  cursor: 'pointer',
  borderRadius: 6,
  padding: '8px 12px',
  background: 'rgba(255,255,255,0.15)',
  transition: 'background 0.15s',
  minWidth: 0,
};

const TemperatureCard: React.FC<Props> = ({
  overview, loading, onNorthboundClick, onAdvanceDeclineClick, onLeadingSectorClick, onLaggingSectorClick,
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

  const leadingSectors = overview.leading_sectors || [];
  const laggingSectors = overview.lagging_sectors || [];

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
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
      {/* 前三张简单卡片 */}
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

      {/* 领涨板块 — 组合卡片：两个子项并排 */}
      {leadingSectors.length > 0 && (
        <div
          style={{
            background: 'linear-gradient(135deg, #722ed1, #531dab)',
            borderRadius: token.borderRadius,
            padding: '16px 20px',
            color: '#fff',
          }}
        >
          <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 10 }}>🏆 领涨板块</div>
          <div style={{ display: 'flex', gap: 8 }}>
            {leadingSectors.map((s) => (
              <div
                key={s.sector_name}
                onClick={() => onLeadingSectorClick?.(s.sector_name)}
                style={sectorSubItemStyle}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255,255,255,0.28)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(255,255,255,0.15)';
                }}
              >
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.sector_name}
                </div>
                <div style={{ fontSize: 12, opacity: 0.9 }}>
                  {s.change_pct > 0 ? '+' : ''}{s.change_pct.toFixed(1)}%
                </div>
                <div style={{ fontSize: 10, opacity: 0.7 }}>
                  {s.main_net_yi > 0 ? '+' : ''}{s.main_net_yi.toFixed(1)}亿
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 领跌板块 — 组合卡片：两个子项并排 */}
      {laggingSectors.length > 0 && (
        <div
          style={{
            background: 'linear-gradient(135deg, #389e0d, #237804)',
            borderRadius: token.borderRadius,
            padding: '16px 20px',
            color: '#fff',
          }}
        >
          <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 10 }}>📉 领跌板块</div>
          <div style={{ display: 'flex', gap: 8 }}>
            {laggingSectors.map((s) => (
              <div
                key={s.sector_name}
                onClick={() => onLaggingSectorClick?.(s.sector_name)}
                style={sectorSubItemStyle}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255,255,255,0.28)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(255,255,255,0.15)';
                }}
              >
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.sector_name}
                </div>
                <div style={{ fontSize: 12, opacity: 0.9 }}>
                  {s.change_pct > 0 ? '+' : ''}{s.change_pct.toFixed(1)}%
                </div>
                <div style={{ fontSize: 10, opacity: 0.7 }}>
                  {s.main_net_yi > 0 ? '+' : ''}{s.main_net_yi.toFixed(1)}亿
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default TemperatureCard;
