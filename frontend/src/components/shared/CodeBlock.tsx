import { Card } from 'antd';
import { CopyOutlined } from '@ant-design/icons';

interface CodeBlockProps {
  code: string;
  title?: string;
  maxHeight?: number;
  onCopy?: () => void;
}

export default function CodeBlock({ code, title = '策略代码', maxHeight = 500, onCopy }: CodeBlockProps) {
  return (
    <Card
      title={title}
      extra={
        onCopy && (
          <CopyOutlined
            style={{ cursor: 'pointer', fontSize: 16 }}
            onClick={onCopy}
          />
        )
      }
    >
      <pre
        style={{
          background: '#1e1e1e',
          color: '#d4d4d4',
          padding: 16,
          borderRadius: 8,
          maxHeight,
          overflow: 'auto',
          whiteSpace: 'pre-wrap',
          fontSize: 13,
          lineHeight: 1.6,
          margin: 0,
        }}
      >
        {code}
      </pre>
    </Card>
  );
}
