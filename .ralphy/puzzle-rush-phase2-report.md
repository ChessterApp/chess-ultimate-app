# Puzzle Rush — Phase 2 (Frontend) Report

Branch: `feat/puzzle-rush-frontend` (cut from `main` @ 5bbec2b0). **Not pushed, not deployed.** No backend changes.

## ⚠️ Needs Alex's eye first: VPS mirror on :3000 is down (my mistake)

My first `npm run build` ran in place in `frontend/`. I killed it within seconds when I realised it would overwrite `.next/standalone`, which PM2's `chess-frontend` serves. But Next had already wiped `.next` at build start.

- **Effect:** `curl localhost:3000/puzzle` now returns **500**.
- **Public sites are unaffected.** `https://chesster.io` and `https://chess-empire.chesster.io` are served by Vercel (checked: 200, `server: Vercel`).
- **Why I didn't fix it:** restoring the mirror needs a rebuild plus `pm2 restart`, which this brief puts out of scope, so I left it.
- **To restore from the deployed code:**
  1. Check out `main`.
  2. Run `export HOME=/root && cd /root/chess-app/frontend && NODE_OPTIONS=--max-old-space-size=2048 npm run build`.
  3. Copy `.next/static` and `public/` into `.next/standalone/`, and `.env.local` too (deploy.sh steps 2–3).
  4. Run `pm2 restart chess-frontend`.
  - Or just run `deploy.sh` from `main`. Note that it pushes.
- All later builds ran in an isolated git worktree under `/var/tmp`, which has since been removed.

## Commits
- `7d2325f9` feat(puzzle-rush): /api/puzzlerush proxy, API client and on-device storage
- `a3df62e0` feat(puzzle-rush): run state machine, run hook and wrong-move clank
- `cbec4b33` feat(puzzle-rush): /puzzle/rush page in Chesster Native v2
- `2852def8` feat(puzzle-rush): entry point from the /puzzle page
- `d9e66f9b` fix(puzzle-rush): keep Fraunces out of the shared fonts module
- (this report)

## Files
| File | What |
|---|---|
| `frontend/next.config.ts` | `/api/puzzlerush/:path*` rewrite. |
| `src/lib/puzzle-rush/types.ts` | Wire types for every endpoint. |
| `src/lib/puzzle-rush/api.ts` | Client. Sends a Clerk bearer, or `X-Guest-Token` for guests, plus the local IANA `tz`. It is not built on `apiFetch`, because that retries 4xx and drops bodies; a move must never be replayed, and the 409 `run_over` body carries the results. |
| `src/lib/puzzle-rush/storage.ts` | Last-played mode (fallback 5 min), rules-seen flag, guest token (sessionStorage only), guest bests (localStorage; Top + Best Today by local day). |
| `src/lib/puzzle-rush/runReducer.ts` | Pure run state machine with a skew-corrected server clock. |
| `src/hooks/usePuzzleRush.ts` | Timers, API calls, sounds, countdown alignment, deadline poll, guest-best recording. |
| `src/hooks/useSoundEffects.ts` | New `clank` sound type, synthesized with Web Audio. It respects the mute setting. |
| `src/components/puzzle-rush/*` | `PuzzleRush` (screens), `RushBoard`, `RunTiles`, `ModeSelect`, `RulesModal`, `ResultsModal`, `RunSummary` (+ `useRunReview`), `Leaderboard`, `fonts.ts` (Fraunces 800), and `PuzzleRush.module.css` (Native v2 tokens; light and dark scoped to the page). |
| `src/app/puzzle/rush/page.tsx` | The route. |
| `src/app/puzzle/page.tsx` | "Play Puzzle Rush →" entry banner under the breadcrumbs. |
| `messages/{en,ru,kz}.json` | New `puzzleRush` namespace in all 3 locales the puzzle pages use, plus `gamesHub.puzzleRush`. |

