# 策略可视化编辑 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让通过可视化构建器创建或 NL 生成的策略，在编辑时直接复用可视化构建器，查看和修改因子/参数，替代旧的代码编辑器。

**Architecture:** 扩展 StrategyBuilder 组件，通过 URL `?id=` 参数区分创建/编辑模式。编辑模式下从后端加载已有 `factor_config` 填充到构建器，保存时提供"更新"和"另存为"两个选项。AI 参考选股策略（`factor_config` 结构不同）不支持可视化编辑。删除已废弃的 StrategyEdit 页面和相关路由。

**Tech Stack:** React 18 + TypeScript + Ant Design 6 + Zustand（前端），后端无需改动。

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `frontend/src/types/strategy.ts` | 补充 `factor_config` 字段 + 新增 `isVisualEditable` 工具函数 |
| `frontend/src/pages/StrategyBuilder.tsx` | 核心改动：编辑模式加载、保存二选一、未保存提示 |
| `frontend/src/pages/StrategyDetail.tsx` | 编辑按钮跳转变更、AI 策略隐藏按钮 |
| `frontend/src/pages/StrategyList.tsx` | 列表编辑按钮跳转变更、AI 策略隐藏按钮 |
| `frontend/src/stores/strategyStore.ts` | 新增 `updateFactorConfig`、`createFromFactorConfig` |
| `frontend/src/App.tsx` | 移除废弃路由 |
| `frontend/src/pages/StrategyEdit.tsx` | 删除 |

---

## 识别 AI 参考选股策略

AI 参考选股策略的 `factor_config` 结构为 `{ indicators: [...] }`，标准策略为 `{ buy_signals, sell_signals, ... }`。

```typescript
// 工具函数：判断策略是否支持可视化编辑
function isVisualEditable(factorConfig: Record<string, unknown> | null | undefined): boolean {
  if (!factorConfig) return false;
  return 'buy_signals' in factorConfig && 'sell_signals' in factorConfig;
}
```

应用到列表和详情页的编辑按钮显隐。

---

### Task 1: 补充前端类型定义

**Files:**
- Modify: `frontend/src/types/strategy.ts`

- [ ] **Step 1: 给 Strategy 接口添加 factor_config 字段和类型守卫**

在 `Strategy` 接口（约第 3 行）添加 `factor_config`：

```typescript
export interface Strategy {
  id: number;
  user_id?: number;
  owner_name?: string;
  name: string;
  description?: string;
  file_path: string;
  params_schema?: string;
  tags?: string[];
  status: string;
  version: number;
  is_published: boolean;
  avg_score?: number | null;
  rating_count?: number;
  factor_config?: Record<string, unknown>;  // 新增
  created_at: string;
  updated_at: string;
}
```

在同一文件末尾添加工具函数：

```typescript
/** 判断策略是否支持可视化编辑（标准信号策略有 buy_signals/sell_signals） */
export function isVisualEditable(factorConfig: Record<string, unknown> | null | undefined): boolean {
  if (!factorConfig) return false;
  return 'buy_signals' in factorConfig && 'sell_signals' in factorConfig;
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/types/strategy.ts
git commit -m "feat: add factor_config to Strategy type and isVisualEditable guard"
```

---

### Task 2: Store 新增方法

**Files:**
- Modify: `frontend/src/stores/strategyStore.ts`

- [ ] **Step 1: 添加 updateFactorConfig 方法**

在 `permanentDeleteStrategy` 方法之后（约第 231 行），`clearError` 之前，添加：

```typescript
// 更新策略因子配置（重新生成代码）
updateFactorConfig: async (id: number, config: Record<string, unknown>, meta?: {
  name?: string;
  description?: string;
  tags?: string[];
}) => {
  set({ loading: true, error: null });
  try {
    // 先更新元数据（如有变化）
    if (meta && (meta.name || meta.description !== undefined || meta.tags)) {
      await strategyService.updateStrategy(id, {
        name: meta.name,
        description: meta.description,
        tags: meta.tags,
      });
    }
    // 更新因子配置
    await strategyService.updateStrategyFactors(id, config as import('@/types/factor').FactorConfig);
    // 刷新数据
    await get().fetchStrategy(id);
    set({ loading: false });
  } catch (error: any) {
    set({ loading: false, error: error.response?.data?.message || '更新因子配置失败' });
    throw error;
  }
},

// 基于因子配置创建新策略（另存为）
createFromFactorConfig: async (config: Record<string, unknown>, name: string, description?: string) => {
  set({ loading: true, error: null });
  try {
    const res = await strategyService.createStrategyWithFactors({
      name,
      description,
      factor_config: config as import('@/types/factor').FactorConfig,
    });
    if (res.code === 0 && res.data) {
      set({ loading: false });
      return res.data;
    }
    throw new Error(res.message || '创建失败');
  } catch (error: any) {
    set({ loading: false, error: error.response?.data?.message || error.message || '创建失败' });
    throw error;
  }
},
```

