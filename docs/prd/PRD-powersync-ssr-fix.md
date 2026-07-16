# PRD: Fix PowerSync SSR Crash (getServerSnapshot)

## Problem
`@tanstack/react-db`'s `useLiveQuery` calls `useSyncExternalStore(subscribe, getSnapshot)` without a third `getServerSnapshot` argument. React requires this for SSR. Result: any page that imports hooks using `useLiveQuery` crashes with HTTP 500 during server rendering.

All 4 migrated hooks import `useLiveQuery` at the module top level, which means even when all feature flags are `false`, the SSR bundle includes the broken code path.

Additionally, the exported hook functions (`useUserGames`, `useOpeningRepertoire`, `useChatSessions`) conditionally call inner hooks (`flag ? usePowerSync() : useLegacy()`), which violates React's rules of hooks.

## Root Cause
- `frontend/node_modules/@tanstack/react-db/dist/esm/useLiveQuery.js` line 105-108: `useSyncExternalStore(subscribe, getSnapshot)` — missing 3rd arg
- 4 hooks import `useLiveQuery` at module level: `useSubscription.ts`, `useUserGames.ts`, `useOpeningRepertoire.ts`, `useChatSessions.ts`

## Fix Strategy
For each of the 4 hooks, restructure so the PowerSync path is **never imported during SSR**:

### Option: Lazy-load PowerSync hooks via `React.lazy` + dynamic import
Since all PowerSync feature flags default to `false`, and these hooks are client-only (`'use client'`), the simplest fix is:

1. **Move each PowerSync hook function into its own file** (e.g., `useUserGames.powersync.ts`)
2. **The main hook file only imports the legacy hook** at the module level
3. **When the feature flag is `true`, dynamically import the PowerSync hook** using a wrapper pattern

BUT this is complex. Simpler approach:

### Chosen approach: Guard `useLiveQuery` with a no-op wrapper for SSR

Create a single utility `frontend/src/lib/powersync/useSafeLiveQuery.ts` that wraps `useLiveQuery`:

```typescript
'use client';

import { useLiveQuery } from '@tanstack/react-db';
import { useSyncExternalStore } from 'react';

// Patch: provide getServerSnapshot to prevent SSR crash
// When running on server, return a disabled/empty state
const isServer = typeof window === 'undefined';

export function useSafeLiveQuery(...args: Parameters<typeof useLiveQuery>) {
  if (isServer) {
    // Return disabled state matching useLiveQuery's disabled return shape
    return {
      state: undefined,
      data: undefined,
      collection: undefined,
      status: 'disabled' as const,
      isLoading: false,
      isReady: true,
      isIdle: false,
      isError: false,
      isCleanedUp: false,
      isEnabled: false,
    };
  }
  return useLiveQuery(...args);
}
```

Wait — this won't work because you can't conditionally call hooks. The `useLiveQuery` call would still be in the server path of the module.

### ACTUAL chosen approach: Split hook files

**For each of the 4 hooks:**

1. **Keep the Legacy hook in the main file** — no `useLiveQuery` import
2. **Move the PowerSync hook to a separate file** (e.g., `useUserGames.powersync.ts`) — this file imports `useLiveQuery`
3. **In the main file, conditionally `React.lazy`-import or use a wrapper component** — OR simply use a React state + useEffect pattern to dynamically load:

Actually the simplest approach that doesn't break hooks rules:

### FINAL approach: Conditional rendering at the component level

No — too invasive. Let me think about this differently.

The REAL simplest fix: **Don't import `@tanstack/react-db` at module top level in hook files. Use dynamic import().**

For each hook file:
1. Remove the top-level `import { useLiveQuery } from '@tanstack/react-db'` and `import { eq } from '@tanstack/db'`
2. The PowerSync inner hook functions should live in separate files that DO have those imports
3. The main exported hook dynamically imports the PowerSync version only when the flag is on

### Files to change

#### 1. `frontend/src/hooks/useSubscription.ts`
- Remove top-level imports of `useLiveQuery`, `eq`, `usePowerSyncContext`
- Remove `useSubscriptionPowerSync` function entirely
- Move it to `useSubscription.powersync.ts`
- Change `useSubscriptionFetch` to NOT call `useSubscriptionPowerSync` when flag is false
- When `LOCAL_FIRST_SUBSCRIPTION` is true, use a state+useEffect pattern to dynamically load the PowerSync hook result

Wait, this still has the hooks-rules problem. You can't conditionally use a hook.

### TRULY FINAL approach: Wrapper component pattern

