"""教育内容服务 — 读取 Markdown 文件，解析 frontmatter，内存缓存"""

import logging
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
                cats = data.get("categories", [])
                if isinstance(cats, list) and all(isinstance(c, dict) for c in cats):
                    self._categories = cats
                else:
                    logger.warning("index.yaml categories 格式错误")
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
            # 使用 category/slug 作为 key，避免不同分类下同名文件冲突
            key = f"{article.category}/{article.slug}"
            if key in self._articles:
                logger.warning("slug 冲突，后加载的文件覆盖: %s", key)
            self._articles[key] = article

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
        # slug 可以是 "macd"（纯文件名）或 "indicators/macd"（含分类前缀）
        article = self._articles.get(slug)
        if article is not None:
            return article.to_dict()
        # 按纯 slug 搜索
        for key, a in self._articles.items():
            if key.endswith(f"/{slug}"):
                return a.to_dict()
        return None
