import { test, expect } from '@playwright/test';
import { navigateViaSidebar } from './helpers';

test.describe('策略列表页', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/strategies');
    await page.waitForLoadState('networkidle');
  });

  test('应能正确加载策略列表页', async ({ page }) => {
    // 页面标题
    await expect(page.getByRole('heading', { name: '策略管理' })).toBeVisible({ timeout: 10000 });

    // 操作按钮
    await expect(page.getByRole('button', { name: '可视化构建' })).toBeVisible();
    await expect(page.getByRole('button', { name: '上传策略' })).toBeVisible();

    // 搜索框
    await expect(page.getByPlaceholder('搜索策略名称')).toBeVisible();

    // 状态筛选 Select
    await expect(page.getByText('状态筛选').first()).toBeVisible();

    // 表格
    await expect(page.locator('.ant-table')).toBeVisible();
  });

  test('应能导航到策略构建器', async ({ page }) => {
    await page.getByRole('button', { name: '可视化构建' }).click();
    await page.waitForURL('**/strategies/builder');
    await expect(page.getByRole('heading', { name: '可视化构建策略' })).toBeVisible();
  });

  test('应能导航到策略上传页', async ({ page }) => {
    await page.getByRole('button', { name: '上传策略' }).click();
    await page.waitForURL('**/strategies/upload');
  });

  test('应能搜索策略', async ({ page }) => {
    const searchInput = page.getByPlaceholder('搜索策略名称');
    await searchInput.fill('测试');
    await searchInput.press('Enter');
    await page.waitForTimeout(500);

    // 清空搜索
    await searchInput.clear();
    await searchInput.press('Enter');
  });

  test('应能按状态筛选', async ({ page }) => {
    // 状态筛选下拉框
    const statusSelect = page.locator('.ant-select').filter({ hasText: '状态筛选' }).first();
    await statusSelect.click();
    await page.waitForTimeout(300);

    // 选择一个筛选项
    const activeOption = page.locator('.ant-select-item-option').filter({ hasText: '活跃' });
    if (await activeOption.isVisible()) {
      await activeOption.click();
      await page.waitForTimeout(500);
    }
  });

  test('应显示策略表格列', async ({ page }) => {
    const tableHeader = page.locator('.ant-table-thead');
    await expect(tableHeader).toBeVisible();

    // 验证关键列存在
    await expect(tableHeader.getByText('策略名称')).toBeVisible();
    await expect(tableHeader.getByText('状态')).toBeVisible();
    await expect(tableHeader.getByText('操作')).toBeVisible();
  });

  test('应能点击策略名称查看详情', async ({ page }) => {
    await page.waitForTimeout(2000);

    // 策略名称在表格中由 Button type="link" 渲染
    const firstStrategyLink = page.locator('.ant-table-tbody tr').first().locator('.ant-btn-link').first();

    if (await firstStrategyLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      const strategyName = await firstStrategyLink.textContent();

      await firstStrategyLink.click();
      await expect(page).toHaveURL(/\/strategies\/\d+/, { timeout: 10000 });
      await page.waitForLoadState('networkidle');

      // 不应显示"策略不存在"
      await expect(page.getByText('策略不存在')).not.toBeVisible({ timeout: 3000 });

      // 页面标题应包含详情
      if (strategyName) {
        await expect(page.getByText(strategyName, { exact: false })).toBeVisible({ timeout: 5000 });
      }
    }
  });

  test('应能通过侧边栏导航到策略管理', async ({ page }) => {
    // 先导航到其他页面
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // 通过侧边栏回到策略管理
    await navigateViaSidebar(page, '策略管理');
    await expect(page).toHaveURL(/\/strategies/);
    await expect(page.getByRole('heading', { name: '策略管理' })).toBeVisible();
  });

  test('列表不应显示已删除的策略', async ({ page }) => {
    await page.waitForTimeout(2000);

    // 检查表格中是否有包含"deleted"状态的行
    const statusCells = page.locator('.ant-table-tbody tr');
    const count = await statusCells.count();

    for (let i = 0; i < count; i++) {
      const rowText = await statusCells.nth(i).textContent();
      // 已删除的数据不应出现在默认列表中
      expect(rowText).not.toContain('deleted');
    }
  });
});
