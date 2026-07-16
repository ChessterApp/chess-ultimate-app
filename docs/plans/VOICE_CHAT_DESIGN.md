# Voice Chat Feature — Design Document

**Date:** 2026-02-08  
**Author:** clawdbot  
**Status:** Plan — awaiting approval

---

## 1. Feature Overview

Add a microphone button to the Chesster chat input that lets users record voice messages. The audio is sent to the backend, transcribed via `faster-whisper` (already installed system-wide), and the resulting text is injected into the normal chat flow as if the user typed it.

**User experience:**
1. User taps/clicks the 🎤 microphone button (next to the Send button)
2. Button turns red + pulsing — recording in progress
3. User taps again (or clicks Stop) to end recording
4. A brief "Transcribing..." indicator appears
5. Transcribed text fills the chat input field (user can edit before sending)
6. OR: auto-sends immediately (configurable in settings)

---

## 2. Architecture

```
Browser (MediaRecorder API)
    │
    │  WebM/Opus audio blob
    ▼
Next.js API Route: POST /api/chat/transcribe
    │
    │  Receives base64 audio, saves to /tmp, calls whisper
    ▼
faster-whisper (system Python, tiny model)
    │
    │  Returns transcribed text
    ▼
Frontend receives text → populates chat input → user sends
```

### Why this architecture?

- **No new dependencies needed** — `faster-whisper` is already installed system-wide, `ffmpeg` is available
- **No new service to manage** — the transcription runs in the Next.js API route via a child process call to system Python
- **Privacy** — audio never leaves the server, transcribed on-device
- **Speed** — `tiny` model transcribes in ~1-2 seconds for short messages
- **No browser compatibility issues** — `MediaRecorder` API is supported in all modern browsers

---

## 3. Step-by-Step Implementation Plan

### Phase 1: Backend — Transcription API Route

**File:** `/root/chess-app/frontend/src/pages/api/chat/transcribe.ts`

**What it does:**
1. Receives POST with `{ audio: "<base64-encoded-audio>" }` 
2. Writes the audio to a temp file (`/tmp/chesster-voice-{uuid}.webm`)
3. Converts to WAV using `ffmpeg` (faster-whisper prefers WAV)
4. Calls system Python with faster-whisper to transcribe
5. Cleans up temp files
6. Returns `{ text: "transcribed text", language: "en", duration: 2.3 }`

**Auth:** Uses `getAuth(req)` from Clerk (same as chat/stream.ts) — only authenticated users can transcribe.

**Config:**
```typescript
export const config = {
  api: {
    bodyParser: {
      sizeLimit: '10mb',  // Voice messages can be a few MB
    },
  },
};
```

**Transcription approach — Python child process:**
```typescript
import { execSync } from 'child_process';

// Write audio to temp file
const audioPath = `/tmp/chesster-voice-${uuid}.webm`;
const wavPath = `/tmp/chesster-voice-${uuid}.wav`;

// Convert to WAV
execSync(`ffmpeg -i ${audioPath} -ar 16000 -ac 1 -f wav ${wavPath} -y`, { timeout: 10000 });

// Transcribe with faster-whisper
const result = execSync(
  `python3 -c "
from faster_whisper import WhisperModel
model = WhisperModel('tiny', device='cpu', compute_type='int8')
segments, info = model.transcribe('${wavPath}')
text = ' '.join(s.text for s in segments).strip()
print(text)
"`, { timeout: 30000 }
);
```

**Why child process instead of a persistent service:**
- The chess backend Flask server doesn't have faster-whisper in its venv
- Adding a new service adds operational complexity
- Voice messages are infrequent — cold-starting the model takes ~1s, transcription ~1-2s
- Total latency: 2-3 seconds — acceptable for this use case
- No memory overhead when not in use

**Alternative considered:** Adding a `/api/transcribe` endpoint to the Python Flask backend. Rejected because:
- Would need to install faster-whisper in the backend venv
- The backend already has memory pressure (SQLite, Supabase, OpenRouter)
- Coupling transcription to the chess backend means restarting it affects chat
- The Next.js API route is simpler and self-contained

### Phase 2: Frontend — Recording Hook

**File:** `/root/chess-app/frontend/src/hooks/useVoiceRecorder.ts`

A custom React hook that encapsulates the MediaRecorder API:

```typescript
interface UseVoiceRecorderReturn {
  isRecording: boolean;
  isTranscribing: boolean;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<string>;  // Returns transcribed text
  cancelRecording: () => void;
  recordingDuration: number;  // Seconds elapsed
  error: string | null;
}
```

**Internals:**
- Uses `navigator.mediaDevices.getUserMedia({ audio: true })` to get mic access
- Creates `MediaRecorder` with `mimeType: 'audio/webm;codecs=opus'` (best browser support)
- Tracks duration via `setInterval` counter
- On stop: collects chunks → creates Blob → converts to base64 → sends to `/api/chat/transcribe`
- Handles permissions gracefully (shows error if mic denied)
- Auto-stops after 60 seconds (configurable max duration)
- Cleans up MediaStream tracks on unmount

**Browser support fallback:**
```typescript
const isSupported = typeof MediaRecorder !== 'undefined' 
  && navigator.mediaDevices?.getUserMedia;
