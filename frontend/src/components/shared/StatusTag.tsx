import { Tag } from 'antd';
import { STRATEGY_STATUS_MAP, BACKTEST_STATUS_MAP } from '@/constants/status';

type StatusType = 'strategy' | 'backtest';

interface StatusTagProps {
  status: string;
  type?: StatusType;
}

export default function StatusTag({ status, type = 'strategy' }: StatusTagProps) {
  const map = type === 'backtest' ? BACKTEST_STATUS_MAP : STRATEGY_STATUS_MAP;
  const config = map[status] || { color: 'default', label: status };
  return <Tag color={config.color}>{config.label}</Tag>;
}