For each hook that has a PowerSync variant:
1. Move the PowerSync hook to a separate `.powersync.ts` file
2. The main file ONLY imports the legacy hook — zero `@tanstack/react-db` imports
3. Export a hook that ALWAYS calls the legacy hook
4. Create a thin `PowerSyncOverrideProvider` component that, when the flag is on, renders a context provider that overrides the hook's return value with the PowerSync version
5. This provider is dynamically imported via `next/dynamic` with `ssr: false`

This is too complex. Let me go with the simplest possible fix:

---

## SIMPLEST FIX (CHOSEN)

The `useLiveQuery` call crashes because `useSyncExternalStore` has no `getServerSnapshot`. The fix is to **patch `useLiveQuery` with a wrapper that provides `getServerSnapshot`**.

Create `frontend/src/lib/powersync/useSafeLiveQuery.ts`:

```typescript
'use client';

// Re-export useLiveQuery but ensure it doesn't crash during SSR.
// @tanstack/react-db's useLiveQuery uses useSyncExternalStore without
// getServerSnapshot. We patch this by re-exporting from a 'use client'
// boundary file that is guaranteed to never run on server.

export { useLiveQuery } from '@tanstack/react-db';
export { eq } from '@tanstack/db';
```

Then in each of the 4 hooks, change imports from:
```
import { useLiveQuery } from '@tanstack/react-db';
import { eq } from '@tanstack/db';
```
to:
```
import { useLiveQuery, eq } from '@/lib/powersync/useSafeLiveQuery';
```

BUT — this alone won't fix it because `'use client'` doesn't prevent server rendering. It only marks the client/server boundary. The code still runs on the server for SSR.

---

## ACTUAL SIMPLEST FIX

The REAL issue: the hooks files (useSubscription, useUserGames, etc.) import `useLiveQuery` at the top level, which means even when the PowerSync code path is never executed (flags are false), the import pulls in `@tanstack/react-db` into the SSR bundle, and when React processes the component tree it encounters `useSyncExternalStore` without `getServerSnapshot`.

**But wait** — if the flag is `false` and the PowerSync hook function is never called, `useSyncExternalStore` should NOT be called. The crash means the PowerSync path IS being invoked.

Looking at `useSubscription.ts` lines 115-126:
```typescript
export function useSubscriptionFetch(): SubscriptionState {
  const { isSignedIn, userId } = useAuth();
  const powerSyncState = useSubscriptionPowerSync(
    LOCAL_FIRST_SUBSCRIPTION ? (userId ?? undefined) : undefined,
  );
  const legacyState = useSubscriptionLegacy(
    LOCAL_FIRST_SUBSCRIPTION ? undefined : isSignedIn,
  );
  return LOCAL_FIRST_SUBSCRIPTION ? powerSyncState : legacyState;
}
```

**AH HA!** `useSubscriptionPowerSync` is ALWAYS called (line 118) — it just gets `undefined` userId. But inside that function, `useLiveQuery` is still called (it returns null/disabled when args are undefined, but the `useSyncExternalStore` call still happens).

Same issue for useUserGames (line 464-465) and useOpeningRepertoire (line 1119-1120) — they conditionally call hooks which violates rules of hooks AND still triggers the import.

**FIX:** For each hook, the exported function must call ONLY the legacy version when the flag is false, and ONLY the PowerSync version when the flag is true. Since both are hooks, and you can't conditionally call hooks, you need to structure it so only one path is present.

Since all flags are env vars resolved at build time (`process.env.NEXT_PUBLIC_*`), the compiler can dead-code-eliminate the PowerSync path IF we structure it as a static conditional.

### Implementation Plan

#### Task 1: Fix `useSubscription.ts`
- Remove the "always call both" pattern
- Since `LOCAL_FIRST_SUBSCRIPTION` is a build-time constant (`false`):
  ```typescript
  export function useSubscriptionFetch(): SubscriptionState {
    if (LOCAL_FIRST_SUBSCRIPTION) {
      return useSubscriptionPowerSync();
    }
    return useSubscriptionLegacy();
  }
  ```
  Wait, this still violates hooks rules at the type level even if one branch is dead.

  Better: keep the module-level conditional, but move the PowerSync hook to a lazy-loaded module:

  ```typescript
  // useSubscription.ts — ONLY legacy code, no @tanstack imports
  import { useState, useEffect, createContext, useContext } from 'react';
  import { useAuth } from '@clerk/nextjs';
  import { LOCAL_FIRST_SUBSCRIPTION } from '@/lib/feature-flags';

  // ... legacy code only ...

  export function useSubscriptionFetch(): SubscriptionState {
    const { isSignedIn } = useAuth();
    return useSubscriptionLegacy(isSignedIn);
  }
  ```

  Then for the PowerSync path, create a separate provider component loaded with `next/dynamic({ ssr: false })`.

  **BUT** this is a massive refactor and the flags are all `false` anyway.

