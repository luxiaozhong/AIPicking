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
