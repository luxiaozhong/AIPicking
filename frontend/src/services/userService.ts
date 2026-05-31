import axios from 'axios';
import type { UserListResponse, UserResponse, UserCreateRequest, UserUpdateRequest } from '@/types/auth';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 10000,
});

// Add token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const userService = {
  async getUsers(params: { page?: number; limit?: number; search?: string } = {}) {
    const response = await api.get<UserListResponse>('/users', { params });
    return response.data;
  },

  async createUser(data: UserCreateRequest) {
    const response = await api.post<{ code: number; data: UserResponse }>('/users', data);
    return response.data;
  },

  async updateUser(id: number, data: UserUpdateRequest) {
    const response = await api.put<{ code: number; data: UserResponse }>(`/users/${id}`, data);
    return response.data;
  },

  async deleteUser(id: number) {
    const response = await api.delete<{ code: number; message: string }>(`/users/${id}`);
    return response.data;
  },

  async deleteUserPermanent(id: number) {
    const response = await api.delete<{ code: number; message: string }>(`/users/${id}/permanent`);
    return response.data;
  },
};

export default userService;
