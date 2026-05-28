import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requireAdmin?: boolean;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, requireAdmin = false }) => {
  const navigate = useNavigate();
  const { isAuthenticated, user, initialize } = useAuthStore();

  useEffect(() => {
    if (!isAuthenticated) {
      initialize().catch(() => {
        navigate('/login', { replace: true });
      });
    }
  }, []);

  if (!isAuthenticated) {
    return null;
  }

  if (requireAdmin && user?.role !== 'admin') {
    navigate('/dashboard', { replace: true });
    return null;
  }

  return <>{children}</>;
};

export default ProtectedRoute;
