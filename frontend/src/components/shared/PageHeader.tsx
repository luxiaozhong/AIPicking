import type { ReactNode } from 'react';
import { Typography, Space, Breadcrumb } from 'antd';
import { Link } from 'react-router-dom';

const { Title } = Typography;

interface BreadcrumbItem {
  title: string;
  path?: string;
}

interface PageHeaderProps {
  title: string;
  breadcrumb?: BreadcrumbItem[];
  extra?: ReactNode;
}

export default function PageHeader({ title, breadcrumb, extra }: PageHeaderProps) {
  return (
    <div style={{ marginBottom: 16 }}>
      {breadcrumb && breadcrumb.length > 0 && (
        <Breadcrumb
          style={{ marginBottom: 8 }}
          items={breadcrumb.map((b) => ({
            title: b.path ? <Link to={b.path}>{b.title}</Link> : b.title,
          }))}
        />
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={2} style={{ margin: 0 }}>
          {title}
        </Title>
        {extra && <Space>{extra}</Space>}
      </div>
    </div>
  );
}
