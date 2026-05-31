# 重构规格：StrategyBuilder 交互对齐 — 拖拽或文案修正

**版本**: 1.0
**状态**: 草稿
**创建日期**: 2026-05-30
**最后更新**: 2026-05-30
**作者**: AI Assistant (基于 Code Review)
**优先级**: 🟢 P2 — UX 一致性改进

---

## 1. 背景与动机

### 问题描述

StrategyBuilder（可视化构建器）声称支持"拖拽"添加因子，但实际是"点击"添加：

| 位置 | 文案/行为 | 实际情况 |
|------|----------|----------|
| 新用户引导 Tour | "通过拖拽技术因子到右侧画布来构建你的量化策略" | 不支持拖拽 |
| FactorLibrary 左侧面板 | 鼠标 hover 显示 pointer cursor | 只能点击添加 |
| StrategyBuilder UI | 因子以卡片形式出现在画布 | 卡片不可拖拽排序 |
| 因子删除 | 卡片上的删除按钮 | 不能拖出画布删除 |

用户期望与实际行为不匹配，造成困惑。

### 两种解决方案

| 方案 | 描述 | 工作量 | 体验提升 |
|------|------|--------|----------|
| **A: 实现真拖拽** | 使用 `@dnd-kit` 实现拖拽添加 + 排序 + 删除 | 4-6 小时 | ⭐⭐⭐⭐⭐ |
| **B: 修正文案** | 更新 Tour 和 UI 文案为 "点击添加"，保持当前交互 | 0.5 小时 | ⭐⭐ |

---

## 2. 方案 A：实现真拖拽（推荐，如果资源允许）

### 2.1 交互设计

```
┌─────────────────────────────────────────────────┐
│  FactorLibrary (左侧)       StrategyCanvas (右侧) │
│                                                  │
│  ┌─ 趋势类 ─┐                                    │
│  │ MA金叉   │──── 拖拽 ────→  ┌─────────────┐   │
│  │ 均线支撑  │                │ 买入信号 (AND)│   │
│  │ 突破新高  │                │ ┌─MA金叉──┐  │   │
│  └──────────┘                │ │ [配置]  │  │   │
│  ┌─ 动量类 ─┐                │ └─────────┘  │   │
│  │ MACD    │                │ ┌─RSI──────┐  │   │
│  │ RSI     │──→            │ │ [配置]  │  │   │
│  └──────────┘                │ └─────────┘  │   │
│                              └─────────────┘   │
│                              ┌─────────────┐   │
│                              │ 卖出信号 (OR) │   │
│                              │ ┌─固定止损──┐ │   │
│                              │ └───────────┘ │   │
│                              └─────────────┘   │
│                              ┌─────────────┐   │
│                              │ 风控因子      │   │
│                              │ (拖到此处)    │   │  ← drop zone
│                              └─────────────┘   │
└─────────────────────────────────────────────────┘
```

### 2.2 拖拽行为

| 操作 | 交互 |
|------|------|
| **从左侧拖到右侧** | 将因子添加到画布，根据 drop zone 自动归类（买入/卖出/风控） |
| **在画布内拖拽** | 调整因子顺序（影响 AND/OR 评估顺序） |
| **在买入/卖出区之间拖拽** | 移动因子到不同信号组 |
| **拖出画布** | 删除因子（或拖到画布外的垃圾桶区域） |
| **双击** | 展开/折叠因子配置面板 |

### 2.3 技术选型

推荐使用 **`@dnd-kit/core` + `@dnd-kit/sortable`**：

- 轻量（~15KB gzipped）
- React 原生支持，无 jQuery 依赖
- 支持键盘无障碍操作
- 排序动画流畅
- 活跃维护（与 React 18 兼容）

### 2.4 实施步骤

#### Step 1: 安装依赖

```bash
cd frontend && npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities
```

**预估**: 5 分钟

#### Step 2: 改造 FactorCard 为可拖拽

