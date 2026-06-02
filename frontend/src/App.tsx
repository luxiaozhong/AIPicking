import React, { useEffect, useState } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import AppLayout from '@/components/Layout/AppLayout';
import ProtectedRoute from '@/components/Auth/ProtectedRoute';
import StrategyList from '@/pages/StrategyList';

import StrategyDetail from '@/pages/StrategyDetail';
import StrategyBuilder from '@/pages/StrategyBuilder';
import AIStrategyBuilder from '@/pages/AIStrategyBuilder';
import BacktestList from '@/pages/BacktestList';
import BacktestDetail from '@/pages/BacktestDetail';
import BacktestForm from '@/pages/BacktestForm';
import TradeSimDetail from '@/pages/TradeSimDetail';
import BatchTradeSimDetail from '@/pages/BatchTradeSimDetail';
import BatchBacktestList from '@/pages/BatchBacktestList';
import BatchBacktestDetail from '@/pages/BatchBacktestDetail';
import Dashboard from '@/pages/Dashboard';
import LoginPage from '@/pages/LoginPage';
import UserManagement from '@/pages/UserManagement';
import EducationPage from '@/pages/EducationPage';
import EducationDetailPage from '@/pages/EducationDetailPage';
import NotFound from '@/pages/NotFound';
import OnboardingWalkthrough from '@/components/OnboardingWalkthrough';
import { useAuthStore } from '@/stores/authStore';

const App: React.FC = () => {
  const [initializing, setInitializing] = useState(true);
  const { isAuthenticated, initialize } = useAuthStore();
  const location = useLocation();

  useEffect(() => {
    initialize().finally(() => setInitializing(false));
  }, []);

  if (initializing) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  // 未登录只显示 LoginPage
  if (!isAuthenticated && location.pathname !== '/login') {
    return <Navigate to="/login" replace />;
  }

  return (
    <AppLayout>
      <OnboardingWalkthrough />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/education"
          element={
            <ProtectedRoute>
              <EducationPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/education/:category/:slug"
          element={
            <ProtectedRoute>
              <EducationDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/strategies"
          element={
            <ProtectedRoute>
              <StrategyList />
            </ProtectedRoute>
          }
        />

        <Route
          path="/strategies/builder"
          element={
            <ProtectedRoute>
              <StrategyBuilder />
            </ProtectedRoute>
          }
        />
        <Route
          path="/strategies/ai-builder"
          element={
            <ProtectedRoute>
              <AIStrategyBuilder />
            </ProtectedRoute>
          }
        />
        <Route
          path="/strategies/:id"
          element={
            <ProtectedRoute>
              <StrategyDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/strategies/:id/backtest"
          element={
            <ProtectedRoute>
              <BacktestForm />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backtests"
          element={
            <ProtectedRoute>
              <BacktestList />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backtests/batch"
          element={
            <ProtectedRoute>
              <BatchBacktestList />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backtests/batch/:id"
          element={
            <ProtectedRoute>
              <BatchBacktestDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backtests/trade-sim/batch/:id"
          element={
            <ProtectedRoute>
              <BatchTradeSimDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backtests/trade-sim/:id"
          element={
            <ProtectedRoute>
              <TradeSimDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/backtests/:id"
          element={
            <ProtectedRoute>
              <BacktestDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/users"
          element={
            <ProtectedRoute requireAdmin>
              <UserManagement />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </AppLayout>
  );
};

export default App;
