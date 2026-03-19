# ISR Headers Configuration

## Overview

This document explains how cache headers are configured for pages using Incremental Static Regeneration (ISR) in the Chesster application.

## Configuration

Headers for ISR pages are configured in `next.config.ts` using the `headers()` function.

### Landing Page (`/`)

The landing page uses ISR with a revalidation period of 3600 seconds (1 hour), configured in `src/app/page.tsx`:

```typescript
export const revalidate = 3600
```

Corresponding cache headers in `next.config.ts`:

```typescript
{
  source: '/',
  headers: [
    {
      key: 'Cache-Control',
      value: 'public, s-maxage=3600, stale-while-revalidate=7200',
    },
  ],
}
```

### Cache Control Directives

- **`public`**: The response can be cached by any cache (browsers, CDNs, etc.)
- **`s-maxage=3600`**: Shared caches (CDNs) can serve cached content for 3600 seconds (1 hour)
- **`stale-while-revalidate=7200`**: Allows serving stale content for up to 7200 seconds (2 hours) while revalidating in the background

### Benefits

1. **Performance**: CDNs can serve cached pages without hitting the origin server
2. **Fresh Content**: Content is revalidated every hour automatically
3. **Resilience**: If revalidation fails, stale content can still be served for up to 2 hours
4. **Better UX**: Users get instant page loads from the cache

## Testing

Run the test suite to verify headers configuration:

```bash
npm test -- __tests__/next.config.test.ts
```

## Future Pages Using ISR

When adding ISR to new pages:

1. Add `export const revalidate = <seconds>` to the page component
2. Add corresponding cache headers in `next.config.ts` with matching `s-maxage` value
3. Set `stale-while-revalidate` to 2x the revalidate time for optimal resilience
4. Add tests in `__tests__/next.config.test.ts`

### Example

For a new page with 30-minute revalidation:

```typescript
// In the page component
export const revalidate = 1800

// In next.config.ts headers()
{
  source: '/your-page',
  headers: [
    {
      key: 'Cache-Control',
      value: 'public, s-maxage=1800, stale-while-revalidate=3600',
    },
  ],
}
```

## References

- [Next.js ISR Documentation](https://nextjs.org/docs/app/building-your-application/data-fetching/incremental-static-regeneration)
- [HTTP Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control)
- [Stale-While-Revalidate](https://web.dev/stale-while-revalidate/)
