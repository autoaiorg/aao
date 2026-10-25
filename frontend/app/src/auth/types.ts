/**
 * Authentication types and interfaces
 * Memory-only security model with session isolation.
 */

export type AuthRole = 'AGENT' | 'CEO';

export interface AuthState {
  token: string | null;
  role: AuthRole;
  isAuthenticated: boolean;
  principalId: string | null;
  sessionId: string; // Rotated on login, logout and credential change to isolate caches
}

export interface AuthContextValue extends AuthState {
  setCredentials: (token: string, role: AuthRole, principalId?: string) => void;
  logout: () => void;
}