## Screens vs spec
| Spec | Status |
|---|---|
| S1 mode select | ✅ Order is 3 min / 5 min / Survival. Preselects the last-played mode, falling back to 5 min. Each card shows a "Best N" pill and a "Today N" line, `--` when empty. Play / Leaderboard tabs. Teal "Start Rush →" CTA. Static start-position board, hidden on mobile so the CTA stays above the fold. Guest note with a sign-in link. |
| S2 rules modal | ✅ Shown on first visit, and reopenable via "How it works". Esc closes it. |
| S3 countdown | ✅ 3/2/1 at 750 ms each, then Go!, as white numerals over the board. Pieces fade in during "3". **Server alignment:** the backend sets `started_at = create + 3 s`. The client converts `started_at` to client time using `server_now` skew, then schedules "3" at `started_at − 2250 ms` so that **Go! lands exactly on the server's `started_at`**. If create latency eats into that window, the countdown starts immediately. |
| S4 in-run | ✅ Board, then the score tile (SOLVED), timer tile (TIME LEFT, or TIME for Survival), hearts (lost left to right, 💔 greyscale), ✓/✕ grid with ratings, coach toast and ⚑ Quit. Turn line reads "**White** to move · puzzle rating N". |
| S5/S6 feedback | ✅ A 22px ✓/✕ badge on the destination square. The score pulses. The wrong move is left on the board. Holds are 160 ms for correct and 240 ms for wrong. |
| S7 transition | ✅ A cover with the board pattern goes up, the board remounts with the new position (no pieces sliding across), the cover fades over 170 ms, then the setup move animates (200 ms) with a teal last-move highlight. Input unlocks only after that. Orientation follows `puzzle.color`. |
| S8 run over | ✅ The board freezes with the last badge. The results modal appears 700 ms later. |
| S9 results modal | ✅ "New Personal Best!" (teal) / "Great Run!" (teal, ≥10) / "Tough One" (red). Ranks Personal · Today · All-time reveal staggered, title last. Stats: longest streak, highest solved, average time. Buttons: Play Again (Enter), New Rush, Share (Web Share, else clipboard), Esc closes. PB fires teal confetti via the existing `canvas-confetti`. Guests see `—` ranks and a sign-in prompt. |
| S10 summary + review | ✅ Big score, end reason, and a clickable 10-per-row grid. Clicking a tile opens an in-page drawer: the board switches to that puzzle, the drawer shows "Your moves" for misses and the solution as SAN chips, and ‹ › (or ← →) steps through. No re-solving. The ended run is fetched once (`GET /runs/:id`). |
| S11 leaderboard | ✅ Global/Personal × Daily/Weekly/All-time for the selected mode. Gold/silver/bronze squares for the top 3. The own row (`me`) is pinned first with a divider. Personal for guests shows a sign-in prompt. |
| Coach | ✅ Triggers on streak 5, streak 10, and the last heart (strikes = 2). It never mentions the position. |
| Timer | ✅ Display comes from the server `deadline`, skew-corrected. At the client-side deadline the board locks and the client asks `GET /runs/:id`, the source of truth because it lazily expires the run, retrying every 500 ms up to 12 times. A 409 `run_over` on a move also ends the run with the body's results. Survival shows elapsed time. Under 10 s the timer turns red. |
| Sounds | ✅ Correct uses `puzzle-solved.mp3` via `useSoundEffects('success')`. Wrong uses the synthesized metallic "clank" (no asset, no download). Move and capture play on user moves and setup moves. |
| Guests | ✅ Playable. The `guest_token` is kept in memory and sessionStorage and cleared at run end. Bests are on-device only. Sign-in prompts appear in S1, the results modal and Personal. |
| Responsive / themes | ✅ Light and dark tokens per §4. At ≤768px the score/timer/strikes tiles sit in a row **above** the board. Checked at 375px on select, in-run, results and summary: **0 px horizontal overflow**. |

## Tests
- New/updated suites:
  - `api.test.ts`: 5 tests. Bearer vs guest header, tz/query, 409 body kept without retry.
  - `runReducer.test.ts`: 12 tests. Correct with reply, a full multi-move puzzle, wrong → strike, 3 strikes end, server timeout, rejected move, coach cues, skew.
  - `storage.test.ts`: 7 tests. Mode preselect, guest bests by day.
  - `usePuzzleRush.test.ts`: 7 tests with fake timers. Countdown alignment, guest header, the wrong → next-puzzle pipeline, reply applied, deadline poll → timeout, 409, quit, 429.
  - `PuzzleRush.test.tsx`: 14 tests. PB / tough / guest results modal, Enter/Esc, results grid, page mode order + preselect + rules + guest bests, ru/kz render, i18n key parity.
  - `useSoundEffects.test.ts`: +2 tests for the clank.
- **Full frontend suite: 388/388 files, 3556/3556 tests passed.**
  - The first full run caught a regression I had introduced: importing `Fraunces` from the shared `lib/fonts.ts` broke 13 suites that mock `next/font/google`. Fixed in `d9e66f9b` by moving Fraunces into a puzzle-rush-local module.
- `npx tsc --noEmit`: clean for the whole project.
- `eslint` on all touched/new files: 0 errors, 0 warnings. The 8 warnings in `app/puzzle/page.tsx` were there before this change.
- `npm run build`: **succeeded** in an isolated worktree. The `/puzzle/rush` route was emitted.
- Manual run against the live local backend (headless Chromium, desktop light/dark plus 375px). The full loop worked: create → countdown → wrong move (✕, strike, clank path) → next puzzle → quit → results modal → summary review stepping → leaderboard.

## Deviations, and why
1. **Leaderboard rows show no avatar or flag.** The backend returns only `display_name`, and there's no avatar or country data to show.
2. **Personal leaderboard rows are labelled with the run date** rather than a name, because those rows are all the same user.
3. **Results header tone thresholds:** a PB gets teal "New Personal Best!"; a score ≥ 10 gets teal "Great Run!"; anything else gets red "Tough One". The spec only fixes PB and low, so 10 is my pick (`LOW_SCORE` in `ResultsModal.tsx`).
4. **No countdown ticks or low-time tick.** These were [INFERRED] in §3 and not in the brief's scope. Only correct, clank, move and capture sounds play.
5. **No Games-hub card.** The hub uses illustrated poster art (`public/games/*.webp`); a CSS stand-in would look off next to it. The sidebar "Puzzles" item already highlights on `/puzzle/rush`. **A poster asset is needed** if Alex wants it in the hub.
6. **Fraunces has no Cyrillic subset**, so ru/kz titles fall back to Georgia.
7. **A guest's PB is only on-device.** The confetti and "New Personal Best!" header for guests come from the localStorage comparison.

## Needs Alex's eye
- **The VPS :3000 mirror is down (see top).**
- **First-visit `SyncBoundary`:** on a browser's very first visit to any MUI route (`/puzzle`, so also `/puzzle/rush`), the page waits for PowerSync's first sync. In headless/dev it never finished. This is existing app behaviour, not Puzzle Rush. Worth confirming that guests aren't stuck on "Syncing your data…" in production.
- The thresholds in deviation 3, and whether the Games hub should get a poster.
- **Migration 049** must be applied in prod for signed-in bests and boards. The local backend responded fine (`/leaderboard` → empty entries).
