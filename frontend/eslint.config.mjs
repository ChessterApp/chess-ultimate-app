import nextConfig from "eslint-config-next";

export default [
  ...nextConfig,
  {
    ignores: [
      "public/**",
      "node_modules/**",
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
    ],
  },
  {
    // New strict React 19 hooks rules introduced in eslint-plugin-react-hooks v7.
    // The codebase predates these — downgrade to warnings so they surface without
    // blocking the lint gate.
    rules: {
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/error-boundaries": "warn",
      "react-hooks/static-components": "warn",
      "react-hooks/immutability": "warn",
      "react-hooks/refs": "warn",
      "react-hooks/purity": "warn",
      "react-hooks/preserve-manual-memoization": "warn",
    },
  },
  {
    // `const module = await import(...)` is idiomatic in vitest tests; the
    // Next.js rule guards against CommonJS shadowing, not local consts.
    files: ["**/__tests__/**/*.{ts,tsx}", "**/*.test.{ts,tsx}"],
    rules: {
      "@next/next/no-assign-module-variable": "off",
    },
  },
  {
    // Stockfish WASM glue legitimately uses `const module` for WebAssembly compile.
    files: ["src/stockfish/**/*.ts"],
    rules: {
      "@next/next/no-assign-module-variable": "off",
    },
  },
];
