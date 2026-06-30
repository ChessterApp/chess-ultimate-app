import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // Stub Next.js `server-only` guard so server modules are importable in tests.
      'server-only': path.resolve(__dirname, './test/stubs/server-only.ts'),
    },
  },
});
