# 仪表盘快捷操作重新设计 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan.

**Goal:** 仪表盘快捷操作增加图标和用途描述，移除快速入门

**Architecture:** 单文件改动，仅修改 `Dashboard.tsx` 的快捷操作区域

**Tech Stack:** React + TypeScript + Ant Design

---

### Task 1: 改造快捷操作区域

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: 替换快捷操作卡片内容**

将第 76-112 行替换为新的快捷操作区域（占满行、带图标和描述）。

具体改动：
1. `Col xs={24} lg={12}` → `Col span={24}`
2. 快捷操作数组从 `{label, path}` 扩展为 `{icon, title, description, path}`
3. 每个卡片渲染图标 + 标题 + 灰色描述文字
4. 移除右侧"快速入门"的 `<Col>` 和 `<Card>`

- [ ] **Step 2: 验证页面渲染**

```bash
cd frontend && npm run dev
```
访问 `/dashboard`，确认 4 个卡片显示图标、标题、描述，2x2 布局正常。

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd frontend && npm run build
```
确认无类型错误。
