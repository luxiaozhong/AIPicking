import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, Switch, message, Space, Tag, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, StopOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { UserResponse } from '@/types/auth';
import userService from '@/services/userService';
import { useAuthStore } from '@/stores/authStore';

const UserManagement: React.FC = () => {
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserResponse | null>(null);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const currentUser = useAuthStore((s) => s.user);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deletingUser, setDeletingUser] = useState<UserResponse | null>(null);
  const [deleteConfirmInput, setDeleteConfirmInput] = useState('');
  const [deleting, setDeleting] = useState(false);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const data = await userService.getUsers({ page, limit: 20 });
      setUsers(data.items);
      setTotal(data.total);
    } catch {
      message.error('获取用户列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, [page]);

  const openCreate = () => {
    setEditingUser(null);
    form.resetFields();
    form.setFieldsValue({ role: 'user', is_active: true });
    setModalOpen(true);
  };

  const openEdit = (user: UserResponse) => {
    setEditingUser(user);
    form.setFieldsValue({
      username: user.username,
      role: user.role,
      is_active: user.is_active,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      if (editingUser) {
        await userService.updateUser(editingUser.id, {
          username: values.username,
          role: values.role,
          is_active: values.is_active,
          ...(values.password ? { password: values.password } : {}),
        });
        message.success('用户已更新');
      } else {
        await userService.createUser(values);
        message.success('用户已创建');
      }

      setModalOpen(false);
      fetchUsers();
    } catch (error: any) {
      if (error.response?.data?.detail) {
        message.error(error.response.data.detail);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeactivate = async (user: UserResponse) => {
    try {
      await userService.deleteUser(user.id);
      message.success(`用户 "${user.username}" 已停用`);
      fetchUsers();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '操作失败');
    }
  };

  const handlePermanentDelete = async () => {
    if (!deletingUser || deleteConfirmInput !== deletingUser.username) {
      message.warning('请输入正确的用户名以确认删除');
      return;
    }
    setDeleting(true);
    try {
      await userService.deleteUserPermanent(deletingUser.id);
      message.success(`用户 "${deletingUser.username}" 已永久删除`);
      setDeleteModalOpen(false);
      setDeletingUser(null);
      setDeleteConfirmInput('');
      fetchUsers();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '操作失败');
    } finally {
      setDeleting(false);
    }
  };

  const columns: ColumnsType<UserResponse> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 80,
    },
    {
      title: '用户名',
      dataIndex: 'username',
    },
    {
      title: '角色',
      dataIndex: 'role',
      render: (role: string) => (
        <Tag color={role === 'admin' ? 'red' : 'blue'}>{role === 'admin' ? '管理员' : '普通用户'}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      render: (active: boolean) => (
        <Tag color={active ? 'green' : 'red'}>{active ? '激活' : '已停用'}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      render: (t: string) => t ? new Date(t).toLocaleString() : '-',
    },
    {
      title: '最后登录',
      dataIndex: 'last_login',
      render: (t: string) => t ? new Date(t).toLocaleString() : '—',
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
          >
            编辑
          </Button>
          {record.is_active && (
            <Popconfirm
              title={`确定停用用户 "${record.username}"？`}
              onConfirm={() => handleDeactivate(record)}
              okText="确定"
              cancelText="取消"
            >
              <Button type="link" danger icon={<StopOutlined />}>
                停用
              </Button>
            </Popconfirm>
          )}
          {record.id !== currentUser?.id && (
            <Button
              type="link"
              danger
              icon={<ExclamationCircleOutlined />}
              onClick={() => {
                setDeletingUser(record);
                setDeleteConfirmInput('');
                setDeleteModalOpen(true);
              }}
            >
              删除
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2>用户管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建用户
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={users}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: setPage,
          showTotal: (t) => `共 ${t} 个用户`,
        }}
      />

      <Modal
        title={editingUser ? '编辑用户' : '新建用户'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="username"
            label="用户名"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 2, max: 50, message: '用户名长度为 2-50 个字符' },
            ]}
          >
            <Input placeholder="用户名" />
          </Form.Item>

          <Form.Item
            name="password"
            label={editingUser ? '新密码（留空不修改）' : '密码'}
            rules={editingUser ? [] : [{ required: true, message: '请输入密码' }]}
          >
            <Input.Password placeholder={editingUser ? '留空则不修改密码' : '密码'} />
          </Form.Item>

          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="user">普通用户</Select.Option>
              <Select.Option value="admin">管理员</Select.Option>
            </Select>
          </Form.Item>

          {editingUser && (
            <Form.Item name="is_active" label="激活状态" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal
        title={
          <span>
            <ExclamationCircleOutlined style={{ color: '#ff4d4f', marginRight: 8 }} />
            永久删除用户
          </span>
        }
        open={deleteModalOpen}
        onOk={handlePermanentDelete}
        onCancel={() => {
          setDeleteModalOpen(false);
          setDeletingUser(null);
          setDeleteConfirmInput('');
        }}
        confirmLoading={deleting}
        okText="确认删除"
        cancelText="取消"
        okButtonProps={{
          danger: true,
          disabled: deleteConfirmInput !== deletingUser?.username,
        }}
        destroyOnClose
      >
        {deletingUser && (
          <div>
            <p style={{ marginBottom: 12 }}>
              此操作不可逆！用户 <strong>"{deletingUser.username}"</strong> 及其所有关联数据将被永久删除：
            </p>
            <ul style={{ color: '#ff4d4f', marginBottom: 16, paddingLeft: 20 }}>
              <li>策略</li>
              <li>回测报告（含批量回测）</li>
              <li>运行记录</li>
              <li>AI 分析任务</li>
            </ul>
            <p>
              请输入用户名 <strong>"{deletingUser.username}"</strong> 以确认：
            </p>
            <Input
              value={deleteConfirmInput}
              onChange={(e) => setDeleteConfirmInput(e.target.value)}
              placeholder={deletingUser.username}
            />
          </div>
        )}
      </Modal>
    </div>
  );
};

export default UserManagement;
