# Implementation Locations - Animated Chess Board

## Overview

This document defines exactly where each component will be implemented in the existing project structure.

---

## Project Structure

```
chess-ultimate-app/
├── frontend/
│   ├── public/
│   │   └── pieces/                           ← Chess assets
│   │       ├── alpha/                        ✅ EXISTS (Lichess pieces)
│   │       └── lichess-brown-board.png       ✅ EXISTS (Board image)
│   └── src/
│       ├── app/
│       │   └── lessons/
│       │       └── [id]/
│       │           └── page.tsx              📝 TO UPDATE (integrate board)
│       ├── components/                       📁 EXISTS (currently has LoadingScreen.tsx)
│       │   └── chess/                        🆕 NEW DIRECTORY
│       │       ├── AnimatedChessBoard.tsx    🆕 NEW (main component)
│       │       ├── BoardControls.tsx         🆕 NEW (hint/reset buttons)
│       │       └── FeedbackDisplay.tsx       🆕 NEW (success/error banner)
│       ├── lib/                              🆕 NEW DIRECTORY
│       │   └── chess/                        🆕 NEW DIRECTORY
│       │       ├── chessgroundConfig.ts      🆕 NEW (board config)
│       │       ├── moveValidator.ts          🆕 NEW (move validation)
│       │       └── animations.ts             🆕 NEW (animation utilities)
│       ├── styles/                           🆕 NEW DIRECTORY
│       │   └── chess-animations.css          🆕 NEW (CSS animations)
│       └── types/                            🆕 NEW DIRECTORY
│           └── lesson.ts                     🆕 NEW (TypeScript interfaces)
└── backend/
    ├── migrations/                           🆕 NEW DIRECTORY
    │   ├── 001_add_chess_board_columns.sql   🆕 NEW (migration)
    │   └── 001_rollback.sql                  🆕 NEW (rollback)
    └── lib/
        └── chess/                            🆕 NEW DIRECTORY
            └── validator.py                  🆕 NEW (server-side validation)
```

---

## Implementation Order

### Phase 1: Setup & Assets (15 min)
**Status:** ✅ COMPLETE

1. ✅ Chess assets in place
   - `frontend/public/pieces/alpha/` (12 SVG files)
   - `frontend/public/pieces/lichess-brown-board.png`

### Phase 2: Database Migration (30 min)

**Location:** `backend/migrations/`

**Files to create:**
1. `backend/migrations/001_add_chess_board_columns.sql`
2. `backend/migrations/001_add_chess_board_columns_rollback.sql`

**Tasks:**
- [ ] Create migration files
- [ ] Run migration in Supabase dev environment
- [ ] Insert sample exercises (3-5 puzzles)
- [ ] Verify data with SQL queries

---

### Phase 3: TypeScript Types (15 min)

**Location:** `frontend/src/types/`

**Files to create:**
1. `frontend/src/types/lesson.ts`

```typescript
// New file: frontend/src/types/lesson.ts
export interface Lesson {
  id: string;
  courseId: string;
  title: string;
  content: string;
  lessonType: 'theory' | 'exercise' | 'practice';
  orderNum: number;

  // Exercise fields
  exerciseFen?: string;
  solutionMove?: string;
  exerciseType?: 'one_move_puzzle';
  hintText?: string;
  successMessage?: string;
}

export interface ExerciseLesson extends Lesson {
  exerciseFen: string;
  solutionMove: string;
}

export function isExerciseLesson(lesson: Lesson): lesson is ExerciseLesson {
  return !!(lesson.exerciseFen && lesson.solutionMove);
}
```

**Tasks:**
- [ ] Create `types/` directory
- [ ] Create `lesson.ts` with interfaces
- [ ] Export types from `types/index.ts`

---

### Phase 4: Chess Utilities (45 min)

**Location:** `frontend/src/lib/chess/`

**Files to create:**

#### 4.1 `chessgroundConfig.ts`
```typescript
// Configuration for Chessground library
import { Config } from 'chessground/config';

export function getChessgroundConfig(
  fen: string,
  onMove: (orig: Key, dest: Key) => void,
  orientation: 'white' | 'black' = 'white'
): Config {
  // ... (from COMPONENT_ARCHITECTURE.md)
}
```

#### 4.2 `moveValidator.ts`
```typescript
// Move validation using chess.js
import { Chess } from 'chess.js';

export class MoveValidator {
  // ... (from COMPONENT_ARCHITECTURE.md)
}
```

#### 4.3 `animations.ts`
```typescript
// Animation controller utilities
export const ANIMATION_CLASSES = { /* ... */ };
export const ANIMATION_DURATIONS = { /* ... */ };
export function animateElement(/* ... */) { /* ... */ }
```

