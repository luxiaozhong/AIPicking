# 重构规格：统一加载/空/错误状态

**版本**: 1.0
**状态**: 草稿
**创建日期**: 2026-05-30
**最后更新**: 2026-05-30
**作者**: AI Assistant (基于 Code Review)
**优先级**: 🟡 P1 — 显著改善用户体验一致性

---

## 1. 背景与动机

当前应用中，不同页面使用不同的 UI 模式处理加载、空数据、错误三种状态：

| 状态 | BacktestForm | BacktestDetail | EducationPage | StrategyEdit | 其他页面 |
|------|-------------|---------------|---------------|-------------|---------|
| **加载中** | `<Spin>` 居中 | `<LoadingSkeleton>` | `<Spin>` 居中 | **无加载态** | 各不同 |
| **空数据** | `<Empty>` 内联 | `<Empty>` 内联 | `<Empty>` 内联 | 无 | 各不同 |
| **错误** | message.error | message.error | 无 | 无 | 各不同 |

这导致：
- 用户看到不一致的视觉反馈，降低信任感
- `EmptyState` 和 `LoadingSkeleton` 已写好但几乎没被使用
- `StrategyEdit` 在数据加载期间显示空白表单，用户可能误填

### 目标

**每个页面在加载/空/错误三种状态上保持一致的用户体验。** 充分利用已有的共享组件。

---

## 2. 现状分析

### 2.1 已有共享组件

| 组件 | 文件 | 当前使用情况 |
|------|------|-------------|
| `LoadingSkeleton` | [frontend/src/components/shared/LoadingSkeleton.tsx](frontend/src/components/shared/LoadingSkeleton.tsx) | 仅 BacktestDetail 使用 |
| `EmptyState` | [frontend/src/components/shared/EmptyState.tsx](frontend/src/components/shared/EmptyState.tsx) | **无页面使用**（死代码） |

### 2.2 页面现状清单

| 页面 | 加载态 | 空态 | 错误态 |
|------|--------|------|--------|
| Dashboard | ✅ 无加载（本地数据） | N/A | ❌ 缺失 |
| StrategyList | ✅ Spin | ✅ Empty | ❌ 缺失 |
| StrategyBuilder | N/A（本地编辑） | ✅ Empty | ❌ 缺失 |
| AIStrategyBuilder | ✅ Spin + 文案 | ✅ Empty | ✅ Alert |
| BacktestList | ✅ Spin | ✅ Empty | ❌ 缺失 |
| BacktestDetail | ✅ LoadingSkeleton | ❌ 缺失 | ❌ 缺失 |
| BacktestForm | ✅ Spin 居中 | ❌ 缺失 | ❌ 缺失 |
| BatchBacktestList | ✅ Spin | ✅ Empty | ❌ 缺失 |
| BatchBacktestDetail | ✅ Spin | ❌ 缺失 | ❌ 缺失 |
| StrategyDetail | ✅ Spin | ❌ 缺失 | ❌ 缺失 |
| StrategyEdit | ❌ **无加载态** | ❌ 缺失 | ❌ 缺失 |
| StrategyUpload | N/A | N/A | ❌ 缺失 |
| EducationPage | ✅ Spin 居中 | ✅ Empty | ❌ 缺失 |
| EducationDetailPage | ✅ Spin | ❌ 缺失 | ❌ 缺失 |
| LoginPage | ✅ Button loading | ❌ 缺失 | ✅ message.error |
| UserManagement | ✅ Spin | ✅ Empty | ❌ 缺失 |
| NotFound | N/A | N/A | N/A |

**统计**: 11/16 页面缺少错误状态，3 个详情页缺少空状态，StrategyEdit 缺少加载态。

---

## 3. 设计规范

### 3.1 加载状态

**原则**：内容型页面用 Skeleton，操作型页面/弹窗用 Spin。

```
┌─ 内容型页面（列表、详情）──→ LoadingSkeleton
│   - 列表：N 行骨架卡片
│   - 详情：详情骨架（标题 + 卡片 + 表格）
│
└─ 操作型（表单提交、短时查询）──→ Spin（居中或内嵌按钮）
    - 页面级加载：居中 Spin
    - 按钮级加载：Button loading={true}
```

**`LoadingSkeleton` 需要扩展**：
- 当前只有 `type="detail"`，需新增 `type="list"`、`type="card-grid"`

