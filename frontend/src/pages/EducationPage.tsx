import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Tabs, Tag, Empty, Spin } from 'antd';
import { ReadOutlined, LineChartOutlined, BulbOutlined, BookOutlined } from '@ant-design/icons';
import educationService from '@/services/educationService';
import type { Category, ArticlePreview } from '@/services/educationService';

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