**Tasks:**
- [ ] Create `lib/chess/` directory
- [ ] Implement `chessgroundConfig.ts`
- [ ] Implement `moveValidator.ts`
- [ ] Implement `animations.ts`
- [ ] Add unit tests (optional for MVP)

---

### Phase 5: CSS Animations (30 min)

**Location:** `frontend/src/styles/`

**Files to create:**
1. `frontend/src/styles/chess-animations.css`

**Content:**
- All keyframe animations from ANIMATION_SPECIFICATIONS.md
- Piece movement animations
- Feedback animations
- Board celebration effects
- Reduced motion support

**Integration:**
Update `frontend/src/app/layout.tsx`:
```typescript
import '@/styles/chess-animations.css'
```

**Tasks:**
- [ ] Create `styles/` directory
- [ ] Create `chess-animations.css` with all animations
- [ ] Import in `layout.tsx`
- [ ] Test with browser dev tools

---

### Phase 6: React Components (2-3 hours)

**Location:** `frontend/src/components/chess/`

**Files to create:**

#### 6.1 `FeedbackDisplay.tsx` (Simple - Start Here)
```typescript
// Feedback banner component
interface FeedbackDisplayProps {
  feedback: 'idle' | 'correct' | 'incorrect' | 'hint';
  message?: string;
}

export function FeedbackDisplay({ feedback, message }: FeedbackDisplayProps) {
  // ... (from COMPONENT_ARCHITECTURE.md)
}
```

#### 6.2 `BoardControls.tsx` (Simple)
```typescript
// Hint and reset buttons
interface BoardControlsProps {
  onHint: () => void;
  onReset?: () => void;
  hintDisabled?: boolean;
}

export function BoardControls({ onHint, onReset, hintDisabled }: BoardControlsProps) {
  // ... (from COMPONENT_ARCHITECTURE.md)
}
```

#### 6.3 `AnimatedChessBoard.tsx` (Complex - Main Component)
```typescript
// Main chess board component
interface AnimatedChessBoardProps {
  fen: string;
  solutionMove: string;
  onCorrectMove: () => void;
  onIncorrectMove: (move: string) => void;
  orientation?: 'white' | 'black';
  showHints?: boolean;
  enableAnimations?: boolean;
}

export default function AnimatedChessBoard({ /* ... */ }: AnimatedChessBoardProps) {
  // ... (from COMPONENT_ARCHITECTURE.md)
}
```

**Tasks:**
- [ ] Create `components/chess/` directory
- [ ] Implement `FeedbackDisplay.tsx`
- [ ] Implement `BoardControls.tsx`
- [ ] Implement `AnimatedChessBoard.tsx`
- [ ] Test components in isolation (Storybook optional)

---

### Phase 7: Integrate into Lesson Page (1 hour)

**Location:** `frontend/src/app/lessons/[id]/page.tsx`

**Current code (lines 191-199):**
```typescript
{lesson.exercise_fen && (
  <div className="bg-gray-100 dark:bg-gray-700 p-4 rounded-lg mb-6">
    <h3 className="font-semibold mb-2">Exercise Position (FEN):</h3>
    <code className="text-sm break-all">{lesson.exercise_fen}</code>
    <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
      Chess board visualization will be added in a future update.
    </p>
  </div>
)}
```

**Replace with:**
```typescript
{lesson.exercise_fen && lesson.solution_move && (
  <div className="mb-6">
    <h3 className="font-semibold mb-4 text-lg">Interactive Exercise:</h3>
    <AnimatedChessBoard
      fen={lesson.exercise_fen}
      solutionMove={lesson.solution_move}
      onCorrectMove={completeLesson}
      onIncorrectMove={(move) => {
        console.log('Incorrect move attempted:', move);
      }}
      showHints={true}
      enableAnimations={true}
    />
  </div>
)}
```

**Additional updates:**
1. Add import: `import AnimatedChessBoard from '@/components/chess/AnimatedChessBoard'`
2. Update Lesson interface to include new fields
3. Handle loading state for chessground

**Tasks:**
- [ ] Import AnimatedChessBoard component
- [ ] Replace placeholder div with AnimatedChessBoard
- [ ] Update Lesson type definition
- [ ] Test with sample exercise
- [ ] Handle edge cases (no solution_move, invalid FEN)

---

### Phase 8: Install Dependencies (5 min)

**Location:** `frontend/package.json`

**Add dependencies:**
```bash
cd frontend
npm install chessground chess.js
```

