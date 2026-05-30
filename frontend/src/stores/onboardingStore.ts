import { create } from 'zustand';

const ONBOARDING_KEY = 'aipicking_onboarding_completed';

interface OnboardingState {
  /** Whether the tour overlay is visible */
  tourOpen: boolean;
  /** Whether this was triggered manually (vs auto on first login) */
  forceOpen: boolean;

  startTour: () => void;
  closeTour: () => void;
  isCompleted: () => boolean;
}

export const useOnboardingStore = create<OnboardingState>((set, get) => ({
  tourOpen: false,
  forceOpen: false,

  startTour: () => set({ tourOpen: true, forceOpen: true }),

  closeTour: () => {
    localStorage.setItem(ONBOARDING_KEY, 'true');
    set({ tourOpen: false, forceOpen: false });
  },

  isCompleted: () => localStorage.getItem(ONBOARDING_KEY) === 'true',
}));

export default useOnboardingStore;
