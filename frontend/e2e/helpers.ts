import { Page, expect } from '@playwright/test';

/**
 * 通过 UI 登录
 * 填写用户名密码 → 点击登录 → 等待跳转到 dashboard
 */
export async function loginViaUi(
  page: Page,
  username = 'admin',
  password = 'admin123',
) {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  await page.getByPlaceholder('用户名').fill(username);
  await page.getByPlaceholder('密码').fill(password);
  await page.getByRole('button', { name: '登 录' }).click();
  await page.waitForURL('**/dashboard', { timeout: 10000 });
  await page.waitForLoadState('networkidle');
}

/**
 * 测试辅助函数（适配新 UI 设计）
 */

/**
 * 等待因子库加载完成（Collapse 组件渲染）
 */
export async function waitForFactorsLoad(page: Page, timeout = 5000) {
  await page.waitForSelector('.ant-collapse-item', { timeout });
}

/**
 * 添加一个因子到策略
 */
export async function addFactorToStrategy(
  page: Page,
  factorName: string,
  target: 'buy' | 'sell' | 'risk' = 'buy',
) {
  // 展开第一个分类
  const category = page.locator('.ant-collapse-header').first();
  if (await category.isVisible()) {
    await category.click();
    await page.waitForTimeout(300);
  }

  // 查找并点击因子
  const factor = page.locator('.ant-collapse-content-box > div').filter({ hasText: factorName }).first();
  await factor.click();

  // 等待成功消息
  await expect(page.locator('.ant-message-success')).toBeVisible({ timeout: 5000 });
}

/**
 * 填充策略基本信息
 */
export async function fillStrategyInfo(page: Page, name: string, description?: string) {
  await page.getByPlaceholder('策略名称').fill(name);
  if (description) {
    await page.getByPlaceholder('策略描述').fill(description);
  }
}

/**
 * 保存策略
 */
export async function saveStrategy(page: Page) {
  await page.getByRole('button', { name: '保存策略' }).click();
}

/**
 * 切换 AI 助手面板（inline Card，非 Modal）
 */
export async function toggleAIAssistant(page: Page) {
  const aiButton = page.getByRole('button', { name: /AI 助手/ });
  await aiButton.click();
  await page.waitForTimeout(500);
}

/**
 * 通过侧边栏导航
 */
export async function navigateViaSidebar(page: Page, label: string) {
  const menuItem = page.locator('.ant-menu-item').filter({ hasText: label });
  await menuItem.click();
  await page.waitForLoadState('networkidle');
}
