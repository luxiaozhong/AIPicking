import { useEffect, useState } from 'react';
import { Card, Form, Input, Button, message } from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import { useStrategyStore } from '@/stores/strategyStore';
import PageHeader from '@/components/shared/PageHeader';
import TagInput from '@/components/shared/TagInput';

const { TextArea } = Input;

export default function StrategyEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEdit = !!id;

  const {
    currentStrategy,
    codeContent,
    loading,
    error,
    fetchStrategy,
    updateStrategy,
    updateStrategyCode,
    clearError,
  } = useStrategyStore();

  const [formData, setFormData] = useState({ name: '', description: '' });
  const [code, setCode] = useState('');
  const [tags, setTags] = useState<string[]>([]);

  useEffect(() => {
    if (isEdit && id) fetchStrategy(parseInt(id));
  }, [isEdit, id, fetchStrategy]);

  useEffect(() => {
    if (currentStrategy) {
      setFormData({
        name: currentStrategy.name,
        description: currentStrategy.description || '',
      });
      setTags(currentStrategy.tags || []);
    }
  }, [currentStrategy]);

  useEffect(() => {
    if (codeContent) setCode(codeContent);
  }, [codeContent]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const handleSubmit = async () => {
    if (!formData.name.trim()) {
      message.error('请输入策略名称');
      return;
    }
    try {
      if (isEdit && id) {
        await updateStrategy(parseInt(id), {
          name: formData.name,
          description: formData.description || undefined,
          tags: tags.length > 0 ? tags : undefined,
        });
        if (code !== codeContent) {
          await updateStrategyCode(parseInt(id), undefined, code);
        }
        message.success('策略更新成功');
      }
      navigate('/strategies');
    } catch {
      message.error('更新失败');
    }
  };

  return (
    <>
      <PageHeader
        title={isEdit ? '编辑策略' : '新建策略'}
        breadcrumb={[
          { title: '策略管理', path: '/strategies' },
          ...(isEdit && currentStrategy
            ? [{ title: currentStrategy.name, path: `/strategies/${id}` }]
            : []),
          { title: isEdit ? '编辑' : '新建' },
        ]}
      />

      <Card>
        <Form layout="vertical" style={{ maxWidth: 900 }}>
          <Form.Item label="策略名称" required>
            <Input
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="请输入策略名称"
            />
          </Form.Item>

          <Form.Item label="策略描述">
            <TextArea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="请输入策略描述"
              rows={3}
            />
          </Form.Item>

          <Form.Item label="策略代码" required>
            <div style={{ border: '1px solid #d9d9d9', borderRadius: 6, overflow: 'hidden' }}>
              <Editor
                height="500px"
                language="python"
                theme="vs-dark"
                value={code}
                onChange={(v) => setCode(v || '')}
                options={{
                  minimap: { enabled: false },
                  fontSize: 14,
                  lineNumbers: 'on',
                  scrollBeyondLastLine: false,
                }}
              />
            </div>
          </Form.Item>

          <Form.Item label="标签">
            <TagInput value={tags} onChange={setTags} />
          </Form.Item>

          <Form.Item>
            <Button type="primary" onClick={handleSubmit} loading={loading} style={{ marginRight: 8 }}>
              {isEdit ? '更新' : '创建'}
            </Button>
            <Button onClick={() => navigate('/strategies')}>取消</Button>
          </Form.Item>
        </Form>
      </Card>
    </>
  );
}
