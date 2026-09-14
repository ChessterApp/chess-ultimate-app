# Wheel of Fortune — Coach Prize Wheel (`/games/wheel`)

## Context
Chesster (Next.js 16 frontend at `frontend/`, Clerk auth, Supabase project qtzujwiqzbgyhdgulvcd). Coaches at the physical chess school hold up a tablet/phone and spin a prize wheel for offline achievements. Reference aesthetic: ornate carnival wheel — gold rim with chasing light bulbs, rich red/cream segments, pointer at top, big center "SPIN" button. There is an existing `coach` area in `frontend/src/app/` — reuse its role-gating pattern.

## Requirements

### 1. Route & gating
- New page `frontend/src/app/games/wheel/page.tsx` (plus components under a sensible dir, e.g. `frontend/src/components/wheel/`).
- Gated to coach/admin roles via Clerk, same pattern as the existing coach pages. Non-coaches get redirected or a friendly "coaches only" screen.
- Fullscreen-friendly layout for tablet/phone held in landscape or portrait.

### 2. Wheel rendering (SVG, fully configurable)
- Segments drawn programmatically in SVG: each segment has `label` (free text, any language), `color`, optional `emoji`.
- Text curves/rotates along the segment and auto-scales so 6–30 segments all stay readable.
- Ornate frame look built with CSS/SVG layers: gold rim, bulbs around the rim with a CSS "chase" animation while spinning, pointer at top, glowing center button.
- Follow the hallmark design skill (available via the Claude Code skill loader at ~/.claude/skills/hallmark) for visual quality — carnival/vintage aesthetic, no generic AI-slop gradients.

### 3. Spin mechanics
- Pure client random: `crypto.getRandomValues`, equal probability per segment.
- Winner chosen FIRST, then a single CSS transform rotation animates to that segment: fast acceleration → long ease-out decay (4–6s total), several full revolutions.
- Tick sound per segment boundary crossing (WebAudio, no audio files needed — synthesized click is fine), confetti burst + winner modal on stop showing the segment label/emoji.
- Haptics via `navigator.vibrate` where supported. Spin button disabled during spin.

### 4. Config editor
- Same-page or sub-route editor, behind the same coach gate: add/remove/reorder segments, edit label + color + emoji.
- Wheel presets: coach can save multiple named wheels (e.g. "младшая группа", "старшая группа"), switch between them, duplicate one.
- Persistence: Supabase table `wheel_presets` (id, name, segments jsonb, created_by, created_at, updated_at) with a migration file following the repo's existing migration conventions (check how prior migrations are numbered/applied). RLS: coaches/admins read all, write own (or simplest policy consistent with existing tables).
- localStorage cache of last-used preset so the wheel still renders if network is flaky at the school.
- Ship 1 sensible default preset (seed or client-side fallback) so first load isn't empty.

### 5. i18n
- All UI chrome (spin button, editor labels, winner modal, gate message) via the app's existing i18n system — add keys for ALL locales the app currently supports (inspect existing locale files and match them). Segment labels are coach-typed free text, no translation needed.

### 6. Tests
- Unit tests for: winner-angle math (segment index → final rotation), random selection uniformity/bounds, preset serialization, and the config reducer/state logic.
- Component render test for the wheel with N segments.
- All existing tests must still pass. Run the frontend test suite before declaring done.

## Constraints
- No backend/Flask changes. No spin outcome tracking, no inventory, no ledger.
- Never `git add -A` — stage specific files. Conventional commit messages.
- Do NOT deploy — build must pass (`npm run build` in `frontend/`), but no deploy.sh, no push.

## Done means
- `/games/wheel` renders, spins smoothly, coach-gated, editor CRUD works against Supabase, presets persist, i18n keys in all locales, tests green, production build passes.
