import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: './',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/v1': {
        target: process.env.AAO_API_TARGET ?? 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/health': {
        target: process.env.AAO_API_TARGET ?? 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/ready': {
        target: process.env.AAO_API_TARGET ?? 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/test/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
    css: false,
    coverage: {
      reporter: ['text', 'json', 'html'],
    },
  },
});
