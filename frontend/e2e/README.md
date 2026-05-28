# E2E 测试说明

使用 Playwright 进行端到端测试。

## 安装

```bash
# 安装依赖
cd frontend
npm install

# 安装 Playwright 浏览器（如果失败，见下方故障排除）
npx playwright install chromium
```

## 运行测试

```bash
# 运行所有测试
npm run test:e2e

# 使用 UI 模式（推荐用于开发）
npm run test:e2e:ui

# 调试模式
npm run test:e2e:debug

# 查看测试报告
npm run test:e2e:report
```

## 测试文件结构

```
e2e/
├── strategy-builder.spec.ts  # 策略构建器测试
├── strategy-list.spec.ts     # 策略列表页测试
├── backtest.spec.ts          # 回测页面测试
├── helpers.ts                # 测试辅助函数
└── README.md                 # 本文件
```

## 测试的页面

### 1. 策略构建器 (`/strategies/builder`)
- ✅ 页面加载
- ✅ 因子库搜索
- ✅ 添加/删除因子
- ✅ 配置因子参数
- ✅ 买入信号逻辑切换
- ✅ AI 助手弹窗
- ✅ 代码预览
- ✅ 保存策略验证

### 2. 策略列表页 (`/strategies`)
- ✅ 页面加载
- ✅ 导航测试
- ✅ 搜索功能

### 3. 回测页面 (`/backtests`)
- ✅ 页面加载
- ✅ 导航测试

## 编写新测试

```typescript
import { test, expect } from '@playwright/test';
import { fillStrategyInfo, saveStrategy } from './helpers';

test.describe('你的测试套件', () => {
  test('测试名称', async ({ page }) => {
    await page.goto('/your-page');
    // 测试逻辑
  });
});
```

## 故障排除

### 问题：self-signed certificate in certificate chain

这是企业网络环境导致的 SSL 证书问题。解决方法：

1. **设置环境变量**（临时）：
   ```bash
   export NODE_TLS_REJECT_UNAUTHORIZED=0
   npx playwright install chromium
   ```

2. **使用国内镜像**：
   ```bash
   export PLAYWRIGHT_BROWSERS_PATH=0
   export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
   npm install -D @playwright/test
   ```

3. **手动下载浏览器**：
   - 从 [Playwright 官网](https://playwright.dev) 手动下载浏览器
   - 解压到 `~/.cache/ms-playwright/`

### 问题：测试超时

增加超时时间：
```typescript
test('慢速测试', async ({ page }) => {
  test.slow(); // 超时时间 x3
  // ...
});
```

或在配置中全局设置：
```typescript
// playwright.config.ts
export default defineConfig({
  timeout: 60000, // 60 秒
});
```

## 最佳实践

1. **使用 `data-testid` 属性**：在组件中添加 `data-testid`，使测试更稳定
2. **避免硬编码等待**：优先使用 `waitForSelector` 而不是 `waitForTimeout`
3. **测试独立性**：每个测试应该能独立运行
4. **使用辅助函数**：将常用操作提取到 `helpers.ts`

## 示例：添加 data-testid

在组件中：
```tsx
<Button data-testid="save-strategy-btn">保存策略</Button>
```

在测试中：
```typescript
await page.getByTestId('save-strategy-btn').click();
```
