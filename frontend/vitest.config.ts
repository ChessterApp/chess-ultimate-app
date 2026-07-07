import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
  },
  // Bypass the app's PostCSS/Tailwind config for CSS imports pulled in by
  // components under test (e.g. chessground stylesheets); the Tailwind v4
  // PostCSS plugin isn't loadable in the Vitest transform pipeline.
  css: {
    postcss: { plugins: [] },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // Stub Next.js `server-only` guard so server modules are importable in tests.
      'server-only': path.resolve(__dirname, './test/stubs/server-only.ts'),
    },
  },
});
