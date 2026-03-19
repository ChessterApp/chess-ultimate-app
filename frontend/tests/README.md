# Frontend Tests

## Pre-render Tests

These tests verify that the landing page is properly serving pre-rendered HTML content for SEO and performance.

### Test Scripts

#### `prerender.test.sh`
Tests the production deployment at `https://vps.chesster.io/`

**Usage:**
```bash
bash tests/prerender.test.sh
```

**What it checks:**
- HTML response is not empty
- DOCTYPE declaration present
- Meta tags (description, Open Graph) present
- Title tag correct
- Hero headline pre-rendered
- Section headings pre-rendered
- Feature sections pre-rendered
- Footer CTA pre-rendered

#### `prerender-localhost.test.sh`
Tests the local deployment at `localhost:3000`

**Usage:**
```bash
bash tests/prerender-localhost.test.sh
```

**What it checks:**
- Service is running on port 3000
- HTML response is not empty
- DOCTYPE declaration present
- Meta tags present
- Content is pre-rendered (not just empty `<div id="__next"></div>`)

### Why Pre-rendering Matters

1. **SEO**: Search engines can crawl and index the actual content
2. **Performance**: Users see content immediately without waiting for JavaScript
3. **Social Sharing**: Meta tags are visible for link previews
4. **Accessibility**: Content is available even if JavaScript fails

### Expected Results

Both tests should pass with all checks green (✅).

If tests fail, verify:
- The application is built with `npm run build`
- The standalone server is running (`pm2 status chess-frontend`)
- The landing page is configured as a Server Component with ISR (hourly revalidation)
- Static assets are correctly copied to `.next/standalone/`

### Related Implementation

The landing page implements:
- Server-side rendering (SSR) via Server Components
- Incremental Static Regeneration (ISR) with hourly revalidation
- Client-side islands for interactive components (LanguageSelector, ScrollToTop)
- Pre-rendered meta tags for SEO and social sharing
