# 重构规格：统一前端状态管理模式

**版本**: 1.0
**状态**: 草稿
**创建日期**: 2026-05-30
**最后更新**: 2026-05-30
**作者**: AI Assistant (基于 Code Review)
**优先级**: 🔴 P0 — 投入产出比最高

---

## 1. 背景与动机

当前前端有两种并存的数据管理模式：

| 模式 | 使用者 | 特点 |
|------|--------|------|
| **Zustand Store** | BacktestList, StrategyList, Dashboard, AIStrategyBuilder, 大部分页面 | 集中式状态、跨组件共享、action 封装 |
| **本地 useState + 直接调用 service** | BatchBacktestList, BacktestForm 部分逻辑 | 状态分散在组件内、无缓存、无法跨组件响应 |

这导致：
- 同一 app 内，开发者需要维护两套心智模型
- BatchBacktestList 无法享受 store 的数据缓存、自动重取、乐观更新
- 新功能不知道该用哪种模式，容易选错

### 目标

**所有数据获取和变更操作统一走 Zustand store。** 组件只负责渲染和触发 action，不直接调用 service。

---

## 2. 影响范围

### 2.1 需要改造的文件

| 文件 | 当前模式 | 改造内容 |
|------|----------|----------|
| `frontend/src/pages/BatchBacktestList.tsx` | useState + backtestService | 迁移到 `useBatchBacktestStore` |
| `frontend/src/pages/BacktestForm.tsx` | useState + backtestService | 提交逻辑移到 `useBacktestStore.submit()` |
| `frontend/src/pages/StrategyEdit.tsx` | useState + strategyService | 迁移到 `useStrategyStore` |
| `frontend/src/pages/StrategyUpload.tsx` | 直接调用 strategyService.upload | 迁移到 `useStrategyStore.uploadStrategy()` |
| `frontend/src/pages/UserManagement.tsx` | useState + userService | 迁移到 `useUserStore`（新增） |
| `frontend/src/stores/backtestStore.ts` | — | **扩展**：添加 batch backtest 相关 state 和 action |
| `frontend/src/stores/strategyStore.ts` | — | **扩展**：添加 upload、edit、code update action |
| `frontend/src/stores/userStore.ts` | — | **新增**：用户管理 state |

### 2.2 不需要改造的文件（已使用 store）

- `Dashboard.tsx` ✅ — 使用 authStore
- `StrategyList.tsx` ✅ — 使用 strategyStore
- `BacktestList.tsx` ✅ — 使用 backtestStore
- `AIStrategyBuilder.tsx` ✅ — 使用 aiStrategyStore
- `LoginPage.tsx` ✅ — 使用 authStore

---

## 3. 架构规范（改造后的目标形态）

### 3.1 Store 定义规范

每个 store 必须包含以下层次：

```typescript
// stores/xxxStore.ts
interface XxxState {
  // 数据
  items: Xxx[];
  total: number;
  currentItem: Xxx | null;

  // 加载状态
  loading: boolean;
  submitting: boolean;  // 提交/保存
  deleting: boolean;

  // 错误状态
  error: string | null;

  // 分页
  page: number;
  pageSize: number;
}

interface XxxActions {
  fetchList: (params?: QueryParams) => Promise<void>;
  fetchDetail: (id: number) => Promise<void>;
  create: (data: CreateXxx) => Promise<void>;
  update: (id: number, data: UpdateXxx) => Promise<void>;
  remove: (id: number) => Promise<void>;
  reset: () => void;
}
```

### 3.2 组件使用规范

```typescript
// ✅ 正确：组件通过 store hook 获取数据和 action
function MyPage() {
  const { items, loading, fetchList, remove } = useMyStore();

  useEffect(() => { fetchList(); }, []);

  return (
    <Table
      dataSource={items}
      loading={loading}
      // remove 由 store 内部处理后自动重取
    />
  );
}

// ❌ 错误：组件直接调用 service 和管理 useState
function MyPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    setLoading(true);
    myService.getList().then(setItems).finally(() => setLoading(false));
  }, []);
}
```

### 3.3 错误处理规范

Store 内的 service 调用统一 try/catch，设置 `error` 字段。组件通过 `error` 渲染错误状态，不自行 try/catch。

```typescript
fetchList: async (params) => {
  try {
    set({ loading: true, error: null });
    const res = await xxxService.getList(params);
    set({ items: res.data.items, total: res.data.total });
  } catch (e) {
    set({ error: e instanceof Error ? e.message : '加载失败' });
  } finally {
    set({ loading: false });
  }
}
```

### 3.4 乐观更新模式

删除操作优先使用乐观更新：

```typescript
remove: async (id) => {
  const prevItems = get().items;
  set({ items: prevItems.filter(i => i.id !== id) }); // 立即生效
  try {
    await xxxService.delete(id);
  } catch {
    set({ items: prevItems }); // 回滚
    set({ error: '删除失败，已恢复' });
  }
}
```

---

## 4. 实施步骤

### Step 1: 新增 `userStore.ts`

- 创建 `frontend/src/stores/userStore.ts`
- 包含 `fetchUsers`, `createUser`, `deleteUser`, `updateUserRole` action
- UserManagement 改为使用此 store

**预估**: 30 分钟

### Step 2: 扩展 `backtestStore.ts` 支持批量回测

- 新增 `batchItems`, `currentBatch`, `batchLoading` state
- 新增 `fetchBatchList`, `fetchBatchDetail`, `deleteBatchBacktest` action
- BatchBacktestList 改为使用 backtestStore

**预估**: 20 分钟

### Step 3: 扩展 `strategyStore.ts`

- 新增 `uploadStrategy`, `updateCode`, `downloadStrategy` action
- StrategyUpload, StrategyEdit 改为使用 strategyStore

**预估**: 20 分钟

### Step 4: BacktestForm 提交逻辑迁移

- `submitBacktest` action 添加到 backtestStore
- BacktestForm 解耦 service 直接调用

**预估**: 15 分钟

### Step 5: 删除不再需要的直接 service 调用

- 清理组件中残留的 `useState` + `useEffect` + service 直接调用模式
- 确保所有页面统一走 store

**预估**: 10 分钟

---

## 5. 验收标准

- [ ] `BatchBacktestList` 使用 `useBacktestStore` 而非 `useState` + 直接 service 调用
- [ ] `StrategyUpload` / `StrategyEdit` 使用 `useStrategyStore` 而非直接 service 调用
- [ ] `UserManagement` 使用新创建的 `useUserStore`
- [ ] `BacktestForm` 的提交逻辑在 store 内完成
- [ ] 全局搜索 `from.*services/.*Service` 在 pages/ 目录下的直接 import 应为 0
- [ ] 所有现有功能回归正常（策略 CRUD、回测提交/查看、用户管理）
- [ ] E2E 测试通过（`npm run test:e2e`）

---

## 6. 风险与注意事项

- **状态冲突**：多个页面同时操作 store 时可能互相影响 → 每个页面的 fetch 在 `useEffect` + 路由变化时触发，互不干扰
- **Store 膨胀**：backtestStore 可能变得过大 → 如果 state 字段超过 15 个，考虑拆分为 `backtestStore` + `batchBacktestSlice`
- **向后兼容**：所有改造是内部重构，不影响 API 接口和组件 props

---

**变更日志**:
- 2026-05-30: 初始版本创建（基于 Code Review 发现）
