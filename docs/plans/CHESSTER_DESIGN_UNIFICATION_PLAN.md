# Chesster Design Unification Plan

## Goal
Unify the design across all Chesster pages to use a consistent **Light Duolingo-style base** with proper **dark mode** support. Currently there are 3 incompatible design systems coexisting — this plan eliminates that.

## Current State (The Problem)

| Page Group | Styling | Background | Dark Mode? |
|------------|---------|------------|------------|
| Dashboard, Learn, Profile, Settings | Tailwind | `bg-gray-50`, white cards | Yes (CSS overrides) |
| Game, Position, Puzzle | MUI `purpleTheme` | `#1a0d2e` (always dark purple) | Always dark, ignores toggle |
| Debut | MUI Box + hardcoded hex | `#1a0d2e` / `#1a1a1a` | Always dark, ignores toggle |
| Editor | Inline styles | `#121212` | Always dark, ignores toggle |
| Sidebar, NavBar, BottomNav | Tailwind | `bg-white` | Yes (CSS overrides) |
| ChatSidebar | Tailwind gradients | `purple-950/40` | Always dark-ish |

**Root cause:** Game/Position/Puzzle/Debut/Editor bypass the Tailwind dark mode system entirely, using hardcoded dark backgrounds via MUI `sx` props and inline styles.

---

## Design Direction: Light Duolingo-style Base

**Light mode:** White/gray backgrounds, purple accents, rounded gamified cards (matches Dashboard/Learn/Settings today).

