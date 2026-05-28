import { create } from 'zustand';

interface ThemeState {
  isDark: boolean;
  toggle: () => void;
  setDark: (dark: boolean) => void;
}

const stored = typeof window !== 'undefined' ? localStorage.getItem('aipicking-theme') : null;

export const useThemeStore = create<ThemeState>((set) => ({
  isDark: stored === 'dark',
  toggle: () =>
    set((state) => {
      const next = !state.isDark;
      localStorage.setItem('aipicking-theme', next ? 'dark' : 'light');
      return { isDark: next };
    }),
  setDark: (dark: boolean) => {
    localStorage.setItem('aipicking-theme', dark ? 'dark' : 'light');
    set({ isDark: dark });
  },
}));
