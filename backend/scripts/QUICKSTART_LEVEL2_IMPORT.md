# Level 2 Puzzle Import - Quick Start Guide

## Current Status

✅ **Infrastructure Ready** - All import scripts are implemented and tested
⚠️ **Blocker** - 5 Lichess studies are private (need to be made public)

## Quick Check

```bash
cd /root/chess-app/backend
source venv/bin/activate
python3 scripts/check_lichess_studies.py
```

## Option 1: Make Studies Public (Fastest)

1. **Log in to Lichess** as "ChessEmpireSchool"

2. **Make these studies public:**
   - https://lichess.org/study/QVTlrUPC (9 lessons)
   - https://lichess.org/study/kxvgKqUv (7 lessons)
   - https://lichess.org/study/iHQPHA1y (8 lessons)
   - https://lichess.org/study/S7W42JDS (5 lessons)
   - https://lichess.org/study/kv5kbvh4 (1 lesson)

   For each study: Click **Share** → Set to **Public**

3. **Run import:**
   ```bash
   cd /root/chess-app/backend
   source venv/bin/activate

   # Test with first 3 lessons
   python3 scripts/import_level2_puzzles.py --dry-run --limit 3

   # Run full import
   python3 scripts/import_level2_puzzles.py
   ```

## Option 2: Manual Download

1. **Create directory:**
   ```bash
   cd /root/chess-app/backend
   mkdir -p data/lichess_studies
   ```

2. **Download PGN files** (while logged in to Lichess):
   - Open each study URL
   - Click "..." → "Study PGN"
   - Save as `data/lichess_studies/{study_id}.pgn`

3. **Run import:**
   ```bash
   source venv/bin/activate

   # Test
   python3 scripts/import_level2_from_local_pgn.py --dry-run --limit 3

   # Full import
   python3 scripts/import_level2_from_local_pgn.py
   ```

## Verify Import

```bash
source venv/bin/activate
python3 -c "
from supabase import create_client
import os

os.environ['SUPABASE_URL'] = 'https://qtzujwiqzbgyhdgulvcd.supabase.co'
os.environ['SUPABASE_SERVICE_KEY'] = 'REDACTED_USE_ENV_VAR'

supabase = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])

# Count total puzzles
result = supabase.table('lesson_puzzles').select('*', count='exact').execute()
print(f'Total puzzles in database: {result.count}')

# Count Level 2 lessons with puzzles
lessons = supabase.table('lessons').select('id, title_ru, puzzle_count').gt('puzzle_count', 0).execute()
level2_count = sum(1 for l in lessons.data if l.get('puzzle_count', 0) > 0)
print(f'Lessons with puzzles: {level2_count}')
"
```

## Troubleshooting

**Problem:** Script fails with "Study not found"
**Solution:** Make sure study is public OR PGN file is downloaded

**Problem:** "Lesson not found in DB"
**Solution:** Lesson titles must match between JSON and database (check Russian titles)

**Problem:** Rate limiting (429 error)
**Solution:** Increase delay with `--delay 2.0` flag

## Expected Results

- **30 lessons** should have puzzles imported
- **Typical puzzle count:** 6-18 puzzles per lesson
- **Total puzzles:** ~300-500 (estimated)

## Help

Full documentation: `backend/scripts/LEVEL2_IMPORT_README.md`
