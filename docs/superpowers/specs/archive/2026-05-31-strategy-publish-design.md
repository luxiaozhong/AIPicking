# 策略发布、评分和评论功能 — 设计文档

**日期:** 2026-05-31

---

## 1. 功能概述

新增策略"发布"功能，让用户可以将自己创建的策略公开。已发布策略对所有人可见且可用于回测，同时支持评分和评论互动。

## 2. 需求决策记录

| 维度 | 决定 |
|------|------|
| 发布流程 | 一键发布，无需管理员审核 |
| 策略列表 | 合并展示，增加筛选（全部 / 我的 / 已发布），默认全部 |
| 打分评论 | 五星评分（1-5）+ 单层文字评论 |
| 非创建者可见范围 | 基本信息 + 因子配置可见，**策略代码隐藏** |
| 评论权限 | 任何人可评论打分；策略创建者可删除自己策略下的不当评论 |
| 回测可见性 | 已发布策略的回测报告所有人可见；未发布策略仅创建者可见 |
| 策略删除 | 级联删除该策略的**所有**回测报告（不限用户） |

---

## 3. 数据库设计

### 3.1 Strategy 表修改

在 `strategies` 表新增字段：

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|------|------|--------|------|------|
| `is_published` | Boolean | `False` | NOT NULL | 策略发布状态 |

### 3.2 新增表：`strategy_ratings`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | Integer | PK, autoincrement | |
| `strategy_id` | Integer | FK → strategies.id ON DELETE CASCADE, NOT NULL | 关联策略 |
| `user_id` | Integer | FK → users.id, NOT NULL | 评分用户 |
| `score` | Integer | NOT NULL, CHECK(1 ≤ score ≤ 5) | 评分 |
| `created_at` | DateTime | NOT NULL | |
| `updated_at` | DateTime | NOT NULL | |

**唯一约束:** `(strategy_id, user_id)` — 每用户每策略仅一条评分，再次提交即为更新。

### 3.3 新增表：`strategy_comments`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | Integer | PK, autoincrement | |
| `strategy_id` | Integer | FK → strategies.id ON DELETE CASCADE, NOT NULL | 关联策略 |
| `user_id` | Integer | FK → users.id, NOT NULL | 评论用户 |
| `content` | Text | NOT NULL | 评论内容 |
| `created_at` | DateTime | NOT NULL | |
| `updated_at` | DateTime | NOT NULL | |

### 3.4 ER 关系

```
users ────< strategies ────< strategy_ratings
   │            │
   │            ├────< strategy_comments
   │            │
   ├───< backtest_reports
   ├───< batch_backtest_reports
   └───< strategy_runs
```

---

## 4. 后端 API 设计

### 4.1 策略发布

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| `PUT` | `/strategies/{id}/publish` | 发布策略 | 策略创建者 |
| `PUT` | `/strategies/{id}/unpublish` | 取消发布 | 策略创建者 |

### 4.2 策略列表

| 方法 | 路径 | 参数 | 说明 |
|------|------|------|------|
| `GET` | `/strategies` | `scope` (新增) | 筛选范围 |

**`scope` 参数逻辑（非 admin）：**

| scope 值 | 返回内容 |
|----------|----------|
| `all`（默认） | 自己的全部策略 + 别人已发布的策略 |
| `mine` | 仅自己创建的 |
| `published` | 仅别人发布的 |

Admin 不受 `scope` 限制，始终看到所有策略。

### 4.3 策略详情 — 权限控制

非创建者对已发布策略的权限矩阵：

| 操作 | 允许 | 说明 |
|------|:--:|------|
| 查看基本信息 | ✅ | 名称、描述、标签、状态、版本、创建者 |
| 查看因子配置 | ✅ | factor_config 字段 |
| 查看策略代码 | ❌ | generated_code / file_path 隐藏 |
| 编辑/删除策略 | ❌ | 403 |
| 发布/取消发布 | ❌ | 403 |
| 跑回测 | ✅ | 正常执行 |

### 4.4 评分 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/strategies/{id}/ratings` | 提交/更新评分，body: `{score: int 1-5}` |
| `GET` | `/strategies/{id}/ratings` | 获取评分统计（平均分、各星级人数、当前用户评分） |

### 4.5 评论 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/strategies/{id}/comments` | 发表评论，body: `{content: str}` |
| `GET` | `/strategies/{id}/comments` | 获取评论列表（分页），含用户信息 |
| `DELETE` | `/strategies/{id}/comments/{comment_id}` | 删除评论（评论作者 或 策略创建者） |

### 4.6 回测可见性修改

**核心规则：** 回测报告可见性由其关联策略的 `is_published` 状态决定。

| 策略状态 | 回测可见性 |
|----------|-----------|
| `is_published == true` | 所有人可见（不管回测是谁跑的） |
| `is_published == false` | 仅回测执行者本人可见 |

**实现方式：**

回测列表和详情的查询逻辑修改为：

