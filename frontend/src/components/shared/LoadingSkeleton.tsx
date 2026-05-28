import { Skeleton, Card } from 'antd';

interface LoadingSkeletonProps {
  type?: 'table' | 'card' | 'detail' | 'code';
  rows?: number;
}

export default function LoadingSkeleton({ type = 'table', rows = 5 }: LoadingSkeletonProps) {
  if (type === 'table') {
    return (
      <Card>
        <Skeleton active title paragraph={{ rows }} />
      </Card>
    );
  }

  if (type === 'card') {
    return (
      <Card>
        <Skeleton active />
      </Card>
    );
  }

  if (type === 'detail') {
    return (
      <Card>
        <Skeleton active paragraph={{ rows: 6 }} />
      </Card>
    );
  }

  if (type === 'code') {
    return (
      <Card title="策略代码">
        <Skeleton active paragraph={{ rows: 15 }} />
      </Card>
    );
  }

  return <Skeleton active paragraph={{ rows }} />;
}
