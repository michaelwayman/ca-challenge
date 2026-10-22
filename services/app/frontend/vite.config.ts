import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ command }) => ({
  plugins: [react()],
  server: {
    // Same-origin in dev: forward the API and the compiled stylesheet to Django.
    proxy: { '/api': 'http://localhost:8000', '/static': 'http://localhost:8000' },
  },
  // One fixed-name ES module that Django serves as a static file. The stylesheet is
  // compiled separately from scss/, so the bundle imports no CSS.
  build: {
    outDir: '../static/js',
    emptyOutDir: true,
    lib: { entry: 'src/main.tsx', formats: ['es'], fileName: () => 'brand-list.js' },
  },
  define: command === 'build' ? { 'process.env.NODE_ENV': '"production"' } : {},
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
}));
