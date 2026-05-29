import { test, expect } from '@playwright/test';
import { loginViaUi, navigateViaSidebar } from './helpers';

test.describe('策略列表页', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/strategies');
    await page.waitForLoadState('networkidle');
  });

  test('应能正确加载策略列表页', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '策略管理' })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('button', { name: '可视化构建' })).toBeVisible();
    await expect(page.getByRole('button', { name: '上传策略' })).toBeVisible();
    await expect(page.getByPlaceholder('搜索策略名称')).toBeVisible();
    await expect(page.getByText('状态筛选').first()).toBeVisible();
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
    await searchInput.clear();
    await searchInput.press('Enter');
  });

  test('应能按状态筛选', async ({ page }) => {
    const statusSelect = page.locator('.ant-select').filter({ hasText: '状态筛选' }).first();
    await statusSelect.click();
    await page.waitForTimeout(300);
    const activeOption = page.locator('.ant-select-item-option').filter({ hasText: '活跃' });
    if (await activeOption.isVisible()) {
      await activeOption.click();
      await page.waitForTimeout(500);
    }
  });

  test('应显示策略表格列', async ({ page }) => {
    const tableHeader = page.locator('.ant-table-thead');
    await expect(tableHeader).toBeVisible();
    await expect(tableHeader.getByText('策略名称')).toBeVisible();
    await expect(tableHeader.getByText('状态')).toBeVisible();
    await expect(tableHeader.getByText('操作')).toBeVisible();
  });

  test('应能点击策略名称查看详情', async ({ page }) => {
    await page.waitForTimeout(2000);
    const firstStrategyLink = page.locator('.ant-table-tbody tr').first().locator('.ant-btn-link').first();
    if (await firstStrategyLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      const strategyName = await firstStrategyLink.textContent();
      await firstStrategyLink.click();
      await expect(page).toHaveURL(/\/strategies\/\d+/, { timeout: 10000 });
      await page.waitForLoadState('networkidle');
      await expect(page.getByText('策略不存在')).not.toBeVisible({ timeout: 3000 });
      if (strategyName) {
        await expect(page.getByText(strategyName, { exact: false })).toBeVisible({ timeout: 5000 });
      }
    }
  });

  test('应能通过侧边栏导航到策略管理', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await navigateViaSidebar(page, '策略管理');
    await expect(page).toHaveURL(/\/strategies/);
    await expect(page.getByRole('heading', { name: '策略管理' })).toBeVisible();
  });

  test('列表不应显示已删除的策略', async ({ page }) => {
    await page.waitForTimeout(2000);
    const statusCells = page.locator('.ant-table-tbody tr');
    const count = await statusCells.count();
    for (let i = 0; i < count; i++) {
      const rowText = await statusCells.nth(i).textContent();
      expect(rowText).not.toContain('deleted');
    }
  });
});

