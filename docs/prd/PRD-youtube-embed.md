# PRD: YouTube Video Embeds + Language-Based Video Switching

## Problem
1. YouTube URLs in lesson content are rendered as plain text strings, not playable video embeds
2. Some lessons have both Russian and Kazakh YouTube videos mixed together in the same content field, visible to all users regardless of language

## Current State

### Database
- Table: `lessons` (Supabase)
- Columns: `content`, `content_ru`, `content_kk` (markdown text)
- `localize()` in `backend/api/lessons.py` picks `content_{locale}` for non-English users
- 37 lessons have YouTube URLs in their `content` field
- 8 lessons have BOTH Russian video + Kazakh video in the same content field
- `content_kk` has 0 lessons with YouTube URLs (Kazakh translations exist for text but NOT for video sections)

### Lessons with dual videos (Russian + Kazakh)
These lessons have a pattern like:
```
## Видео урок
https://www.youtube.com/embed/XXXX (Russian video)

## Видео (Қазақша)
https://youtu.be/YYYY (Kazakh video)
```

The 8 dual-video lessons:
1. Check (Шах) - RU: JJLiGr_e57o, KK: kUyGUCeMt7w
2. Checkmate (Мат) - RU: leHhUag7CkE, KK: QGmkx2-sPZI
3. The Pawn (Пешка) - RU: dDVyfOMWTNo, KK: MYpa00Vr9B0
4. The Knight (Конь) - RU: oSh_Glu8nRQ, KK: -FxFa31tiOM
5. The King (Король) - RU: wfb5UYf54qE, KK: vPuewRyXMtU
6. The Rook (Ладья) - RU: B5KJXmM1qSc, KK: MrkUaEcnwVg
7. The Bishop (Слон) - RU: fLLl5OT_XPQ, KK: ej0MTV0JLVU
8. The Queen (Ферзь) - RU: a2TjkGqtQkY, KK: wxf5fty7ZiQ

### Frontend
- File: `frontend/src/app/learn/[courseSlug]/[lessonSlug]/page.tsx`
- Uses `<ReactMarkdown>{lesson.content}</ReactMarkdown>` (line 300)
- Already imports `useLocale()` from next-intl (line 9)
- Locale is passed as `?locale=` query param to API

## Requirements

### 1. YouTube Embed Renderer (Frontend)
Add a custom ReactMarkdown component override that detects YouTube URLs and renders them as responsive `<iframe>` embeds.

**Detection patterns:**
- `https://www.youtube.com/embed/VIDEO_ID` (already embed format)
- `https://youtu.be/VIDEO_ID` (short format)
- `https://www.youtube.com/watch?v=VIDEO_ID` (standard format)

**Render as:**
```html
<div style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden;">
  <iframe
    src="https://www.youtube.com/embed/VIDEO_ID"
    style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"
    frameBorder="0"
    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
    allowFullScreen
  />
</div>
```

**Implementation:** Add a custom `components` prop to ReactMarkdown. Override the `p` renderer — when a paragraph contains only a YouTube URL (as text), render an iframe embed instead of a `<p>` tag.

### 2. Database Content Restructuring (Kazakh Videos)
For the 8 dual-video lessons, move the Kazakh video into `content_kk` so that `localize()` automatically serves the right video per language.

**For each of the 8 lessons:**

a. In `content` (English) and `content_ru`: Remove the "## Видео (Қазақша)" section and the Kazakh YouTube URL. Keep only the Russian video under "## Видео урок".

b. In `content_kk`: If `content_kk` is NULL or empty, copy the full content from `content_ru`, then replace the Russian video URL with the Kazakh video URL and remove the "## Видео (Қазақша)" section. If `content_kk` already has text content, just append the Kazakh video section as "## Видео сабағы" with the Kazakh YouTube URL.

**Write a Python migration script** at `backend/scripts/migrate_youtube_videos.py` that:
1. Reads all 8 dual-video lessons from Supabase
2. For each: extracts Kazakh video URL, removes Kazakh section from content/content_ru, ensures content_kk has the Kazakh video
3. Updates Supabase
4. Prints a summary of changes
5. Has a `--dry-run` flag for preview

### 3. No Backend Changes Needed
The existing `localize()` function already handles content_kk switching. No backend code changes required.

## Files to Modify
1. `frontend/src/app/learn/[courseSlug]/[lessonSlug]/page.tsx` — Add YouTube embed renderer to ReactMarkdown
2. `backend/scripts/migrate_youtube_videos.py` — New migration script for DB content

## Testing
1. After frontend change: verify YouTube URLs render as playable iframes (not plain text)
2. After DB migration: verify Russian users see Russian video only, Kazakh users see Kazakh video only
3. Lessons with only Russian video should work unchanged for all locales
4. Build must succeed: `npm run build`

## Deploy
Standard Chesster deploy procedure after build succeeds.
