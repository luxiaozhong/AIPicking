import { useState } from 'react';
import { Input, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';

interface TagInputProps {
  value?: string[];
  onChange?: (tags: string[]) => void;
}

export default function TagInput({ value = [], onChange }: TagInputProps) {
  const [inputVisible, setInputVisible] = useState(false);
  const [inputValue, setInputValue] = useState('');

  const handleRemove = (removed: string) => {
    onChange?.(value.filter((t) => t !== removed));
  };

  const handleConfirm = () => {
    const trimmed = inputValue.trim();
    if (trimmed && !value.includes(trimmed)) {
      onChange?.([...value, trimmed]);
    }
    setInputVisible(false);
    setInputValue('');
  };

  return (
    <>
      {value.map((tag) => (
        <Tag key={tag} closable onClose={() => handleRemove(tag)}>
          {tag}
        </Tag>
      ))}
      {inputVisible ? (
        <Input
          autoFocus
          size="small"
          style={{ width: 80 }}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onBlur={handleConfirm}
          onPressEnter={handleConfirm}
        />
      ) : (
        <Tag
          icon={<PlusOutlined />}
          style={{ borderStyle: 'dashed' }}
          onClick={() => setInputVisible(true)}
        >
          新标签
        </Tag>
      )}
    </>
  );
}
