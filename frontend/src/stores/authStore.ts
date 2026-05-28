import { create } from 'zustand';
import type { UserInfo, LoginRequest } from '@/types/auth';
import authService from '@/services/authService';

interface AuthState {
  user: UserInfo | null;
  isAuthenticated: boolean;
  loading: boolean;
  error: string | null;

  login: (data: LoginRequest) => Promise<void>;
  logout: () => void;
  initialize: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  loading: false,
  error: null,

  login: async (data: LoginRequest) => {
    set({ loading: true, error: null });
    try {
      const result = await authService.login(data);
      set({
        user: result.user,
        isAuthenticated: true,
        loading: false,
      });
    } catch (error: any) {
      set({
        loading: false,
        error: error.response?.data?.detail || '登录失败',
      });
      throw error;
    }
  },

  logout: () => {
    authService.logout();
    set({ user: null, isAuthenticated: false });
  },

  initialize: async () => {
    const token = authService.getToken();
    if (!token) {
      set({ isAuthenticated: false });
      return;
    }

    try {
      const user = await authService.getMe();
      set({ user, isAuthenticated: true });
    } catch {
      // Token expired, try refresh
      try {
        await authService.refresh();
        const user = await authService.getMe();
        set({ user, isAuthenticated: true });
      } catch {
        authService.logout();
        set({ user: null, isAuthenticated: false });
      }
    }
  },

  clearError: () => set({ error: null }),
}));

export default useAuthStore;
