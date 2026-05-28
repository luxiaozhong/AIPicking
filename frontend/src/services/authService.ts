import axios from 'axios';
import type { LoginRequest, LoginResponse, RefreshResponse, UserInfo } from '@/types/auth';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 10000,
});

const TOKEN_KEY = 'access_token';
const REFRESH_KEY = 'refresh_token';

// 请求拦截器：自动注入 Token（与 api.ts 保持一致，确保硬刷新时 getMe/refresh 携带 Token）
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const authService = {
  async login(data: LoginRequest): Promise<LoginResponse> {
    const response = await api.post<{ code: number; data: LoginResponse }>('/auth/login', data);
    const result = response.data.data;
    localStorage.setItem(TOKEN_KEY, result.access_token);
    localStorage.setItem(REFRESH_KEY, result.refresh_token);
    return result;
  },

  async refresh(): Promise<string> {
    const refreshToken = localStorage.getItem(REFRESH_KEY);
    if (!refreshToken) throw new Error('No refresh token');

    const response = await api.post<{ code: number; data: RefreshResponse }>('/auth/refresh', {
      refresh_token: refreshToken,
    });
    const newToken = response.data.data.access_token;
    localStorage.setItem(TOKEN_KEY, newToken);
    return newToken;
  },

  async getMe(): Promise<UserInfo> {
    const response = await api.get<{ code: number; data: UserInfo }>('/auth/me');
    return response.data.data;
  },

  getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  },

  getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_KEY);
  },

  logout(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export default authService;
