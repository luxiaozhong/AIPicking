import { useState, useEffect } from 'react';
import { Button, Input, List, Typography, message, Popconfirm } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useStrategyStore } from '@/stores/strategyStore';
import type { CommentItem } from '@/types/strategy';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

interface Props {
  strategyId: number;
  isOwner: boolean;
}

export default function StrategyComments({ strategyId, isOwner }: Props) {
  const { fetchComments, addComment, deleteComment } = useStrategyStore();
  const [comments, setComments] = useState<CommentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [newComment, setNewComment] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const load = async (p = 1) => {
    const result = await fetchComments(strategyId, p);
    if (result) {
      setComments(result.items);
      setTotal(result.total);
      setPage(result.page);
    }
  };

  useEffect(() => {
    load(1);
  }, [strategyId]);

  const handleSubmit = async () => {
    if (!newComment.trim()) return;
    setSubmitting(true);
    try {
      await addComment(strategyId, newComment.trim());
      setNewComment('');
      message.success('评论成功');
      load(1);
    } catch {
      message.error('评论失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (commentId: number) => {
    try {
      await deleteComment(strategyId, commentId);
      message.success('删除成功');
      load(page);
    } catch {
      message.error('删除失败');
    }
  };

  return (
    <div>
      <Text strong>评论 ({total})</Text>
      <div style={{ marginTop: 16, marginBottom: 16 }}>
        <TextArea
          rows={3}
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="分享你对这个策略的看法..."
          maxLength={2000}
          showCount
        />
        <Button
          type="primary"
          onClick={handleSubmit}
          loading={submitting}
          disabled={!newComment.trim()}
          style={{ marginTop: 8 }}
        >
          发表评论
        </Button>
      </div>
      <List
        dataSource={comments}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => load(p),
        }}
        renderItem={(item: CommentItem) => (
          <List.Item
            actions={
              isOwner
                ? [
                    <Popconfirm
                      key="delete"
                      title="确定删除此评论？"
                      onConfirm={() => handleDelete(item.id)}
                      okText="确定"
                      cancelText="取消"
                    >
                      <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>,
                  ]
                : undefined
            }
          >
            <List.Item.Meta
              title={<Text strong>{item.user_name || '匿名用户'}</Text>}
              description={
                <>
                  <Paragraph style={{ marginBottom: 4 }}>{item.content}</Paragraph>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {new Date(item.created_at).toLocaleString()}
                  </Text>
                </>
              }
            />
          </List.Item>
        )}
      />
    </div>
  );
}
