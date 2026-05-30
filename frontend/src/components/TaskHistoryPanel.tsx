import React from 'react';
import { Card, List, Tag, Space, Typography, Spin, Empty, Button, Popconfirm } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import type { AnalysisTask } from '@/types/aiStrategy';

const { Text } = Typography;

interface TaskHistoryPanelProps {
  tasks: AnalysisTask[];
  loading: boolean;
  currentTaskId: string | null;
  onTaskClick: (taskId: string) => void;
  onTaskDelete: (taskId: string) => void;
}

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  completed: { color: 'green', label: '已完成' },
  review: { color: 'blue', label: '待生成' },
  processing: { color: 'blue', label: '分析中' },
  generating: { color: 'blue', label: '生成中' },
  failed: { color: 'red', label: '失败' },
};

const CLICKABLE_STATUSES = new Set(['completed', 'review']);

const TaskHistoryPanel: React.FC<TaskHistoryPanelProps> = ({
  tasks,
  loading,
  currentTaskId,
  onTaskClick,
  onTaskDelete,
}) => {
  return (
    <Card title="历史分析" size="small">
      {loading ? (
        <Spin style={{ display: 'block', textAlign: 'center' }} />
      ) : tasks.length === 0 ? (
        <Empty description="暂无分析记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          size="small"
          dataSource={tasks}
          renderItem={(t) => {
            const cfg = STATUS_CONFIG[t.status] || {
              color: 'default',
              label: t.status,
            };
            const isClickable = CLICKABLE_STATUSES.has(t.status);
            const isActive = t.task_id === currentTaskId;
            return (
              <List.Item
                style={{
                  cursor: isClickable ? 'pointer' : 'default',
                  background: isActive ? '#f0f5ff' : undefined,
                }}
                onClick={() => {
                  if (isClickable) onTaskClick(t.task_id);
                }}
                actions={[
                  <Popconfirm
                    key="delete"
                    title="确定删除此分析记录？"
                    onConfirm={(e) => {
                      e?.stopPropagation();
                      onTaskDelete(t.task_id);
                    }}
                    onCancel={(e) => e?.stopPropagation()}
                    okText="删除"
                    cancelText="取消"
                  >
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Popconfirm>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Text strong>{t.ts_code}</Text>
                      <Tag color={cfg.color}>{cfg.label}</Tag>
                    </Space>
                  }
                  description={`${t.date} · ${(t.created_at || '').slice(0, 16)}`}
                />
              </List.Item>
            );
          }}
        />
      )}
    </Card>
  );
};

export default TaskHistoryPanel;
