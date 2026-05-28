import EChartsWrapper from './EChartsWrapper';
import type { RecommendationItem } from '@/types/backtest';

interface Props {
  recommendations: RecommendationItem[];
  loading?: boolean;
}

export default function ReturnComparisonChart({ recommendations, loading }: Props) {
  const stocks = recommendations.filter(
    (r) => r.return_3d != null || r.return_7d != null || r.return_15d != null,
  );

  if (stocks.length === 0) return <EChartsWrapper options={{}} empty />;

  const option = {
    tooltip: {
      trigger: 'axis' as const,
      formatter: (params: unknown) => {
        const items = params as { name: string; seriesName: string; value: number }[];
        return `${items[0].name}<br/>${items.map((p) => `${p.seriesName}: ${(p.value * 100).toFixed(2)}%`).join('<br/>')}`;
      },
    },
    legend: { data: ['3天收益', '7天收益', '15天收益'] },
    grid: { left: 80, right: 20, top: 40, bottom: 60 },
    xAxis: {
      type: 'category' as const,
      data: stocks.map((r) => r.name),
      axisLabel: { rotate: 30 },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` },
    },
    series: [
      {
        name: '3天收益',
        type: 'bar' as const,
        data: stocks.map((r) => r.return_3d),
        itemStyle: { color: '#1677ff' },
      },
      {
        name: '7天收益',
        type: 'bar' as const,
        data: stocks.map((r) => r.return_7d),
        itemStyle: { color: '#52c41a' },
      },
      {
        name: '15天收益',
        type: 'bar' as const,
        data: stocks.map((r) => r.return_15d),
        itemStyle: { color: '#722ed1' },
      },
    ],
  };

  return <EChartsWrapper options={option} loading={loading} />;
}
