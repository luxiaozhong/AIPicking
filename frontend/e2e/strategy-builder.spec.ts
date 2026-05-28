import { test, expect } from '@playwright/test';

test.describe('策略构建器', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/strategies/builder');
    await page.waitForLoadState('networkidle');
  });

  test('页面应正确加载策略构建器', async ({ page }) => {
    // 页面标题
    await expect(page.getByRole('heading', { name: '可视化构建策略' })).toBeVisible({ timeout: 10000 });

    // 面包屑导航
    await expect(page.locator('.ant-breadcrumb')).toBeVisible();

    // 策略名称输入框
    await expect(page.getByPlaceholder('策略名称')).toBeVisible();

    // 策略描述输入框
    await expect(page.getByPlaceholder('策略描述')).toBeVisible();

    // 工具栏按钮
    await expect(page.getByRole('button', { name: 'AI 助手' })).toBeVisible();
    await expect(page.getByRole('button', { name: '保存策略' })).toBeVisible();
    await expect(page.getByRole('button', { name: '预览代码' })).toBeVisible();

    // 因子区域标题（无 emoji，使用图标）
    await expect(page.locator('.ant-card').filter({ hasText: '买入信号因子' })).toBeVisible();
    await expect(page.locator('.ant-card').filter({ hasText: '卖出信号因子' })).toBeVisible();
    await expect(page.locator('.ant-card').filter({ hasText: '风控因子' })).toBeVisible();
  });

  test('应能搜索因子', async ({ page }) => {
    const searchInput = page.getByPlaceholder('搜索因子...');
    await expect(searchInput).toBeVisible();

    // 输入搜索关键词
    await searchInput.fill('均线');
    await page.waitForTimeout(800);

    // 清空搜索
    await searchInput.clear();
    await page.waitForTimeout(500);
  });

  test('应能添加买入因子', async ({ page }) => {
    await page.waitForTimeout(1000);

    // 展开第一个分类
    const firstCategory = page.locator('.ant-collapse-header').first();
    if (await firstCategory.isVisible()) {
      await firstCategory.click();
      await page.waitForTimeout(300);

      // 点击第一个因子
      const firstFactor = page.locator('.ant-collapse-content-box > div').first();
      if (await firstFactor.isVisible()) {
        await firstFactor.click();

        // 验证成功消息
        await expect(page.locator('.ant-message-success')).toContainText('已添加', { timeout: 5000 });

        // 因子应出现在买入信号区域
        await expect(page.locator('.ant-card').filter({ hasText: '买入信号因子' }).locator('.ant-empty')).not.toBeVisible({ timeout: 3000 });
      }
    }
  });

  test('应能删除已添加的因子', async ({ page }) => {
    // 先添加一个因子
    await page.waitForTimeout(1000);
    const firstCategory = page.locator('.ant-collapse-header').first();

    if (await firstCategory.isVisible()) {
      await firstCategory.click();
      await page.waitForTimeout(300);

      const firstFactor = page.locator('.ant-collapse-content-box > div').first();
      if (await firstFactor.isVisible()) {
        await firstFactor.click();
        await page.waitForTimeout(500);

        // 点击删除按钮（危险按钮）
        const deleteButton = page.locator('.ant-btn-dangerous').first();
        if (await deleteButton.isVisible()) {
          await deleteButton.click();
        }
      }
    }
  });

  test('应能展开和折叠因子分类', async ({ page }) => {
    await page.waitForTimeout(1000);

    const firstCategory = page.locator('.ant-collapse-header').first();
    if (await firstCategory.isVisible()) {
      // 展开
      await firstCategory.click();
      await page.waitForTimeout(500);

      // 折叠
      await firstCategory.click();
      await page.waitForTimeout(500);
    }
  });

  test('未输入策略名称时应提示警告', async ({ page }) => {
    const saveButton = page.getByRole('button', { name: '保存策略' });
    await saveButton.click();

    // 验证警告消息
    await expect(page.locator('.ant-message-warning')).toContainText('请输入策略名称', { timeout: 5000 });
  });

  test('应能切换 AI 助手面板', async ({ page }) => {
    // AI 助手面板初始应隐藏
    const aiPanelBefore = page.locator('.ant-card').filter({ hasText: /用自然语言描述|生成策略/ });
    await expect(aiPanelBefore).not.toBeVisible();

    // 点击 AI 助手按钮打开面板（inline Card，非 Modal）
    const aiButton = page.getByRole('button', { name: 'AI 助手' });
    await aiButton.click();
    await page.waitForTimeout(500);

    // 面板应可见
    await expect(aiPanelBefore).toBeVisible();

    // 验证面板内容
    await expect(aiPanelBefore.locator('textarea')).toBeVisible();
    await expect(page.getByRole('button', { name: '生成策略' })).toBeVisible();

    // 再次点击按钮关闭面板
    await aiButton.click();
    await page.waitForTimeout(300);
    await expect(aiPanelBefore).not.toBeVisible();
  });

  test('应能通过侧边栏导航离开构建器', async ({ page }) => {
    // 通过侧边栏导航到策略管理
    const menuItem = page.locator('.ant-menu-item').filter({ hasText: '策略管理' });
    if (await menuItem.isVisible()) {
      await menuItem.click();
      await page.waitForURL('**/strategies');
      await expect(page).toHaveURL(/strategies/);
    }
  });

  test('应能完整创建策略并返回列表', async ({ page }) => {
    // 1. 输入策略名称
    const strategyName = `E2E测试策略_${Date.now()}`;
    await page.getByPlaceholder('策略名称').fill(strategyName);

    // 2. 输入策略描述
    await page.getByPlaceholder('策略描述').fill('这是 E2E 测试创建的策略');

    // 3. 添加一个因子
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

    // 4. 保存策略
    const saveButton = page.getByRole('button', { name: '保存策略' });
    await saveButton.click();

    // 5. 验证保存成功
    await expect(page.locator('.ant-message-success')).toContainText('策略创建成功', { timeout: 15000 });

    // 6. 验证代码预览弹窗出现
    const codeModal = page.locator('.ant-modal').filter({ hasText: '生成的策略代码' });
    await expect(codeModal).toBeVisible({ timeout: 5000 });

    // 验证代码内容存在
    await expect(codeModal.locator('pre')).toBeVisible();

    // 7. 点击"返回策略列表"关闭弹窗并跳转
    const backButton = codeModal.getByRole('button', { name: '返回策略列表' });
    await backButton.click();

    // 8. 验证跳转到策略列表
    await expect(page).toHaveURL(/\/strategies/, { timeout: 10000 });
    await page.waitForLoadState('networkidle');

    // 9. 验证新策略出现在列表中
    await expect(page.locator('.ant-table')).toBeVisible();
  });
});
