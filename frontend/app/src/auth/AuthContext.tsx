/**
 * AuthContext
 * Keeps agent credentials and CEO CSRF material in memory; CEO bearer is exchanged for an HttpOnly session cookie.
 *
 * Strict Volatile Memory Policy:
 * - Agent bearers and CEO CSRF material reside only in volatile runtime memory.
 * - CEO session secret is held only in a server-issued HttpOnly cookie; JS never reads or persists it.
 * - Rotates sessionId cryptographically on login, logout, and credential updates using crypto.randomUUID().
 * - Logout completely purges the token, aborts pending queries, and cleans caches.
 * - Token is never logged or exposed in error messages.
 */

import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import type { AuthState, AuthContextValue, AuthRole } from './types';

const AuthContext = createContext<AuthContextValue | null>(null);

function generateSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  }
  throw new Error(
    'CRITICAL SECURITY ERROR: Web Crypto API is unavailable. In-memory session IDs require cryptographic entropy and cannot fall back to pseudo-random generators.'
  );
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
    csrfToken: null,
    cookieSession: false,
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
        csrfToken: null,
        cookieSession: false,
        sessionId: generateSessionId(),
      });
    },
    [onCredentialsChange]
  );

  const setCeoCookieSession = useCallback((csrfToken: string) => {
    if (onCredentialsChange) onCredentialsChange();
    setAuth({
      token: null, role: 'CEO', isAuthenticated: true, principalId: null,
      csrfToken, cookieSession: true, sessionId: generateSessionId(),
    });
  }, [onCredentialsChange]);

  const logout = useCallback(() => {
    if (onLogoutCleanup) {
      onLogoutCleanup();
    }

    setAuth({
      token: null,
      role: 'AGENT',
      isAuthenticated: false,
      principalId: null,
      csrfToken: null,
      cookieSession: false,
      sessionId: generateSessionId(),
    });
  }, [onLogoutCleanup]);

  const value = useMemo(
    () => ({
      ...auth,
      setCredentials,
      setCeoCookieSession,
      logout,
    }),
    [auth, setCredentials, setCeoCookieSession, logout]
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