test.describe.serial('策略删除、恢复与彻底删除', () => {
  let testStrategyName: string;
  let testStrategyId: number;
  let authToken: string;

  test.beforeEach(async ({ page }) => {
    await loginViaUi(page);

    // 提取 JWT token 用于后续 API 调用
    authToken = await page.evaluate(() => localStorage.getItem('access_token')) || '';

    await page.goto('/strategies/builder');
    await page.waitForLoadState('networkidle');

    testStrategyName = `E2E删除测试_${Date.now()}`;
    await page.getByPlaceholder('策略名称').fill(testStrategyName);
    await page.getByPlaceholder('策略描述').fill('E2E delete/restore test');

    await page.waitForTimeout(1000);
    const firstCategory = page.locator('.ant-collapse-header').first();
    if (await firstCategory.isVisible()) {
      await firstCategory.click();
      await page.waitForTimeout(300);
      const firstFactor = page.locator('.ant-collapse-content-box > div').first();
      if (await firstFactor.isVisible()) {
        await firstFactor.click();
        await page.waitForTimeout(500);
      }
    }

    await page.getByRole('button', { name: '保存策略' }).click();
    await expect(page.locator('.ant-message-success').last()).toContainText('策略创建成功', { timeout: 15000 });

    // 关闭代码预览弹窗
    const codeModal = page.locator('.ant-modal').filter({ hasText: '生成的策略代码' });
    if (await codeModal.isVisible({ timeout: 5000 }).catch(() => false)) {
      await codeModal.getByRole('button', { name: '返回策略列表' }).click();
    }
    await expect(page).toHaveURL(/\/strategies/, { timeout: 10000 });
    await page.waitForLoadState('networkidle');

    // 获取新创建策略的 ID
    const searchInput = page.getByPlaceholder('搜索策略名称');
    await searchInput.fill(testStrategyName);
    await searchInput.press('Enter');
    await page.waitForTimeout(500);

    // 点击策略名称进入详情页，从 URL 提取 ID
    const strategyLink = page.locator('.ant-table-row').first().locator('.ant-btn-link').first();
    await expect(strategyLink).toBeVisible({ timeout: 5000 });
    await strategyLink.click();
    await page.waitForURL(/\/strategies\/\d+/, { timeout: 10000 });
    const url = page.url();
    testStrategyId = parseInt(url.match(/\/strategies\/(\d+)/)?.[1] || '0', 10);
    expect(testStrategyId).toBeGreaterThan(0);

    // 返回列表页
    await page.goto('/strategies');
    await page.waitForLoadState('networkidle');
  });

  test('应能软删除策略后在已删除视图恢复', async ({ page }) => {
    // 通过 API 软删除
    const deleteRes = await page.evaluate(async ({ url, token }) => {
      const res = await fetch(url, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
      const body = await res.text();
      return { ok: res.ok, status: res.status, body };
    }, { url: `/api/v1/strategies/${testStrategyId}`, token: authToken });
    expect(deleteRes.ok, `Delete failed: ${deleteRes.status} ${deleteRes.body}`).toBe(true);

    // 刷新页面 → 默认活跃视图不应该有该策略
    await page.goto('/strategies');
    await page.waitForLoadState('networkidle');
    const searchInput = page.getByPlaceholder('搜索策略名称');
    await searchInput.fill(testStrategyName);
    await searchInput.press('Enter');
    await page.waitForTimeout(500);
    // 活跃列表中不应包含已删除的策略（表格可能为空）
    const activeRows = page.locator('.ant-table-row');
    const activeCount = await activeRows.count();
    if (activeCount > 0) {
      await expect(activeRows.first()).not.toContainText(testStrategyName, { timeout: 5000 });
    }

    // 切换到"已删除"视图验证策略出现在已删除列表
    await searchInput.clear();
    await searchInput.press('Enter');
    await page.waitForLoadState('networkidle');
    const statusSelect = page.locator('.ant-select').filter({ hasText: new RegExp('活跃|状态筛选') }).first();
    await statusSelect.click();
    await page.waitForTimeout(300);
    await page.locator('.ant-select-item-option').filter({ hasText: '已删除' }).click();
    await page.waitForLoadState('networkidle');

    await searchInput.fill(testStrategyName);
    await searchInput.press('Enter');
    await page.waitForTimeout(500);

    const deletedRow = page.locator('.ant-table-row').first();
    await expect(deletedRow).toContainText(testStrategyName, { timeout: 5000 });
    // 已删除视图应显示"恢复"和"彻底删除"按钮
    await expect(deletedRow.locator('.ant-btn-link').filter({ hasText: '恢复' })).toBeVisible({ timeout: 3000 });
    await expect(deletedRow.locator('.ant-btn-dangerous').filter({ hasText: '彻底删除' })).toBeVisible({ timeout: 3000 });

    // 通过 API 恢复
    const restoreRes = await page.evaluate(async ({ url, token }) => {
      const res = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ status: 'active' }),
      });
      const body = await res.text();
      return { ok: res.ok, status: res.status, body };
    }, { url: `/api/v1/strategies/${testStrategyId}`, token: authToken });
    expect(restoreRes.ok, `Restore failed: ${restoreRes.status} ${restoreRes.body}`).toBe(true);

    // 刷新 → 活跃视图应重新出现该策略
    await page.reload();
    await page.waitForLoadState('networkidle');
    await searchInput.fill(testStrategyName);
    await searchInput.press('Enter');
    await page.waitForTimeout(500);

    const activeRow = page.locator('.ant-table-row').first();
    await expect(activeRow).toContainText(testStrategyName, { timeout: 5000 });
    // 应显示"删除"按钮（不是"恢复"或"彻底删除"）
    await expect(activeRow.locator('.ant-btn-dangerous').filter({ hasText: '删除' })).toBeVisible({ timeout: 3000 });
  });

  test('应能彻底删除策略（同时删除关联回测）', async ({ page }) => {
    // 通过 API 软删除
    const deleteRes = await page.evaluate(async ({ url, token }) => {
      const res = await fetch(url, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
      const body = await res.text();
      return { ok: res.ok, status: res.status, body };
    }, { url: `/api/v1/strategies/${testStrategyId}`, token: authToken });
    expect(deleteRes.ok, `Delete failed: ${deleteRes.status} ${deleteRes.body}`).toBe(true);

    // 通过 API 彻底删除
    const permanentRes = await page.evaluate(async ({ url, token }) => {
      const res = await fetch(url, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
      const body = await res.text();
      return { ok: res.ok, status: res.status, body };
    }, { url: `/api/v1/strategies/${testStrategyId}/permanent`, token: authToken });
    expect(permanentRes.ok, `Permanent delete failed: ${permanentRes.status} ${permanentRes.body}`).toBe(true);

    // 刷新页面，验证策略从所有视图消失
    await page.reload();
    await page.waitForLoadState('networkidle');

    // 活跃视图搜索不应找到
    let searchInput = page.getByPlaceholder('搜索策略名称');
    await searchInput.fill(testStrategyName);
    await searchInput.press('Enter');
    await page.waitForTimeout(500);
    let activeRows = page.locator('.ant-table-row');
    if (await activeRows.count() > 0) {
      await expect(activeRows.first()).not.toContainText(testStrategyName, { timeout: 5000 });
    }

    // 已删除视图也不应找到
    await searchInput.clear();
    await searchInput.press('Enter');
    await page.waitForLoadState('networkidle');
    const statusSelect = page.locator('.ant-select').filter({ hasText: new RegExp('活跃|状态筛选') }).first();
    await statusSelect.click();
    await page.waitForTimeout(300);
    await page.locator('.ant-select-item-option').filter({ hasText: '已删除' }).click();
    await page.waitForLoadState('networkidle');

    await searchInput.fill(testStrategyName);
    await searchInput.press('Enter');
    await page.waitForTimeout(500);

    // 不应该有任何行包含该策略名
    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();
    let found = false;
    for (let i = 0; i < rowCount; i++) {
      const rowText = await rows.nth(i).textContent();
      if (rowText?.includes(testStrategyName)) {
        found = true;
        break;
      }
    }
    expect(found).toBe(false);
  });
});