```python
# 非 admin 用户可见的回测：
# 自己的回测 OR 关联策略已发布的回测
query = query.join(Strategy).where(
    (BacktestReport.user_id == user_id) |
    (Strategy.is_published == True)
)
```

回测响应增加 `backtest_user_name` 字段，标识回测执行者。

**策略删除级联：** 保持不变，`permanent_delete_strategy` 按 `strategy_id` 删除全部回测（已是现有行为）。

---

## 5. 前端设计

### 5.1 策略列表页改造

**文件:** `frontend/src/pages/StrategyList.tsx`

变更点：
- 新增 `scope` 筛选器：全部 / 我的 / 已发布（替代原有隐藏逻辑）
- 新增列：**发布状态**（`已发布` / `私密` Tag）、**评分**（⭐ 均分）
- 操作列权限区分：
  - 自己的策略：查看 / 编辑 / 删除 / 发布开关
  - 别人的已发布策略：查看 / 回测
- 非创建者看到"回测"按钮跳转到回测表单页

### 5.2 策略详情页改造

已发布策略对非创建者：
- 基本信息 + 因子配置 → 正常展示
- 代码区 → 隐藏，显示占位文案："代码仅对创建者可见"
- 页面底部新增评分 & 评论区

### 5.3 评分 & 评论区

```
┌──────────────────────────────────────┐
│  ⭐ 平均 4.2（32 人评分）              │
│  [★★★★☆]  ← 当前用户评分（可点击）    │
├──────────────────────────────────────┤
│  评论 (15)                            │
│  ┌────────────────────────────────┐   │
│  │ 用户A · ⭐4  · 2小时前         │   │
│  │ 这个策略在震荡市表现不错         │   │
│  │                           [× 删除]│  │ ← 仅策略所有者可见
│  ├────────────────────────────────┤   │
│  │ 用户B · ⭐5  · 1天前           │   │
│  │ 简单好用，回测收益很稳           │   │
│  └────────────────────────────────┘   │
│  ┌────────────────────────────────┐   │
│  │  [输入评论...]         [提交]   │   │
│  └────────────────────────────────┘   │
└──────────────────────────────────────┘
```

### 5.4 前端服务层

`strategyService.ts` 新增方法：

```typescript
publishStrategy(id: number): Promise<void>
unpublishStrategy(id: number): Promise<void>
rateStrategy(id: number, score: number): Promise<void>
getStrategyRatings(id: number): Promise<RatingsData>
addComment(id: number, content: string): Promise<void>
getComments(id: number, page: number): Promise<CommentList>
deleteComment(strategyId: number, commentId: number): Promise<void>
```

`strategyStore.ts` 新增 actions：发布/取消发布、评分、评论管理。

---

## 6. 数据迁移

新建 `backend/migrate_add_publish.py`：

1. `ALTER TABLE strategies ADD COLUMN is_published BOOLEAN DEFAULT FALSE`
2. `CREATE TABLE strategy_ratings (...)`
3. `CREATE TABLE strategy_comments (...)`

向后兼容：现有策略全部 `is_published = False`。

---

## 7. 测试计划

### 7.1 后端测试

| 测试场景 | 关键断言 |
|---------|----------|
| 发布流程 | 创建者发布/取消发布成功(200)；非创建者返回 403 |
| 列表 scope | `mine` 仅自己的；`published` 仅别人已发布的；`all` 合并两者 |
| 列表 admin | admin 始终看到全部策略 |
| 详情权限 | 非创建者看不到代码；因子配置可见 |
| 修改权限 | 非创建者编辑/删除已发布策略返回 403 |
| 回测权限 | 非创建者可用已发布策略跑回测 |
| 回测可见性 | 已发布策略的回测所有人可见；未发布仅执行者可见 |
| 回测删除级联 | 删除策略时关联回测全部删除 |
| 评分 CRUD | 提交/更新评分；获取统计；唯一约束 |
| 评论 CRUD | 发表；列表；评论作者可删除；策略所有者可删除；他人删评论 403 |

### 7.2 前端 E2E 测试

| 测试场景 |
|---------|
| scope 筛选器切换 |
| 非创建者操作列仅显示"查看"+"回测" |
| 已发布策略详情：代码隐藏、因子配置可见 |
| 评分组件交互 |
| 评论发表、分页、删除 |

---

## 8. 实现清单

- [ ] 数据库迁移脚本
- [ ] 策略模型 + `is_published` 字段
- [ ] 评分/评论模型
- [ ] 策略发布/取消发布 API
- [ ] 策略列表 scope 筛选
- [ ] 策略详情权限控制（隐藏代码）
- [ ] 评分 API（提交 + 统计）
- [ ] 评论 API（发表 + 列表 + 删除）
- [ ] 回测列表/详情可见性修改
- [ ] 回测响应增加执行者名称
- [ ] 前端：策略列表页改造
- [ ] 前端：策略详情页改造
- [ ] 前端：评分评论组件
- [ ] 前端：strategyService 新增方法
- [ ] 前端：strategyStore 新增 actions
- [ ] 后端测试
- [ ] 前端 E2E 测试
