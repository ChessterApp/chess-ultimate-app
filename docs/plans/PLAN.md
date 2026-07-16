# Plan: Fix EditGameModal & AddGameModal to use light theme

## Problem
Both `EditGameModal` and `AddGameModal` hardcode a dark navy background (`#0f0f1a`) and white text colors, ignoring the MUI theme system. The app's default is `chessterLightTheme` (white background, dark text). The modals should follow the theme.

## Changes

### 1. EditGameModal.tsx
- **Remove** `bgcolor: '#0f0f1a'` and `border: '1px solid rgba(139, 92, 246, 0.3)'` from `PaperProps` — let MUI use `background.paper` (#FFFFFF in light mode)
- **Remove** `color: '#fff'` from the title Typography — use `text.primary` (auto)
- **Remove** `backgroundColor: 'rgba(0, 0, 0, 0.7)'` and `backdropFilter` from backdrop — use MUI defaults
- **Update** `fieldSx`: change `bgcolor: 'rgba(255,255,255,0.03)'` to `bgcolor: 'grey.50'` (light grey tint, works in both themes)
- **Update** Cancel button hover: `rgba(255,255,255,0.06)` → `'action.hover'` (theme-aware)
- **Update** Save button: keep the purple gradient — it works on both themes since the text is white on purple

### 2. AddGameModal.tsx (same treatment)
- **Same PaperProps fix** — remove `bgcolor: '#0f0f1a'`, remove purple border
- **Same title Typography fix** — remove `color: '#fff'`
- **Same backdrop fix** — remove hardcoded dark backdrop
- **Same `fieldSx` fix** — `'grey.50'` instead of `rgba(255,255,255,0.03)`
- **Same button hover fix** — `'action.hover'`
- **PGN textarea** `bgcolor` fix
- **Board entry** move list: `rgba(255,255,255,0.03)` → `'grey.50'`, move number color `rgba(255,255,255,0.4)` → `text.disabled`, move text `#fff` → `text.primary`
- **Scoresheet** upload border: `rgba(255,255,255,0.15)` → `'divider'`, preview box border fix
- **Scoresheet ready** box `bgcolor` fix
- **Chip** unselected colors: `rgba(255,255,255,0.06)` → `'action.hover'`, hover → `'action.selected'`

### Files touched
1. `frontend/src/components/openings/EditGameModal.tsx` — ~10 line changes
2. `frontend/src/components/openings/AddGameModal.tsx` — ~20 line changes

### No backend changes needed

### Deploy
- `git add` both files, commit, push
- Vercel auto-deploys from main
- VPS: `bash /root/chess-app/frontend/deploy.sh`
- Verify with browser on chesster.io
