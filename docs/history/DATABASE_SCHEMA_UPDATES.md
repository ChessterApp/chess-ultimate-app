# Database Schema Updates - Animated Chess Board

## Overview

This document defines the database schema changes required to support interactive 1-move puzzle exercises with the animated chess board.

---

## Current Schema

**Table: `lessons`**

```sql
CREATE TABLE lessons (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  course_id UUID REFERENCES courses(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  content TEXT,
  lesson_type TEXT CHECK (lesson_type IN ('theory', 'exercise', 'practice')),
  exercise_fen TEXT,  -- Current: FEN position string
  order_num INTEGER NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## Required Changes

### 1. Add `solution_move` Column

**Purpose:** Store the correct move for 1-move puzzle exercises in UCI notation

```sql
ALTER TABLE lessons
ADD COLUMN solution_move TEXT;
```

**Constraints:**
- Format: UCI notation (e.g., "e2e4", "e7e8q" for promotion)
- Required for lessons where `exercise_fen` is not null
- Validated to ensure the move is legal in the given position

**Examples:**
- `"e2e4"` - Pawn moves from e2 to e4
- `"e7e8q"` - Pawn promotes to queen
- `"e1g1"` - Kingside castling (special case)

---

### 2. Add `exercise_type` Column

**Purpose:** Distinguish between different exercise formats

```sql
ALTER TABLE lessons
ADD COLUMN exercise_type TEXT DEFAULT 'one_move_puzzle'
CHECK (exercise_type IN ('one_move_puzzle', 'multi_move', 'position_eval', 'opening_practice'));
```

**Values:**
- `one_move_puzzle` (MVP) - Find the single correct move
- `multi_move` (future) - Solve a sequence of moves
- `position_eval` (future) - Evaluate who's better
- `opening_practice` (future) - Learn opening moves

---

### 3. Add `hint_text` Column

**Purpose:** Provide contextual hints for exercises

```sql
ALTER TABLE lessons
ADD COLUMN hint_text TEXT;
```

**Examples:**
- `"Look for a check!"`
- `"The queen is undefended"`
- `"Can you win material?"`

---

### 4. Add `success_message` Column

**Purpose:** Custom celebration message after solving

```sql
ALTER TABLE lessons
ADD COLUMN success_message TEXT;
```

**Examples:**
- `"Perfect! That's checkmate!"`
- `"Excellent! You won the queen!"`
- `"Great move! Now white is winning."`

---

## Complete Updated Schema

```sql
CREATE TABLE lessons (
  -- Existing columns
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  course_id UUID REFERENCES courses(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  content TEXT,
  lesson_type TEXT CHECK (lesson_type IN ('theory', 'exercise', 'practice')),
  order_num INTEGER NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

  -- Exercise columns
  exercise_fen TEXT,
  solution_move TEXT,  -- NEW: UCI notation
  exercise_type TEXT DEFAULT 'one_move_puzzle'  -- NEW
    CHECK (exercise_type IN ('one_move_puzzle', 'multi_move', 'position_eval', 'opening_practice')),
  hint_text TEXT,  -- NEW
  success_message TEXT,  -- NEW

  -- Constraints
  CONSTRAINT valid_exercise CHECK (
    (exercise_fen IS NULL AND solution_move IS NULL) OR
    (exercise_fen IS NOT NULL AND solution_move IS NOT NULL)
  )
);
```

---

## Migration Script

**File:** `backend/migrations/001_add_chess_board_columns.sql`

```sql
-- Migration: Add columns for animated chess board exercises
-- Created: 2025-01-20

BEGIN;

-- Add solution_move column
ALTER TABLE lessons
ADD COLUMN IF NOT EXISTS solution_move TEXT;

-- Add exercise_type column with default
ALTER TABLE lessons
ADD COLUMN IF NOT EXISTS exercise_type TEXT DEFAULT 'one_move_puzzle'
CHECK (exercise_type IN ('one_move_puzzle', 'multi_move', 'position_eval', 'opening_practice'));

-- Add hint_text column
ALTER TABLE lessons
ADD COLUMN IF NOT EXISTS hint_text TEXT;

-- Add success_message column
ALTER TABLE lessons
ADD COLUMN IF NOT EXISTS success_message TEXT;

-- Add constraint: exercise_fen and solution_move must both be set or both null
ALTER TABLE lessons
ADD CONSTRAINT valid_exercise CHECK (
  (exercise_fen IS NULL AND solution_move IS NULL) OR
  (exercise_fen IS NOT NULL AND solution_move IS NOT NULL)
);

-- Create index for faster exercise queries
CREATE INDEX IF NOT EXISTS idx_lessons_exercise_type ON lessons(exercise_type)
WHERE exercise_fen IS NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN lessons.solution_move IS 'UCI notation for the correct move (e.g., e2e4, e7e8q)';
COMMENT ON COLUMN lessons.exercise_type IS 'Type of chess exercise: one_move_puzzle, multi_move, position_eval, opening_practice';
COMMENT ON COLUMN lessons.hint_text IS 'Hint text to help students solve the exercise';
COMMENT ON COLUMN lessons.success_message IS 'Custom message shown after solving the exercise';

COMMIT;
```

---

## Rollback Script

**File:** `backend/migrations/001_add_chess_board_columns_rollback.sql`

```sql
-- Rollback: Remove animated chess board columns
-- Created: 2025-01-20

BEGIN;

-- Drop constraint
ALTER TABLE lessons
DROP CONSTRAINT IF EXISTS valid_exercise;

-- Drop index
DROP INDEX IF EXISTS idx_lessons_exercise_type;

-- Drop columns
ALTER TABLE lessons
DROP COLUMN IF EXISTS solution_move,
DROP COLUMN IF EXISTS exercise_type,
DROP COLUMN IF EXISTS hint_text,
DROP COLUMN IF EXISTS success_message;

COMMIT;
```

---

## Sample Data - MVP Exercises

### Exercise 1: Checkmate in 1

```sql
INSERT INTO lessons (
  course_id,
  title,
  content,
  lesson_type,
  order_num,
  exercise_fen,
  solution_move,
  exercise_type,
  hint_text,
  success_message
) VALUES (
  'course-uuid-here',
  'Lesson 1: Back Rank Mate',
  'The back rank mate is one of the most important checkmate patterns. When a king is trapped on its starting rank by its own pawns, a rook or queen can deliver checkmate.',
  'exercise',
  1,
  '6k1/5ppp/8/8/8/8/8/R6K w - - 0 1',  -- White to move, Ra8# is mate
  'a1a8',  -- Solution: Ra8#
  'one_move_puzzle',
  'The black king is trapped by its own pawns. Can you deliver checkmate on the back rank?',
  'Perfect! That''s back rank mate! The king had nowhere to go.'
);
```

### Exercise 2: Win Material

```sql
INSERT INTO lessons (
  course_id,
  title,
  content,
  lesson_type,
  order_num,
  exercise_fen,
  solution_move,
  exercise_type,
  hint_text,
  success_message
) VALUES (
  'course-uuid-here',
  'Lesson 2: Fork the King and Queen',
  'A knight fork is when the knight attacks two pieces at once. The knight can fork the king and queen, winning the queen!',
  'exercise',
  2,
  'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 1',
  'f3g5',  -- Solution: Ng5 forks king and queen
  'one_move_puzzle',
  'Look for a knight move that attacks two pieces at once!',
  'Excellent! You won the queen with a knight fork!'
);
```

### Exercise 3: Simple Check

```sql
INSERT INTO lessons (
  course_id,
  title,
  content,
  lesson_type,
  order_num,
  exercise_fen,
  solution_move,
  exercise_type,
  hint_text,
  success_message
) VALUES (
  'course-uuid-here',
  'Lesson 3: Check!',
  'Giving check forces your opponent to respond. Sometimes a check can help you win material or improve your position.',
  'exercise',
  3,
  'rnbqkb1r/pppp1ppp/5n2/4p3/4P3/3P1N2/PPP2PPP/RNBQKB1R w KQkq - 0 1',
  'f1b5',  -- Solution: Bb5+ check
  'one_move_puzzle',
  'Move your bishop to give check!',
  'Great! You gave check and attacked the knight too!'
);
```

---

## Updated TypeScript Interface

**File:** `frontend/src/types/lesson.ts`

```typescript
export interface Lesson {
  id: string;
  courseId: string;
  title: string;
  content: string;
  lessonType: 'theory' | 'exercise' | 'practice';
  orderNum: number;
  createdAt: string;
  updatedAt: string;

  // Exercise fields
  exerciseFen?: string;
  solutionMove?: string;  // NEW: UCI notation (e.g., "e2e4")
  exerciseType?: 'one_move_puzzle' | 'multi_move' | 'position_eval' | 'opening_practice';  // NEW
  hintText?: string;  // NEW
  successMessage?: string;  // NEW
}

// Helper type for exercises specifically
export interface ExerciseLesson extends Lesson {
  exerciseFen: string;
  solutionMove: string;
  exerciseType: 'one_move_puzzle';
  hintText?: string;
  successMessage?: string;
}

// Type guard
export function isExerciseLesson(lesson: Lesson): lesson is ExerciseLesson {
  return !!(lesson.exerciseFen && lesson.solutionMove);
}
```

---

## Backend API Updates

### Lesson Response Schema

```typescript
// backend/src/api/lessons.ts

interface LessonResponse {
  id: string;
  course_id: string;
  title: string;
  content: string;
  lesson_type: 'theory' | 'exercise' | 'practice';
  order_num: number;
  created_at: string;
  updated_at: string;

  // Exercise fields (null if not an exercise)
  exercise_fen: string | null;
  solution_move: string | null;  // NEW
  exercise_type: string | null;  // NEW
  hint_text: string | null;  // NEW
  success_message: string | null;  // NEW
}
```

### Validation Function

```typescript
// backend/src/lib/chess/validator.ts

import { Chess } from 'chess.js';

export function validateExerciseData(
  exerciseFen: string,
  solutionMove: string
): { valid: boolean; error?: string } {
  try {
    // 1. Validate FEN
    const chess = new Chess(exerciseFen);

    // 2. Validate move format (UCI notation)
    const uciRegex = /^[a-h][1-8][a-h][1-8][qrbn]?$/;
    if (!uciRegex.test(solutionMove)) {
      return {
        valid: false,
        error: 'Invalid UCI notation. Expected format: e2e4 or e7e8q',
      };
    }

    // 3. Extract move parts
    const from = solutionMove.slice(0, 2);
    const to = solutionMove.slice(2, 4);
    const promotion = solutionMove.length === 5 ? solutionMove[4] : undefined;

    // 4. Validate move is legal
    const move = chess.move({ from, to, promotion });
    if (!move) {
      return {
        valid: false,
        error: `Move ${solutionMove} is not legal in position ${exerciseFen}`,
      };
    }

    return { valid: true };
  } catch (error) {
    return {
      valid: false,
      error: error instanceof Error ? error.message : 'Unknown validation error',
    };
  }
}
```

---

## Testing Data

### Test Script to Insert Sample Exercises

```sql
-- Insert test exercises for MVP
-- Run in Supabase SQL Editor

BEGIN;

-- Get the first course ID (update with actual course ID)
WITH first_course AS (
  SELECT id FROM courses LIMIT 1
)
-- Exercise 1: Back rank mate
INSERT INTO lessons (
  course_id, title, content, lesson_type, order_num,
  exercise_fen, solution_move, exercise_type, hint_text, success_message
)
SELECT
  id,
  'Back Rank Mate',
  'The king is trapped on the back rank. Deliver checkmate!',
  'exercise',
  100,
  '6k1/5ppp/8/8/8/8/8/R6K w - - 0 1',
  'a1a8',
  'one_move_puzzle',
  'The black king is trapped. Use your rook!',
  'Perfect! That''s back rank mate!'
FROM first_course;

-- Exercise 2: Knight fork
INSERT INTO lessons (
  course_id, title, content, lesson_type, order_num,
  exercise_fen, solution_move, exercise_type, hint_text, success_message
)
SELECT
  id,
  'Knight Fork',
  'Find the move that attacks king and queen!',
  'exercise',
  101,
  'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 1',
  'f3g5',
  'one_move_puzzle',
  'The knight can attack two pieces at once!',
  'Excellent! You won the queen!'
FROM first_course;

-- Exercise 3: Pin the knight
INSERT INTO lessons (
  course_id, title, content, lesson_type, order_num,
  exercise_fen, solution_move, exercise_type, hint_text, success_message
)
SELECT
  id,
  'Pin the Knight',
  'Pin the knight to the king!',
  'exercise',
  102,
  'rnbqkb1r/pppp1ppp/5n2/4p3/4P3/3P1N2/PPP2PPP/RNBQKB1R w KQkq - 0 1',
  'f1b5',
  'one_move_puzzle',
  'Use your bishop to attack the knight!',
  'Great! The knight is pinned!'
FROM first_course;

COMMIT;
```

---

## Supabase Configuration

### Row Level Security (RLS) Policies

```sql
-- Enable RLS on lessons table
ALTER TABLE lessons ENABLE ROW LEVEL SECURITY;

-- Policy: Users can read all lessons
CREATE POLICY "Users can read lessons"
ON lessons
FOR SELECT
TO authenticated
USING (true);

-- Policy: Admins can manage lessons
CREATE POLICY "Admins can manage lessons"
ON lessons
FOR ALL
TO authenticated
USING (
  auth.jwt() ->> 'role' = 'admin'
);
```

---

## Migration Checklist

- [ ] Backup production database
- [ ] Run migration script in development environment
- [ ] Validate new columns exist
- [ ] Test constraint with invalid data
- [ ] Insert sample exercises
- [ ] Update backend API types
- [ ] Update frontend TypeScript interfaces
- [ ] Test exercise creation in admin panel
- [ ] Test exercise display in lesson page
- [ ] Run migration in production
- [ ] Verify no data loss
- [ ] Monitor for errors

---

## Next Steps

1. ✅ Schema updates defined
2. ⏳ Run migration in development
3. ⏳ Update backend API
4. ⏳ Update frontend types
5. ⏳ Implement AnimatedChessBoard component
6. ⏳ Test with sample exercises
7. ⏳ Deploy to production

---

## References

- [Supabase Migrations](https://supabase.com/docs/guides/database/migrations)
- [PostgreSQL Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [Chess.js Move Validation](https://github.com/jhlywa/chess.js/blob/master/README.md)
- [UCI Notation Format](https://en.wikipedia.org/wiki/Universal_Chess_Interface)
- [COMPONENT_ARCHITECTURE.md](COMPONENT_ARCHITECTURE.md)
- [ANIMATED_BOARD_PRD.md](ANIMATED_BOARD_PRD.md)
