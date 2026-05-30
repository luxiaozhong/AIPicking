import { useEffect } from 'react';
import { useOnboardingStore } from '@/stores/onboardingStore';
import { useAuthStore } from '@/stores/authStore';

/**
 * Auto-opens the onboarding tour for first-time users after login.
 * Only triggers once per localStorage — subsequent logins won't auto-open.
 */
export function useOnboarding() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const loading = useAuthStore((s) => s.loading);
  const { tourOpen, forceOpen, startTour, isCompleted } = useOnboardingStore();

  useEffect(() => {
    // Only auto-trigger when auth is confirmed and tour hasn't been completed
    if (isAuthenticated && !loading && !forceOpen && !isCompleted()) {
      // Brief delay to let the page render before showing the tour
      const timer = setTimeout(() => startTour(), 600);
      return () => clearTimeout(timer);
    }
  }, [isAuthenticated, loading]);

  return { tourOpen };
}

export default useOnboarding;