**Version requirements:**
- `chessground`: ^9.0.0
- `chess.js`: ^1.0.0-beta.8

**Tasks:**
- [ ] Run npm install
- [ ] Verify no dependency conflicts
- [ ] Test import in components

---

### Phase 9: Backend Validation (Optional - 30 min)

**Location:** `backend/lib/chess/`

**File to create:**
`backend/lib/chess/validator.py`

```python
import chess

def validate_exercise(fen: str, solution_move: str) -> dict:
    """
    Validate exercise FEN and solution move
    Returns: {"valid": bool, "error": str | None}
    """
    try:
        board = chess.Board(fen)
        move = chess.Move.from_uci(solution_move)

        if move not in board.legal_moves:
            return {
                "valid": False,
                "error": f"Move {solution_move} is not legal in position"
            }

        return {"valid": True, "error": None}
    except Exception as e:
        return {"valid": False, "error": str(e)}
```

**Tasks:**
- [ ] Create validator.py
- [ ] Add endpoint to validate exercises
- [ ] Call from admin panel when creating exercises

---

## Directory Creation Commands

Run these commands to create all necessary directories:

```bash
# Navigate to project root
cd /home/marblemaster/Desktop/Cursor/chess-ultimate-app

# Frontend directories
mkdir -p frontend/src/components/chess
mkdir -p frontend/src/lib/chess
mkdir -p frontend/src/styles
mkdir -p frontend/src/types

# Backend directories
mkdir -p backend/migrations
mkdir -p backend/lib/chess

# Verify structure
echo "✅ Directories created:"
find frontend/src -type d -name "chess" -o -name "types" -o -name "styles"
find backend -type d -name "migrations"
```

---

## File Creation Checklist

### Frontend

**Assets:**
- [x] `frontend/public/pieces/alpha/*.svg` (12 files)
- [x] `frontend/public/pieces/lichess-brown-board.png`

**Types:**
- [ ] `frontend/src/types/lesson.ts`
- [ ] `frontend/src/types/index.ts`

**Utilities:**
- [ ] `frontend/src/lib/chess/chessgroundConfig.ts`
- [ ] `frontend/src/lib/chess/moveValidator.ts`
- [ ] `frontend/src/lib/chess/animations.ts`
- [ ] `frontend/src/lib/chess/index.ts`

**Styles:**
- [ ] `frontend/src/styles/chess-animations.css`

**Components:**
- [ ] `frontend/src/components/chess/FeedbackDisplay.tsx`
- [ ] `frontend/src/components/chess/BoardControls.tsx`
- [ ] `frontend/src/components/chess/AnimatedChessBoard.tsx`
- [ ] `frontend/src/components/chess/index.ts`

**Pages:**
- [ ] Update: `frontend/src/app/lessons/[id]/page.tsx`
- [ ] Update: `frontend/src/app/layout.tsx` (import CSS)

### Backend

**Migrations:**
- [ ] `backend/migrations/001_add_chess_board_columns.sql`
- [ ] `backend/migrations/001_add_chess_board_columns_rollback.sql`

**Validation:**
- [ ] `backend/lib/chess/validator.py`

---

## Implementation Timeline

**Total Estimated Time:** 5-6 hours

| Phase | Task | Time | Files |
|-------|------|------|-------|
| 1 | Setup & Assets | ✅ DONE | 13 files |
| 2 | Database Migration | 30 min | 2 files |
| 3 | TypeScript Types | 15 min | 2 files |
| 4 | Chess Utilities | 45 min | 4 files |
| 5 | CSS Animations | 30 min | 1 file |
| 6 | React Components | 2-3 hours | 4 files |
| 7 | Lesson Page Integration | 1 hour | 2 files |
| 8 | Install Dependencies | 5 min | package.json |
| 9 | Backend Validation (optional) | 30 min | 1 file |

---

## Testing Strategy

### Unit Tests (Optional for MVP)
- `lib/chess/moveValidator.test.ts`
- `lib/chess/animations.test.ts`

### Integration Tests
- Test AnimatedChessBoard with sample FEN
- Test correct move flow
- Test incorrect move flow
- Test hint system

### E2E Tests
- Create lesson with exercise
- Complete exercise successfully
- Verify lesson completion

---

## Next Steps

**Ready to proceed?** Let's implement in this order:

1. **Database Migration** - Get the data structure ready
2. **TypeScript Types** - Define interfaces
3. **Chess Utilities** - Build the foundation
4. **CSS Animations** - Add visual polish
5. **Components** - Build UI piece by piece
6. **Integration** - Connect to lesson page
7. **Testing** - Verify everything works

**Should we start with Phase 2 (Database Migration)?**