- [ ] **Step 2: 在 State 接口中声明新方法签名**

在 `StrategyState` interface 中（约第 4-55 行），`permanentDeleteStrategy` 之后添加：

```typescript
updateFactorConfig: (id: number, config: Record<string, unknown>, meta?: {
  name?: string;
  description?: string;
  tags?: string[];
}) => Promise<void>;

createFromFactorConfig: (config: Record<string, unknown>, name: string, description?: string) => Promise<Strategy>;
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/stores/strategyStore.ts
git commit -m "feat: add updateFactorConfig and createFromFactorConfig to strategyStore"
```

---

### Task 3: StrategyBuilder 编辑模式

**Files:**
- Modify: `frontend/src/pages/StrategyBuilder.tsx`

这是核心改动，分步骤完成。

- [ ] **Step 1: 添加 imports 和 URL 参数读取**

在文件顶部（约第 1 行），更新 imports：

```typescript
import { useState, useEffect, useCallback, useRef } from 'react';
import { Input, Button, Card, Select, message, Modal, Space, Tabs, Tag, Dropdown } from 'antd';
import { useSearchParams, useNavigate } from 'react-router-dom';  // 新增
```

在组件函数开头（约第 34 行 `export default function StrategyBuilder()` 之后），添加编辑模式状态：

```typescript
export default function StrategyBuilder() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const editId = searchParams.get('id');  // 编辑模式：策略 ID
  const isEditMode = !!editId;

  // 编辑模式：从 store 加载策略
  const {
    currentStrategy,
    codeContent,
    loading: storeLoading,
    fetchStrategy,
    updateFactorConfig,
    createFromFactorConfig,
  } = useStrategyStore();

  // ... 保留现有 state ...
```

- [ ] **Step 2: 编辑模式加载逻辑**

在现有的 `useEffect` 加载数据（约第 70 行）之后，添加编辑模式数据加载：

```typescript
// 编辑模式：加载策略 factor_config
useEffect(() => {
  if (!editId) return;
  const id = parseInt(editId, 10);
  if (isNaN(id)) return;

  fetchStrategy(id).then(() => {
    // fetchStrategy 更新 currentStrategy，这里通过闭包无法获取最新值
    // 使用 useStrategyStore.getState() 获取
  });
}, [editId]);

// 监听 currentStrategy 变化，填充表单
const [editLoaded, setEditLoaded] = useState(false);
useEffect(() => {
  if (!isEditMode || editLoaded || !currentStrategy) return;

  // 检查是否支持可视化编辑
  if (!isVisualEditable(currentStrategy.factor_config)) {
    message.warning('该策略不支持可视化编辑（AI 参考选股策略）');
    navigate('/strategies');
    return;
  }

  // 填充名称、描述
  setStrategyName(currentStrategy.name);
  setStrategyDesc(currentStrategy.description || '');

  // 填充 factor_config
  const fc = currentStrategy.factor_config as FactorConfig;
  if (fc) {
    setFactorConfig({
      ...emptyFactorConfig(),
      ...fc,
      selection_conditions: {
        logic: 'AND',
        ...(fc.selection_conditions || {}),
        conditions: fc.selection_conditions?.conditions || [],
      },
      buy_signals: {
        logic: 'AND',
        ...(fc.buy_signals || {}),
        factors: fc.buy_signals?.factors || [],
      },
      sell_signals: {
        logic: 'OR',
        ...(fc.sell_signals || {}),
        factors: fc.sell_signals?.factors || [],
      },
      scoring_modifiers: fc.scoring_modifiers || [],
      risk_factors: fc.risk_factors || [],
    });
  }
  setEditLoaded(true);
}, [isEditMode, currentStrategy, editLoaded, navigate]);
```

- [ ] **Step 3: 保存按钮区域**

替换现有的"保存策略"按钮（约第 335-337 行），改为根据模式显示不同按钮：

