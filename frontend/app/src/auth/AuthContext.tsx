/**
 * AuthContext
 * Enforces memory-only credential retention and strict session isolation.
 *
 * Rules:
 * - NO localStorage, sessionStorage, cookies, or URL storage.
 * - Rotates sessionId on login, logout, and credential updates.
 * - Logout completely purges the token, aborts pending queries, and cleans caches.
 * - Token is never logged or exposed in error messages.
 */

import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import type { AuthState, AuthContextValue, AuthRole } from './types';

const AuthContext = createContext<AuthContextValue | null>(null);

function generateSessionId(): string {
  return `sess-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

export interface AuthProviderProps {
  children: React.ReactNode;
  onLogoutCleanup?: () => void;
  onCredentialsChange?: () => void;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({
  children,
  onLogoutCleanup,
  onCredentialsChange,
}) => {
  const [auth, setAuth] = useState<AuthState>({
    token: null,
    role: 'AGENT',
    isAuthenticated: false,
    principalId: null,
    sessionId: generateSessionId(),
  });

  const setCredentials = useCallback(
    (token: string, role: AuthRole, principalId?: string) => {
      const trimmed = token.trim();
      if (!trimmed) return;

      if (onCredentialsChange) {
        onCredentialsChange();
      }

      setAuth({
        token: trimmed,
        role,
        isAuthenticated: true,
        principalId: principalId || null,
        sessionId: generateSessionId(),
      });
    },
    [onCredentialsChange]
  );

  const logout = useCallback(() => {
    if (onLogoutCleanup) {
      onLogoutCleanup();
    }

    setAuth({
      token: null,
      role: 'AGENT',
      isAuthenticated: false,
      principalId: null,
      sessionId: generateSessionId(),
    });
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
