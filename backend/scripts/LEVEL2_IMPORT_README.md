# Level 2 (Chess Tactics) Puzzle Import

## Problem

The Level 2 course puzzles are hosted in **private** Lichess studies owned by user "ChessEmpireSchool". The Lichess API does not allow accessing private studies, so the automated import script cannot fetch the puzzle data.

## Studies to Import

| Study ID | Lessons | URL |
|----------|---------|-----|
| QVTlrUPC | 9 | https://lichess.org/study/QVTlrUPC |
| kxvgKqUv | 7 | https://lichess.org/study/kxvgKqUv |
| iHQPHA1y | 8 | https://lichess.org/study/iHQPHA1y |
| S7W42JDS | 5 | https://lichess.org/study/S7W42JDS |
| kv5kbvh4 | 1 | https://lichess.org/study/kv5kbvh4 |

**Total:** 30 lessons with puzzles

## Solution 1: Make Studies Public (Recommended)

The study owner needs to make the studies public:

1. Log in to Lichess as "ChessEmpireSchool"
2. For each study:
   - Open the study on Lichess
   - Click the "Share" button
   - Change visibility to **"Public"**
   - Save changes
3. Run the automated import script:
   ```bash
   cd /root/chess-app/backend
   source venv/bin/activate
   python3 scripts/import_level2_puzzles.py
   ```

## Solution 2: Manual PGN Download (Workaround)

If the studies cannot be made public, download PGN files manually:

### Step 1: Create Directory
```bash
cd /root/chess-app/backend
mkdir -p data/lichess_studies
```

### Step 2: Download PGN Files

For each study, download the PGN file:

```bash
# As the study owner on Lichess:
# 1. Open https://lichess.org/study/{study_id}
# 2. Click "..." menu → "Study PGN"
# 3. Save the file as {study_id}.pgn

# Example for study QVTlrUPC:
# Save to: backend/data/lichess_studies/QVTlrUPC.pgn
```

Or use `wget` if you have authentication:
```bash
cd data/lichess_studies
wget -O QVTlrUPC.pgn "https://lichess.org/api/study/QVTlrUPC.pgn"
wget -O kxvgKqUv.pgn "https://lichess.org/api/study/kxvgKqUv.pgn"
wget -O iHQPHA1y.pgn "https://lichess.org/api/study/iHQPHA1y.pgn"
wget -O S7W42JDS.pgn "https://lichess.org/api/study/S7W42JDS.pgn"
wget -O kv5kbvh4.pgn "https://lichess.org/api/study/kv5kbvh4.pgn"
```

### Step 3: Run Local Import Script

```bash
cd /root/chess-app/backend
source venv/bin/activate

# Test with dry run first
python3 scripts/import_level2_from_local_pgn.py --dry-run --limit 3

# Run full import
python3 scripts/import_level2_from_local_pgn.py
```

## Verification

After import, verify the puzzle counts:

```bash
source venv/bin/activate
python3 -c "
from supabase import create_client
import os

os.environ['SUPABASE_URL'] = 'https://qtzujwiqzbgyhdgulvcd.supabase.co'
os.environ['SUPABASE_SERVICE_KEY'] = 'REDACTED_USE_ENV_VAR'

supabase = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])

# Get all Level 2 lessons
lessons = supabase.table('lessons').select('id, title_ru').execute()

# For each lesson, count puzzles
import json
results = []
for lesson in lessons.data:
    puzzles = supabase.table('lesson_puzzles').select('*', count='exact').eq('lesson_id', lesson['id']).execute()
    if puzzles.count > 0:
        results.append({'title': lesson.get('title_ru', lesson['id']), 'count': puzzles.count})

results.sort(key=lambda x: x['count'], reverse=True)
print(json.dumps(results, indent=2, ensure_ascii=False))
"
```

## Files Created

- `backend/scripts/import_level2_puzzles.py` - Automated import from Lichess API (requires public studies)
- `backend/scripts/import_level2_from_local_pgn.py` - Import from local PGN files
- `backend/scripts/import_lichess_study.py` - Updated with `--chapter-id` flag support

## Next Steps

1. **Contact study owner** to make studies public OR download PGN files
2. **Run appropriate import script** (API or local)
3. **Verify** puzzle counts in database
4. **Test** lessons in the Chesster app to ensure puzzles load correctly