- 用 `useSortable` 包裹 FactorCard
- 添加 drag handle 图标（⠿ 或 拖拽手柄）
- 保留点击展开配置的交互

**预估**: 30 分钟

**文件**: [frontend/src/components/builder/FactorCard.tsx](frontend/src/components/builder/FactorCard.tsx)

#### Step 3: 改造 StrategyCanvas 为 drop 区域

- 用 `DndContext` + `SortableContext` 包裹画布
- 定义 3 个 DropZone：buySignals、sellSignals、riskFactors
- 实现 onDragEnd 处理：添加/移动/删除因子

**预估**: 45 分钟

**文件**: [frontend/src/pages/StrategyBuilder.tsx](frontend/src/pages/StrategyBuilder.tsx)

#### Step 4: 改造 FactorLibrary 为 drag source

- 因子列表项注册为可拖拽源
- 拖拽时显示因子名称的 drag overlay
- 保留点击添加作为辅助方式（无障碍兼容）

**预估**: 30 分钟

**文件**: [frontend/src/components/builder/FactorLibrary.tsx](frontend/src/components/builder/FactorLibrary.tsx)

#### Step 5: 更新 Onboarding Tour

- 将 Tour 步骤中的"拖拽"描述与真实交互对齐
- 添加拖拽操作的视觉示意

**预估**: 15 分钟

#### Step 6: E2E 测试更新

- 更新 `strategy-builder.spec.ts` 中的交互断言
- 添加拖拽操作的 E2E 测试

**预估**: 20 分钟

### 2.5 验收标准（方案 A）

- [ ] 因子可以从左侧拖拽到右侧画布的对应区域（买入/卖出/风控）
- [ ] 因子在画布内可以拖拽排序
- [ ] 因子可以拖出画布删除（或拖到垃圾桶区域）
- [ ] 点击添加仍然可用（辅助交互）
- [ ] 键盘操作可用（Tab 导航 + Enter 添加）
- [ ] Tour 描述与实际交互一致
- [ ] E2E 测试通过

---

## 3. 方案 B：修正文案（快速方案）

### 3.1 修改内容

只需要修改 3 处文案：

| 文件 | 位置 | 修改 |
|------|------|------|
| [frontend/src/components/OnboardingWalkthrough.tsx](frontend/src/components/OnboardingWalkthrough.tsx) | Tour 步骤 3 的描述 | "通过拖拽技术因子" → "通过点击左侧因子库中的技术因子" |
| [frontend/src/pages/StrategyBuilder.tsx](frontend/src/pages/StrategyBuilder.tsx) | FactorLibrary 区域的标题或提示 | 添加提示文字 "点击因子添加到画布" |
| [frontend/src/components/builder/FactorLibrary.tsx](frontend/src/components/builder/FactorLibrary.tsx) | 因子的 tooltip | 添加 "点击添加" tooltip |

### 3.2 验收标准（方案 B）

- [ ] Tour 不再提及"拖拽"
- [ ] 左侧因子库有"点击添加"的引导文案
- [ ] 用户不会期望拖拽功能

---

## 4. 方案对比

| 维度 | 方案 A（真拖拽） | 方案 B（修文案） |
|------|-----------------|-------------------|
| 工作量 | 2-3 小时 | 15 分钟 |
| 用户体验 | ⭐⭐⭐⭐⭐ 直观、高效 | ⭐⭐ 可用但平淡 |
| 维护成本 | 新增 dnd-kit 依赖 | 无 |
| 差异化竞争力 | 强（竞品少有） | 弱 |
| 适合阶段 | 有充足时间打磨时 | 快速消除误导 |

---

## 5. 建议

**建议先实施方案 B（立即修文案消除误导），再在后续迭代中实施方案 A（实现真拖拽）。**

这样可以：
1. 立即消除用户体验落差
2. 不影响后续拖拽功能的开发
3. 方案 A 的规格可以保留作为后续迭代的需求

---

**变更日志**:
- 2026-05-30: 初始版本创建（基于 Code Review 发现）