```typescript
{isEditMode ? (
  <>
    <Dropdown
      menu={{
        items: [
          {
            key: 'update',
            label: '更新策略',
            onClick: handleUpdate,
          },
          {
            key: 'saveAs',
            label: '另存为新策略',
            onClick: () => setSaveAsModalOpen(true),
          },
        ],
      }}
    >
      <Button type="primary" loading={loading}>
        保存 <DownOutlined />
      </Button>
    </Dropdown>
  </>
) : (
  <Button type="primary" onClick={handleSave} loading={loading}>
    保存策略
  </Button>
)}
```

需要在 imports 添加 `DownOutlined`。

- [ ] **Step 4: 更新策略逻辑**

在 `handleSave` 函数之后添加：

```typescript
// 编辑模式：更新策略
const handleUpdate = async () => {
  if (!strategyName.trim()) {
    message.warning('请输入策略名称');
    return;
  }
  if (!editId) return;
  setLoading(true);
  try {
    await updateFactorConfig(parseInt(editId, 10), factorConfig, {
      name: strategyName,
      description: strategyDesc,
    });
    message.success('策略更新成功！');
  } catch (err: unknown) {
    message.error((err as Error)?.message || '更新失败');
  } finally {
    setLoading(false);
  }
};

// 编辑模式：另存为新策略
const [saveAsModalOpen, setSaveAsModalOpen] = useState(false);
const [saveAsName, setSaveAsName] = useState('');

const handleSaveAs = async () => {
  if (!saveAsName.trim()) {
    message.warning('请输入新策略名称');
    return;
  }
  setLoading(true);
  try {
    const newStrategy = await createFromFactorConfig(
      factorConfig,
      saveAsName,
      strategyDesc,
    );
    message.success('新策略创建成功！');
    setSaveAsModalOpen(false);
    if (newStrategy) {
      navigate(`/strategies/${newStrategy.id}`);
    }
  } catch (err: unknown) {
    message.error((err as Error)?.message || '另存失败');
  } finally {
    setLoading(false);
  }
};
```

- [ ] **Step 5: 另存为 Modal**

在页面 JSX 末尾（`</>` 之前）添加 Modal：

```tsx
<Modal
  title="另存为新策略"
  open={saveAsModalOpen}
  onOk={handleSaveAs}
  onCancel={() => setSaveAsModalOpen(false)}
  confirmLoading={loading}
  okText="创建"
  cancelText="取消"
>
  <Input
    placeholder="请输入新策略名称"
    value={saveAsName}
    onChange={(e) => setSaveAsName(e.target.value)}
    style={{ marginTop: 16 }}
    defaultValue={strategyName ? `${strategyName} - 副本` : ''}
    onFocus={(e) => {
      if (!saveAsName && strategyName) {
        setSaveAsName(`${strategyName} - 副本`);
      }
    }}
  />
</Modal>
```

- [ ] **Step 6: 页面标题区分创建/编辑**

修改 `PageHeader`（约第 259-264 行）：

```tsx
<PageHeader
  title={isEditMode ? `编辑策略：${strategyName}` : '可视化构建策略'}
  breadcrumb={[
    { title: '策略管理', path: '/strategies' },
    ...(isEditMode
      ? [
          { title: strategyName || '策略详情', path: `/strategies/${editId}` },
          { title: '编辑' },
        ]
      : [{ title: '可视化构建' }]),
  ]}
/>
```

- [ ] **Step 7: 未保存提示**

在组件中添加 `beforeunload` 监听：

```typescript
// 未保存提示
const [isDirty, setIsDirty] = useState(false);

// 监听 factorConfig 变化（跳过首次编辑加载）
useEffect(() => {
  if (editLoaded) {
    setIsDirty(true);
  }
}, [factorConfig, strategyName, strategyDesc]);

useEffect(() => {
  const handler = (e: BeforeUnloadEvent) => {
    if (isDirty) {
      e.preventDefault();
      e.returnValue = '';
    }
  };
  window.addEventListener('beforeunload', handler);
  return () => window.removeEventListener('beforeunload', handler);
}, [isDirty]);
```

- [ ] **Step 8: 提交**

```bash
git add frontend/src/pages/StrategyBuilder.tsx
git commit -m "feat: add edit mode to StrategyBuilder with update/save-as"
```

---

### Task 4: 详情页和列表页入口变更

**Files:**
- Modify: `frontend/src/pages/StrategyDetail.tsx`
- Modify: `frontend/src/pages/StrategyList.tsx`

