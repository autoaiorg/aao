/**
 * Authentication types and interfaces
 * Memory-only security model.
 */

export type AuthRole = 'AGENT' | 'CEO';

export interface AuthState {
  token: string | null;
  role: AuthRole;
  isAuthenticated: boolean;
  principalId: string | null;
}

export interface AuthContextValue extends AuthState {
  setCredentials: (token: string, role: AuthRole, principalId?: string) => void;
  logout: () => void;
}
