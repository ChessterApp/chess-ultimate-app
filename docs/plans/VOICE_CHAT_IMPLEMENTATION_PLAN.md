# Voice Chat — Step-by-Step Implementation Plan

**Date:** 2026-02-08  
**Status:** Ready to execute  
**No recording time limit** — users record as long as they want

---

## Step 1: Create the Transcription API Route

**File:** `src/pages/api/chat/transcribe.ts` (NEW)

**What:** A Next.js API route that receives base64-encoded audio from the browser, transcribes it with faster-whisper, and returns text.

**Details:**
- `POST /api/chat/transcribe`
- Body: `{ audio: "<base64>" }` — the raw audio blob from MediaRecorder
- Auth: Clerk `getAuth(req)` — same as `stream.ts`
- Body size limit: `25mb` (no recording time limit means potentially long files)
- Process:
  1. Decode base64 → write to `/tmp/chesster-voice-{uuid}.webm`
  2. `ffmpeg -i input.webm -ar 16000 -ac 1 -f wav output.wav -y` (convert to 16kHz mono WAV for whisper)
  3. Run system Python: `python3 -c "from faster_whisper import WhisperModel; ..."` with `tiny` model
  4. Parse stdout → extract transcribed text
  5. Clean up both temp files in `finally` block
  6. Return `{ success: true, text: "...", language: "en", duration_seconds: 5.2 }`
- Error responses:
  - 401: Unauthorized (no Clerk token)
  - 400: Missing audio data, or audio too short
  - 500: Transcription failed (ffmpeg error, whisper error)
- Timeout: 120 seconds for the Python process (long recordings need more time)

**Python transcription script** (executed as child process):
```python
import sys, json
from faster_whisper import WhisperModel
model = WhisperModel("tiny", device="cpu", compute_type="int8")
segments, info = model.transcribe(sys.argv[1])
text = " ".join(s.text for s in segments).strip()
print(json.dumps({"text": text, "language": info.language, "duration": info.duration}))
```

Save this as a standalone script at `src/pages/api/chat/transcribe-worker.py` so we don't inline Python in TypeScript strings. The API route calls `execSync('python3 transcribe-worker.py /tmp/file.wav')`.

**Test after this step:**
```bash
# Create a test WAV
ffmpeg -f lavfi -i "sine=frequency=440:duration=2" -ar 16000 -ac 1 /tmp/test-voice.wav -y

# Test transcription directly
python3 -c "
from faster_whisper import WhisperModel
model = WhisperModel('tiny', device='cpu', compute_type='int8')
segments, info = model.transcribe('/tmp/test-voice.wav')
text = ' '.join(s.text for s in segments).strip()
print(f'Text: {text}')
print(f'Language: {info.language}')
print(f'Duration: {info.duration}s')
"
```

---

## Step 2: Create the Voice Recorder Hook

**File:** `src/hooks/useVoiceRecorder.ts` (NEW)

**What:** A React hook that manages browser microphone recording and communicates with the transcription API.

**Interface:**
```typescript
interface UseVoiceRecorderOptions {
  onTranscriptionComplete?: (text: string) => void;
  onError?: (error: string) => void;
  autoSend?: boolean;
}

interface UseVoiceRecorderReturn {
  // State
  isRecording: boolean;
  isTranscribing: boolean;
  isSupported: boolean;        // false if browser doesn't support MediaRecorder
  recordingDuration: number;   // seconds elapsed while recording
  error: string | null;
  
  // Actions
  startRecording: () => Promise<void>;
  stopRecording: () => void;   // stops and triggers transcription
  cancelRecording: () => void; // stops and discards
}
```

**Internals:**
1. **Browser check:** On mount, check `typeof MediaRecorder !== 'undefined' && navigator.mediaDevices?.getUserMedia`. Set `isSupported` accordingly.
2. **startRecording():**
   - Request mic permission: `navigator.mediaDevices.getUserMedia({ audio: true })`
   - Create `MediaRecorder` with preferred MIME type:
     - Try `audio/webm;codecs=opus` first (Chrome, Firefox, Edge)
     - Fallback to `audio/webm` then `audio/mp4` (Safari)
   - Start collecting chunks via `ondataavailable`
   - Start a `setInterval` timer updating `recordingDuration` every second
   - Set `isRecording = true`
3. **stopRecording():**
   - Call `recorder.stop()`
   - In `onstop` handler: assemble chunks → create Blob → convert to base64
   - Set `isRecording = false`, `isTranscribing = true`
   - POST to `/api/chat/transcribe` with the base64 audio
   - On success: call `onTranscriptionComplete(text)`, set `isTranscribing = false`
   - On error: set `error`, `isTranscribing = false`
4. **cancelRecording():**
   - Call `recorder.stop()` but discard chunks
   - Stop and release all MediaStream tracks
   - Reset all state
