import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Anchor, Button, Spin, Tag, Result } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import educationService from '@/services/educationService';
import type { Article } from '@/services/educationService';
import InteractiveMACDPage from '@/pages/InteractiveMACDPage';

const difficultyColors: Record<string, string> = {
  '入门': 'green',
  '中级': 'blue',
  '高级': 'red',
};

const EducationDetailPage: React.FC = () => {
  const { category, slug } = useParams<{ category: string; slug: string }>();
  const navigate = useNavigate();

  // 当访问 MACD 文章时，渲染交互学习页面
  if (category === 'indicators' && slug === 'macd') {
    return <InteractiveMACDPage />;
  }
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