```
If not supported, the mic button is hidden.

### Phase 3: Frontend — UI Integration

**File:** `/root/chess-app/frontend/src/components/tabs/ChatTab.tsx`

Changes to the Chat Input section (bottom of the chat panel):

**Current layout:**
```
[  Text input field  ] [Send]
```

**New layout:**
```
[  Text input field  ] [🎤] [Send]
```

**When recording:**
```
[  🔴 Recording... 0:05  ] [⏹ Stop] [✕ Cancel]
```

**When transcribing:**
```
[  ⏳ Transcribing...     ] [disabled]
```

**Implementation details:**

1. **Microphone button** — `IconButton` with `Mic` icon from MUI, positioned between input and Send button
2. **Recording state** — replaces the text input with a recording indicator (red pulsing dot + timer)
3. **Stop button** — same position as Send, changes to Stop icon during recording
4. **Cancel button** — small X to discard the recording
5. **After transcription** — text appears in the input field, user can edit or press Send
6. **Auto-send option** — toggle in Settings dialog (default: OFF, so user can review)

**Visual design (matching existing dark theme):**
- Mic button: same style as Send button (`#9c27b0` purple)
- Recording indicator: red (`#ff4444`) with CSS pulse animation
- Transcribing: purple spinner (same as "Chesster is thinking...")

### Phase 4: Settings Integration

Add to the existing Settings dialog in ChatTab:

```
Voice Input
─────────────────────────
[Toggle] Auto-send after transcription
  When ON, transcribed text sends immediately
  When OFF, text appears in input for review

[Toggle] Show transcription confidence
  Display confidence % next to transcribed messages
```

Stored in localStorage via `useLocalStorage`:
- `chat_voice_autosend` (default: false)
- `chat_voice_show_confidence` (default: false)

---

## 4. File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `src/pages/api/chat/transcribe.ts` | **CREATE** | New API route — receives audio, returns text |
| `src/hooks/useVoiceRecorder.ts` | **CREATE** | New hook — MediaRecorder + transcribe API call |
| `src/components/tabs/ChatTab.tsx` | **MODIFY** | Add mic button, recording UI, settings toggles |
| `src/hooks/useChesster.ts` | **NO CHANGE** | The existing `sendChatMessage` works as-is — transcribed text just fills the input |

---

## 5. Edge Cases & Error Handling

| Scenario | Handling |
|----------|---------|
| **Mic permission denied** | Show tooltip: "Microphone access required. Check browser permissions." Hide mic button. |
| **Browser doesn't support MediaRecorder** | Hide mic button entirely (graceful degradation) |
| **Empty transcription** (silence/noise) | Show message: "Couldn't hear anything. Try again?" Don't fill input. |
| **Transcription fails** (Python error) | Show error snackbar, don't lose anything — user can retry or type manually |
| **Recording too long** (>60s) | Auto-stop at 60 seconds, proceed with transcription |
| **Recording too short** (<0.5s) | Discard and show: "Recording too short. Hold the button longer." |
| **Multiple rapid clicks** | Debounce — ignore clicks while recording/transcribing |
| **User navigates away while recording** | `useEffect` cleanup stops recording and releases mic |
| **Server overloaded** | 30-second timeout on transcription API, error message if exceeded |

---

## 6. Performance & Resource Impact

| Metric | Impact |
|--------|--------|
| **Memory (idle)** | Zero — no model loaded until needed |
| **Memory (transcribing)** | ~150MB for ~3 seconds (tiny model loads, runs, exits) |
| **CPU (transcribing)** | 1-2 seconds of CPU burst on system Python |
| **Disk** | Temp files cleaned up immediately after use |
| **Network** | Audio blob ~50-200KB for 5-10 second message (WebM/Opus is very efficient) |
| **Bundle size** | ~0 increase — uses only browser APIs and MUI icons already imported |

---

## 7. Security Considerations

- **Auth required** — transcription endpoint checks Clerk JWT (same as chat)
- **File cleanup** — temp files deleted immediately after transcription (in `finally` block)
- **Input sanitization** — base64 audio validated, file paths use UUID (no user input in paths)
- **Rate limiting** — could add rate limiting later if abused (not critical for MVP)
- **No audio persistence** — audio is never saved to disk permanently, only transcribed text flows into chat

---

## 8. Future Enhancements (Not in MVP)

- **Streaming transcription** — show words as they're recognized (needs WebSocket)
- **Voice commands** — "analyze this position", "show me best move" detected from speech
- **Multi-language** — faster-whisper auto-detects language, could add language preference
- **Audio playback** — save and replay voice messages in chat history
- **Push-to-talk** — hold mic button to record, release to send (mobile UX)

---

## 9. Implementation Order

1. **Backend first** — create `transcribe.ts`, test with curl
2. **Hook second** — create `useVoiceRecorder.ts`, test in isolation
3. **UI last** — integrate into ChatTab, test full flow
4. **Build & deploy** — `npm run build`, sync static, restart PM2

Estimated implementation time: **2-3 hours** (mostly the UI polish)

---

## 10. Testing Plan

### Manual tests:
1. ✅ Click mic → grants permission → starts recording (red indicator)
2. ✅ Speak → stop → text appears in input → edit → send works
3. ✅ Auto-send toggle → speak → stop → message sends immediately
4. ✅ Cancel during recording → no transcription, input cleared
5. ✅ Short recording (<0.5s) → error message
6. ✅ Long recording (>60s) → auto-stops
7. ✅ Deny mic permission → appropriate error, mic button disabled
8. ✅ Multiple languages (if user speaks Russian/Kazakh) → transcription works
9. ✅ Background noise → still produces reasonable output

### curl test for API:
```bash
# Record a test audio file
ffmpeg -f lavfi -i "sine=frequency=440:duration=2" /tmp/test.wav -y

# Convert to base64
AUDIO_B64=$(base64 -w0 /tmp/test.wav)

# Test the endpoint (will need a valid Clerk token)
curl -X POST http://localhost:3000/api/chat/transcribe \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <clerk-token>" \
  -d "{\"audio\": \"$AUDIO_B64\"}"
```
