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
