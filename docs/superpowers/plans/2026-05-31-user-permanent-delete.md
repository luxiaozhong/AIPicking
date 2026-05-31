# 用户永久删除功能 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有用户停用功能基础上，新增永久硬删除功能（级联删除关联数据）

**Architecture:** 后端新增 `DELETE /api/v1/users/{user_id}/permanent` 端点，service 层在单个事务内手动级联删除子表数据后删除用户；前端在用户管理页操作列添加"删除"按钮，使用 Modal + 输入用户名二次确认

**Tech Stack:** FastAPI + SQLAlchemy async + PostgreSQL (asyncpg) / React 18 + TypeScript + Ant Design 6

**Spec:** [2026-05-31-user-permanent-delete-design.md](../specs/2026-05-31-user-permanent-delete-design.md)

---

### 文件结构

| 文件 | 操作 | 职责 |
|---|---|---|
| `backend/app/services/auth_service.py` | 修改 | 新增 `permanent_delete_user` 函数 |
| `backend/app/api/users.py` | 修改 | 新增 `DELETE /{user_id}/permanent` 路由 |
| `backend/tests/test_users.py` | 创建 | 测试硬删除端点 |
| `frontend/src/services/userService.ts` | 修改 | 新增 `deleteUserPermanent` 方法 |
| `frontend/src/pages/UserManagement.tsx` | 修改 | 操作列加"删除"按钮 + 确认 Modal |

---

### Task 1: 后端 service 层 — `permanent_delete_user`

**Files:**
- Modify: `backend/app/services/auth_service.py`

- [ ] **Step 1: 在 `auth_service.py` 末尾新增 `permanent_delete_user` 函数**

```python
from sqlalchemy import delete

async def permanent_delete_user(db: AsyncSession, user_id: int) -> bool:
    """永久删除用户及其所有关联数据，返回 True 表示成功

    级联删除范围：
    - strategies, backtest_reports, strategy_runs,
      batch_backtest_reports, ai_strategy_tasks
    - ai_factors.created_by 置 NULL（因子可能被他人引用）
    """
    from ..models.strategy import Strategy
    from ..models.backtest import BacktestReport, StrategyRun, BatchBacktestReport
    from ..models.ai_task import AIStrategyTask
    from ..models.ai_factor import AIFactor

    user = await get_user_by_id(db, user_id)
    if not user:
        return False

    # 1. 删除策略
    await db.execute(
        delete(Strategy).where(Strategy.user_id == user_id)
    )
    # 2. 删除回测报告
    await db.execute(
        delete(BacktestReport).where(BacktestReport.user_id == user_id)
    )
    # 3. 删除运行记录
    await db.execute(
        delete(StrategyRun).where(StrategyRun.user_id == user_id)
    )
    # 4. 删除批量回测报告
    await db.execute(
        delete(BatchBacktestReport).where(BatchBacktestReport.user_id == user_id)
    )
    # 5. 删除 AI 任务
    await db.execute(
        delete(AIStrategyTask).where(AIStrategyTask.user_id == user_id)
    )
    # 6. AI 因子 created_by 置 NULL
    from sqlalchemy import update
    await db.execute(
        update(AIFactor)
        .where(AIFactor.created_by == user_id)
        .values(created_by=None)
    )
    # 7. 删除用户
    await db.delete(user)

    return True
```

---

### Task 2: 后端 API 路由 — `DELETE /{user_id}/permanent`

**Files:**
- Modify: `backend/app/api/users.py`

- [ ] **Step 1: 在 `users.py` 的 `delete_user` 函数之后新增硬删除端点**

在 `users.py` 末尾（`delete_user` 函数之后）添加：

```python
@router.delete("/{user_id}/permanent", status_code=200)
async def permanent_delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """永久删除用户（管理员，硬删除 + 级联删除关联数据）"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自己的账号",
        )

    # 查找目标用户
    target_user = await auth_service.get_user_by_id(db, user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 保护默认管理员
    if target_user.username == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除默认管理员账号",
        )

    await auth_service.permanent_delete_user(db, user_id)

    return {"code": 0, "message": "用户已永久删除"}
```

- [ ] **Step 2: 验证路由注册正确**

不需要修改 `main.py`，因为 `users.router` 已经注册在 `/api/v1/users` 前缀下，新路由 `/"{user_id}/permanent"` 会自动映射到 `DELETE /api/v1/users/{user_id}/permanent`。

---

### Task 3: 后端测试

**Files:**
- Create: `backend/tests/test_users.py`

- [ ] **Step 1: 创建测试文件**

