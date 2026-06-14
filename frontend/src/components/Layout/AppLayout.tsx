import React from 'react';
import { Layout, Menu, Switch, Dropdown, Button, Space, theme } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  LineChartOutlined,
  BarChartOutlined,
  BulbOutlined,
  UserOutlined,
  TeamOutlined,
  LogoutOutlined,
  ReadOutlined,
  QuestionCircleOutlined,
  FireOutlined,
  DollarOutlined,
  StockOutlined,
  AimOutlined,
} from '@ant-design/icons';
import { useThemeStore } from '@/stores/themeStore';
import { useAuthStore } from '@/stores/authStore';
import { useOnboardingStore } from '@/stores/onboardingStore';

const { Header, Sider, Content, Footer } = Layout;

interface AppLayoutProps {
  children: React.ReactNode;
}

const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { token: themeToken } = theme.useToken();
  const { isDark, toggle } = useThemeStore();
  const { user, logout } = useAuthStore();
  const startTour = useOnboardingStore((s) => s.startTour);

  // 登录页不显示布局
  if (location.pathname === '/login') {
    return <>{children}</>;
  }

  const isAdmin = user?.role === 'admin';

  const menuItems = [
    {
      key: '/dashboard',
      icon: <DashboardOutlined />,
      label: '仪表盘',
    },
    {
      key: '/market-heat',
      icon: <FireOutlined />,
      label: '市场热度',
    },
    {
      key: '/fund-flow',
      icon: <DollarOutlined />,
      label: '资金流向',
    },
    {
      key: '/strategy-tracker',
      icon: <AimOutlined />,
      label: '当前策略',
    },
    {
      key: '/index-macd',
      icon: <StockOutlined />,
      label: '指数MACD',
    },
    {
      key: '/education',
      icon: <ReadOutlined />,
      label: '学习中心',
    },
    {
      key: '/strategies',
      icon: <LineChartOutlined />,
      label: '策略管理',
    },
    {
      key: '/backtests',
      icon: <BarChartOutlined />,
      label: '简单回测',
    },
    {
      key: '/backtests/trade-sim',
      icon: <BarChartOutlined />,
      label: '交易模拟',
    },
    ...(isAdmin
      ? [
          {
            key: '/users',
            icon: <TeamOutlined />,
            label: '用户管理',
          },
        ]
      : []),
  ];

  const selectedKey = (() => {
    if (location.pathname.startsWith('/users')) return '/users';
    if (location.pathname.startsWith('/backtests/trade-sim')) return '/backtests/trade-sim';
    if (location.pathname.startsWith('/backtests')) return '/backtests';
    if (location.pathname.startsWith('/strategies')) return '/strategies';
    if (location.pathname.startsWith('/education')) return '/education';
    if (location.pathname.startsWith('/market-heat')) return '/market-heat';
    if (location.pathname.startsWith('/fund-flow')) return '/fund-flow';
    if (location.pathname.startsWith('/strategy-tracker')) return '/strategy-tracker';
    if (location.pathname.startsWith('/index-macd')) return '/index-macd';
    if (location.pathname.startsWith('/dashboard')) return '/dashboard';
    return '/dashboard';
  })();

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  const userMenuItems = [
    {
      key: 'username',
      label: user?.username || '用户',
      disabled: true,
    },
    {
      key: 'role',
      label: isAdmin ? '管理员' : '普通用户',
      disabled: true,
    },
    { type: 'divider' as const },
    {
      key: 'onboarding',
      icon: <QuestionCircleOutlined />,
      label: '操作引导',
      onClick: () => startTour(),
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
      onClick: handleLogout,
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        breakpoint="lg"
        collapsedWidth={64}
        style={{ position: 'sticky', top: 0, height: '100vh' }}
      >
        <div
          style={{
            color: '#fff',
            fontSize: 16,
            fontWeight: 'bold',
            padding: '16px 24px',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
          }}
        >
          AIpicking
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: themeToken.colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            paddingRight: 24,
            borderBottom: `1px solid ${themeToken.colorBorderSecondary}`,
            gap: 16,
          }}
        >
          <Space size="small">
            <BulbOutlined style={{ fontSize: 16 }} />
            <Switch size="small" checked={isDark} onChange={toggle} />
          </Space>
          <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
            <Button type="text" icon={<UserOutlined />}>
              {user?.username || '用户'}
            </Button>
          </Dropdown>
        </Header>
        <Content style={{ padding: 24, background: themeToken.colorBgLayout, minHeight: 360 }}>
          {children}
        </Content>
        <Footer style={{ textAlign: 'center', fontSize: 12, color: '#999' }}>
          AIpicking ©{new Date().getFullYear()} Created with React + FastAPI
        </Footer>
      </Layout>
    </Layout>
  );
};

export default AppLayout;