5. **Cleanup (useEffect return):**
   - Stop any active recording
   - Release MediaStream tracks
   - Clear interval timer

**Auth:** Uses `useAuth()` from Clerk to get token for the API call:
```typescript
const { getToken } = useAuth();
// In the transcribe call:
const token = await getToken();
fetch('/api/chat/transcribe', {
  headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ audio: base64Audio })
});
```

**No time limit** — the recording runs until the user stops it. The duration counter keeps going. Long recordings (10+ minutes) will produce larger files but faster-whisper handles them fine.

**Test after this step:** Import hook in a temporary test component, verify recording starts/stops, check that audio blob is created and API call returns text.

---

## Step 3: Integrate into ChatTab UI

**File:** `src/components/tabs/ChatTab.tsx` (MODIFY)

### 3a. Add imports and hook

At the top of ChatTab, add the new hook and MUI icons:
```typescript
import { Mic, Stop as StopIcon, Close as CloseIcon } from "@mui/icons-material";
import useVoiceRecorder from "../../hooks/useVoiceRecorder";
```

Inside the component, use the hook:
```typescript
const {
  isRecording,
  isTranscribing,
  isSupported: voiceSupported,
  recordingDuration,
  error: voiceError,
  startRecording,
  stopRecording,
  cancelRecording,
} = useVoiceRecorder({
  onTranscriptionComplete: (text) => {
    if (autoSendVoice) {
      // Set input and immediately send
      setChatInput(text);
      // Need to trigger send on next tick after state updates
      setTimeout(() => sendChatMessage(gameInfo, currentMove, puzzleMode, puzzleQuery, playMode, questionMode), 50);
    } else {
      setChatInput(text);
    }
  },
  onError: (err) => {
    setVoiceErrorSnackbar(err);
  },
});
```

### 3b. Modify the Chat Input area

Replace the current input section at the bottom of ChatTab. The layout changes based on state:

**Default state (not recording):**
```
[ Text input field                    ] [🎤] [Send ➤]
```

**Recording state:**
```
[ 🔴 Recording... 1:23               ] [⏹ Stop] [✕]
```

**Transcribing state:**
```
[ ⏳ Transcribing your message...     ]  [disabled]
```

**Implementation:**

The Chat Input `<Paper>` section currently has:
```tsx
<Stack direction="row" spacing={1}>
  <TextField ... />
  <Button ... ><Send /></Button>
</Stack>
```

Change to:
```tsx
<Stack direction="row" spacing={1} alignItems="center">
  {isRecording ? (
    // Recording indicator
    <>
      <Box sx={{
        flex: 1, display: "flex", alignItems: "center", gap: 1,
        px: 2, py: 1,
        backgroundColor: "rgba(255, 68, 68, 0.1)",
        border: "1px solid rgba(255, 68, 68, 0.3)",
        borderRadius: 1,
      }}>
        <Box sx={{
          width: 10, height: 10, borderRadius: "50%",
          backgroundColor: "#ff4444",
          animation: "pulse 1.5s ease-in-out infinite",
          "@keyframes pulse": {
            "0%, 100%": { opacity: 1 },
            "50%": { opacity: 0.4 },
          },
        }} />
        <Typography variant="body2" sx={{ color: "#ff6b6b", fontWeight: 500 }}>
          Recording... {formatDuration(recordingDuration)}
        </Typography>
      </Box>
      <IconButton onClick={stopRecording} sx={{
        backgroundColor: "#ff4444", color: "white",
        "&:hover": { backgroundColor: "#cc3333" },
      }}>
        <StopIcon />
      </IconButton>
      <IconButton onClick={cancelRecording} size="small" sx={{ color: "#ff6b6b" }}>
        <CloseIcon fontSize="small" />
      </IconButton>
    </>
  ) : isTranscribing ? (
    // Transcribing indicator
    <Box sx={{
      flex: 1, display: "flex", alignItems: "center", gap: 1,
      px: 2, py: 1,
      backgroundColor: "rgba(156, 39, 176, 0.1)",
      border: "1px solid rgba(156, 39, 176, 0.3)",
      borderRadius: 1,
    }}>
      <CircularProgress size={16} sx={{ color: "#9c27b0" }} />
      <Typography variant="body2" sx={{ color: "#ce93d8" }}>
        Transcribing your message...
      </Typography>
    </Box>
  ) : (
    // Normal input
    <>
      <TextField ... /> {/* existing text field, unchanged */}
      {voiceSupported && (
        <IconButton
          onClick={startRecording}
          disabled={chatLoading}
          sx={{
            color: "#9c27b0",
            "&:hover": { backgroundColor: "rgba(156, 39, 176, 0.1)" },
            "&:disabled": { color: "rgba(156, 39, 176, 0.3)" },
          }}
        >
          <Mic />
        </IconButton>
      )}
      <Button ... > {/* existing Send button, unchanged */}
        <Send fontSize="small" />
      </Button>
    </>
  )}
</Stack>
```

