# Streaming UX Polish — PRD

## Overview
The streaming SSE pipeline already works (Mastra textStream -> delta events -> onToken -> message content update). The task is to polish the UX to feel like ChatGPT/Claude/Telegram streaming.

## Changes Required

### 1. Blinking Cursor at End of Text While Streaming
Add a blinking cursor character (block cursor) at the end of the assistant message while tokens are arriving. Use a CSS keyframe animation with 530ms blink rate. The cursor should only show on the LAST assistant message when streaming is active.

Implementation: Add a `<span>` with a blinking block cursor after the message text. Conditionally render it when `isStreaming && isLastAssistantMessage`.

### 2. Two-Phase Loading Indicator
Currently the "Chesster is thinking..." spinner (CircularProgress) shows the ENTIRE time, controlled by `chatLoading=true` in useChesster state.

Fix:
- Add a new state `isStreaming` (boolean) to the useChesster hook
- Phase 1: Show spinner until the first token arrives (chatLoading=true, isStreaming=false)
- Phase 2: On first token, set isStreaming=true. Hide the spinner. Show blinking cursor at end of streaming text instead.
- On completion: set both chatLoading=false and isStreaming=false.

Pass `isStreaming` as a new prop to ChatTab. In ChatTab, change the loading indicator condition:
- Show spinner only when `chatLoading && !isStreaming` (waiting for first token)
- Show cursor when `isStreaming` (tokens arriving)

### 3. Simulated Streaming for Clawdbot Fallback
In `frontend/src/pages/api/chat/stream.ts`, the `handleClawdbot()` function sends the entire response as ONE delta chunk on line ~242. Instead, split the response into words and send them with small delays to simulate streaming feel.

```typescript
// Instead of: sendEvent({ delta: response.content });
// Do: split into words and send with delays
const words = response.content.split(/(\s+)/);
for (const word of words) {
  sendEvent({ delta: word });
  await new Promise(r => setTimeout(r, 15));
}
```

### 4. Deferred Markdown Rendering
Currently ReactMarkdown re-renders on every single token (expensive, causes layout flicker). During streaming, render the text as plain text with `whiteSpace: pre-wrap`. Once streaming completes (isStreaming becomes false), switch to full ReactMarkdown rendering.

In ChatTab.tsx, change the assistant message rendering (around line 1169-1215):
- If `isStreaming` AND this is the last assistant message: render as plain Typography (no ReactMarkdown)
- Otherwise: render with ReactMarkdown as before

### 5. Smooth Auto-Scroll During Streaming
The current auto-scroll (useEffect on chatMessages) may not fire on every token update since the code mutates the last message object rather than creating a new array entry.

Fix: In the onToken callback in useChesster.ts, after updating the message content, also trigger a scroll. Or: pass a scrollRef and call scrollIntoView in the token handler.

Simpler approach: In ChatTab, add a useEffect that watches for `isStreaming` and sets up an interval that scrolls to bottom every 100ms while streaming, then clears on streaming end.

## Key Files
- `frontend/src/components/tabs/ChatTab.tsx` — UI rendering, loading indicator, cursor, markdown toggle
- `frontend/src/hooks/useChesster.ts` — sendChatMessage, onToken/onComplete callbacks, state management
- `frontend/src/pages/api/chat/stream.ts` — handleClawdbot simulated streaming

## Architecture Notes
- `chatLoading` boolean controls the spinner (lines 1264-1318 in ChatTab.tsx)
- `onToken` callback (line 835-843 in useChesster.ts) mutates the last message content via setState
- ReactMarkdown renders assistant messages (line 1170-1215 in ChatTab.tsx)
- ChatTab receives `chatLoading` as a prop from useChesster
- The ChatTabProps interface is at line 49-72 in ChatTab.tsx
- State interface is around line 50-60 in useChesster.ts

## Constraints
- Do NOT change the SSE protocol format
- Do NOT change the Mastra agent integration
- Keep all existing functionality working
- Stack: Next.js (pages router), TypeScript, MUI, react-markdown
- Test by building: cd frontend && npm run build

## Testing
After implementation, run `cd frontend && npm run build` to verify no TypeScript errors or build failures.
