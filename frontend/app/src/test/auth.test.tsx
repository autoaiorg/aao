import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import React from 'react';
import { AuthProvider, useAuth } from '../auth/AuthContext';

describe('AuthContext Memory-Only Model', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('keeps credentials strictly in memory and never writes to localStorage or sessionStorage', () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <AuthProvider>{children}</AuthProvider>
    );

    const { result } = renderHook(() => useAuth(), { wrapper });

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.token).toBeNull();

    act(() => {
      result.current.setCredentials('secret-in-memory-token', 'AGENT', 'agent-007');
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.token).toBe('secret-in-memory-token');
    expect(result.current.principalId).toBe('agent-007');

    // Verify localStorage & sessionStorage remain completely empty
    expect(localStorage.getItem('token')).toBeNull();
    expect(sessionStorage.getItem('token')).toBeNull();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('purges token and triggers onLogoutCleanup on logout', () => {
    const cleanupSpy = vi.fn();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <AuthProvider onLogoutCleanup={cleanupSpy}>{children}</AuthProvider>
    );

    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.setCredentials('temp-token', 'CEO');
    });

    expect(result.current.isAuthenticated).toBe(true);

    act(() => {
      result.current.logout();
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.token).toBeNull();
    expect(result.current.principalId).toBeNull();
    expect(cleanupSpy).toHaveBeenCalled();
  });
});
