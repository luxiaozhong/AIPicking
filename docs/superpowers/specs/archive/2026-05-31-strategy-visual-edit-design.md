# 策略可视化编辑 — 设计文档

**日期**: 2026-05-31
**状态**: 待审批

## 背景

当前策略编辑页 (`StrategyEdit.tsx`) 只提供 Monaco 代码编辑器，无法查看或修改策略的因子配置和参数。用户在可视化构建器创建策略后，编辑时只能看到自动生成的 Python 代码，无法直观地调整因子组合。

代码上传型功能已废弃，所有策略均为因子配置型，都存储了 `factor_config` JSON 数据。

## 目标

让已有策略能够通过可视化构建器编辑因子和参数，实现"创建即编辑"的一致体验。

## 范围

- **支持**: 通过可视化构建器创建的标准策略、通过自然语言生成的策略
- **不支持**: AI 参考选股策略（使用动态生成因子 + 相似度匹配，结构不同）

---

## 设计

### 1. 入口变更

**策略详情页 (`StrategyDetail.tsx`)：**
- 标准策略 / NL 生成策略："编辑"按钮 → 跳转 `/strategies/builder?id={strategyId}`
- AI 参考选股策略：隐藏编辑按钮
  - 判断依据：检查 `factor_config` 是否包含 `buy_signals` / `sell_signals` 结构

**策略构建器页 (`StrategyBuilder.tsx`)：**
- 无 `?id=` 参数：空白创建模式（现有行为）
- 有 `?id=` 参数：编辑模式
  - 加载策略 `factor_config` + 元数据（名称、描述、标签）
  - 页面标题变为"编辑策略：{策略名称}"
  - 5 个区域自动填充已有配置

**旧编辑页 (`StrategyEdit.tsx`)：**
- 删除该页面及其路由 `/strategies/:id/edit`
- 列表页等引用该路由的地方改为 `/strategies/builder?id=xxx`

### 2. 编辑模式数据流

```
?id=xxx 存在
  → useEffect 调用 fetchStrategy(xxx)
  → 从 currentStrategy.factor_config 解析 JSON
  → 填充到构建器 5 个区域：
      selectionConditions / scoringModifiers / buySignals / sellSignals / riskFactors
  → 填充策略名称、描述到顶部表单
```

**类型补充**：前端 `Strategy` 接口需添加 `factor_config?: FactorConfig` 字段。

### 3. 保存行为

编辑模式底部显示两个保存按钮：

| 按钮 | 行为 |
|------|------|
| **更新策略** | 调用 `PUT /strategies/:id/factors` → 更新 `factor_config` → 重新生成代码 → 版本号 +1 → 留在当前页 |
| **另存为新策略** | 弹出 Modal 输入新名称（预填"原名称 - 副本"）→ 调用 `POST /strategies` → 跳转到新策略详情页 |

两种保存均同时更新名称、描述、标签（如有修改）。

### 4. 边界情况

| 场景 | 处理 |
|------|------|
| AI 参考选股策略直接访问 `?id=xxx` | 页面检测到不支持的结构，显示"该策略不支持可视化编辑"，提供返回链接 |
| 加载中 | 构建器显示 Loading 状态 |
| 加载失败 | 显示错误提示 + "返回策略列表"按钮 |
| `factor_config` 为空 | 以空白模式打开，顶部提示"策略配置为空，请添加因子" |
| 有修改但未保存就离开 | `beforeunload` 事件 + 路由守卫提示用户 |

### 5. Store 新增方法

**`strategyStore.ts`：**
```typescript
// 更新策略因子配置（重新生成代码）
updateFactorConfig: (id: number, config: FactorConfig, meta?: {...}) => Promise<void>

// 基于因子配置创建新策略（另存为）
createFromFactorConfig: (config: FactorConfig, name: string, description?: string) => Promise<Strategy>
```

---

## 涉及文件

### 前端
| 文件 | 改动 |
|------|------|
| `frontend/src/pages/StrategyBuilder.tsx` | 新增编辑模式（`?id=` 参数加载、保存 UI） |
| `frontend/src/pages/StrategyDetail.tsx` | 编辑按钮改跳转、AI 策略隐藏按钮 |
| `frontend/src/pages/StrategyEdit.tsx` | 删除 |
| `frontend/src/App.tsx` | 移除 `/strategies/:id/edit` 路由 |
| `frontend/src/stores/strategyStore.ts` | 新增 `updateFactorConfig`、`createFromFactorConfig` |
| `frontend/src/types/strategy.ts` | `Strategy` 接口添加 `factor_config` 字段 |
| `frontend/src/services/strategyService.ts` | 新增 `updateFactorConfig` API 调用 |

### 后端
无需改动（现有 API 已覆盖所有需求）。

---

## 参考

- 现有 `PUT /strategies/:id/factors` — 更新因子配置并重新生成代码
- 现有 `POST /strategies` — 创建新策略（body 含 `factor_config`）
- 现有 `GET /strategies/:id` — 返回 `data.factor_config` + `code_content`
