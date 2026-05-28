import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import { themeConfig } from './theme/themeConfig';
import { useThemeStore } from './stores/themeStore';
import './assets/styles/global.css';

function Root() {
  const isDark = useThemeStore((s) => s.isDark);

  return (
    <ConfigProvider
      theme={{
        ...themeConfig,
        algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
      }}
      locale={zhCN}
    >
      <App />
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Root />
    </BrowserRouter>
  </React.StrictMode>
);
