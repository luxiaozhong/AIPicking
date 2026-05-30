# 策略教育功能（学习中心）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「学习中心」模块，提供策略教程/案例分析/操作指南，文章以 Markdown 文件存储，后端解析 frontmatter 并缓存，前端渲染展示

**Architecture:** 后端新增 `education_service.py` + `education.py` 路由，启动时扫描 `content/education/` 目录解析 .md 文件 frontmatter 到内存缓存。前端新增两个页面（列表 + 详情），通过 `educationService.ts` 调用 API，用 `react-markdown` 渲染文章

**Tech Stack:** FastAPI + pyyaml（解析 frontmatter）、React + react-markdown + remark-gfm + react-syntax-highlighter

---

### Task 1: 创建示例内容文件

**Files:**
- Create: `backend/content/education/index.yaml`
- Create: `backend/content/education/indicators/macd.md`
- Create: `backend/content/education/strategies/breakout.md`
- Create: `backend/content/education/guides/create-strategy.md`

- [ ] **Step 1: 创建 index.yaml**

```bash
mkdir -p backend/content/education/{indicators,strategies,guides}
```

- [ ] **Step 2: 写入 index.yaml**

File: `backend/content/education/index.yaml`

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
    label: 操作指南
    icon: BookOutlined
    order: 3
```

- [ ] **Step 3: 写入示例文章 macd.md**

File: `backend/content/education/indicators/macd.md`

```markdown
---
title: "MACD 指标详解"
category: indicators
tags: ["macd", "动量", "入门"]
difficulty: 入门
order: 1
---

## MACD 是什么？

MACD（Moving Average Convergence Divergence，指数平滑异同移动平均线）是一种趋势跟踪动量指标，由 Gerald Appel 在 1970 年代提出。

## MACD 的构成

MACD 由三条线组成：

- **DIF（快线）**：12 日 EMA - 26 日 EMA
- **DEA（慢线/信号线）**：DIF 的 9 日 EMA
- **柱状图（MACD 柱）**：DIF - DEA

## 基本用法

### 金叉买入信号

当 DIF 线从下方向上穿过 DEA 线时，形成「金叉」，是买入信号。

### 死叉卖出信号

当 DIF 线从上方向下穿过 DEA 线时，形成「死叉」，是卖出信号。

### 背离信号

- **顶背离**：股价创新高，但 MACD 的 DIF 未创新高 → 卖出信号
- **底背离**：股价创新低，但 MACD 的 DIF 未创新低 → 买入信号

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| FAST | 快线周期 | 12 |
| SLOW | 慢线周期 | 26 |
| SIGNAL | 信号线周期 | 9 |
```

- [ ] **Step 4: 写入示例文章 breakout.md**

File: `backend/content/education/strategies/breakout.md`

```markdown
---
title: "突破策略案例"
category: strategies
tags: ["突破", "趋势", "中级"]
difficulty: 中级
order: 1
---

## 什么是突破策略？

突破策略基于价格突破关键支撑位或阻力位时产生的交易信号。

## 策略逻辑

1. 计算过去 N 日的最高价和最低价
2. 当收盘价突破 N 日最高价时，产生买入信号
3. 当收盘价跌破 N 日最低价时，产生卖出信号

## 参数优化

- N 值过小会产生过多假信号
- N 值过大会错过短期机会
- 建议先用 20 日作为基准参数回测

## 适用场景

适合趋势明显的市场，不适合震荡市。
```

- [ ] **Step 5: 写入示例文章 create-strategy.md**

File: `backend/content/education/guides/create-strategy.md`

```markdown
---
title: "如何创建策略"
category: guides
tags: ["操作", "入门"]
difficulty: 入门
order: 1
---

## 创建策略的三种方式

### 方式一：上传策略脚本

进入「策略管理」页面，点击「上传策略」按钮，提交 Python 脚本文件。

### 方式二：可视化构建

进入「策略管理」→「可视化构建」，通过选择因子组合来构建策略。

### 方式三：AI 参考选股

进入「策略管理」→「AI 参考选股」，输入参考股票和时间段，AI 会分析股票特征并生成选股策略。

## 下一步

