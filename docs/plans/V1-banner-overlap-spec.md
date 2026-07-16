# V1 "Banner Overlap" — Themed Play Pages Rollout (all bots, all tiers)

## Goal
Redesign the bot-play setup screen and in-game sidebar so they carry the bot's
tier "world" theme (Fresh River / Emerald Forest / Volcano Arena / Sky Castle),
following the approved V1 "Banner Overlap" mockup. The chess board itself must
remain 100% unchanged.

## Pixel reference (approved mockup)
- HTML source: `/root/clawd/mockups/chesster-fresh-river/v1.html`
- Renders: `/root/clawd/mockups/chesster-fresh-river/fresh-river-v1-setup.png`
  and `fresh-river-v1-game.png`
The mockup shows the Fresh River (beginner) theme. Reproduce the structure and
translate colors from `TIER_WORLDS` so the same components render all 4 themes.
NOTE: the mockup shows a themed frame/glow around the board — DO NOT implement
that part. Board area stays exactly as it is today.

## Key files
- `src/app/play/page.tsx` — phase state machine (selecting → setup → playing).
  `selectedBot` is in scope for all phases.
- `src/components/play/GameSetup.tsx` — setup screen to redesign.
- `src/data/bots.ts` — `TIER_WORLDS`, `tierWorld(tier)` already exist with
  gradient + frame (main/deep/tint) + scenery colors per tier. Use these as the
  single source of truth. Do NOT invent new palette values.

## Tasks

### 1. Setup screen (`GameSetup.tsx`)
- Full-width world banner: tier `headerGradient`, wave-edge SVG bottom border,
  large world emoji watermark, world name + tier label.
- Bot avatar ~164px in a white/tinted ring, overlapping banner bottom edge into
  the card below. Fallback (bot emoji on tinted circle) if no avatar image.
- Below: bot name (Fredoka), rating pill, description, play-style chip —
  styled with the world's `frame` colors.
- Color picker (white/black/random) and Play button restyled in world
  `frame.main`/`deep` colors. Play button is the primary CTA, large.
- Back button keeps working.

### 2. Game screen (playing/ended phases in `play/page.tsx`)
- Extract the current inline opponent sidebar into a new
  `src/components/play/GameSidebar.tsx`.
- Sidebar card: gradient world header (short banner), 84px bot avatar
  overlapping the header edge, bot name + rating.
- "Thinking…" state becomes a themed speech bubble next to the avatar; keep the
  existing pulse/animation logic and all existing game-state props/behavior.
- Game-over panel and "New Game" button restyled in world colors.
- Subtle page background tint using the world `frame.tint` behind
  board + sidebar (keep it very light; must not affect board contrast).
- Mobile: sidebar collapses to a compact themed bar above the board; board
  width priority unchanged.

### 3. Board — ZERO changes
- No modifications to chessground CSS, board colors, highlights, piece sets,
  board frame, or anything inside the board container.

### 4. Avatars for advanced/master bots (`src/data/bots.ts`)
A parallel process is generating 8 new avatar files into
`frontend/public/bots/`: `viktor.webp`, `elena.webp`, `kenji.webp`,
`sofia.webp`, `magnus.webp`, `alexa.webp`, `kaspar.webp`, `garuda.webp`.
- Add `avatar: '/bots/<name>.webp'` to those 8 BOTS entries (viktor-1700,
  elena-1800, kenji-1900, sofia-2000, magnus-2100, alexa-2300, kaspar-2400,
  garuda-2600). Make no other edits to the BOTS array.
- The UI must gracefully fall back to the emoji avatar if the file 404s
  (files may land after you finish — that's OK).

### 5. Dark mode + i18n
- No hardcoded light-only hex for text/surfaces where the app has dark-mode
  support; follow existing conventions in the codebase.
- Any new user-facing strings go through the existing i18n mechanism used by
  the play components (check how GameSetup/bot page do it and follow suit).

### 6. Tests + verification
- Component tests for GameSetup and GameSidebar: renders correct world theme
  per tier (4 tiers), avatar fallback path, thinking-bubble state, game-over
  state.
- Run the frontend test suite and typecheck/lint; all must pass.
- `npm run build` must succeed.

## Constraints
- `export HOME=/root` before git commands.
- NEVER `git add -A` — stage specific files only.
- Do NOT commit this spec file.
- Do NOT touch backend, deploy scripts, or chessground CSS files.
- Conventional commit messages.
