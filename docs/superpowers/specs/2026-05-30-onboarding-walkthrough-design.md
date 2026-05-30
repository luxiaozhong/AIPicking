# Onboarding Walkthrough — Design Spec

**Date:** 2026-05-30
**Status:** Implemented

## Overview

First-time users get a simple 6-step guided tour (mask + tooltip bubbles) after login. The walkthrough is skipable and re-triggerable from the user menu.

## Requirements

- **Trigger:** Auto-show on first login (never completed before); manually from "操作引导" menu item
- **State:** `localStorage` key `aipicking_onboarding_completed` — no backend changes
- **Tech:** antd 6 `Tour` component (already in project, no new dependency)
- **Scope:** Core workflow (strategies → backtest) + AI stock picking feature

## Walkthrough Steps

| Step | Title | Target | Selector | Page |
|------|-------|--------|----------|------|
| 1 | 欢迎使用 AIpicking | Dashboard card area | `.ant-card` | `/dashboard` |
| 2 | 功能导航 | Sidebar menu | `.ant-layout-sider` | all |
| 3 | ⭐ AI 参考选股 | "AI 参考选股" button | `[data-tour-id="btn-ai-builder"]` | `/strategies` |
| 4 | 可视化构建策略 | "可视化构建" button | `[data-tour-id="btn-visual-builder"]` | `/strategies` |
| 5 | 回测验证 | "回测报告" menu item | `menuItemByText('回测报告')` | all |
| 6 | 随时回顾 | Header user dropdown button | `headerUserButton()` | all |

Steps 3-4 require navigation to `/strategies`. The Tour component temporarily closes during navigation and reopens at the correct step on route change (500ms delay).

## Architecture

```
frontend/src/
├── hooks/
│   └── useOnboarding.ts          ← localStorage check + auto-trigger on first login
├── components/
│   └── OnboardingWalkthrough.tsx  ← antd <Tour> + 6 step definitions + navigation logic
├── stores/
│   └── onboardingStore.ts        ← Zustand store (tourOpen, startTour, closeTour)
├── components/Layout/
│   └── AppLayout.tsx             ← "操作引导" in user dropdown menu
└── App.tsx                       ← Mounts <OnboardingWalkthrough /> inside AppLayout
```

### Data Flow

```
Login success → authStore.isAuthenticated = true
                     ↓
OnboardingWalkthrough mounts inside AppLayout
  └─ useOnboarding() checks localStorage
                     ↓
    ┌─ isCompleted()? → no → startTour() after 600ms → Tour open (step 1)
    │
    └─ isCompleted()? → yes → idle, wait for manual trigger
                                  ↑
              User clicks "操作引导" → onboardingStore.startTour()
                  → forceOpen: true → skips auto-trigger check
```

## Files Changed

### New Files
1. `frontend/src/stores/onboardingStore.ts` — Zustand store, localStorage persistence
2. `frontend/src/hooks/useOnboarding.ts` — Auto-trigger on first login (called by OnboardingWalkthrough)
3. `frontend/src/components/OnboardingWalkthrough.tsx` — Tour component, steps, navigation

### Modified Files
1. `frontend/src/App.tsx` — Import and mount `<OnboardingWalkthrough />` inside AppLayout
2. `frontend/src/components/Layout/AppLayout.tsx` — Import `QuestionCircleOutlined`, `useOnboardingStore`, add "操作引导" menu item
3. `frontend/src/pages/StrategyList.tsx` — Add `data-tour-id` attributes to AI builder and visual builder buttons; fix text wrapping in strategy name column

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Target element not found | `qs()` / helpers return `document.body` as fallback |
| Page refresh mid-tour | Zustand resets → Tour closes → localStorage not written → re-shows on next login |
| Manual navigation during tour | Tour stays open; target may resolve to fallback |
| Token expired during tour | Auth redirect to /login → AppLayout unmounts |
| localStorage cleared | User treated as new → auto-trigger on next login |
