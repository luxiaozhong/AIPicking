# 策略教育功能 — 设计文档

**日期**: 2026-05-29  
**状态**: 待实现  
**分阶段**: Phase 1（文章）→ Phase 2（交互示例）

---

## 概述

新增「学习中心」模块，提供策略相关的教程、案例分析和平台操作指南，帮助用户理解和应用策略。

## 内容管理

### 存储方式

文章以 Markdown 文件存储在 `backend/content/education/`，按分类建子目录，`index.yaml` 定义分类元数据。

```
backend/content/education/
├── indicators/              # 指标讲解
│   ├── macd.md
│   ├── rsi.md
│   └── kdj.md
├── strategies/              # 策略案例
│   ├── breakout.md
│   └── ma-cross.md
├── guides/                  # 平台操作指南
│   ├── create-strategy.md
│   └── run-backtest.md
└── index.yaml               # 分类定义 + 排序
```

### Frontmatter 规范

```yaml
---
title: "MACD 指标详解"
category: indicators
tags: ["macd", "momentum", "入门"]
difficulty: 入门
order: 1
---
```

### index.yaml 规范

```yaml
categories:
  - key: indicators
    label: 指标讲解
    icon: LineChartOutlined
    order: 1
  - key: strategies
    label: 策略案例
    icon: BulbOutlined
    order: 2
  - key: guides
    label: 平台操作指南
    icon: BookOutlined
    order: 3
```

## 后端 API

### 新文件

- `app/api/education.py` — 路由
- `app/services/education_service.py` — 文件读取 + frontmatter 解析 + 内存缓存

### 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/education/categories` | 返回分类列表（从 index.yaml 读取） |
| GET | `/api/v1/education/articles?category=indicators` | 文章列表（不含正文），可按分类筛选 |
| GET | `/api/v1/education/articles/{slug}` | 单篇文章完整内容（元数据 + markdown 正文） |

文章 `slug` 由文件名决定：`macd.md` → slug 为 `macd`。同一 slug 在不同分类下不冲突（通过 `category` 路径区分）。

### 启动行为

服务启动时扫描 `content/education/` 目录，解析所有 `.md` 文件的 frontmatter，缓存到内存。

### 错误处理

- `.md` 文件解析失败 → log warning，跳过该文件，不影响其他文章
- `index.yaml` 不存在 → 按目录名自动生成默认分类
- 文章 slug 不存在 → 返回 404

## 前端

### 新页面

- `/education` — 学习中心首页，按分类浏览文章
- `/education/:category/:slug` — 文章详情页

### 组件树

```
EducationPage
├── CategoryTabs          # 分类 Tab 切换
└── ArticleCard           # 文章卡片（标题、摘要、难度标签）

EducationDetailPage
├── ArticleToc            # 右侧目录导航（从 headings 提取）
├── ArticleContent        # Markdown 渲染正文
└── InteractiveSlot       # 预留交互组件插槽（Phase 2）
```

### 数据流

前端 `educationService.ts` → REST API → Backend EducationService → 文件系统

不新增 Zustand store（数据量小，无跨页面共享状态）。

### 依赖

- `react-markdown` + `remark-gfm` — Markdown 渲染
- `react-syntax-highlighter` — 代码块高亮
- Ant Design `Card`, `Tabs`, `Tag`, `Anchor`, `Empty`

### 导航变更

侧边栏 `AppLayout.tsx` 新增「学习中心」菜单项（`ReadOutlined`），路由 `/education`，放在仪表盘和策略管理之间。

### 错误处理

- 文章不存在 → 现有一致的 NotFound 风格
- Markdown 渲染异常 → 降级显示原始文本
- 分类下无文章 → 空状态提示
- 安全：react-markdown 默认 sanitize HTML，无需额外处理

### 性能

文章 < 50 篇，后端全量内存缓存，前端无需分页或懒加载。

## Phase 2 展望

- 文章内嵌入交互组件（图表参数调节等），预留 `InteractiveSlot` 插槽
- 通过 MDX 或自定义标记扩展 Markdown 语法
- 搜索功能

## 不在范围

- AI 动态生成内容
- 用户共创/投稿
- 视频嵌入
- 后台管理 UI（手动编辑 .md 文件即可）