**Dark mode:** Dark neutral backgrounds (#0f0f0f / #1a1a1a), same purple accents but lighter, proper contrast ratios.

**Chess board area exception:** The board itself and its immediate container can use a slightly darker/neutral background in light mode (e.g. `bg-gray-100`) for visual contrast — the board is a canvas, not a UI element.

---

## Implementation Plan

### Phase 1: Design Token Foundation
**Files:** `globals.css`, `theme.ts`

**1.1 — Extend CSS custom properties for semantic theming**
Add to `:root` in `globals.css`:
```css
:root {
  /* Surface hierarchy (light mode) */
  --surface-page: #FAFAFA;        /* Page background (gray-50) */
  --surface-card: #FFFFFF;        /* Card/panel background */
  --surface-raised: #F4F4F5;     /* Raised elements (gray-100) */
  --surface-overlay: #FFFFFF;    /* Modals, dropdowns */
  --surface-board: #F0F0F0;      /* Chess board container */

  /* Text hierarchy */
  --text-primary: #18181B;       /* gray-900 */
  --text-secondary: #52525B;     /* gray-600 */
  --text-muted: #A1A1AA;         /* gray-400 */
  --text-on-primary: #FFFFFF;    /* White text on purple buttons */

  /* Borders */
  --border-default: #E4E4E7;     /* gray-200 */
  --border-subtle: #F4F4F5;      /* gray-100 */
  --border-strong: #D4D4D8;      /* gray-300 */

  /* Interactive */
  --interactive-hover: #F4F4F5;  /* gray-100 */
  --interactive-active: #EDE9FE; /* purple-100 */
}
```

Add dark mode overrides in `html.dark`:
```css
html.dark {
  --surface-page: #0f0f0f;
  --surface-card: #1a1a1a;
  --surface-raised: #252525;
  --surface-overlay: #1E1E1E;
  --surface-board: #1a1a1a;

  --text-primary: #F0F0F0;
  --text-secondary: #B0B0B0;
  --text-muted: #777;
  --text-on-primary: #FFFFFF;

  --border-default: #333;
  --border-subtle: #2a2a2a;
  --border-strong: #444;

  --interactive-hover: #252525;
  --interactive-active: rgba(139, 92, 246, 0.2);
}
```

**1.2 — Refactor MUI theme to follow CSS variables**
Update `theme.ts`:
- Make `purpleTheme` colors reference-only (documentation), not used for page backgrounds
- Create a single `chessterMuiTheme` that reads from CSS variables via `var()` where possible, or uses the same neutral palette
- Remove `agineTheme` and `darkGreyTheme` (unused, confirmed by audit)
- MUI components that appear on these pages (Button, Paper, Card, Typography, Chip, etc.) should use transparent/inherit backgrounds by default, letting the Tailwind surface classes control the page background

---

### Phase 2: Convert Dark-Hardcoded Pages to Tailwind
**Goal:** Every page uses the same `bg-[var(--surface-page)]` or Tailwind utility approach. No more hardcoded hex backgrounds.

**2.1 — Game page** (`/src/app/game/page.tsx`)
- Replace `<Box sx={{ backgroundColor: purpleTheme.background.main }}>` with `<div className="min-h-screen bg-gray-50 dark:bg-[#0f0f0f]">`
- Convert inner MUI `Box`/`Paper`/`Stack` elements to use Tailwind classes where they control layout/color
- Keep MUI components for complex widgets (dialogs, menus, tabs) but remove their hardcoded dark backgrounds
- The board container keeps a neutral background: `bg-gray-100 dark:bg-gray-900`
- Move panels (analysis, moves, chat) to white cards: `bg-white dark:bg-[#1a1a1a] rounded-2xl shadow-sm border border-gray-200 dark:border-[#333]`

**2.2 — Position page** (`/src/app/position/page.tsx`)
- Same pattern as Game: replace `purpleTheme.background.main` wrapper
- Convert to `<div className="min-h-screen bg-gray-50 dark:bg-[#0f0f0f]">`
- Panels become white cards with proper dark mode

**2.3 — Puzzle page** (`/src/app/puzzle/page.tsx`)
- Same pattern: remove `purpleTheme.background.main`
- Puzzle info cards, stats, timer → white cards with purple accents
- Board container stays neutral

**2.4 — Debut page** (`/src/app/debut/page.tsx`)
- Replace `bgcolor: { xs: '#1a0d2e', lg: '#1a1a1a' }` with Tailwind surface classes
- Convert the right panel, notation container from hardcoded `#222`, `#2a2a2a` to card pattern
- Opening tree/explorer UI → white cards

**2.5 — Editor page** (`/src/app/editor/page.tsx`)
- Replace `style={{ backgroundColor: "#121212" }}` with Tailwind class
- Convert to standard page pattern: `bg-gray-50 dark:bg-[#0f0f0f]`

---

### Phase 3: Component Consistency
**Goal:** Shared components follow the same visual language.

**3.1 — ChatSidebar** (`/src/components/ChatSidebar.tsx`)
- Currently uses `purple-950/40` gradient — this is the AI chat, so a slightly different treatment is OK
- But align it with the design system: in light mode use `bg-white border-r border-gray-200` with purple accent header
- In dark mode: `bg-[#1a1a1a] border-r border-[#333]`
- Keep the purple gradient only for the chat header/brand area, not the entire sidebar

**3.2 — Navigation components** (already light, mostly fine)
- DesktopSidebar: ✅ Already `bg-white` with proper active states
- NavBar: ✅ Already `bg-white`
- BottomNavigation: ✅ Already `bg-white`
- Add dark mode classes where missing: `dark:bg-[#1a1a1a] dark:border-[#333]` etc.
- Verify these respond to `html.dark` toggle (they should via CSS overrides, but explicit classes are more reliable)

**3.3 — Analysis/Evaluation components**
- Components like `EngineEvaluation`, `MoveList`, `OpeningExplorer` that live inside Game/Position pages
- Convert from MUI dark theme colors to card-based Tailwind approach
- Use semantic classes: `text-gray-900 dark:text-gray-100` instead of `color: purpleTheme.text.primary`

**3.4 — Gamification components** (StreakBanner, XPDisplay, LevelBadge)
- ✅ Already Tailwind-based and consistent
- Verify dark mode appearance

---

### Phase 4: MUI Component Overrides
**Goal:** MUI components that remain (dialogs, menus, complex widgets) match the design.

**4.1 — Create a theme-aware MUI wrapper**
- Single `ChessterThemeProvider` that detects `html.dark` class and switches between light/dark MUI palette
- Light palette: white paper, gray backgrounds, dark text
- Dark palette: #1a1a1a paper, #0f0f0f backgrounds, light text
- This replaces the hardcoded `agineTheme` approach

**4.2 — Apply in ClientShell.tsx**
- Wrap `{children}` in `<ChessterThemeProvider>` so all MUI components inherit correct palette
- The provider reads from `useDarkMode` hook and switches MUI theme accordingly

---

### Phase 5: Polish & QA

**5.1 — Gradient headers**
- Dashboard, Learn, Profile, Settings all use `bg-gradient-to-br from-purple-600 to-purple-800` headers
- Ensure Game, Position, Puzzle, Debut, Editor get the same header treatment for consistency
- Each page should have: gradient header → page title/breadcrumb → content cards

**5.2 — Card design consistency**
- All content cards across all pages: `bg-white dark:bg-[#1a1a1a] rounded-2xl shadow-sm border border-gray-200 dark:border-[#2a2a2a] p-4`
- Standardize padding, border-radius, shadow depth

**5.3 — Typography consistency**
- Page titles: `text-2xl font-bold text-gray-900 dark:text-gray-100`
- Section headers: `text-lg font-semibold text-gray-800 dark:text-gray-200`
- Body: `text-sm text-gray-600 dark:text-gray-400`
- Ensure no leftover MUI Typography with hardcoded colors

**5.4 — Interactive elements**
- All buttons use purple primary: `bg-purple-600 hover:bg-purple-700 text-white rounded-lg`
- Secondary buttons: `bg-gray-100 hover:bg-gray-200 text-gray-700 dark:bg-[#252525] dark:text-gray-300`
- Inputs: `bg-white dark:bg-[#1a1a1a] border border-gray-300 dark:border-[#444] rounded-lg`

**5.5 — Remove dead code**
- Delete `agineTheme` and `darkGreyTheme` from `theme.ts` (unused)
- Clean up any orphaned MUI color references

---

## File Change Summary

| File | Change Type | Scope |
|------|------------|-------|
| `globals.css` | Add semantic CSS variables + dark overrides | ~40 new lines |
| `theme.ts` | Rewrite: single theme, remove unused | Major refactor |
| `ClientShell.tsx` | Add MUI ThemeProvider wrapper | Small |
| `game/page.tsx` | Convert from MUI dark to Tailwind light | Major |
| `position/page.tsx` | Convert from MUI dark to Tailwind light | Major |
| `puzzle/page.tsx` | Convert from MUI dark to Tailwind light | Major |
| `debut/page.tsx` | Convert from hardcoded dark to Tailwind | Major |
| `editor/page.tsx` | Convert from inline dark to Tailwind | Medium |
| `ChatSidebar.tsx` | Align with design system | Medium |
| `DesktopSidebar.tsx` | Add explicit dark mode classes | Small |
| `Navbar.tsx` | Add explicit dark mode classes | Small |
| `BottomNavigation.tsx` | Add explicit dark mode classes | Small |
| Various analysis components | Convert MUI colors to Tailwind | Medium each |

---

## Execution Strategy

Given the scope (12+ files, some major), this should be broken into **sub-agent tasks** by phase:

1. **Phase 1** — Foundation (globals.css + theme.ts) — must go first
2. **Phase 2** — Page conversions (can be parallelized per page)
3. **Phase 3** — Component consistency (after pages are done)
4. **Phase 4** — MUI theme provider (can parallel with Phase 3)
5. **Phase 5** — Polish, QA, dead code removal

Each phase ends with a visual verification: build + check in browser.

---

## What Stays Dark

- **Chess board squares** — controlled by board theme system (Classic, Forest, etc.) — untouched
- **Chess piece styles** — SVG/image based — untouched
- **Board container** — gets a neutral `bg-gray-100 dark:bg-gray-900` treatment, slightly different from page background for visual separation
- **Loading screen animations** — keep the colorful wave (it's a splash, not a page)

## What Changes

- Every page background: light gray in light mode, near-black in dark mode
- Every panel/card: white in light mode, dark gray in dark mode
- All text: proper contrast in both modes
- Navigation: explicit dark mode support (not just CSS override hacks)
- MUI components: theme-aware via provider
