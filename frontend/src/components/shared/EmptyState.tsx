import { Empty, Button } from 'antd';

interface EmptyStateProps {
  description?: string;
  actionText?: string;
  onAction?: () => void;
}

export default function EmptyState({ description = '暂无数据', actionText, onAction }: EmptyStateProps) {
  return (
    <Empty description={description}>
      {actionText && onAction && (
        <Button type="primary" onClick={onAction}>
          {actionText}
        </Button>
      )}
    </Empty>
  );
}