```python
"""用户管理相关测试"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import Base, get_db
from app.models.user import User
from app.services.auth_service import (
    hash_password, create_access_token, seed_default_admin,
    create_user as create_user_svc, deactivate_user as deactivate_user_svc,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def test_session(test_engine):
    session_factory = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(test_session):
    """创建测试客户端，override get_db 使用测试数据库"""
    async def override_get_db():
        try:
            yield test_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


def _auth_header(user_id: int = 1, role: str = "admin") -> dict:
    """生成管理员的 Authorization header"""
    token = create_access_token(user_id, role)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_permanent_delete_user_success(client, test_session):
    """测试永久删除用户：成功删除普通用户及其关联数据"""
    # 创建测试用户
    user = await create_user_svc(test_session, "testuser", "password123", role="user")
    await test_session.commit()

    response = await client.delete(
        f"/api/v1/users/{user.id}/permanent",
        headers=_auth_header(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "已永久删除" in data["message"]

    # 确认用户已从数据库删除
    from sqlalchemy import select
    result = await test_session.execute(select(User).where(User.id == user.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_permanent_delete_nonexistent_user(client, test_session):
    """测试删除不存在的用户返回 404"""
    response = await client.delete(
        "/api/v1/users/99999/permanent",
        headers=_auth_header(),
    )

    assert response.status_code == 404
    data = response.json()
    assert "不存在" in data["detail"]


@pytest.mark.asyncio
async def test_permanent_delete_self(client, test_session):
    """测试不能删除自己"""
    response = await client.delete(
        "/api/v1/users/1/permanent",  # admin user_id=1
        headers=_auth_header(user_id=1),
    )

    assert response.status_code == 400
    data = response.json()
    assert "不能删除自己" in data["detail"]


@pytest.mark.asyncio
async def test_permanent_delete_default_admin(client, test_session):
    """测试不能删除默认 admin"""
    # 查找 admin 用户
    from sqlalchemy import select
    result = await test_session.execute(select(User).where(User.username == "admin"))
    admin = result.scalar_one_or_none()

    if admin:
        # 用另一个管理员身份尝试删除 admin
        other_admin = await create_user_svc(test_session, "otheradmin", "123456", role="admin")
        await test_session.commit()

        response = await client.delete(
            f"/api/v1/users/{admin.id}/permanent",
            headers=_auth_header(user_id=other_admin.id),
        )

        assert response.status_code == 400
        data = response.json()
        assert "默认管理员" in data["detail"]


@pytest.mark.asyncio
async def test_permanent_delete_with_cascade(client, test_session):
    """测试硬删除级联删除策略和回测数据"""
    from app.models.strategy import Strategy
    from app.models.backtest import BacktestReport, StrategyRun, BatchBacktestReport
    from app.models.ai_task import AIStrategyTask
    from app.models.ai_factor import AIFactor

    user = await create_user_svc(test_session, "cascadetest", "123456", role="user")
    await test_session.commit()

    # 创建关联数据
    strategy = Strategy(name="test_strategy", user_id=user.id)
    test_session.add(strategy)
    await test_session.commit()
    await test_session.refresh(strategy)

    backtest = BacktestReport(
        strategy_id=strategy.id, user_id=user.id, cutoff_date="20260101"
    )
    run = StrategyRun(
        strategy_id=strategy.id, user_id=user.id,
        cutoff_date="20260101", recommendations="[]",
    )
    batch = BatchBacktestReport(
        strategy_id=strategy.id, user_id=user.id,
        start_date="20260101", end_date="20260110",
    )
    task = AIStrategyTask(user_id=user.id, task_type="stock_reference")
    factor = AIFactor(
        factor_id="test_factor_001", name="test_factor",
        category="momentum", created_by=user.id,
    )
    test_session.add_all([backtest, run, batch, task, factor])
    await test_session.commit()

    # 执行删除
    response = await client.delete(
        f"/api/v1/users/{user.id}/permanent",
        headers=_auth_header(),
    )

    assert response.status_code == 200

    # 验证级联删除
    from sqlalchemy import select as sel

    assert (await test_session.execute(sel(Strategy).where(Strategy.user_id == user.id))).scalar_one_or_none() is None
    assert (await test_session.execute(sel(BacktestReport).where(BacktestReport.user_id == user.id))).scalar_one_or_none() is None
    assert (await test_session.execute(sel(StrategyRun).where(StrategyRun.user_id == user.id))).scalar_one_or_none() is None
    assert (await test_session.execute(sel(BatchBacktestReport).where(BatchBacktestReport.user_id == user.id))).scalar_one_or_none() is None
    assert (await test_session.execute(sel(AIStrategyTask).where(AIStrategyTask.user_id == user.id))).scalar_one_or_none() is None

    # AIFactor created_by 应置为 NULL，但记录保留
    factor_result = await test_session.execute(sel(AIFactor).where(AIFactor.factor_id == "test_factor_001"))
    factor_record = factor_result.scalar_one_or_none()
    assert factor_record is not None
    assert factor_record.created_by is None

    # 用户本身已删除
    assert (await test_session.execute(sel(User).where(User.id == user.id))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_permanent_delete_requires_admin(client, test_session):
    """测试非管理员不能删除用户"""
    user = await create_user_svc(test_session, "regularuser", "123456", role="user")
    await test_session.commit()

    response = await client.delete(
        f"/api/v1/users/1/permanent",
        headers=_auth_header(user_id=user.id, role="user"),
    )

    assert response.status_code == 403
```

