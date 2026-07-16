# Supabase Schema Migration - Manual Setup Guide

## Overview
The slug columns need to be created in Supabase before the migration script can populate them with data.

## Steps to Complete

### Step 1: Access Supabase SQL Editor
1. Go to [Supabase Dashboard](https://supabase.com)
2. Select your project: **chess-app** (qtzujwiqzbgyhdgulvcd)
3. Navigate to **SQL Editor** in the left sidebar
4. Click **New Query** (or **+** button)

### Step 2: Create Slug Columns
Copy and paste this SQL into the editor:

```sql
-- Add slug column to courses table
ALTER TABLE courses 
ADD COLUMN IF NOT EXISTS slug TEXT UNIQUE;

-- Add slug column to lessons table
ALTER TABLE lessons 
ADD COLUMN IF NOT EXISTS slug TEXT;

-- Add index for faster lookups (optional but recommended)
CREATE INDEX IF NOT EXISTS idx_courses_slug ON courses(slug);
CREATE INDEX IF NOT EXISTS idx_lessons_slug ON lessons(slug);
```

### Step 3: Execute the Query
1. Click the **▶ Run** button (or Ctrl+Enter)
2. You should see: `Query executed successfully` at the bottom

### Step 4: Run the Migration Script
After the columns are created, run this on the VPS:

```bash
ssh root@104.248.190.155
cd /root/chess-app/backend
python3 migrate_slugs.py
```

Expected output:
```
============================================================
CHESS APP - SLUG MIGRATION & SYNC
============================================================

=== STEP 1: Adding slug columns ===
Checking courses table for slug column...
✓ Slug column already exists in courses table

=== STEP 2: Syncing course slugs ===
  ✓ Chess Fundamentals → chess-fundamentals
  ✓ Checkmate Patterns → checkmate-patterns

=== STEP 3: Syncing lesson slugs ===
  Updated 47 lessons

============================================================
MIGRATION COMPLETE
============================================================
Updated courses: 2
Updated lessons: 47
```

## Verification

### Via Supabase Dashboard:
1. Go to **Table Editor**
2. Open **courses** table
3. Check that the `slug` column now shows values like:
   - `chess-fundamentals`
   - `checkmate-patterns`

### Via SQL Query:
```sql
-- Check courses have slugs
SELECT id, title, slug FROM courses;

-- Count lessons with slugs
SELECT COUNT(*) as total_lessons,
       COUNT(slug) as lessons_with_slugs 
FROM lessons;
```

## If Migration Fails

**Issue**: "column 'slug' already exists"
- Solution: The columns are already there - skip to Step 4

**Issue**: "Permission denied" when running SQL
- Solution: Use a Supabase role with admin rights, or contact your Supabase account owner

**Issue**: "migrate_slugs.py not found"
- Solution: The script is at `/root/chess-app/backend/migrate_slugs.py` on the VPS

## What This Does

- **slug columns**: Store URL-friendly identifiers for courses/lessons
- **Backend**: Already has fallback slug generation (no downtime if migration fails)
- **Frontend**: URLs like `/learn/chess-fundamentals/the-king` now map directly to DB
- **Future**: Seed script auto-generates slugs for new content

## Next Steps After Migration

1. ✓ Restart backend: `systemctl --user restart chess-backend`
2. ✓ Clear frontend cache: Hard refresh browser (Cmd+Shift+R / Ctrl+Shift+R)
3. ✓ Test URLs: Visit `/learn` and click through courses

## Troubleshooting

If you encounter issues:
1. Check Supabase dashboard for the columns existing
2. Verify environment variables are set: `echo $SUPABASE_URL`
3. Run migration script again
4. Check logs: `tail -f /root/chess-app/backend/backend.log`

