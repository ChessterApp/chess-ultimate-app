# Fix Plan: Chat Routing + Language Detection

**Date:** 2026-02-08
**Issues:** 
1. Non-chess / general questions route to Mastra instead of Clawdbot
2. Russian (and other non-English) messages get English responses

---

## Root Cause Analysis

### Issue 1: Wrong routing

**File:** `src/lib/router/index.ts`

The `routeRequest()` function uses English keyword matching:
- `CLAWDBOT_KEYWORDS` — 28 English words ("coach", "help", "improve", etc.)
- `MASTRA_KEYWORDS` — 14 English words ("best move", "analyze", etc.)
- **Default (no match): `return 'mastra'`** ← THIS IS THE PROBLEM

When a user writes in Russian "Привет, кто такой высман", ZERO keywords match because they're all English. The function falls through to the default → `mastra`.

**Why this is wrong:** Mastra is a position analysis specialist with tools (Stockfish, FEN analysis). It should ONLY handle explicit position-related queries. Clawdbot (Claude) is the general-purpose coaching assistant that can handle any topic, any language, and has memory/personality.

### Issue 2: English responses to Russian queries

**File:** `src/pages/api/chat/stream.ts` line 176

```typescript
runtimeContext.set("lang", MASTRA_LANGUAGE);  // Always "English"
```

This sets the Mastra agent's language to "English" unconditionally. The system prompt contains `"YOU MUST SPEAK IN ENGLISH"` (replaced with the lang value). So even if the user writes in Russian, Mastra responds in English.

**File:** `src/server/mastra/agents/prompt.ts` lines 249, 397, 487, 594

All 4 system prompts have: `- YOU MUST SPEAK IN ENGLISH`

The `.replace("ENGLISH", lang)` in agents/index.ts substitutes the language, but `lang` always comes from the hardcoded env var `MASTRA_LANGUAGE=English`.

---

## Implementation Plan

### Step 1: Fix default route — Change from `mastra` to `clawdbot`

**File:** `src/lib/router/index.ts`

**Change:** The final `return 'mastra'` default → `return 'clawdbot'`

**Logic change:**
- If Mastra keywords match → route to Mastra (position analysis)
- If Clawdbot keywords match → route to Clawdbot (coaching)
- If NOTHING matches → route to Clawdbot (safe default)

This ensures that any unrecognized query (non-English, general questions, off-topic) goes to Clawdbot, which is better at handling free-form conversation.

**Also change** the `hasPositionReference` fallback:
```typescript
// Current: if no position reference and has "how"/"why" → clawdbot, else mastra
// New: if no keywords match at all → clawdbot (always)
```

**Exact edit in `routeRequest()`:**
```typescript
// OLD:
  // Default to Mastra for speed
  return 'mastra';

// NEW:
  // Default to Clawdbot — it handles general conversation, 
  // non-English queries, and off-topic questions better.
  // Mastra only activates on explicit position analysis keywords.
  return 'clawdbot';
```

### Step 2: Add Russian keywords to routing lists

**File:** `src/lib/router/index.ts`

Add Russian equivalents to both keyword arrays so Russian-speaking users get proper routing even before hitting the default:

**CLAWDBOT_KEYWORDS additions:**
```typescript
// Russian coaching keywords
'помоги', 'помощь', 'научи', 'учить', 'урок', 'тренировка',
'улучшить', 'прогресс', 'стратегия', 'план', 'совет',
'подскажи', 'объясни', 'расскажи', 'покажи',
'коучинг', 'тренер', 'наставник',
// Common non-chess queries (should go to Clawdbot)
'привет', 'здравствуй', 'кто такой', 'кто это', 'что такое',
'как дела', 'спасибо', 'пока',
// Kazakh greetings (Alex is in Kazakhstan)
'сәлем', 'рахмет',
```

**MASTRA_KEYWORDS additions:**
```typescript
// Russian position analysis keywords
'лучший ход', 'оценка', 'позиция', 'анализ', 'рассчитай',
'угроза', 'тактика', 'шах', 'мат', 'вариант',
```

### Step 3: Add language detection for Mastra

