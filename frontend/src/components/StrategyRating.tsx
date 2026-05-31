import { useState, useEffect } from 'react';
import { Rate, message, Space, Typography } from 'antd';
import { useStrategyStore } from '@/stores/strategyStore';
import type { RatingStats } from '@/types/strategy';

const { Text } = Typography;

interface Props {
  strategyId: number;
}

export default function StrategyRating({ strategyId }: Props) {
  const { rateStrategy, fetchRatings } = useStrategyStore();
  const [stats, setStats] = useState<RatingStats | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchRatings(strategyId).then(setStats);
  }, [strategyId, fetchRatings]);

  const handleRate = async (value: number) => {
    setSubmitting(true);
    try {
      await rateStrategy(strategyId, value);
      message.success('评分成功');
      const fresh = await fetchRatings(strategyId);
      setStats(fresh);
    } catch {
      message.error('评分失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ textAlign: 'center', padding: '16px 0' }}>
      <Space direction="vertical" size={8}>
        <Text strong style={{ fontSize: 24 }}>
          {stats?.average ? `⭐ ${stats.average.toFixed(1)}` : '暂无评分'}
        </Text>
        <Text type="secondary">
          {stats?.count ? `${stats.count} 人评分` : '成为第一个评分的人'}
        </Text>
        <Rate
          value={stats?.current_user_score ?? 0}
          onChange={handleRate}
          disabled={submitting}
        />
      </Space>
    </div>
  );
}
