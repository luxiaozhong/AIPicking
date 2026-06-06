import React from 'react';
import { Spin, theme, Tooltip } from 'antd';
import type { OverviewData, StressOverview } from '@/services/marketHeatService';

/** 市场温度维度：标签、满分、计算公式 */
const MARKET_DIM_META: Array<{
  key: string;
  label: string;
  max: number;
  formula: string;
}> = [
  { key: 'capital', label: '资金面', max: 20, formula: '北向资金净流入金额分档' },
  { key: 'breadth', label: '涨跌结构', max: 20, formula: '上涨家数占比 × 25' },
  { key: 'sentiment', label: '情绪面', max: 20, formula: '涨停/跌停比 × 活跃度加权' },
  { key: 'concentration', label: '集中度', max: 20, formula: '头部3行业资金流入占比（倒U型）' },
  { key: 'continuity', label: '热度延续', max: 20, formula: '热门主题 Jaccard 相似度 × 20' },
];

/** 板块温度维度：标签、满分、计算公式 */
const BOARD_DIM_META: Array<{
  key: string;
  label: string;
  max: number;
  formula: string;
}> = [
  { key: 'breadth', label: '涨跌结构', max: 40, formula: '上涨家数占比 × 50' },
  { key: 'sentiment', label: '情绪面', max: 30, formula: '涨停/跌停比 × 活跃度加权' },
  { key: 'volume', label: '量能', max: 30, formula: '当日成交额 / 近20日均成交额 × 15' },
];

/** 市场温度 Tooltip：维度分数 + 计算公式 */
function renderMarketDimTooltip(dimensions: Record<string, number> | undefined) {
  if (!dimensions) return null;
  return (
    <div style={{ fontSize: 12, lineHeight: '20px', minWidth: 200 }}>
      {MARKET_DIM_META.map(({ key, label, max, formula }) => (
        <div key={key} style={{ marginBottom: 4 }}>
          <div>
            {label}: <b>{dimensions[key] ?? '--'}</b>/{max}
          </div>
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.55)' }}>{formula}</div>
        </div>
      ))}
    </div>
  );
}

/** 板块温度 Tooltip：维度分数 + 计算公式 */
function renderBoardDimTooltip(dimensions: Record<string, number> | undefined) {
  if (!dimensions) return null;
  return (
    <div style={{ fontSize: 12, lineHeight: '20px', minWidth: 220 }}>
      {BOARD_DIM_META.map(({ key, label, max, formula }) => (
        <div key={key} style={{ marginBottom: 4 }}>
          <div>
            {label}: <b>{dimensions[key] ?? '--'}</b>/{max}
          </div>
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.55)' }}>{formula}</div>
        </div>
      ))}
    </div>
  );
}

/** 压力指数维度：标签、满分、计算公式（越高越恐慌） */
const STRESS_DIM_META: Array<{
  key: string;
  label: string;
  max: number;
  formula: string;
}> = [
  { key: 'decline', label: '指数跌幅', max: 25, formula: '全A等权涨跌幅分档' },
  { key: 'volatility', label: '波动率', max: 25, formula: '20日年化波动率（VIX核心法）' },
  { key: 'limitdown', label: '跌停潮', max: 25, formula: '跌停占比（A股特有恐慌信号）' },
  { key: 'breadth', label: '下跌广度', max: 15, formula: '下跌家数占比分档' },
  { key: 'northbound', label: '北向出逃', max: 10, formula: '北向资金净流出分档' },
];

/** 压力等级颜色（方向与温度相反：越高越红） */
const STRESS_COLORS: Record<string, [string, string]> = {
  '平稳': ['#52c41a', '#389e0d'],
  '关注': ['#a0d911', '#7cb305'],
  '压力': ['#faad14', '#d48806'],
  '恐慌': ['#ff7a45', '#fa541c'],
  '危机': ['#ff4d4f', '#cf1322'],
};

/** 压力指数 Tooltip：维度分数 + 计算公式 */
function renderStressDimTooltip(dimensions: Record<string, number> | undefined) {
  if (!dimensions) return null;
  return (
    <div style={{ fontSize: 12, lineHeight: '20px', minWidth: 220 }}>
      {STRESS_DIM_META.map(({ key, label, max, formula }) => (
        <div key={key} style={{ marginBottom: 4 }}>
          <div>
            {label}: <b>{dimensions[key] ?? '--'}</b>/{max}
          </div>
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.55)' }}>{formula}</div>
        </div>
      ))}
    </div>
  );
}

