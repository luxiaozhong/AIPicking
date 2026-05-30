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

// === MACD Interactive Types ===

export interface CaseAnnotation {
  id: string;
  date: string;
  type: 'golden_cross' | 'death_cross' | 'top_divergence' | 'bottom_divergence';
  label: string;
  desc: string;
}

export interface CaseStock {
  ts_code: string;
  name: string;
}

export interface CaseDateRange {
  start: string;
  end: string;
}

export interface CaseStep {
  step: number;
  title: string;
  content_file: string;
  content: string;
  visible_annotations: string[];
  highlight_params: string | null;
}

export interface MACDCase {
  id: string;
  title: string;
  stock: CaseStock;
  date_range: CaseDateRange;
  annotations: CaseAnnotation[];
  steps: CaseStep[] | null;
}

export interface MACDCasesData {
  default_params: { fast: number; slow: number; signal: number };
  cases: MACDCase[];
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

  async getMACDCases(): Promise<MACDCasesData> {
    const res = await api.get('/education/macd-interactive/cases');
    return res.data.data;
  },

  async getKDJCases(): Promise<MACDCasesData> {
    const res = await api.get('/education/kdj-interactive/cases');
    return res.data.data;
  },

  async getRSICases(): Promise<MACDCasesData> {
    const res = await api.get('/education/rsi-interactive/cases');
    return res.data.data;
  },
};

export default educationService;
