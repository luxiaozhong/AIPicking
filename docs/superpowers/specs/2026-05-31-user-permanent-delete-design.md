# 用户永久删除功能 — 设计文档

## 概述

在现有用户停用（软删除）基础上，新增永久硬删除功能。管理员可从数据库彻底删除用户及其所有关联数据。

## 需求摘要

- 硬删除与软删除（停用）并存，各自独立操作
- 级联删除用户所有关联数据
- 禁止删除自己
- 禁止删除默认管理员 `admin`（种子账户保护）
- 管理员之间可互相删除（遵循以上约束）

---

## 后端

### 新端点

```
DELETE /api/v1/users/{user_id}/permanent
```

**鉴权：** `require_admin`

### 业务约束

| 条件 | HTTP | detail |
|---|---|---|
| 用户不存在 | 404 | `"用户不存在"` |
| 删除自身 | 400 | `"不能删除自己的账号"` |
| 删除默认 admin（username == "admin"） | 400 | `"不能删除默认管理员账号"` |

### 级联删除范围

在一个事务内按顺序执行：

1. 删除 `strategies` 中 `user_id` 匹配的记录
2. 删除 `backtest_reports` 中 `user_id` 匹配的记录
3. 删除 `strategy_runs` 中 `user_id` 匹配的记录
4. 删除 `batch_backtest_reports` 中 `user_id` 匹配的记录
5. 删除 `ai_strategy_tasks` 中 `user_id` 匹配的记录
6. `ai_factors` 中 `created_by` 匹配的置为 NULL（不删除，因子可能被他人引用）
7. 删除 `users` 记录本身

事务失败时全部回滚。

### service 层

`auth_service.py` 新增：

```python
async def permanent_delete_user(db: AsyncSession, user_id: int) -> bool
    """永久删除用户及其所有关联数据，返回 True 表示成功"""
```

### API 路由

`users.py` 新增 `@router.delete("/{user_id}/permanent")` 处理函数。

**返回格式：**
```json
{"code": 0, "message": "用户已永久删除"}
```

---

## 前端

### userService.ts

新增方法：

```typescript
async deleteUserPermanent(id: number) {
    const response = await api.delete<{ code: number; message: string }>(`/users/${id}/permanent`);
    return response.data;
}
```

### UserManagement.tsx

**操作列新增"删除"按钮：**

- 所有用户（含已停用）都显示，但当前登录用户不显示
- 点击弹出确认 Modal，需输入目标用户名才能确认
- Modal 内容：
  - 警告图标 + "永久删除用户"标题
  - 列出会被级联删除的数据类型（策略、回测报告、运行记录、AI 任务）
  - 输入框：请输入用户名 "xxx" 以确认
  - 确认按钮在用户名匹配前 disabled
- 成功后：`message.success` + 刷新列表
- 失败：复用现有错误处理，显示后端返回的 detail

**按钮展示规则：**

| 用户状态 | 停用按钮 | 删除按钮 |
|---|---|---|
| 激活 | ✅ | ✅ |
| 已停用 | ❌ | ✅ |
| 当前登录用户 | ✅（后端拦截） | ❌（不渲染） |

---

## 文件变更清单

| 文件 | 变更 |
|---|---|
| `backend/app/api/users.py` | 新增 `DELETE /{user_id}/permanent` 路由 |
| `backend/app/services/auth_service.py` | 新增 `permanent_delete_user` 函数 |
| `frontend/src/services/userService.ts` | 新增 `deleteUserPermanent` 方法 |
| `frontend/src/pages/UserManagement.tsx` | 操作列加"删除"按钮 + 确认 Modal |

---

## 测试要点

- 正常删除普通用户（含关联数据全部清除）
- 删除已停用用户
- 删除自己的 400
- 删除 admin 的 400
- 删除不存在的用户 404
- 事务回滚验证（中途失败的原子性）
