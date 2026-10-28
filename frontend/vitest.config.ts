import { defineConfig } from 'vitest/config';
import path from 'path';

// Node 25+ defines global localStorage/sessionStorage (localStorage is undefined
// without --localstorage-file). Vitest's jsdom environment does not override
// globals Node already has, so jsdom tests got Node's storage instead of
// jsdom's. Turn Node's off in the workers; older Node lacks the flag (28.10).
const nodeWebStorageOff = process.allowedNodeEnvironmentFlags.has('--experimental-webstorage')
  ? ['--no-experimental-webstorage']
  : [];

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    execArgv: nodeWebStorageOff,
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
