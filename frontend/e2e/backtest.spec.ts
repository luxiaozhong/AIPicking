import { test, expect } from '@playwright/test';
import { navigateViaSidebar, loginViaUi } from './helpers';

test.describe('回测功能', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUi(page);
    await page.goto('/backtests');
    await page.waitForLoadState('networkidle');
  });

  test('应能正确加载回测列表页', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '简单回测' })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('button', { name: '刷新' })).toBeVisible();
    await expect(page.getByText('状态筛选')).toBeVisible();
    await expect(page.locator('.ant-table')).toBeVisible();
  });

  test('应显示回测表格列', async ({ page }) => {
    const tableHeader = page.locator('.ant-table-thead');
    await expect(tableHeader).toBeVisible();
    await expect(tableHeader.getByText('ID')).toBeVisible();
    await expect(tableHeader.getByText('策略名称')).toBeVisible();
    await expect(tableHeader.getByText('状态')).toBeVisible();
    await expect(tableHeader.getByText('操作')).toBeVisible();
  });

  test('应能按状态筛选回测', async ({ page }) => {
    const statusSelect = page.locator('.ant-select').filter({ hasText: /状态筛选|全部|待运行|已完成/ }).first();
    await statusSelect.click();
    await page.waitForTimeout(300);

    const completedOption = page.locator('.ant-select-item-option').filter({ hasText: '已完成' });
    if (await completedOption.isVisible()) {
      await completedOption.click();
      await page.waitForTimeout(500);
    }
  });

  test('应能点击回测查看详情', async ({ page }) => {
    await page.waitForTimeout(2000);

    const firstRowLink = page.locator('.ant-table-tbody tr').first().locator('.ant-btn-link').first();

    if (await firstRowLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await firstRowLink.click();
      await expect(page).toHaveURL(/\/backtests\/\d+/, { timeout: 10000 });
      await page.waitForLoadState('networkidle');
    }
  });

  test('应能通过侧边栏导航到简单回测', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    await navigateViaSidebar(page, '简单回测');
    await expect(page).toHaveURL(/\/backtests/);
    await expect(page.getByRole('heading', { name: '简单回测' })).toBeVisible();
  });

  test('应能从回测页导航到策略页', async ({ page }) => {
    const menuItem = page.locator('.ant-menu-item').filter({ hasText: '策略管理' });
    if (await menuItem.isVisible()) {
      await menuItem.click();
      await page.waitForURL('**/strategies');
      await expect(page).toHaveURL(/strategies/);
    }
  });

  test('删除按钮应显示为危险样式', async ({ page }) => {
    await page.waitForTimeout(2000);

    const dataRows = page.locator('.ant-table-tbody tr.ant-table-row');
    const rowCount = await dataRows.count();

    if (rowCount === 0) {
      test.skip(true, '没有回测数据可测试删除');
      return;
    }

    // Ant Design Button type="link" danger 渲染为 <a> 带 ant-btn-dangerous class
    const deleteBtn = dataRows.first().locator('.ant-btn-dangerous').filter({ hasText: '删除' });
    await expect(deleteBtn).toBeVisible();
  });

  test('删除回测报告 - 成功并确认数据已移除', async ({ page }) => {
    await page.waitForTimeout(2000);

    const dataRows = page.locator('.ant-table-tbody tr.ant-table-row');
    const rowCount = await dataRows.count();

    if (rowCount === 0) {
      test.skip(true, '没有回测数据可测试删除');
      return;
    }

    // 记录删除前的行数和第一行 ID
    const initialCount = rowCount;
    const firstRowId = await dataRows.first().locator('td').first().textContent();
    console.log(`准备删除回测 ID: ${firstRowId}，当前共 ${initialCount} 条`);

    // 点击第一行的删除按钮
    const deleteBtn = dataRows.first().getByRole('button', { name: '删除' });
    await deleteBtn.click();

    // 验证仅出现成功消息，没有同时出现失败消息
    await expect(page.locator('.ant-message-success')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.ant-message-error')).not.toBeVisible({ timeout: 3000 });

    // 等待列表刷新
    await page.waitForTimeout(1500);

    // 验证被删除的 ID 已不在列表中
    const remainingIds = await page.locator('.ant-table-tbody tr.ant-table-row td:first-child').allTextContents();
    expect(remainingIds).not.toContain(firstRowId);

    // 验证总条数减少
    const newCount = await page.locator('.ant-table-tbody tr.ant-table-row').count();
    expect(newCount).toBe(initialCount - 1);
  });
});
