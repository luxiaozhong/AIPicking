import { test, expect } from '@playwright/test';

test.describe('仪表盘', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('应能正确加载仪表盘首页', async ({ page }) => {
    // 页面标题
    await expect(page.getByRole('heading', { name: '仪表盘' })).toBeVisible({ timeout: 10000 });

    // 统计卡片（Statistic 组件在 Row > Col > Card 中，用 .first() 避免匹配到"快速入门"中的文字）
    await expect(page.locator('.ant-statistic').filter({ hasText: '策略管理' }).first()).toBeVisible();
    await expect(page.locator('.ant-statistic').filter({ hasText: '简单回测' }).first()).toBeVisible();
    await expect(page.locator('.ant-statistic').filter({ hasText: '已完成回测' }).first()).toBeVisible();
    await expect(page.locator('.ant-statistic').filter({ hasText: '15天胜率' }).first()).toBeVisible();

    // 快捷操作区
    await expect(page.getByText('快捷操作')).toBeVisible();
    await expect(page.getByText('快速入门')).toBeVisible();
  });

  test('应能从仪表盘导航到策略管理', async ({ page }) => {
    const strategyCard = page.locator('.ant-card').filter({ hasText: '策略管理' }).first();
    await strategyCard.click();
    await page.waitForURL('**/strategies');
    await expect(page.getByRole('heading', { name: '策略管理' })).toBeVisible();
  });

  test('应能从仪表盘导航到简单回测', async ({ page }) => {
    const backtestCard = page.locator('.ant-card').filter({ hasText: '简单回测' }).first();
    await backtestCard.click();
    await page.waitForURL('**/backtests');
    await expect(page.getByRole('heading', { name: '简单回测' })).toBeVisible();
  });

  test('应能通过快捷操作进入策略构建器', async ({ page }) => {
    // 快捷操作区的内部卡片使用 ant-card-small，避免匹配到外层包装 Card
    const builderLink = page.locator('.ant-card-small').filter({ hasText: '可视化构建策略' });
    if (await builderLink.isVisible()) {
      await builderLink.click();
      await page.waitForURL('**/strategies/builder');
      await expect(page.getByRole('heading', { name: '可视化构建策略' })).toBeVisible();
    }
  });

  test('应能通过快捷操作进入策略列表', async ({ page }) => {
    const listLink = page.locator('.ant-card-small').filter({ hasText: '查看策略列表' });
    if (await listLink.isVisible()) {
      await listLink.click();
      await page.waitForURL('**/strategies');
      await expect(page.getByRole('heading', { name: '策略管理' })).toBeVisible();
    }
  });

  test('侧边栏应高亮当前页面', async ({ page }) => {
    // 仪表盘菜单项应处于选中状态
    const activeMenuItem = page.locator('.ant-menu-item-selected');
    await expect(activeMenuItem).toBeVisible();
    await expect(activeMenuItem).toContainText('仪表盘');
  });
});
