import { useState, useEffect } from 'react';
import { Card, Form, Input, Button, message, Upload } from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import { InboxOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useStrategyStore } from '@/stores/strategyStore';
import PageHeader from '@/components/shared/PageHeader';
import TagInput from '@/components/shared/TagInput';

const { TextArea } = Input;
const { Dragger } = Upload;

export default function StrategyUpload() {
  const navigate = useNavigate();
  const { uploadStrategy, loading, error, clearError } = useStrategyStore();

  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState<string[]>([]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const handleSubmit = async () => {
    if (!file) {
      message.error('请上传策略脚本文件');
      return;
    }
    try {
      const result = await uploadStrategy(
        file,
        name || undefined,
        description || undefined,
        tags.length > 0 ? tags.join(',') : undefined,
      );
      if (result.code === 0) {
        message.success('策略上传成功');
        navigate('/strategies');
      } else {
        message.error(result.message || '上传失败');
      }
    } catch {
      message.error('上传失败');
    }
  };

  return (
    <>
      <PageHeader
        title="上传策略"
        breadcrumb={[
          { title: '策略管理', path: '/strategies' },
          { title: '上传策略' },
        ]}
      />

      <Card style={{ maxWidth: 700 }}>
        <Form layout="vertical" onFinish={handleSubmit}>
          <Form.Item label="策略脚本文件" required>
            <Dragger
              accept=".py"
              maxCount={1}
              onChange={(info: { fileList: UploadFile[] }) => {
                setFile(info.fileList.length > 0 ? info.fileList[0].originFileObj || null : null);
              }}
              beforeUpload={(f: File) => {
                if (!f.name.endsWith('.py')) {
                  message.error('只能上传 .py 文件');
                  return false;
                }
                return false;
              }}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">点击或拖拽 .py 文件到此区域上传</p>
              <p className="ant-upload-hint">仅支持 Python 策略脚本文件</p>
            </Dragger>
          </Form.Item>

          <Form.Item label="策略名称">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="留空则使用文件名"
            />
          </Form.Item>

          <Form.Item label="策略描述">
            <TextArea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="请输入策略描述"
              rows={4}
            />
          </Form.Item>

          <Form.Item label="标签">
            <TagInput value={tags} onChange={setTags} />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} style={{ marginRight: 8 }}>
              上传策略
            </Button>
            <Button onClick={() => navigate('/strategies')}>取消</Button>
          </Form.Item>
        </Form>
      </Card>
    </>
  );
}