创建策略后，建议立即运行回测验证策略效果。
```

- [ ] **Step 6: Commit**

```bash
git add backend/content/education/
git commit -m "feat: add sample education content files"
```

---

### Task 2: EducationService — 文件解析 + 内存缓存

**Files:**
- Create: `backend/app/services/education_service.py`
- Note: `backend/app/services/__init__.py` 无需修改（服务类无 __init__ 导入）

- [ ] **Step 1: 实现 EducationService**

File: `backend/app/services/education_service.py`

```python
"""教育内容服务 — 读取 Markdown 文件，解析 frontmatter，内存缓存"""

import logging
import os
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

CONTENT_DIR = Path(__file__).resolve().parent.parent.parent / "content" / "education"


class ArticleItem:
    """文章列表项（不含正文）"""
    def __init__(self, slug: str, title: str, category: str, tags: list[str],
                 difficulty: str, order: int):
        self.slug = slug
        self.title = title
        self.category = category
        self.tags = tags
        self.difficulty = difficulty
        self.order = order

    def to_dict(self):
        return {
            "slug": self.slug,
            "title": self.title,
            "category": self.category,
            "tags": self.tags,
            "difficulty": self.difficulty,
            "order": self.order,
        }


class ArticleFull(ArticleItem):
    """文章完整内容（含正文）"""
    def __init__(self, slug: str, title: str, category: str, tags: list[str],
                 difficulty: str, order: int, body: str):
        super().__init__(slug, title, category, tags, difficulty, order)
        self.body = body

    def to_dict(self):
        d = super().to_dict()
        d["body"] = self.body
        return d