- [ ] **Step 1: StrategyDetail 编辑按钮**

修改第 101 行的编辑按钮，将导航目标改为 builder 并增加显隐条件：

```tsx
{/* 编辑按钮 — 仅标准信号策略可可视化编辑 */}
{isOwner && isVisualEditable(currentStrategy.factor_config) && (
  <Button icon={<EditOutlined />} onClick={() => navigate(`/strategies/builder?id=${currentStrategy.id}`)}>
    编辑
  </Button>
)}
```

在文件顶部 import 添加：

```typescript
import { isVisualEditable } from '@/types/strategy';
```

- [ ] **Step 2: StrategyList 编辑按钮**

修改第 238 行的编辑按钮：

```tsx
{isVisualEditable(record.factor_config) && (
  <Button type="link" size="small" onClick={() => navigate(`/strategies/builder?id=${record.id}`)}>
    编辑
  </Button>
)}
```

在文件顶部 import 添加：

```typescript
import { isVisualEditable } from '@/types/strategy';
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/StrategyDetail.tsx frontend/src/pages/StrategyList.tsx
git commit -m "feat: route edit buttons to visual builder, hide for AI strategies"
```

---

### Task 5: 清理废弃路由和页面

**Files:**
- Modify: `frontend/src/App.tsx`
- Delete: `frontend/src/pages/StrategyEdit.tsx`

- [ ] **Step 1: 移除路由**

在 `App.tsx` 中：

删除 import（第 8 行）：
```typescript
// 删除这一行
import StrategyEdit from '@/pages/StrategyEdit';
```

删除 `/strategies/new` 路由（第 87-94 行）：
```typescript
// 删除整个 Route
<Route
  path="/strategies/new"
  element={
    <ProtectedRoute>
      <StrategyEdit />
    </ProtectedRoute>
  }
/>
```

删除 `/strategies/:id/edit` 路由（第 119-126 行）：
```typescript
// 删除整个 Route
<Route
  path="/strategies/:id/edit"
  element={
    <ProtectedRoute>
      <StrategyEdit />
    </ProtectedRoute>
  }
/>
```

- [ ] **Step 2: 删除旧编辑页文件**

```bash
rm frontend/src/pages/StrategyEdit.tsx
```

- [ ] **Step 3: 检查其他引用**

运行检查确保没有遗漏的 `StrategyEdit` 引用：

```bash
grep -r "StrategyEdit\|/strategies/new\|/strategies/:id/edit" frontend/src/ --include="*.tsx" --include="*.ts"
```

应无输出（除已删除文件）。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/App.tsx
git rm frontend/src/pages/StrategyEdit.tsx 2>/dev/null || git add -u frontend/src/pages/StrategyEdit.tsx
git commit -m "feat: remove deprecated StrategyEdit page and routes"
```

---

### Task 6: 端到端验证

- [ ] **Step 1: 启动开发服务器**

```bash
cd frontend && npm run dev &
cd backend && source venv/bin/activate && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
```

- [ ] **Step 2: 验证创建流程未受影响**

1. 访问 `/strategies/builder`（无 `?id=`）
2. 确认空白创建模式正常：添加因子、设置参数、输入名称、保存
3. 确认新策略创建成功并跳转

- [ ] **Step 3: 验证编辑流程**

1. 进入一个标准策略的详情页
2. 点击"编辑"→ 应跳转到 `/strategies/builder?id=xxx`
3. 确认因子和参数已自动加载
4. 修改参数 → 点击"更新策略" → 确认保存成功
5. 修改参数 → 点击"另存为新策略" → 输入新名称 → 确认新策略创建

- [ ] **Step 4: 验证 AI 策略不显示编辑**

1. 查看 AI 参考选股策略详情页 → 不应出现编辑按钮
2. 策略列表中 AI 策略行 → 不应出现编辑按钮
3. 直接访问 `/strategies/builder?id=<AI策略ID>` → 应提示不支持并跳回列表

- [ ] **Step 5: 验证旧路由已移除**

1. 访问 `/strategies/:id/edit` → 应 404
2. 访问 `/strategies/new` → 应 404

- [ ] **Step 6: 运行现有测试确保无回归**

```bash
cd frontend && npm run build  # TypeScript 编译检查
cd backend && pytest
```

- [ ] **Step 7: 提交**

```bash
git commit -m "chore: verification complete, no regressions"
```