interface Props {
  overview: OverviewData | null;
  loading: boolean;
  sectorFundTotalYI?: number | null;
  sectorFundLoading?: boolean;
  stressOverview?: StressOverview | null;
  stressLoading?: boolean;
  onTemperatureClick?: () => void;
  onNorthboundClick?: () => void;
  onAdvanceDeclineClick?: () => void;
  onLeadingSectorClick?: (sectorName: string) => void;
  onLaggingSectorClick?: (sectorName: string) => void;
  onBoardTemperatureClick?: (boardCode: string, boardName: string) => void;
  onSectorFundClick?: () => void;
  onStressClick?: () => void;
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
  overview, loading, sectorFundTotalYI, sectorFundLoading,
  stressOverview, stressLoading,
  onTemperatureClick, onNorthboundClick, onAdvanceDeclineClick,
  onLeadingSectorClick, onLaggingSectorClick, onBoardTemperatureClick,
  onSectorFundClick, onStressClick,
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
      onClick: onTemperatureClick,
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* 第一排：市场温度 + 压力指数 + 主板温度 + 双创温度 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {/* 市场温度 */}
        {cards.filter(c => c.label === '🔥 市场温度').map((card) => (
          <Tooltip
            key={card.label}
            title={renderMarketDimTooltip(t.dimensions)}
            placement="bottom"
          >
            <div
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
          </Tooltip>
        ))}
        {/* 压力指数 */}
        {(() => {
          if (stressLoading) {
            return (
              <div style={{
                background: 'linear-gradient(135deg, #8c8c8c, #595959)',
                borderRadius: token.borderRadius, padding: '12px 16px', color: '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Spin size="small" />
              </div>
            );
          }
          const s = stressOverview;
          if (!s) {
            return (
              <div style={{
                background: 'linear-gradient(135deg, #8c8c8c, #595959)',
                borderRadius: token.borderRadius, padding: '12px 16px', color: '#fff',
              }}>
                <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 4 }}>⚠️ 压力指数</div>
                <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 2 }}>--</div>
                <div style={{ fontSize: 11, opacity: 0.75 }}>暂无数据</div>
              </div>
            );
          }
          const [sStart, sEnd] = STRESS_COLORS[s.level] || STRESS_COLORS['平稳'];
          return (
            <Tooltip
              key="stress"
              title={renderStressDimTooltip(s.dimensions)}
              placement="bottom"
            >
              <div
                onClick={onStressClick}
                style={{
                  background: `linear-gradient(135deg, ${sStart}, ${sEnd})`,
                  borderRadius: token.borderRadius,
                  padding: '12px 16px',
                  color: '#fff',
                  cursor: onStressClick ? 'pointer' : 'default',
                  transition: 'transform 0.15s',
                }}
                onMouseEnter={(e) => { if (onStressClick) e.currentTarget.style.transform = 'scale(1.03)'; }}
                onMouseLeave={(e) => { if (onStressClick) e.currentTarget.style.transform = 'scale(1)'; }}
              >
                <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 4 }}>⚠️ 压力指数</div>
                <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 2 }}>{s.score}</div>
                <div style={{ fontSize: 11, opacity: 0.75 }}>{s.level}</div>
              </div>
            </Tooltip>
          );
        })()}
        {/* 主板温度 — 上证主板 + 深证主板 */}
        {(() => {
          const mainBoards = overview.board_temperatures?.filter(
            bt => bt.board_code === 'sh_main' || bt.board_code === 'sz_main'
          ) || [];
          if (mainBoards.length === 0) return null;
          const avgScore = mainBoards.reduce((s, bt) => s + bt.score, 0) / mainBoards.length;
          const avgLevel = avgScore <= 30 ? '冰点' : avgScore <= 50 ? '偏冷' : avgScore <= 70 ? '中性' : avgScore <= 85 ? '偏热' : '过热';
          const [pStart, pEnd] = TEMP_COLORS[avgLevel] || TEMP_COLORS['中性'];
          return (
            <div style={{
              background: `linear-gradient(135deg, ${pStart}, ${pEnd})`,
              borderRadius: token.borderRadius,
              padding: '12px 16px',
              color: '#fff',
            }}>
              <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 10 }}>📊 主板温度</div>
              <div style={{ display: 'flex', gap: 8 }}>
                {mainBoards.map(bt => (
                  <Tooltip key={bt.board_code} title={renderBoardDimTooltip(bt.dimensions)} placement="bottom">
                    <div
                      onClick={onBoardTemperatureClick ? () => onBoardTemperatureClick(bt.board_code, bt.board_name) : undefined}
                      style={sectorSubItemStyle}
                      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.28)'; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.15)'; }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {bt.board_name}
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 2 }}>
                        {bt.score}°
                      </div>
                      <div style={{ fontSize: 11, opacity: 0.75 }}>{bt.level}</div>
                    </div>
                  </Tooltip>
                ))}
              </div>
            </div>
          );
        })()}

        {/* 双创温度 — 科创板 + 创业板 */}
        {(() => {
          const starBoards = overview.board_temperatures?.filter(
            bt => bt.board_code === 'sh_star' || bt.board_code === 'sz_chi'
          ) || [];
          if (starBoards.length === 0) return null;
          const avgScore = starBoards.reduce((s, bt) => s + bt.score, 0) / starBoards.length;
          const avgLevel = avgScore <= 30 ? '冰点' : avgScore <= 50 ? '偏冷' : avgScore <= 70 ? '中性' : avgScore <= 85 ? '偏热' : '过热';
          const [pStart, pEnd] = TEMP_COLORS[avgLevel] || TEMP_COLORS['中性'];
          return (
            <div style={{
              background: `linear-gradient(135deg, ${pStart}, ${pEnd})`,
              borderRadius: token.borderRadius,
              padding: '12px 16px',
              color: '#fff',
            }}>
              <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 10 }}>🚀 双创温度</div>
              <div style={{ display: 'flex', gap: 8 }}>
                {starBoards.map(bt => (
                  <Tooltip key={bt.board_code} title={renderBoardDimTooltip(bt.dimensions)} placement="bottom">
                    <div
                      onClick={onBoardTemperatureClick ? () => onBoardTemperatureClick(bt.board_code, bt.board_name) : undefined}
                      style={sectorSubItemStyle}
                      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.28)'; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.15)'; }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {bt.board_name}
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 2 }}>
                        {bt.score}°
                      </div>
                      <div style={{ fontSize: 11, opacity: 0.75 }}>{bt.level}</div>
                    </div>
                  </Tooltip>
                ))}
              </div>
            </div>
          );
        })()}
      </div>

      {/* 第二排：涨跌比 + 北向 + 领涨/领跌 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
        {cards.filter(c => c.label !== '🔥 市场温度').map((card) => (
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

      {/* 板块资金流 */}
      <div
        onClick={onSectorFundClick}
        style={{
          background: sectorFundTotalYI != null && sectorFundTotalYI >= 0
            ? 'linear-gradient(135deg, #eb2f96, #c41d7f)'
            : 'linear-gradient(135deg, #13c2c2, #08979c)',
          borderRadius: token.borderRadius,
          padding: '16px 20px',
          color: '#fff',
          cursor: onSectorFundClick ? 'pointer' : 'default',
          transition: 'transform 0.15s',
          opacity: sectorFundLoading ? 0.7 : 1,
        }}
        onMouseEnter={(e) => { if (onSectorFundClick) e.currentTarget.style.transform = 'scale(1.02)'; }}
        onMouseLeave={(e) => { if (onSectorFundClick) e.currentTarget.style.transform = 'scale(1)'; }}
      >
        <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 4 }}>📈 板块资金流</div>
        <div style={{ fontSize: 24, fontWeight: 700, marginBottom: 2 }}>
          {sectorFundLoading ? '...' : (
            sectorFundTotalYI != null
              ? `${sectorFundTotalYI > 0 ? '+' : ''}${sectorFundTotalYI.toFixed(1)}亿`
              : '--'
          )}
        </div>
        <div style={{ fontSize: 11, opacity: 0.75 }}>
          {sectorFundTotalYI != null
            ? (sectorFundTotalYI >= 0 ? '行业资金净流入' : '行业资金净流出')
            : '全行业资金流向'}
        </div>
      </div>
      </div>
    </div>
  );
};

export default TemperatureCard;
