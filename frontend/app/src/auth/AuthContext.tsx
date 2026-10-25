/**
 * AuthContext
 * Enforces memory-only credential retention.
 *
 * Rules:
 * - NO localStorage, sessionStorage, cookies, or URL storage.
 * - Logout completely purges the token and clears client query caches.
 * - Token is never logged or exposed in error messages.
 */

import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import type { AuthState, AuthContextValue, AuthRole } from './types';

const AuthContext = createContext<AuthContextValue | null>(null);

export interface AuthProviderProps {
  children: React.ReactNode;
  onLogoutCleanup?: () => void;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children, onLogoutCleanup }) => {
  const [auth, setAuth] = useState<AuthState>({
    token: null,
    role: 'AGENT',
    isAuthenticated: false,
    principalId: null,
  });

  const setCredentials = useCallback((token: string, role: AuthRole, principalId?: string) => {
    const trimmed = token.trim();
    if (!trimmed) return;
    setAuth({
      token: trimmed,
      role,
      isAuthenticated: true,
      principalId: principalId || null,
    });
  }, []);

  const logout = useCallback(() => {
    setAuth({
      token: null,
      role: 'AGENT',
      isAuthenticated: false,
      principalId: null,
    });
    if (onLogoutCleanup) {
      onLogoutCleanup();
    }
  }, [onLogoutCleanup]);

  const value = useMemo(
    () => ({
      ...auth,
      setCredentials,
      logout,
    }),
    [auth, setCredentials, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