- [ ] **Step 2: 运行测试确认失败（因为 service 和路由尚未实现）**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_users.py -v 2>&1 | tail -20
```

预期：导入错误或 404（因为 `permanent_delete_user` 和路由尚未添加）

---

### Task 4: 前端 service 层

**Files:**
- Modify: `frontend/src/services/userService.ts`

- [ ] **Step 1: 在 `userService` 对象中新增 `deleteUserPermanent` 方法**

在 `userService.ts` 的 `deleteUser` 方法之后添加：

```typescript
  async deleteUserPermanent(id: number) {
    const response = await api.delete<{ code: number; message: string }>(`/users/${id}/permanent`);
    return response.data;
  },
```

完整文件变化：在 line 37 `},` 之后插入上述代码。

---

### Task 5: 前端 UI — 删除按钮 + 确认 Modal

**Files:**
- Modify: `frontend/src/pages/UserManagement.tsx`

- [ ] **Step 1: 新增 import**

```typescript
// 在现有 import 行的最后添加
import { ExclamationCircleOutlined } from '@ant-design/icons';
```

同时修改 Ant Design 的 import（顶部）：
```typescript
import { Table, Button, Modal, Form, Input, Select, Switch, message, Space, Tag, Popconfirm } from 'antd';
```
`Modal` 和 `Input` 和 `Space` 和 `Popconfirm` 已经存在，只需确保都有引入。

- [ ] **Step 2: 新增状态变量**

在 `UserManagement` 组件内部，现有 `const [submitting, setSubmitting] = useState(false);` 之后添加：

```typescript
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deletingUser, setDeletingUser] = useState<UserResponse | null>(null);
  const [deleteConfirmInput, setDeleteConfirmInput] = useState('');
  const [deleting, setDeleting] = useState(false);
```

- [ ] **Step 3: 新增 `handlePermanentDelete` 函数**

在 `handleDeactivate` 函数之后添加：

```typescript
  const handlePermanentDelete = async () => {
    if (!deletingUser || deleteConfirmInput !== deletingUser.username) return;
    setDeleting(true);
    try {
      await userService.deleteUserPermanent(deletingUser.id);
      message.success(`用户 "${deletingUser.username}" 已永久删除`);
      setDeleteModalOpen(false);
      setDeletingUser(null);
      setDeleteConfirmInput('');
      fetchUsers();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除失败');
    } finally {
      setDeleting(false);
    }
  };
```

- [ ] **Step 4: 修改操作列，新增"删除"按钮**

在现有 `操作` 列的 `render` 中，`editingUser` 编辑按钮逻辑改为：**当前登录用户不显示删除按钮**。需要先获取当前登录用户信息。在组件顶部，从 authStore 获取：

从 authStore 获取当前用户，在组件顶部已有 `import userService from '@/services/userService';` 下方添加：
```typescript
import { useAuthStore } from '@/stores/authStore';
```

在 `const UserManagement: React.FC = () => {` 下一行添加：
```typescript
  const currentUser = useAuthStore((s) => s.user);
```

将操作列 `render` 修改为：

```typescript
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
```

- [ ] **Step 5: 添加删除确认 Modal**

在 `UserManagement` 的 JSX 中，现有的编辑/创建 Modal（`<Modal title={editingUser ? '编辑用户' : '新建用户'}...`）的 `</Modal>` 之后，`</div>` 之前，添加：

```tsx
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
              <li>回测报告</li>
              <li>运行记录</li>
              <li>批量回测报告</li>
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
```

- [ ] **Step 6: 运行 TypeScript 检查**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

确保没有类型错误。

---

### Task 6: 运行全部测试 + 手动验证

- [ ] **Step 1: 运行后端测试**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_users.py -v
```

- [ ] **Step 2: 运行全量后端测试确保无回归**

```bash
cd backend && source venv/bin/activate && python -m pytest -v
```

- [ ] **Step 3: 启动前后端并手动验证**

```bash
./restart.sh
```

手动验证步骤：
1. 用 admin 登录 → 进入用户管理页
2. 新建测试用户 → 确认操作列出现"删除"按钮
3. 点击删除 → 确认 Modal 弹出，不匹配用户名时按钮 disabled
4. 输入正确用户名 → 点击确认删除 → 用户从列表消失
5. 确认 admin 用户行不显示删除按钮
6. 对已停用用户，确认"停用"按钮消失，但"删除"按钮仍显示