**File:** `src/pages/api/chat/stream.ts`

Add a simple language detection function that checks the user's query and passes the detected language to Mastra's runtime context.

**Add helper function:**
```typescript
/**
 * Simple language detection based on character scripts.
 * Returns the language name for the Mastra system prompt.
 */
function detectLanguage(text: string): string {
  // Count Cyrillic vs Latin characters
  const cyrillic = (text.match(/[\u0400-\u04FF]/g) || []).length;
  const latin = (text.match(/[a-zA-Z]/g) || []).length;
  const cjk = (text.match(/[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF]/g) || []).length;
  const arabic = (text.match(/[\u0600-\u06FF]/g) || []).length;
  
  const total = cyrillic + latin + cjk + arabic;
  if (total === 0) return MASTRA_LANGUAGE; // fallback to env setting
  
  if (cyrillic / total > 0.5) return 'Russian';
  if (cjk / total > 0.3) return 'Chinese';
  if (arabic / total > 0.3) return 'Arabic';
  
  return MASTRA_LANGUAGE; // Default to env setting for Latin-script languages
}
```

**Change in `handleMastra()`:**
```typescript
// OLD:
runtimeContext.set("lang", MASTRA_LANGUAGE);

// NEW:
const detectedLang = detectLanguage(query);
runtimeContext.set("lang", detectedLang);
```

This means:
- Russian query → `"YOU MUST SPEAK IN Russian"` in system prompt
- English query → `"YOU MUST SPEAK IN English"` (unchanged)
- Mixed/unclear → falls back to `MASTRA_LANGUAGE` env var

### Step 4: Update Clawdbot gateway to pass language hint

**File:** `src/lib/clawdbot/gateway.ts` (or `stream.ts` handleClawdbot)

The Chesster gateway (Claude) auto-detects language naturally, so this is mostly a nice-to-have. But we can add a language hint to the gateway message for consistency:

**In `handleClawdbot()` in stream.ts:**
```typescript
// OLD:
const response = await callGateway(userId, {
  action: "chat",
  payload: { message: query, fen },
  timeout: 60000,
});

// NEW:
const detectedLang = detectLanguage(query);
const langHint = detectedLang !== 'English' 
  ? `\n[User is writing in ${detectedLang}. Please respond in ${detectedLang}.]` 
  : '';
const response = await callGateway(userId, {
  action: "chat",
  payload: { message: query + langHint, fen },
  timeout: 60000,
});
```

### Step 5: Build and deploy

```bash
cd /root/chess-app/frontend
npm run build
cp -r public .next/standalone/public
mkdir -p .next/standalone/.next
cp -r .next/static .next/standalone/.next/static
cp src/pages/api/chat/transcribe-worker.py .next/standalone/transcribe-worker.py
export HOME=/root
pm2 restart chess-frontend
```

### Step 6: Test

**Test cases:**
1. Russian greeting: "Привет, как дела?" → should route to Clawdbot, respond in Russian
2. Russian non-chess: "Кто такой Каспаров?" → should route to Clawdbot, respond in Russian
3. English coaching: "Help me improve my endgame" → should route to Clawdbot, respond in English
4. English analysis: "What's the best move here?" → should route to Mastra, respond in English
5. Russian analysis: "Какой лучший ход?" → should route to Mastra, respond in Russian
6. Mixed: "Analyze this позиция" → should route to Mastra (has "analyze"), respond in English

---

## Files Changed

| File | Change | Risk |
|------|--------|------|
| `src/lib/router/index.ts` | Default route + Russian keywords | Low — only changes routing, not logic |
| `src/pages/api/chat/stream.ts` | Language detection + gateway hint | Low — additive change, fallback to current behavior |

## What This Does NOT Change

- Mastra agent code (`agents/index.ts`, `prompt.ts`) — untouched
- Clawdbot gateway code (`gateway.ts`) — message format only
- Frontend components — untouched
- useChesster hook — untouched

---

## Summary

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Wrong routing | English-only keywords + default=mastra | Default→clawdbot + Russian keywords |
| English responses | Hardcoded `MASTRA_LANGUAGE=English` | Detect language from query text |
