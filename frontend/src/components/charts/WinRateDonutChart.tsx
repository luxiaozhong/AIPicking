import EChartsWrapper from './EChartsWrapper';
import type { BacktestSummary } from '@/types/backtest';

interface Props {
  summary: BacktestSummary;
  loading?: boolean;
}

export default function WinRateDonutChart({ summary, loading }: Props) {
  const winRates = [
    { name: '3天胜率', value: summary.win_rate_3d || 0 },
    { name: '7天胜率', value: summary.win_rate_7d || 0 },
    { name: '15天胜率', value: summary.win_rate_15d || 0 },
  ];

  const option = {
    tooltip: {
      trigger: 'item' as const,
      formatter: (p: unknown) => {
        const d = p as { name: string; percent: number };
        return `${d.name}: ${d.percent.toFixed(1)}%`;
      },
    },
    series: winRates.map((wr, i) => ({
      name: wr.name,
      type: 'pie' as const,
      radius: ['50%', '72%'],
      center: [`${20 + i * 30}%`, '50%'],
      label: {
        show: true,
        position: 'inside' as const,
        formatter: `${wr.name}\n{(d|(value * 100).toFixed(0))}%`,
        fontSize: 12,
      },
      data: [
        { value: wr.value, name: '盈' },
        { value: 1 - wr.value, name: '亏' },
      ],
      color: ['#52c41a', '#f0f0f0'],
    })),
  };

  return <EChartsWrapper options={option} loading={loading} height={220} />;
}
