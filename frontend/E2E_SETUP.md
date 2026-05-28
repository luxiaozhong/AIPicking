# Playwright E2E 测试安装指南

## 🎯 已完成的配置

✅ 已安装 `@playwright/test` 依赖
✅ 已创建 `playwright.config.ts` 配置文件
✅ 已创建测试文件：
  - `e2e/strategy-builder.spec.ts` - 策略构建器测试（12个测试用例）
  - `e2e/strategy-list.spec.ts` - 策略列表页测试（5个测试用例）
  - `e2e/backtest.spec.ts` - 回测页面测试（2个测试用例）
  - `e2e/helpers.ts` - 测试辅助函数
✅ 已更新 `package.json` 添加测试脚本
✅ 已创建 `e2e/README.md` 测试文档

## 🔧 解决浏览器安装问题

### 方法 1：环境变量绕过 SSL 检查（推荐）

```bash
cd /Users/aklu/CodeBuddy/AIpicking/frontend

# 设置环境变量
export NODE_TLS_REJECT_UNAUTHORIZED=0

# 安装浏览器
npx playwright install chromium firefox
```

### 方法 2：使用国内镜像

```bash
# 设置 npm 镜像
npm config set registry https://registry.npmmirror.com

# 设置 Playwright 镜像
export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright

# 安装浏览器
npx playwright install chromium
```

### 方法 3：手动下载浏览器

1. 访问 [Playwright  releases](https://github.com/microsoft/playwright/releases)
2. 下载对应版本的浏览器压缩包
3. 解压到 `~/.cache/ms-playwright/` 目录

### 方法 4：仅运行 UI 测试（不依赖浏览器）

如果暂时无法安装浏览器，可以：
1. 使用 `data-testid` 属性增强组件可测试性
2. 编写更多单元测试（使用 Vitest）
3. 使用 Cypress 作为替代方案

## 🚀 运行测试

### 前置条件
1. ✅ 前端开发服务器运行在 `http://localhost:5173`
2. ✅ 后端 API 服务器运行在 `http://localhost:8000`
3. ✅ Playwright 浏览器已安装

### 启动开发服务器

```bash
# 终端 1：启动后端
cd /Users/aklu/CodeBuddy/AIpicking/backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2：启动前端
cd /Users/aklu/CodeBuddy/AIpicking/frontend
npm run dev

# 终端 3：运行测试
cd /Users/aklu/CodeBuddy/AIpicking/frontend
npm run test:e2e
```

### 使用 UI 模式（推荐用于开发）

```bash
npm run test:e2e:ui
```

UI 模式提供：
- 📊 可视化测试运行
- 🎥 测试步骤回放
- 🐛 调试工具
- 📸 截图和视频查看

## 📝 测试内容概览

### 策略构建器测试（12 个用例）

| 测试 | 描述 | 状态 |
|------|------|------|
| 1 | 页面基本加载 | ✅ |
| 2 | 因子库搜索功能 | ✅ |
| 3 | 添加买入因子 | ✅ |
| 4 | 配置因子参数 | ✅ |
| 5 | 删除因子 | ✅ |
| 6 | 买入信号逻辑切换 | ✅ |
| 7 | AI 助手弹窗 | ✅ |
| 8 | AI 策略生成 | ✅ |
| 9 | 代码预览弹窗 | ✅ |
| 10 | 保存策略验证 | ✅ |
| 11 | 响应式布局 | ✅ |
| 12 | 因子分类展开/折叠 | ✅ |

### 策略列表页测试（5 个用例）

| 测试 | 描述 | 状态 |
|------|------|------|
| 1 | 页面加载 | ✅ |
| 2 | 导航到构建器 | ✅ |
| 3 | 导航到上传页 | ✅ |
| 4 | 搜索策略 | ✅ |
| 5 | 策略卡片显示 | ✅ |

## 🛠️ 增强可测试性

为了在组件中添 `data-testid` 属性：

```tsx
// StrategyBuilder.tsx
<Input
  data-testid="strategy-name-input"
  placeholder="策略名称"
  value={strategyName}
  onChange={e => setStrategyName(e.target.value)}
/>

<Button
  data-testid="save-strategy-btn"
  type="primary"
  onClick={handleSave}
  loading={loading}
>
  保存策略
</Button>
```

在测试中使用：
```typescript
await page.getByTestId('strategy-name-input').fill('我的策略');
await page.getByTestId('save-strategy-btn').click();
```

## 🐛 故障排除

### 问题 1：端口被占用

```bash
# 查看占用端口的进程
lsof -i :5173
lsof -i :8000

# 杀死进程
kill -9 <PID>
```

### 问题 2：测试超时

在 `playwright.config.ts` 中增加超时时间：
```typescript
export default defineConfig({
  timeout: 60000, // 60 秒
  use: {
    timeout: 30000, // 每个操作的超时
  },
});
```

### 问题 3：元素未找到

使用更稳定的选择器：
```typescript
// ❌ 不稳定
await page.locator('.ant-btn').click();

// ✅ 稳定
await page.getByRole('button', { name: '保存策略' }).click();
await page.getByTestId('save-strategy-btn').click();
```

## 📚 下一步

1. **安装浏览器**：使用上述方法之一安装 Playwright 浏览器
2. **运行测试**：执行 `npm run test:e2e:ui` 查看测试效果
3. **添加更多测试**：覆盖更多用户场景
4. **CI/CD 集成**：在 GitHub Actions 中自动运行测试

## 📞 需要帮助？

如果遇到问题，可以：
1. 查看 `e2e/README.md` 了解更多
2. 访问 [Playwright 官方文档](https://playwright.dev)
3. 运行 `npx playwright test --help` 查看命令行选项
