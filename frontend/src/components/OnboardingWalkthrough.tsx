import { useState, useEffect, useCallback } from 'react';
import { Tour } from 'antd';
import type { TourProps } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import { useOnboardingStore } from '@/stores/onboardingStore';
import { useOnboarding } from '@/hooks/useOnboarding';

/** Helper: find a menu item by its label text */
function menuItemByText(text: string): HTMLElement {
  const items = document.querySelectorAll('.ant-menu-item');
  for (const item of items) {
    const title = item.querySelector('.ant-menu-title-content');
    if (title?.textContent?.trim() === text) return item as HTMLElement;
  }
  return document.body; // fallback
}

/** Helper: find the header user button */
function headerUserButton(): HTMLElement {
  const header = document.querySelector('.ant-layout-header');
  if (!header) return document.body;
  const buttons = header.querySelectorAll('button');
  return (buttons[buttons.length - 1] as HTMLElement) || document.body;
}

/** Helper: query selector, returns body as fallback for antd Tour type compatibility */
function qs(selector: string): HTMLElement {
  return (document.querySelector(selector) as HTMLElement) || document.body;
}

type StepKey = 'welcome' | 'sidebar' | 'ai-builder' | 'visual-builder' | 'backtest' | 'help';

const STEP_KEYS: StepKey[] = [
  'welcome',
  'sidebar',
  'ai-builder',
  'visual-builder',
  'backtest',
  'help',
];

interface StepDef {
  key: StepKey;
  title: string;
  description: string;
  target: () => HTMLElement;
  /** Which page this step needs to be on (null = any page) */
  page: string | null;
}

const STEPS: StepDef[] = [
  {
    key: 'welcome',
    title: '欢迎使用 AIpicking 🎉',
    description:
      '这是一个量化策略研究与回测平台。你可以在这里创建策略、运行回测，以及使用 AI 分析选股。仪表盘上的快捷操作卡片可以帮你快速进入核心功能。',
    target: () => qs('.ant-card'),
    page: null,
  },
  {
    key: 'sidebar',
    title: '功能导航',
    description:
      '左侧导航栏汇集了所有功能：仪表盘、学习中心、策略管理、简单回测和交易模拟。点击即可切换。',
    target: () => qs('.ant-layout-sider'),
    page: null,
  },
  {
    key: 'ai-builder',
    title: '⭐ AI 参考选股',
    description:
      '这是平台的核心特色功能。输入任意股票代码和日期，AI 将自动分析 50+ 技术指标，并从市场中找到最相似的标的。点击这里开始体验。',
    target: () => qs('[data-tour-id="btn-ai-builder"]'),
    page: '/strategies',
  },
  {
    key: 'visual-builder',
    title: '可视化构建策略',
    description:
      '不想写代码？使用可视化构建器，通过拖拽技术因子来组合交易策略，直观高效。',
    target: () => qs('[data-tour-id="btn-visual-builder"]'),
    page: '/strategies',
  },
  {
    key: 'backtest',
    title: '回测验证',
    description:
      '策略创建完成后，在这里提交回测任务，验证策略在历史数据上的表现。支持单策略回测和批量多日期回测。',
    target: () => menuItemByText('简单回测'),
    page: null,
  },
  {
    key: 'help',
    title: '随时回顾',
    description:
      '引导结束！你可以随时通过右上角用户菜单中的「操作引导」重新查看本教程。祝投资顺利！',
    target: () => headerUserButton(),
    page: null,
  },
];

const OnboardingWalkthrough: React.FC = () => {
  // Auto-trigger on first login
  useOnboarding();
  const { tourOpen, closeTour } = useOnboardingStore();
  const navigate = useNavigate();
  const location = useLocation();

  const [current, setCurrent] = useState(0);
  const [open, setOpen] = useState(false);
  const [navigating, setNavigating] = useState(false);

  // Reset state when tour opens/closes — setState-during-render pattern (React recommended)
  const [prevTourOpen, setPrevTourOpen] = useState(tourOpen);
  if (tourOpen !== prevTourOpen) {
    setPrevTourOpen(tourOpen);
    setCurrent(0);
    setOpen(tourOpen);
    setNavigating(false);
  }

  // After a page navigation for a step, reopen the tour
  useEffect(() => {
    if (!navigating) return;

    // Check if we've arrived at the target page for the current step
    const targetPage = STEPS[current]?.page;
    if (!targetPage || location.pathname === targetPage) {
      const timer = setTimeout(() => {
        setNavigating(false);
        setOpen(true);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [location.pathname, navigating, current]);

  const handleChange = useCallback(
    (next: number) => {
      if (next < 0 || next >= STEPS.length) return;

      const step = STEPS[next];
      // If this step needs a different page than we're on, navigate first
      if (step.page && location.pathname !== step.page) {
        setOpen(false);
        setNavigating(true);
        setCurrent(next);
        navigate(step.page);
        return;
      }

      setCurrent(next);
    },
    [location.pathname, navigate],
  );

  const handleClose = useCallback(() => {
    setOpen(false);
    setNavigating(false);
    closeTour();
  }, [closeTour]);

  const tourSteps: TourProps['steps'] = STEPS.map((step) => ({
    title: step.title,
    description: step.description,
    target: step.target,
    // Ensure prev/next buttons show correctly
    nextButtonProps: {
      children:
        STEP_KEYS.indexOf(step.key) === STEPS.length - 1 ? '完成' : '下一步',
    },
    prevButtonProps: {
      children: '上一步',
    },
  }));

  return (
    <Tour
      open={open}
      current={current}
      onClose={handleClose}
      onChange={handleChange}
      steps={tourSteps}
      mask={{
        color: 'rgba(0, 0, 0, 0.5)',
      }}
      placement="bottom"
    />
  );
};

export default OnboardingWalkthrough;