**Helper function** (add inside component):
```typescript
const formatDuration = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};
```

### 3c. Add error snackbar for voice errors

Add state:
```typescript
const [voiceErrorSnackbar, setVoiceErrorSnackbar] = useState<string | null>(null);
```

Add snackbar (near the existing copy snackbar):
```tsx
<Snackbar
  open={!!voiceErrorSnackbar}
  autoHideDuration={4000}
  onClose={() => setVoiceErrorSnackbar(null)}
  anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
>
  <Alert severity="error" variant="filled" onClose={() => setVoiceErrorSnackbar(null)}>
    {voiceErrorSnackbar}
  </Alert>
</Snackbar>
```

### 3d. Update props

The `ChatTabProps` interface needs `useAuth` to be available inside ChatTab for the voice hook. Since `useAuth` is already imported at the top of ChatTab for the existing TTS functionality, no new prop is needed — the hook calls `useAuth()` internally.

---

## Step 4: Add Settings Toggle

**File:** `src/components/tabs/ChatTab.tsx` (same file, Settings Dialog section)

Add a new localStorage state:
```typescript
const [autoSendVoice, setAutoSendVoice] = useLocalStorage<boolean>(
  "chat_voice_autosend",
  false
);
```

Add to the Settings Dialog content (after the existing "Display Options" section):

```tsx
<Divider sx={{ borderColor: "rgba(255,255,255,0.1)" }} />
<Box>
  <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
    Voice Input
  </Typography>
  <Stack spacing={2}>
    {voiceSupported ? (
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Box>
          <Typography variant="body2" sx={{ color: "grey.300" }}>
            Auto-send after transcription
          </Typography>
          <Typography variant="caption" sx={{ color: "grey.500" }}>
            Send immediately without reviewing text
          </Typography>
        </Box>
        <Switch
          checked={autoSendVoice}
          onChange={(e) => setAutoSendVoice(e.target.checked)}
          sx={{
            '& .MuiSwitch-switchBase.Mui-checked': { color: '#9c27b0' },
            '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: '#9c27b0' },
          }}
        />
      </Stack>
    ) : (
      <Typography variant="body2" sx={{ color: "grey.500" }}>
        Voice input not available in this browser
      </Typography>
    )}
  </Stack>
</Box>
```

---

## Step 5: Create the Transcription Worker Script

**File:** `src/pages/api/chat/transcribe-worker.py` (NEW)

A standalone Python script to avoid inlining Python in TypeScript:

```python
#!/usr/bin/env python3
"""Transcribe audio file using faster-whisper. Called by transcribe.ts API route."""
import sys
import json

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No audio file path provided"}))
        sys.exit(1)
    
    audio_path = sys.argv[1]
    
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path)
        
        text = " ".join(segment.text for segment in segments).strip()
        
        result = {
            "text": text,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "duration": round(info.duration, 2),
        }
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
```

---

## Step 6: Build, Deploy, Test

```bash
cd /root/chess-app/frontend

# 1. Build
npm run build

# 2. Sync static files for standalone build
cp -r public .next/standalone/public
mkdir -p .next/standalone/.next
cp -r .next/static .next/standalone/.next/static

# 3. Copy the Python worker script to standalone build
cp src/pages/api/chat/transcribe-worker.py .next/standalone/

# 4. Restart frontend
export HOME=/root
pm2 restart chess-frontend

# 5. Verify
sleep 5
pm2 logs chess-frontend --lines 10 --nostream
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/
```

**Manual testing checklist:**
1. Open Chesster in browser → chat panel → mic button visible
2. Click mic → browser asks for permission → allow
3. Speak something → click Stop → "Transcribing..." appears
4. Text appears in input field → review → press Send → normal chat flow
5. Toggle auto-send in settings → record again → message sends automatically
6. Test cancel during recording → input stays empty
7. Test on mobile browser (if accessible)
8. Test with long recording (2+ minutes) → should still work

---

## Summary

| Step | File | Action | Dependencies |
|------|------|--------|-------------|
| 1 | `src/pages/api/chat/transcribe.ts` | CREATE | None (faster-whisper + ffmpeg exist) |
| 2 | `src/hooks/useVoiceRecorder.ts` | CREATE | Step 1 (API route) |
| 3 | `src/components/tabs/ChatTab.tsx` | MODIFY | Step 2 (hook) |
| 4 | `src/components/tabs/ChatTab.tsx` | MODIFY | Step 3 (settings in same file) |
| 5 | `src/pages/api/chat/transcribe-worker.py` | CREATE | None |
| 6 | Build + deploy | COMMAND | Steps 1-5 |

**No recording time limit.** Users record as long as they want. The only limits are:
- 25MB body size (enough for ~30+ minutes of WebM/Opus audio)
- 120 second transcription timeout (enough for very long recordings)

**Estimated implementation time:** 2-3 hours