def _parse_frontmatter(filepath: Path) -> Optional[dict]:
    """解析 .md 文件的 YAML frontmatter，返回 dict 或 None"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        logger.warning("无法读取文件: %s", filepath)
        return None

    if not content.startswith("---"):
        logger.warning("文件缺少 frontmatter: %s", filepath)
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        logger.warning("frontmatter 格式错误: %s", filepath)
        return None

    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        logger.warning("YAML 解析失败: %s", filepath)
        return None

    if not isinstance(meta, dict):
        return None

    body = parts[2].strip()
    # 从文件名推导 slug
    slug = filepath.stem
    # 从目录名推导 category（如果 frontmatter 未指定）
    category = meta.get("category", filepath.parent.name)

    return {
        "slug": slug,
        "title": meta.get("title", slug),
        "category": category,
        "tags": meta.get("tags", []),
        "difficulty": meta.get("difficulty", "通用"),
        "order": meta.get("order", 99),
        "body": body,
    }


class EducationService:
    """教育内容服务 — 单例，启动时加载全部内容到内存"""

    _instance: Optional["EducationService"] = None

    def __init__(self):
        self._categories: list[dict] = []
        self._articles: dict[str, ArticleFull] = {}  # slug -> full article
        self._loaded = False

    @classmethod
    def instance(cls) -> "EducationService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self) -> None:
        """启动时调用，扫描目录加载所有文章"""
        self._load_categories()
        self._load_articles()
        self._loaded = True
        logger.info("教育内容加载完成: %d 个分类, %d 篇文章",
                     len(self._categories), len(self._articles))

    def _load_categories(self) -> None:
        index_file = CONTENT_DIR / "index.yaml"
        if index_file.exists():
            try:
                data = yaml.safe_load(index_file.read_text(encoding="utf-8"))
                self._categories = data.get("categories", [])
            except Exception:
                logger.warning("index.yaml 解析失败，使用默认分类")

        if not self._categories:
            # 降级：按目录名自动生成分类
            cats = set()
            for md_file in CONTENT_DIR.rglob("*.md"):
                cat = md_file.parent.name
                if cat not in cats:
                    cats.add(cat)
            self._categories = [
                {"key": c, "label": c, "icon": "ReadOutlined", "order": i}
                for i, c in enumerate(sorted(cats))
            ]

    def _load_articles(self) -> None:
        for md_file in CONTENT_DIR.rglob("*.md"):
            parsed = _parse_frontmatter(md_file)
            if parsed is None:
                continue
            article = ArticleFull(**parsed)
            self._articles[article.slug] = article

    @property
    def loaded(self) -> bool:
        return self._loaded

    def get_categories(self) -> list[dict]:
        return sorted(self._categories, key=lambda c: c.get("order", 99))

    def get_articles(self, category: Optional[str] = None) -> list[dict]:
        items = list(self._articles.values())
        if category:
            items = [a for a in items if a.category == category]
        items.sort(key=lambda a: (a.category, a.order))
        return [a.to_dict() for a in items]

    def get_article(self, slug: str) -> Optional[dict]:
        article = self._articles.get(slug)
        if article is None:
            return None
        return article.to_dict()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/education_service.py
git commit -m "feat: add EducationService for markdown content parsing and caching"
```

---

### Task 3: Education API 路由

**Files:**
- Create: `backend/app/api/education.py`

- [ ] **Step 1: 实现路由**

File: `backend/app/api/education.py`

```python
"""教育内容 API"""

from fastapi import APIRouter, Depends, Query, HTTPException

from ..middleware.auth import get_current_user
from ..models.user import User
from ..services.education_service import EducationService

router = APIRouter()


@router.get("/categories")
async def get_categories(
    current_user: User = Depends(get_current_user),
):
    """获取所有分类"""
    svc = EducationService.instance()
    return {"code": 0, "message": "ok", "data": svc.get_categories()}


@router.get("/articles")
async def get_articles(
    category: str | None = Query(None, description="按分类筛选"),
    current_user: User = Depends(get_current_user),
):
    """获取文章列表（不含正文）"""
    svc = EducationService.instance()
    articles = svc.get_articles(category=category)
    # 列表不返回 body
    articles_preview = [
        {k: v for k, v in a.items() if k != "body"}
        for a in articles
    ]
    return {"code": 0, "message": "ok", "data": articles_preview}


@router.get("/articles/{slug}")
async def get_article(
    slug: str,
    current_user: User = Depends(get_current_user),
):
    """获取单篇文章完整内容"""
    svc = EducationService.instance()
    article = svc.get_article(slug)
    if article is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    return {"code": 0, "message": "ok", "data": article}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/education.py
git commit -m "feat: add education API routes"
```

---

### Task 4: 注册路由 + 服务启动加载

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: 在 main.py 中注册路由并触发服务加载**

在 main.py 的 import 和路由注册区域添加 education 相关代码。

**Step 1a: 找到 router import 行，添加 education import**

```python
# 在 from .api import strategies, backtests, batch_backtests, factors, ai, auth, users, stocks 后追加
from .api import strategies, backtests, batch_backtests, factors, ai, auth, users, stocks, education
```

**Step 1b: 在最后一条 app.include_router 后追加**

```python
app.include_router(education.router, prefix="/api/v1/education", tags=["education"])
```

**Step 1c: 在 startup_event 末尾触发服务加载**

修改 `startup_event` 函数：

```python
@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    await init_db()
    # 加载教育内容
    from .services.education_service import EducationService
    EducationService.instance().load()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: register education router and load content on startup"
```

---

### Task 5: 后端测试

**Files:**
- Create: `backend/tests/test_education.py`

- [ ] **Step 1: 写测试**

File: `backend/tests/test_education.py`

```python
"""教育内容服务测试"""

import tempfile
from pathlib import Path

import pytest

from app.services.education_service import (
    EducationService,
    _parse_frontmatter,
)


class TestParseFrontmatter:
    def test_valid_frontmatter(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("---\ntitle: 测试\ncategory: indicators\ntags: [a, b]\ndifficulty: 入门\norder: 1\n---\n\n# 正文内容\n\nHello world.")
        result = _parse_frontmatter(md)
        assert result is not None
        assert result["title"] == "测试"
        assert result["category"] == "indicators"
        assert result["tags"] == ["a", "b"]
        assert result["difficulty"] == "入门"
        assert result["order"] == 1
        assert "正文内容" in result["body"]

    def test_no_frontmatter(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("# 没有 frontmatter\n正文")
        result = _parse_frontmatter(md)
        assert result is None

    def test_malformed_yaml(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("---\n: bad yaml: [\n---\n正文")
        result = _parse_frontmatter(md)
        assert result is None

    def test_slug_from_filename(self, tmp_path):
        md = tmp_path / "macd.md"
        md.write_text("---\ntitle: MACD\n---\n\n正文")
        result = _parse_frontmatter(md)
        assert result["slug"] == "macd"


class TestEducationService:
    def test_get_categories(self):
        svc = EducationService.instance()
        if not svc.loaded:
            svc.load()
        categories = svc.get_categories()
        assert isinstance(categories, list)
        assert len(categories) >= 1
        for cat in categories:
            assert "key" in cat
            assert "label" in cat

    def test_get_articles(self):
        svc = EducationService.instance()
        if not svc.loaded:
            svc.load()
        articles = svc.get_articles()
        assert isinstance(articles, list)
        assert len(articles) >= 1
        for a in articles:
            assert "slug" in a
            assert "title" in a
            assert "body" in a

    def test_get_articles_filtered(self):
        svc = EducationService.instance()
        if not svc.loaded:
            svc.load()
        articles = svc.get_articles(category="indicators")
        for a in articles:
            assert a["category"] == "indicators"

    def test_get_article_exists(self):
        svc = EducationService.instance()
        if not svc.loaded:
            svc.load()
        article = svc.get_article("macd")
        assert article is not None
        assert article["title"] == "MACD 指标详解"
        assert "body" in article

    def test_get_article_not_exists(self):
        svc = EducationService.instance()
        if not svc.loaded:
            svc.load()
        article = svc.get_article("nonexistent")
        assert article is None
```

- [ ] **Step 2: 运行测试，确认通过**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_education.py -v
```

预期: 7 tests passed

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_education.py
git commit -m "test: add education service tests"
```

---

### Task 6: 前端依赖安装

**Files:**
- Modify: `frontend/package.json` (npm install 会自动更新)

- [ ] **Step 1: 安装依赖**

```bash
cd frontend && npm install react-markdown remark-gfm react-syntax-highlighter
```

- [ ] **Step 2: 验证安装**

```bash
cd frontend && node -e "require('react-markdown'); require('remark-gfm'); console.log('OK')"
```

预期: `OK`

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "deps: add react-markdown, remark-gfm, react-syntax-highlighter"
```

---

### Task 7: educationService.ts

**Files:**
- Create: `frontend/src/services/educationService.ts`

- [ ] **Step 1: 实现 educationService**

File: `frontend/src/services/educationService.ts`

```typescript
import api from './api';

export interface Category {
  key: string;
  label: string;
  icon: string;
  order: number;
}

export interface ArticlePreview {
  slug: string;
  title: string;
  category: string;
  tags: string[];
  difficulty: string;
  order: number;
}

export interface Article extends ArticlePreview {
  body: string;
}

const educationService = {
  async getCategories(): Promise<Category[]> {
    const res = await api.get('/education/categories');
    return res.data.data;
  },

  async getArticles(category?: string): Promise<ArticlePreview[]> {
    const params = category ? { category } : {};
    const res = await api.get('/education/articles', { params });
    return res.data.data;
  },

  async getArticle(slug: string): Promise<Article> {
    const res = await api.get(`/education/articles/${slug}`);
    return res.data.data;
  },
};

export default educationService;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/educationService.ts
git commit -m "feat: add educationService for learning center API calls"
```

---

### Task 8: EducationPage（学习中心首页）

**Files:**
- Create: `frontend/src/pages/EducationPage.tsx`

- [ ] **Step 1: 实现 EducationPage**

File: `frontend/src/pages/EducationPage.tsx`

```tsx
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Tabs, Tag, Empty, Spin } from 'antd';
import { ReadOutlined, LineChartOutlined, BulbOutlined, BookOutlined } from '@ant-design/icons';
import educationService, { Category, ArticlePreview } from '@/services/educationService';

const iconMap: Record<string, React.ReactNode> = {
  LineChartOutlined: <LineChartOutlined />,
  BulbOutlined: <BulbOutlined />,
  BookOutlined: <BookOutlined />,
  ReadOutlined: <ReadOutlined />,
};

const difficultyColors: Record<string, string> = {
  '入门': 'green',
  '中级': 'blue',
  '高级': 'red',
};

const EducationPage: React.FC = () => {
  const navigate = useNavigate();
  const [categories, setCategories] = useState<Category[]>([]);
  const [articles, setArticles] = useState<ArticlePreview[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState<string>('');

  useEffect(() => {
    const fetch = async () => {
      try {
        const [cats, arts] = await Promise.all([
          educationService.getCategories(),
          educationService.getArticles(),
        ]);
        setCategories(cats);
        setArticles(arts);
        if (cats.length > 0) setActiveCategory(cats[0].key);
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, []);

  const filteredArticles = activeCategory
    ? articles.filter((a) => a.category === activeCategory)
    : articles;

  const handleTabChange = (key: string) => {
    setActiveCategory(key);
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      <h2 style={{ marginBottom: 24 }}>学习中心</h2>
      {categories.length === 0 ? (
        <Empty description="暂无分类" />
      ) : (
        <>
          <Tabs
            activeKey={activeCategory}
            onChange={handleTabChange}
            items={categories.map((cat) => ({
              key: cat.key,
              label: (
                <span>
                  {iconMap[cat.icon] || <ReadOutlined />}
                  {' '}{cat.label}
                </span>
              ),
            }))}
          />
          {filteredArticles.length === 0 ? (
            <Empty description="该分类下暂无文章" style={{ marginTop: 40 }} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {filteredArticles.map((article) => (
                <Card
                  key={article.slug}
                  hoverable
                  onClick={() => navigate(`/education/${article.category}/${article.slug}`)}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <h3 style={{ margin: 0 }}>{article.title}</h3>
                      <div style={{ marginTop: 8 }}>
                        <Tag color={difficultyColors[article.difficulty] || 'default'}>
                          {article.difficulty}
                        </Tag>
                        {article.tags.map((tag) => (
                          <Tag key={tag}>{tag}</Tag>
                        ))}
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default EducationPage;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/EducationPage.tsx
git commit -m "feat: add EducationPage with category tabs and article cards"
```

---

### Task 9: EducationDetailPage（文章详情页）

**Files:**
- Create: `frontend/src/pages/EducationDetailPage.tsx`

- [ ] **Step 1: 实现 EducationDetailPage**

File: `frontend/src/pages/EducationDetailPage.tsx`

```tsx
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Anchor, Button, Spin, Tag, Result } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import educationService, { Article } from '@/services/educationService';

const difficultyColors: Record<string, string> = {
  '入门': 'green',
  '中级': 'blue',
  '高级': 'red',
};

const EducationDetailPage: React.FC = () => {
  const { category, slug } = useParams<{ category: string; slug: string }>();
  const navigate = useNavigate();
  const [article, setArticle] = useState<Article | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    setError(false);
    educationService
      .getArticle(slug)
      .then(setArticle)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [slug]);

  // Extract headings for TOC
  const tocItems = React.useMemo(() => {
    if (!article) return [];
    const headingRegex = /^(#{1,3})\s+(.+)$/gm;
    const items: { key: string; href: string; title: string }[] = [];
    let match;
    while ((match = headingRegex.exec(article.body)) !== null) {
      const level = match[1].length;
      const title = match[2];
      const id = title.replace(/\s+/g, '-').toLowerCase();
      items.push({ key: id, href: `#${id}`, title });
    }
    return items;
  }, [article]);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (error || !article) {
    return (
      <Result
        status="404"
        title="文章不存在"
        subTitle="请检查链接是否正确"
        extra={
          <Button type="primary" onClick={() => navigate('/education')}>
            返回学习中心
          </Button>
        }
      />
    );
  }

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/education')}
        style={{ marginBottom: 16 }}
      >
        返回学习中心
      </Button>
      <div style={{ display: 'flex', gap: 32 }}>
        <article style={{ flex: 1, minWidth: 0 }}>
          <h1>{article.title}</h1>
          <div style={{ marginBottom: 24 }}>
            <Tag color={difficultyColors[article.difficulty] || 'default'}>
              {article.difficulty}
            </Tag>
            {article.tags.map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </div>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || '');
                const code = String(children).replace(/\n$/, '');
                if (match) {
                  return (
                    <SyntaxHighlighter
                      style={oneDark}
                      language={match[1]}
                      PreTag="div"
                    >
                      {code}
                    </SyntaxHighlighter>
                  );
                }
                return (
                  <code className={className} {...props}>
                    {children}
                  </code>
                );
              },
            }}
          >
            {article.body}
          </ReactMarkdown>
        </article>
        {tocItems.length > 0 && (
          <aside style={{ width: 200, flexShrink: 0 }}>
            <div style={{ position: 'sticky', top: 24 }}>
              <h4 style={{ marginBottom: 8 }}>目录</h4>
              <Anchor
                items={tocItems}
                affix={false}
                onClick={(e, link) => {
                  e.preventDefault();
                  document.querySelector(link.href)?.scrollIntoView({ behavior: 'smooth' });
                }}
              />
            </div>
          </aside>
        )}
      </div>
    </div>
  );
};

export default EducationDetailPage;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/EducationDetailPage.tsx
git commit -m "feat: add EducationDetailPage with markdown rendering and TOC"
```

---

### Task 10: 注册路由 + 侧边栏菜单

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout/AppLayout.tsx`

- [ ] **Step 1: App.tsx — 添加路由**

**Step 1a: 添加 import**

```tsx
import EducationPage from '@/pages/EducationPage';
import EducationDetailPage from '@/pages/EducationDetailPage';
```

**Step 1b: 在 `<Routes>` 中添加路由（放在 dashboard 路由之后、strategies 路由之前）**

```tsx
<Route
  path="/education"
  element={
    <ProtectedRoute>
      <EducationPage />
    </ProtectedRoute>
  }
/>
<Route
  path="/education/:category/:slug"
  element={
    <ProtectedRoute>
      <EducationDetailPage />
    </ProtectedRoute>
  }
/>
```

- [ ] **Step 2: AppLayout.tsx — 添加侧边栏菜单项**

**Step 2a: 在 imports 中追加 `ReadOutlined`（如果尚未导入）**

检查 `@ant-design/icons` import 行，确保包含 `ReadOutlined`：

```tsx
import {
  DashboardOutlined,
  LineChartOutlined,
  BarChartOutlined,
  BulbOutlined,
  UserOutlined,
  TeamOutlined,
  LogoutOutlined,
  ReadOutlined,  // 新增
} from '@ant-design/icons';
```

**Step 2b: 在 menuItems 数组中添加菜单项（放在 dashboard 之后）**

```tsx
{
  key: '/education',
  icon: <ReadOutlined />,
  label: '学习中心',
},
```

**Step 2c: 在 selectedKey 逻辑中添加路由匹配**

```tsx
if (location.pathname.startsWith('/education')) return '/education';
```

- [ ] **Step 3: 类型检查**

```bash
cd frontend && npx tsc --noEmit
```

预期: 无类型错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Layout/AppLayout.tsx
git commit -m "feat: register education routes and sidebar menu item"
```

---

### Task 11: 验证

- [ ] **Step 1: 启动后端并测试 API**

```bash
cd backend && source venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 3
# 测试分类接口
curl -s http://localhost:8000/api/v1/education/categories | python -m json.tool
# 测试文章列表接口
curl -s http://localhost:8000/api/v1/education/articles | python -m json.tool
# 测试单篇文章接口
curl -s http://localhost:8000/api/v1/education/articles/macd | python -m json.tool
```

预期: 所有三个接口返回 `code: 0`，data 包含正确数据

- [ ] **Step 2: 启动前端验证页面**

```bash
cd frontend && npm run dev &
```

打开浏览器访问：
- `http://localhost:5173/education` — 查看学习中心首页
- `http://localhost:5173/education/indicators/macd` — 查看 MACD 文章

预期: 分类 Tab 正常切换，文章卡片可点击，详情页 Markdown 正常渲染，侧边目录导航正常

- [ ] **Step 3: 运行后端测试**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_education.py -v
```

预期: 全部 PASS

- [ ] **Step 4: 构建检查**

```bash
cd frontend && npm run build
```

预期: 无错误
