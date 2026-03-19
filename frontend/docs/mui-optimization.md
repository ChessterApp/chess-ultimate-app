# MUI ThemeProvider Optimization

## Overview
The MUI (Material-UI) ThemeProvider is now conditionally loaded only on routes that actually use MUI components. This optimization reduces bundle size and improves performance for pages that don't use MUI.

## Implementation

### Routes that load MUI
The following routes will load the MUI ThemeProvider:
- `/debut` - Opening explorer with MUI components
- `/game` - Game viewer with MUI dialogs
- `/position` - Position analyzer with MUI controls
- `/puzzle` - Puzzle interface with MUI components
- `/repertoire` - Repertoire manager with MUI components
- `/practice` - Practice interface with MUI components
- `/courses` - Course interface with MUI components

### Routes that don't load MUI
The following routes will NOT load MUI:
- `/` - Landing page (uses only Tailwind CSS)
- `/sign-in` - Authentication page (Clerk components)
- `/sign-up` - Authentication page (Clerk components)
- `/profile` - Profile page (Tailwind CSS)
- `/settings` - Settings page (Tailwind CSS)
- Any other routes not listed above

## Technical Details

### Dynamic Import
The `MuiProvider` component is lazy-loaded using React's `lazy()` API:

```tsx
const MuiProvider = lazy(() => import("@/components/providers/MuiProvider"))
```

This creates a separate bundle chunk that's only loaded when needed.

### Route Detection
The `ClientShell` component checks the current pathname against a list of MUI routes:

```tsx
const MUI_ROUTES = ['/debut', '/game', '/position', '/puzzle', '/repertoire', '/practice', '/courses']
const needsMui = MUI_ROUTES.some(route => pathname?.startsWith(route))
```

### Conditional Wrapping
The content is conditionally wrapped with `MuiProvider` based on the route:

```tsx
if (needsMui) {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <MuiProvider>{content}</MuiProvider>
    </Suspense>
  )
}

return content
```

## Benefits

1. **Reduced Initial Bundle Size**: Pages that don't use MUI (landing, auth, profile) don't load the MUI library
2. **Faster Page Loads**: Less JavaScript to parse and execute on non-MUI pages
3. **Better Code Splitting**: MUI is in its own chunk that's loaded on-demand
4. **Maintains Functionality**: All existing MUI components continue to work as expected on routes that need them

## Tree-Shaking

Next.js and webpack will automatically tree-shake unused MUI components from the bundle. With this optimization:
- On routes without MUI, the entire MUI library is excluded
- On routes with MUI, only the components actually used are included

## Testing

The implementation includes tests that verify:
1. MUI provider is loaded on routes that need it (`/debut`, `/game`, etc.)
2. MUI provider is NOT loaded on routes that don't need it (`/`, `/sign-in`, etc.)
3. The application builds successfully
4. All functionality works as expected

## Maintenance

When adding new routes that use MUI components, add them to the `MUI_ROUTES` array in `ClientShell.tsx`:

```tsx
const MUI_ROUTES = ['/debut', '/game', '/position', '/puzzle', '/repertoire', '/practice', '/courses', '/your-new-route']
```