### PRAGMATIC FIX

The most pragmatic fix that stops the crash NOW:

#### Option A: Patch the useLiveQuery call site
Create a monkey-patch that provides `getServerSnapshot` to `useSyncExternalStore`. This is hacky.

#### Option B: Move all @tanstack/react-db imports behind dynamic import()
In each hook file, instead of top-level import, use:
```typescript
const { useLiveQuery } = await import('@tanstack/react-db');
```
But you can't await in a hook.

#### Option C: (WINNER) Remove all useLiveQuery calls from hooks that run unconditionally
Since ALL flags are `false`, the PowerSync hooks are dead code. Remove the unconditional call pattern. Make each exported hook call ONLY the legacy version. Keep the PowerSync functions as dead code for now — they'll be activated later when the flag is turned on.

For `useSubscription.ts`:
```typescript
export function useSubscriptionFetch(): SubscriptionState {
  const { isSignedIn } = useAuth();
  // PowerSync path disabled until LOCAL_FIRST_SUBSCRIPTION is enabled
  // and @tanstack/react-db SSR support is resolved
  return useSubscriptionLegacy(isSignedIn);
}
```

For `useUserGames.ts`:
```typescript
export function useUserGames() {
  // PowerSync path disabled until LOCAL_FIRST_GAMES is enabled
  return useUserGamesLegacy();
}
```

For `useOpeningRepertoire.ts`:
```typescript
export function useOpeningRepertoire() {
  return useOpeningRepertoireLegacy();
}
```

For `useChatSessions.ts`:
```typescript
export const useChatSessions = () => {
  return useChatSessionsLegacy();
};
```

**AND critically**: remove the top-level imports of `useLiveQuery`, `eq`, `usePowerSyncContext` from these 4 files. Move them inside the PowerSync functions as dynamic imports, OR keep the imports but ensure the PowerSync functions are never called.

Actually — just removing the `useLiveQuery` calls from the hot path isn't enough if the MODULE IMPORT still pulls it in and triggers side effects. Let me check:

The `import { useLiveQuery } from '@tanstack/react-db'` is a static import. Even if `useLiveQuery` is never called, the module is still loaded into the bundle. BUT the `useSyncExternalStore` inside `useLiveQuery` is only called when the function is invoked, not at import time. So the crash only happens when `useLiveQuery` is CALLED.

**Therefore: just ensuring the PowerSync hooks are never called (by making the exported hooks always use legacy) should fix the crash, even if the imports remain.**

## FINAL IMPLEMENTATION PLAN

### Task 1: Fix useSubscription.ts (lines 115-126)
Change `useSubscriptionFetch` to only call legacy:
```typescript
export function useSubscriptionFetch(): SubscriptionState {
  const { isSignedIn } = useAuth();
  // TODO: Enable PowerSync path when LOCAL_FIRST_SUBSCRIPTION flag is on
  // and @tanstack/react-db provides getServerSnapshot for SSR
  return useSubscriptionLegacy(isSignedIn);
}
```

### Task 2: Fix useUserGames.ts (line 464-466)
Change to:
```typescript
export function useUserGames() {
  return useUserGamesLegacy();
}
```

### Task 3: Fix useOpeningRepertoire.ts (line 1119-1121)
Change to:
```typescript
export function useOpeningRepertoire() {
  return useOpeningRepertoireLegacy();
}
```

### Task 4: Fix useChatSessions.ts (line 523-525)
Change to:
```typescript
export const useChatSessions = () => {
  return useChatSessionsLegacy();
};
```

### Task 5: Run tests — `npx vitest run`
### Task 6: Run build — `npm run build`
### Task 7: Commit all changes

## Files Changed
1. `frontend/src/hooks/useSubscription.ts`
2. `frontend/src/hooks/useUserGames.ts`
3. `frontend/src/hooks/useOpeningRepertoire.ts`
4. `frontend/src/hooks/useChatSessions.ts`

## DO NOT
- Touch PowerSync provider, schema, connector, or collections
- Touch feature flag definitions
- Remove PowerSync hook functions (they'll be used when flags are enabled)
- Touch any Stockfish files
- Add any new dependencies
