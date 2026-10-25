import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../auth/AuthContext';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Don't retry client errors (401, 403, 404)
        if (error instanceof Error && error.message.includes('403')) return false;
        if (error instanceof Error && error.message.includes('401')) return false;
        return failureCount < 1;
      },
      refetchOnWindowFocus: false,
      staleTime: 15 * 1000,
    },
  },
});

export const Providers: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider onLogoutCleanup={() => queryClient.clear()}>
        {children}
      </AuthProvider>
    </QueryClientProvider>
  );
};
