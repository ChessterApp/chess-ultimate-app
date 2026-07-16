# TASK: Rename level display names and add Level 4 (master)

## What to do
Keep internal DB keys (beginner, intermediate, advanced) UNCHANGED. Add "master" as the new Level 4 DB key. Change DISPLAY labels in translations to Level 1-4.

| DB Key       | Old Display  | New Display (EN) | New Display (RU) | New Display (KZ) |
|--------|------------|-------------|-------------|-------------|
| beginner     | Beginner     | Level 1 | Уровень 1 | 1-деңгей |
| intermediate | Intermediate | Level 2 | Уровень 2 | 2-деңгей |
| advanced     | Advanced     | Level 3 | Уровень 3 | 3-деңгей |
| master (NEW) | n/a          | Level 4 | Уровень 4 | 4-деңгей |

## Files to edit (ALL of these, no exceptions):

### 1. Translation files (3 files)
- `frontend/messages/en.json` — change ALL occurrences:
  - Around line 145-147: dashboard.levels.beginner/intermediate/advanced values to "Level 1"/"Level 2"/"Level 3", ADD "master": "Level 4"
  - Around line 229-231: learn.beginner/intermediate/advanced values to "Level 1"/"Level 2"/"Level 3", ADD "master": "Level 4"
  - Around line 949-968: onboarding section beginner/intermediate/advanced objects — update display names, ADD master object
  - Search the ENTIRE file for any other beginner/intermediate/advanced display strings that users see
- `frontend/messages/ru.json` — same pattern with Russian translations (Уровень 1 through Уровень 4)
- `frontend/messages/kz.json` — same pattern with Kazakh translations (1-деңгей through 4-деңгей)

### 2. frontend/src/app/learn/page.tsx
- Line 18: Add master to Course type union: 'beginner' | 'intermediate' | 'advanced' | 'master'
- Line 122-129: Add master to coursesByLevel grouping object
- After the Advanced Section (after line 226): Add a Level 4 / Master section with purple color (bg-purple-500 dot), same pattern as the other sections

### 3. frontend/src/components/gamification/LessonPath.tsx
- Line 18: Add master to Course level type union
- Line 29-48: Add master to levelColors object with purple theme (bg-purple-500, border-purple-500, text-purple-600, bg-purple-100)
- Line 202: Add master to HorizontalLessonPathProps level type union

### 4. frontend/src/app/learn/[courseSlug]/page.tsx
- Line 201-208: Add master entry to getLevelLabel function
- Line 220-224: Add master styling to the badge (purple theme: bg-purple-100 text-purple-800)

### 5. frontend/src/app/dashboard/page.tsx
- Line 22: Add master to Course level type union
- Line 161-168: Add master entry to getLevelTranslation function
- Line 237-240: Add master styling to the badge (purple theme: bg-purple-100 text-purple-700)

### 6. backend/schema.sql
- Line 17: Update CHECK constraint to include 'master'

## IMPORTANT RULES:
- Do NOT change any DB key values (beginner/intermediate/advanced stay as DB values)
- Only change DISPLAY labels in translation files + add master everywhere
- Use purple color theme for master level (progression: green -> amber -> red -> purple)
- Do NOT touch onboarding page logic unless it displays level names from translations
- SKIP live DB migration — just update schema.sql
- After editing, run: cd frontend && npm run build to verify no TypeScript errors
- git add ONLY the specific files you changed
- Commit with message: "feat: rename levels to Level 1-4 and add Level 4 (master)"
- git push origin main