```typescript
// LoadingSkeleton.tsx 扩展后的 props
interface LoadingSkeletonProps {
  type: 'detail' | 'list' | 'card-grid' | 'form';
  rows?: number; // list 模式下的行数，默认 5
  cols?: number; // card-grid 模式下的列数，默认 3
}
```

### 3.2 空状态

**原则**：一律使用 `EmptyState` 共享组件，不再内联 `<Empty>`。

`EmptyState` 需增强为可操作的空状态：

```typescript
interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  actionText?: string;      // 按钮文案
  onAction?: () => void;    // 按钮回调
  type?: 'default' | 'search' | 'filter';  // 不同场景预设
}
```

页面中统一用法：
```tsx
// ❌ 旧模式
<Empty description="还没有策略" />

// ✅ 新模式
<EmptyState
  type="search"
  title="还没有策略"
  description="创建你的第一个量化策略，开始回测验证"
  actionText="创建策略"
  onAction={() => navigate('/strategies/builder')}
/>
```

### 3.3 错误状态

**原则**：每个数据获取路径都应有 error 处理。新增 `ErrorState` 共享组件。

```typescript
// components/shared/ErrorState.tsx（新增）
interface ErrorStateProps {
  message?: string;
  detail?: string;
  onRetry?: () => void;
  onBack?: () => void;
}
```

渲染效果：
```
┌─────────────────────────────────────────┐
│              ⚠️                          │
│        数据加载失败                       │
│    网络连接异常，请检查网络后重试          │
│                                          │
│        [重试]  [返回首页]                │
└─────────────────────────────────────────┘
```

页面中统一用法：
```tsx
if (error) {
  return <ErrorState message={error} onRetry={() => fetchList()} />;
}
```

### 3.4 状态优先级

页面内三种状态的渲染优先级：

```
if (error)      → <ErrorState />
if (loading)    → <LoadingSkeleton />
if (empty)      → <EmptyState />
                 → <Content />
```

---

## 4. 实施步骤

### Step 1: 增强 `LoadingSkeleton`

- 添加 `type="list"` 渲染表格骨架行
- 添加 `type="card-grid"` 渲染卡片骨架
- 文件：[frontend/src/components/shared/LoadingSkeleton.tsx](frontend/src/components/shared/LoadingSkeleton.tsx)

**预估**: 20 分钟

### Step 2: 增强 `EmptyState` 并推广

- 添加 `actionText` / `onAction` / `type` props
- 替换所有页面中的内联 `<Empty>` 为 `<EmptyState>`
- 所有空状态提供引导性操作按钮

**预估**: 30 分钟

### Step 3: 新增 `ErrorState` 组件

- 创建 `frontend/src/components/shared/ErrorState.tsx`
- 渲染错误图标 + 消息 + 重试按钮
- 支持区分错误类型（网络错误 / 服务端错误 / 权限错误）

**预估**: 20 分钟

### Step 4: 逐页添加错误处理

- 在所有使用 store/service 的页面添加 `error` 状态渲染
- 11 个缺少错误状态的页面逐一补全

**预估**: 40 分钟

### Step 5: 修复 StrategyEdit 加载态

- 添加 `LoadingSkeleton type="form"` 在数据加载期间显示
- 防止用户在空白表单上误操作

**预估**: 10 分钟

---

## 5. 验收标准

- [ ] `LoadingSkeleton` 支持 `list`、`card-grid`、`detail`、`form` 四种类型
- [ ] `EmptyState` 被所有页面使用，无内联 `<Empty>` 残留
- [ ] `ErrorState` 被所有数据获取页面使用
- [ ] 所有页面按 `error → loading → empty → content` 优先级渲染
- [ ] `StrategyEdit` 有加载态
- [ ] E2E 测试通过（`npm run test:e2e`）

---

## 6. 原则总结

| 状态 | 用什么 | 何时用 |
|------|--------|--------|
| 加载中 | `<LoadingSkeleton type="..." />` | 首次数据加载 |
| 加载中（操作） | `<Spin />` 或 `Button loading` | 提交、刷新等操作 |
| 空数据 | `<EmptyState />` | 列表/表格无数据 |
| 错误 | `<ErrorState />` | 网络异常、服务端错误 |
| 全部正常 | `<Content />` | 渲染实际内容 |

---

**变更日志**:
- 2026-05-30: 初始版本创建（基于 Code Review 发现）
