import { test, expect } from '@playwright/test';
import { navigateViaSidebar, loginViaUi } from './helpers';

test.describe('批量回测功能', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUi(page);
  });

  // ============================================================
  // 批量回测列表页（现已合并到简单回测页面）
  // ============================================================

  test('应能加载简单回测页并切换到批量回测', async ({ page }) => {
    await page.goto('/backtests');
    await page.waitForLoadState('networkidle');

    // 统一页面标题为"简单回测"
    await expect(page.getByRole('heading', { name: '简单回测' })).toBeVisible({ timeout: 10000 });

    // 切换到批量回测 tab
    await page.locator('.ant-radio-button-wrapper').filter({ hasText: '批量回测' }).click();
    await page.waitForTimeout(300);

    await expect(page.locator('.ant-table')).toBeVisible();
  });

  test('应显示批量回测表格列', async ({ page }) => {
    await page.goto('/backtests');
    await page.waitForLoadState('networkidle');

    // 切换到批量回测 tab
    await page.locator('.ant-radio-button-wrapper').filter({ hasText: '批量回测' }).click();
    await page.waitForTimeout(300);

    const tableHeader = page.locator('.ant-table-thead');
    await expect(tableHeader).toBeVisible();
    await expect(tableHeader.getByText('名称')).toBeVisible();
    await expect(tableHeader.getByText('策略')).toBeVisible();
    await expect(tableHeader.getByText('日期范围')).toBeVisible();
    await expect(tableHeader.getByText('状态')).toBeVisible();
    await expect(tableHeader.getByText('进度')).toBeVisible();
    await expect(tableHeader.getByText('操作')).toBeVisible();
  });

  test('应能通过侧边栏导航到简单回测', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    await navigateViaSidebar(page, '简单回测');
    await expect(page).toHaveURL(/\/backtests/);
    await expect(page.getByRole('heading', { name: '简单回测' })).toBeVisible();
  });

  test('应能按策略筛选批量回测', async ({ page }) => {
    await page.goto('/backtests');
    await page.waitForLoadState('networkidle');

    // 切换到批量回测 tab
    await page.locator('.ant-radio-button-wrapper').filter({ hasText: '批量回测' }).click();
    await page.waitForTimeout(300);

    const strategySelect = page.locator('.ant-select').filter({ hasText: '按策略筛选' });
    await expect(strategySelect).toBeVisible();
    await strategySelect.click();
    await page.waitForTimeout(300);

    // 如果有选项则选择一个，没有则关闭
    const firstOption = page.locator('.ant-select-item-option').first();
    if (await firstOption.isVisible()) {
      await firstOption.click();
      await page.waitForTimeout(500);
    } else {
      // 没有可筛选的策略，关闭下拉
      await page.keyboard.press('Escape');
    }
  });

  // ============================================================
  // 批量回测表单 — 模式切换（BacktestForm 页面内部）
  // ============================================================

  test.describe('回测表单 - 批量模式', () => {
    test.beforeEach(async ({ page }) => {
      // 导航到策略列表，选择一个策略进入回测表单
      await page.goto('/strategies');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      // 尝试获取第一个策略的 ID 并直接导航到回测表单
      const firstRow = page.locator('.ant-table-tbody tr.ant-table-row').first();
      const hasData = await firstRow.isVisible({ timeout: 5000 }).catch(() => false);

      if (hasData) {
        // 从 URL 中提取策略 ID（点击链接后跳转）
        const firstStrategyLink = firstRow.locator('.ant-btn-link').first();
        await firstStrategyLink.click();
        await page.waitForURL(/\/strategies\/\d+/, { timeout: 10000 });
        await page.waitForLoadState('networkidle');

        // 尝试在详情页找到"运行回测"按钮（可能在页面顶部或 Tab 内）
        const runBtn = page.getByRole('button', { name: /运行回测/ });
        const hasRunBtn = await runBtn.isVisible({ timeout: 3000 }).catch(() => false);

        if (hasRunBtn) {
          await runBtn.click();
        } else {
          // 直接通过 URL 导航到回测表单页
          const currentUrl = page.url();
          const match = currentUrl.match(/\/strategies\/(\d+)/);
          if (match) {
            await page.goto(`/strategies/${match[1]}/backtest`);
          }
        }
        await page.waitForLoadState('networkidle');
      }
    });

    test('应显示模式切换按钮（单日/批量）', async ({ page }) => {
      const isOnFormPage = await page.url().includes('/backtest');
      if (!isOnFormPage) {
        test.skip(true, '无法进入回测表单页');
        return;
      }

      const singleRadio = page.locator('.ant-radio-button-wrapper').filter({ hasText: '单日回测' });
      const batchRadio = page.locator('.ant-radio-button-wrapper').filter({ hasText: '批量回测' });

      await expect(singleRadio).toBeVisible({ timeout: 5000 });
      await expect(batchRadio).toBeVisible();
    });

    test('默认应显示单日模式的日期选择器', async ({ page }) => {
      const isOnFormPage = await page.url().includes('/backtest');
      if (!isOnFormPage) {
        test.skip(true, '无法进入回测表单页');
        return;
      }

      // 单日模式默认选中
      const singleRadio = page.locator('.ant-radio-button-wrapper-checked').filter({ hasText: '单日回测' });
      await expect(singleRadio).toBeVisible({ timeout: 5000 });

      // 验证标签 "截止日" 存在
      await expect(page.locator('.ant-form-item').filter({ hasText: '截止日' }).first()).toBeVisible();
    });

    test('切换到批量模式应显示日期范围选择器', async ({ page }) => {
      const isOnFormPage = await page.url().includes('/backtest');
      if (!isOnFormPage) {
        test.skip(true, '无法进入回测表单页');
        return;
      }

      // 切换到批量模式
      await page.locator('.ant-radio-button-wrapper').filter({ hasText: '批量回测' }).click();
      await page.waitForTimeout(300);

      // 应显示日期范围标签
      await expect(page.locator('.ant-form-item').filter({ hasText: '日期范围' })).toBeVisible();
      // 应显示报告名称输入框
      await expect(page.locator('input[placeholder*="4月回测"]')).toBeVisible();
    });

    test('批量模式切回单日模式应恢复截止日选择器', async ({ page }) => {
      const isOnFormPage = await page.url().includes('/backtest');
      if (!isOnFormPage) {
        test.skip(true, '无法进入回测表单页');
        return;
      }

      // 切到批量
      await page.locator('.ant-radio-button-wrapper').filter({ hasText: '批量回测' }).click();
      await page.waitForTimeout(300);

      // 切回单日
      await page.locator('.ant-radio-button-wrapper').filter({ hasText: '单日回测' }).click();
      await page.waitForTimeout(300);

      // 应恢复截止日选择器
      await expect(page.locator('label.ant-form-item-required').filter({ hasText: '截止日' })).toBeVisible();
      await expect(page.locator('label').filter({ hasText: '日期范围' })).not.toBeVisible();
    });

    test('单日模式的截止日应有快捷选项', async ({ page }) => {
      const isOnFormPage = await page.url().includes('/backtest');
      if (!isOnFormPage) {
        test.skip(true, '无法进入回测表单页');
        return;
      }

      // 确保在单日模式
      const isSingleChecked = await page.locator('.ant-radio-button-wrapper-checked').filter({ hasText: '单日回测' }).isVisible().catch(() => false);
      if (!isSingleChecked) {
        await page.locator('.ant-radio-button-wrapper').filter({ hasText: '单日回测' }).click();
        await page.waitForTimeout(200);
      }

      // 点击日期选择器
      const datePicker = page.locator('.ant-picker').first();
      await datePicker.click();

      // 应显示快捷选项
      await expect(page.getByText('昨天')).toBeVisible({ timeout: 3000 });
      await expect(page.getByText('上周五')).toBeVisible();
      await expect(page.getByText('本月1日')).toBeVisible();
    });

    test('追踪天数复选框应始终可见', async ({ page }) => {
      const isOnFormPage = await page.url().includes('/backtest');
      if (!isOnFormPage) {
        test.skip(true, '无法进入回测表单页');
        return;
      }

      // 单日模式
      await expect(page.getByText('3天')).toBeVisible();
      await expect(page.getByText('7天')).toBeVisible();
      await expect(page.getByText('15天')).toBeVisible();

      // 切换到批量模式
      await page.locator('.ant-radio-button-wrapper').filter({ hasText: '批量回测' }).click();
      await page.waitForTimeout(300);

      // 追踪天数仍应可见
      await expect(page.getByText('3天')).toBeVisible();
      await expect(page.getByText('7天')).toBeVisible();
      await expect(page.getByText('15天')).toBeVisible();
    });

    test('目标股票输入框在两种模式下都可见', async ({ page }) => {
      const isOnFormPage = await page.url().includes('/backtest');
      if (!isOnFormPage) {
        test.skip(true, '无法进入回测表单页');
        return;
      }

      // 单日模式
      const stockInput = page.locator('input[placeholder*="300328.SZ"]');
      await expect(stockInput).toBeVisible();

      // 切到批量模式
      await page.locator('.ant-radio-button-wrapper').filter({ hasText: '批量回测' }).click();
      await page.waitForTimeout(300);

      // 输入框仍应可见
      await expect(stockInput).toBeVisible();
    });
  });

  // ============================================================
  // 批量回测详情页
  // ============================================================

  test.describe('批量回测详情页', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/backtests');
      await page.waitForLoadState('networkidle');
      // 切换到批量回测 tab
      await page.locator('.ant-radio-button-wrapper').filter({ hasText: '批量回测' }).click();
      await page.waitForTimeout(2000);
    });

    test('应能从列表页点击名称进入详情页', async ({ page }) => {
      const firstRowLink = page.locator('.ant-table-tbody tr').first().locator('.ant-btn-link').first();

      if (await firstRowLink.isVisible({ timeout: 5000 }).catch(() => false)) {
        await firstRowLink.click();
        await expect(page).toHaveURL(/\/backtests\/batch\/\d+/, { timeout: 10000 });
        await page.waitForLoadState('networkidle');

        // 顶部应有面包屑或标题
        await expect(page.getByRole('heading').first()).toBeVisible();
      } else {
        test.skip(true, '没有批量回测数据可查看');
      }
    });

    test('详情页应显示基本信息', async ({ page }) => {
      const firstRowLink = page.locator('.ant-table-tbody tr').first().locator('.ant-btn-link').first();

      if (!(await firstRowLink.isVisible({ timeout: 5000 }).catch(() => false))) {
        test.skip(true, '没有批量回测数据');
        return;
      }

      await firstRowLink.click();
      await page.waitForURL(/\/backtests\/batch\/\d+/, { timeout: 10000 });
      await page.waitForLoadState('networkidle');

      // 应显示描述信息
      const descriptions = page.locator('.ant-descriptions');
      await expect(descriptions).toBeVisible({ timeout: 5000 });

      // 应显示关键字段
      await expect(page.getByText('策略名称')).toBeVisible();
      await expect(page.getByText('状态')).toBeVisible();
      await expect(page.getByText('日期范围')).toBeVisible();
    });

    test('详情页应有返回列表按钮', async ({ page }) => {
      const firstRowLink = page.locator('.ant-table-tbody tr').first().locator('.ant-btn-link').first();

      if (!(await firstRowLink.isVisible({ timeout: 5000 }).catch(() => false))) {
        test.skip(true, '没有批量回测数据');
        return;
      }

      await firstRowLink.click();
      await page.waitForURL(/\/backtests\/batch\/\d+/, { timeout: 10000 });
      await page.waitForLoadState('networkidle');

      const backBtn = page.getByRole('button', { name: '返回列表' });
      await expect(backBtn).toBeVisible();

      await backBtn.click();
      // 返回简单回测页
      await expect(page).toHaveURL(/\/backtests(?!\/\w)/, { timeout: 10000 });
    });

    test('已完成的批量回测应显示每日结果折叠面板', async ({ page }) => {
      // 先检查列表里是否有已完成的报告
      const completedRow = page.locator('.ant-table-tbody tr').filter({ hasText: '已完成' }).first();
      const hasCompleted = await completedRow.isVisible({ timeout: 3000 }).catch(() => false);

      if (!hasCompleted) {
        test.skip(true, '没有已完成的批量回测数据');
        return;
      }

      // 点击已完成的报告
      const completedLink = completedRow.locator('.ant-btn-link').first();
      await completedLink.click();
      await page.waitForURL(/\/backtests\/batch\/\d+/, { timeout: 10000 });
      await page.waitForLoadState('networkidle');

      // 应显示 Collapse 面板
      const collapsePanels = page.locator('.ant-collapse-item');
      const panelCount = await collapsePanels.count();

      if (panelCount > 0) {
        // 第一个面板默认展开
        const firstPanel = collapsePanels.first();
        await expect(firstPanel.locator('.ant-collapse-content-active')).toBeVisible({ timeout: 5000 });
      }
    });
  });

  // ============================================================
  // 删除批量回测
  // ============================================================

  test.describe('删除批量回测', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/backtests');
      await page.waitForLoadState('networkidle');
      // 切换到批量回测 tab
      await page.locator('.ant-radio-button-wrapper').filter({ hasText: '批量回测' }).click();
      await page.waitForTimeout(2000);
    });

    test('删除按钮应显示为危险样式', async ({ page }) => {
      const dataRows = page.locator('.ant-table-tbody tr.ant-table-row');
      const rowCount = await dataRows.count();

      if (rowCount === 0) {
        test.skip(true, '没有批量回测数据可测试删除');
        return;
      }

      const deleteBtn = dataRows.first().locator('.ant-btn-dangerous').filter({ hasText: '删除' });
      await expect(deleteBtn).toBeVisible();
    });

    test('删除批量回测 - 成功并确认数据已移除', async ({ page }) => {
      const dataRows = page.locator('.ant-table-tbody tr.ant-table-row');
      const rowCount = await dataRows.count();

      if (rowCount === 0) {
        test.skip(true, '没有批量回测数据可测试删除');
        return;
      }

      const initialCount = rowCount;
      const firstName = await dataRows.first().locator('td').first().textContent();

      // 点击第一行的删除按钮
      const deleteBtn = dataRows.first().getByRole('button', { name: '删除' });
      await deleteBtn.click();

      // 等待 Popconfirm 弹出并确认
      const popconfirm = page.locator('.ant-popconfirm');
      await popconfirm.waitFor({ state: 'visible', timeout: 3000 }).catch(() => {});
      const okBtn = popconfirm.getByRole('button', { name: /确/ });
      const hasOkBtn = await okBtn.isVisible({ timeout: 2000 }).catch(() => false);
      if (hasOkBtn) {
        await okBtn.click();
      }

      // 等待删除完成并刷新
      await page.waitForTimeout(2000);

      // 验证数据已移除 — 名称不应再出现
      const remainingNames = await page.locator('.ant-table-tbody tr.ant-table-row td:first-child').allTextContents();
      expect(remainingNames).not.toContain(firstName);

      const newCount = await page.locator('.ant-table-tbody tr.ant-table-row').count();
      expect(newCount).toBeLessThan(initialCount);
    });
  });

  // ============================================================
  // 导航联动测试
  // ============================================================

  test('侧边栏高亮 - 简单回测页应高亮对应菜单项', async ({ page }) => {
    await page.goto('/backtests');
    await page.waitForLoadState('networkidle');

    const activeMenuItem = page.locator('.ant-menu-item-selected');
    await expect(activeMenuItem).toBeVisible({ timeout: 5000 });
    await expect(activeMenuItem.filter({ hasText: '简单回测' })).toBeVisible();
  });

  test('侧边栏高亮 - 批量回测详情页也应高亮简单回测菜单', async ({ page }) => {
    await page.goto('/backtests');
    await page.waitForLoadState('networkidle');
    // 切换到批量回测 tab
    await page.locator('.ant-radio-button-wrapper').filter({ hasText: '批量回测' }).click();
    await page.waitForTimeout(2000);

    const firstRowLink = page.locator('.ant-table-tbody tr').first().locator('.ant-btn-link').first();
    if (!(await firstRowLink.isVisible({ timeout: 5000 }).catch(() => false))) {
      test.skip(true, '没有批量回测数据');
      return;
    }

    await firstRowLink.click();
    await page.waitForURL(/\/backtests\/batch\/\d+/, { timeout: 10000 });
    await page.waitForLoadState('networkidle');

    // 侧边栏高亮应为"简单回测"
    const activeMenuItem = page.locator('.ant-menu-item-selected');
    await expect(activeMenuItem.filter({ hasText: '简单回测' })).toBeVisible({ timeout: 5000 });
  });

  test('简单回测页应默认为单策略回测 tab', async ({ page }) => {
    await page.goto('/backtests');
    await page.waitForLoadState('networkidle');

    // 默认选中"单策略回测"
    const singleRadio = page.locator('.ant-radio-button-wrapper-checked').filter({ hasText: '单策略回测' });
    await expect(singleRadio).toBeVisible({ timeout: 5000 });

    await expect(page.locator('.ant-table')).toBeVisible();
  });
});
