# Phase 5 — Online Play: Reskin to the Bot-Game Design — Report

Purely presentational reskin of the live-play UI to the bot-game design system.
No changes to `lib/live-game/`, `hooks/useLiveGame.ts`, `hooks/liveGameState.ts`,
any `app/api/` route, or Flask. No migrations.

## Deliverable 1 — Extract the celebratory core

- **New: `components/play/GameEndModalBase.tsx`** — the shared presentational
  core. Holds the layout, Lottie celebration, win chime, framer-motion
  choreography, reduced-motion handling, and the `gameEnd` outcome→title/copy
  mapping. Takes a generic `EndModalTheme` (`{ main, deep, tint, screenGradient }`),
  an `avatar` slot, an `actions` slot, `outcome`, `resigned`, and `opponentName`
  (interpolated into the existing `{botName}` title keys, so no locale churn).
- **`components/play/GameEndModal.tsx`** — now a thin wrapper over the base.
  Public API is byte-identical (`bot, outcome, resigned, open, onClose,
  onPlayAgain, onTryStronger, onChooseAnother`). It supplies the `BotAvatar` and
  the bot-specific action buttons (Play again / Try a stronger bot / Choose
  another bot) with the same testids and `readableText` styling.
- **Bot page (`app/play/page.tsx`) diff: ZERO lines.** `GameEndModal.test.tsx`
  passes unchanged (23 assertions, regression gate green).

## Deliverable 2 — `LiveGameEndModal`

- **New: `components/play/LiveGameEndModal.tsx`** — built on the shared core.
  - Initial-letter avatar (no portrait exists for online opponents).
  - Fixed online palette (`LIVE_PLAY_THEME`, blue→teal `#2E6BFF`), extracted to
    `lib/livePlayTheme.ts` and shared with the chrome.
  - Actions: **Rematch** POSTs `/api/games/challenge` with the same time control
    and colors swapped (my color → opposite `colorChoice`), copies the returned
    invite link (same clipboard pattern as `PlayFriendCard`), and `router.push`es
    to the new lobby; an inline error surfaces on failure without navigating.
    **Back to Play** pushes `/play`. No "try a stronger bot" equivalent.
- **New: `lib/liveOutcome.ts`** — maps terminal `{winnerId, result, reason}` +
  viewer id → `{ outcome: GameOutcome, resigned }`. `checkmate`/`flag` → win/loss,
  player `resign` → `resigned` loss, draws → `draw`, and `abort`/`expired` → `null`
  (no modal). The page opens the modal ~0.8s after the game ends (reduced-motion:
  immediate), dismissible with the board reviewable underneath.

## Deliverable 3 — In-game chrome

`GameHeader`/`GameDock` were **too bot-coupled to reuse directly** (rating pill,
world pill, thinking bubble vs. presence dot + clock), so — as the spec allows —
dedicated live chrome was built in the same visual language instead of forcing a
shared shell neither side would cleanly share:

- **New: `components/play/LiveGameHeader.tsx`** — rounded white card: opponent
  initial-letter avatar, name, presence dot (from `opponentConnected`), and the
  opponent clock (highlighted on their move).
- **New: `components/play/LiveGameDock.tsx`** — rounded white card in the
  `GameDock` language: player line + clock, draw-offer accept/decline banner,
  and Abort (when legal) / Offer draw / Resign. Resign uses the bot flow's
  kid-friendly confirm **dialog** (replacing the old inline confirm toggle).
- **`WorldScenery`** is **reused directly** behind the board with a neutral
  `tier="beginner"` theme.

## Deliverable 4 — Lobby / accept / expired + PlayFriendCard

- `app/play/live/[gameId]/page.tsx` restyled: loading, not-found, expired, lobby
  (copy-link), accept, aborted-review, and result screens all use the rounded
  white card language (fredoka titles, nunito body, `LIVE_PLAY_THEME` accents).
  All existing behavior, states, and copy semantics preserved (testids intact:
  `copy-link`, `accept-challenge`, `new-challenge`, `opponent-disconnected`,
  `draw-offer-banner`, `resign`, `confirm-resign`, `abort`, `offer-draw`,
  `accept-draw`, `decline-draw`).
- `PlayFriendCard.tsx` title aligned to the fredoka display font used by the
  surrounding play cards.

## Tests

- **New: `lib/__tests__/liveOutcome.test.ts`** — 12 tests: winner/end_reason →
  GameOutcome/resigned from both colors' POV, all draw reasons, abort/expired →
  null, and unresolved / spectator edge cases.
- **New: `components/play/__tests__/LiveGameEndModal.test.tsx`** — 10 tests:
  win/loss/resigned/draw states, initial-letter avatar, Rematch fires the
  challenge POST with swapped colors + copies the link + navigates, Rematch error
  path, Back to Play, dismiss, closed.
- **Extended: `__tests__/gameEnd-i18n.test.ts`** — added the 3 new live keys to
  `REQUIRED_KEYS` (parity test already enforced identical key sets).
- Regression gate green **unchanged**: `GameEndModal.test.tsx`,
  `GameHeader.test.tsx`, `GameDock.test.tsx`.

## i18n

New keys added to `en` / `kz` / `ru`: `rematchCreating`, `rematchFailed`,
`backToPlay`. Key sets stay identical across locales.

## Verification

- `npx vitest run` → **196 files / 1807 tests passing** (1785 baseline + 22 new).
- `npx tsc --noEmit` → zero new errors in touched files (pre-existing errors in
  unrelated files unchanged).
- `npx eslint` on all touched files → clean (0 errors, 0 warnings).

## Deviations

- **Opponent name/avatar:** the phase 1–4 data model exposes only Clerk ids
  (`whiteId`/`blackId`/`opponentId`), no display name, and resolving a username
  would require a new API/profile lookup (out of scope — "purely presentational,
  no API changes"). The chrome/modal therefore label the opponent generically as
  "Opponent" with an initial-letter avatar. Wiring a real username is a natural
  follow-up once a profile endpoint exists.
- **Chrome built fresh, not extracted:** unlike the modal (a genuinely shared
  celebration core), `GameHeader`/`GameDock` share little concrete structure with
  the live chrome, so live-specific components were authored in the shared visual
  language rather than extracting a thin shell. Their tests stay green trivially
  (files untouched).
- **Resign confirm** moved from the old inline two-button toggle to the bot
  flow's kid-friendly confirm dialog (deliverable 3's explicit intent); testids
  `resign` / `confirm-resign` preserved.
