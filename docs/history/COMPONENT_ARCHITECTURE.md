# Component Architecture - Animated Chess Board

## Overview

This document defines the component architecture for integrating the animated chess board into the lesson page using the Chessground library.

---

## Component Hierarchy

```
LessonPage (pages/lessons/[id]/page.tsx)
└── AnimatedChessBoard (new component)
    ├── Chessground (library component)
    ├── MoveValidator (chess.js integration)
    ├── AnimationController (CSS animations)
    └── FeedbackSystem (success/error states)
```

---

## 1. AnimatedChessBoard Component

**Location:** `frontend/src/components/chess/AnimatedChessBoard.tsx`

### Props Interface

```typescript
interface AnimatedChessBoardProps {
  // Initial position in FEN notation
  fen: string;

  // Solution move in UCI notation (e.g., "e2e4")
  solutionMove: string;

  // Callback when user makes correct move
  onCorrectMove: () => void;

  // Callback when user makes incorrect move
  onIncorrectMove: (attemptedMove: string) => void;

  // Board orientation
  orientation?: 'white' | 'black';

  // Enable/disable move hints
  showHints?: boolean;

  // Enable/disable animations
  enableAnimations?: boolean;
}
```

### State Management

```typescript
interface BoardState {
  // Current position (updated after moves)
  currentFen: string;

  // Move validation state
  isValidating: boolean;

  // Feedback state
  feedback: 'idle' | 'correct' | 'incorrect' | 'hint';

  // Move history for undo
  moveHistory: string[];

  // Hint state
  hintShown: boolean;
}
```

### Component Structure

```typescript
export default function AnimatedChessBoard({
  fen,
  solutionMove,
  onCorrectMove,
  onIncorrectMove,
  orientation = 'white',
  showHints = true,
  enableAnimations = true,
}: AnimatedChessBoardProps) {
  const [state, setState] = useState<BoardState>({
    currentFen: fen,
    isValidating: false,
    feedback: 'idle',
    moveHistory: [],
    hintShown: false,
  });

  const boardRef = useRef<HTMLDivElement>(null);
  const chessRef = useRef<Chess>(new Chess(fen));
  const groundRef = useRef<Api | null>(null);

  // Initialize chessground
  useEffect(() => {
    // Setup chessground instance
  }, []);

  // Handle user moves
  const handleMove = (orig: Key, dest: Key) => {
    // Validate and process move
  };

  // Show hint
  const showHint = () => {
    // Highlight solution move square
  };

  return (
    <div className="animated-chess-board">
      <div ref={boardRef} className="chessground-wrapper" />
      <BoardControls onHint={showHint} />
      <FeedbackDisplay feedback={state.feedback} />
    </div>
  );
}
```

---

## 2. Chessground Configuration

**File:** `frontend/src/lib/chess/chessgroundConfig.ts`

```typescript
import { Config } from 'chessground/config';

export function getChessgroundConfig(
  fen: string,
  onMove: (orig: Key, dest: Key) => void,
  orientation: 'white' | 'black' = 'white'
): Config {
  return {
    fen,
    orientation,

    // Movement settings
    movable: {
      free: false, // Only legal moves
      color: 'both',
      showDests: true, // Show legal move hints
      events: {
        after: onMove,
      },
    },

    // Disable features for beginners
    premovable: {
      enabled: false,
    },

    drawable: {
      enabled: false, // No arrows in MVP
    },

    // Visual settings
    highlight: {
      lastMove: true,
      check: true,
    },

    // Coordinates
    coordinates: true,

    // Animation
    animation: {
      enabled: true,
      duration: 200,
    },

    // Disable drag for premove
    draggable: {
      enabled: true,
      showGhost: true,
    },
  };
}
```

---

## 3. Move Validator

**File:** `frontend/src/lib/chess/moveValidator.ts`

```typescript
import { Chess } from 'chess.js';

export class MoveValidator {
  private chess: Chess;

  constructor(fen: string) {
    this.chess = new Chess(fen);
  }

  /**
   * Check if move is legal
   */
  isLegalMove(from: string, to: string): boolean {
    const moves = this.chess.moves({ verbose: true });
    return moves.some(m => m.from === from && m.to === to);
  }

  /**
   * Check if move matches solution
   */
  isSolutionMove(from: string, to: string, solution: string): boolean {
    const moveUci = `${from}${to}`;
    return moveUci === solution;
  }

  /**
   * Make move and return new FEN
   */
  makeMove(from: string, to: string): string | null {
    const move = this.chess.move({ from, to });
    if (!move) return null;
    return this.chess.fen();
  }

  /**
   * Get legal moves for a square
   */
  getLegalMoves(square: string): string[] {
    const moves = this.chess.moves({ square, verbose: true });
    return moves.map(m => m.to);
  }

  /**
   * Get FEN
   */
  getFen(): string {
    return this.chess.fen();
  }

  /**
   * Reset to initial position
   */
  reset(fen: string): void {
    this.chess.load(fen);
  }
}
```

---

## 4. Animation Controller

**File:** `frontend/src/lib/chess/animations.ts`

```typescript
/**
 * CSS class names for board animations
 */
export const ANIMATION_CLASSES = {
  // Piece animations
  PIECE_MOVE: 'piece-move-arc',
  PIECE_CAPTURE: 'piece-capture',
  PIECE_CORRECT: 'piece-correct-glow',
  PIECE_INCORRECT: 'piece-shake',

  // Square animations
  SQUARE_HINT: 'square-hint-pulse',
  SQUARE_CORRECT: 'square-correct-flash',
  SQUARE_INCORRECT: 'square-incorrect-flash',

  // Board feedback
  BOARD_SUCCESS: 'board-success-celebration',
  BOARD_ERROR: 'board-error-shake',
} as const;

/**
 * Animation durations in milliseconds
 */
export const ANIMATION_DURATIONS = {
  PIECE_MOVE: 400,
  PIECE_CAPTURE: 300,
  FEEDBACK: 600,
  HINT: 1000,
  CELEBRATION: 1200,
} as const;

/**
 * Apply animation to element
 */
export function animateElement(
  element: HTMLElement,
  animationClass: string,
  duration: number
): Promise<void> {
  return new Promise((resolve) => {
    element.classList.add(animationClass);

    setTimeout(() => {
      element.classList.remove(animationClass);
      resolve();
    }, duration);
  });
}

/**
 * Animate piece move with arc trajectory
 */
export function animatePieceMove(
  pieceElement: HTMLElement,
  fromSquare: string,
  toSquare: string
): Promise<void> {
  // Calculate arc trajectory
  // Apply CSS transform with arc path
  return animateElement(
    pieceElement,
    ANIMATION_CLASSES.PIECE_MOVE,
    ANIMATION_DURATIONS.PIECE_MOVE
  );
}

/**
 * Show success celebration
 */
export function showSuccessCelebration(boardElement: HTMLElement): Promise<void> {
  return animateElement(
    boardElement,
    ANIMATION_CLASSES.BOARD_SUCCESS,
    ANIMATION_DURATIONS.CELEBRATION
  );
}

/**
 * Show error feedback
 */
export function showErrorFeedback(boardElement: HTMLElement): Promise<void> {
  return animateElement(
    boardElement,
    ANIMATION_CLASSES.BOARD_ERROR,
    ANIMATION_DURATIONS.FEEDBACK
  );
}

/**
 * Pulse hint on square
 */
export function pulseHintSquare(squareElement: HTMLElement): Promise<void> {
  return animateElement(
    squareElement,
    ANIMATION_CLASSES.SQUARE_HINT,
    ANIMATION_DURATIONS.HINT
  );
}
```

---

## 5. Feedback System

**File:** `frontend/src/components/chess/FeedbackDisplay.tsx`

```typescript
interface FeedbackDisplayProps {
  feedback: 'idle' | 'correct' | 'incorrect' | 'hint';
  message?: string;
}

export function FeedbackDisplay({ feedback, message }: FeedbackDisplayProps) {
  if (feedback === 'idle') return null;

  const config = {
    correct: {
      icon: '✓',
      color: 'bg-green-500',
      title: 'Correct!',
      defaultMessage: 'Great move! You found the solution.',
    },
    incorrect: {
      icon: '✗',
      color: 'bg-red-500',
      title: 'Not quite',
      defaultMessage: 'Try again! Think about what the position needs.',
    },
    hint: {
      icon: '💡',
      color: 'bg-yellow-500',
      title: 'Hint',
      defaultMessage: 'The highlighted square shows where to move.',
    },
  }[feedback];

  return (
    <div
      className={`
        feedback-banner ${config.color} text-white p-4 rounded-lg
        flex items-center space-x-3 mt-4
        animate-in slide-in-from-top-2 duration-300
      `}
    >
      <span className="text-2xl">{config.icon}</span>
      <div>
        <h4 className="font-bold">{config.title}</h4>
        <p className="text-sm">{message || config.defaultMessage}</p>
      </div>
    </div>
  );
}
```

---

## 6. Board Controls

**File:** `frontend/src/components/chess/BoardControls.tsx`

```typescript
interface BoardControlsProps {
  onHint: () => void;
  onReset?: () => void;
  hintDisabled?: boolean;
}

export function BoardControls({
  onHint,
  onReset,
  hintDisabled = false,
}: BoardControlsProps) {
  return (
    <div className="board-controls flex space-x-2 mt-4">
      <button
        onClick={onHint}
        disabled={hintDisabled}
        className="
          px-4 py-2 bg-yellow-500 hover:bg-yellow-600
          text-white font-semibold rounded
          disabled:opacity-50 disabled:cursor-not-allowed
          transition-colors
        "
      >
        💡 Show Hint
      </button>

      {onReset && (
        <button
          onClick={onReset}
          className="
            px-4 py-2 bg-gray-500 hover:bg-gray-600
            text-white font-semibold rounded
            transition-colors
          "
        >
          ↻ Reset
        </button>
      )}
    </div>
  );
}
```

---

## 7. Integration with Lesson Page

**File:** `frontend/src/app/lessons/[id]/page.tsx`

### Updated Lesson Interface

```typescript
interface Lesson {
  id: string;
  title: string;
  content: string;
  lesson_type: string;
  exercise_fen: string | null;
  solution_move: string | null; // NEW: UCI notation like "e2e4"
}
```

### Replace Placeholder (Lines 191-199)

```typescript
{lesson.exercise_fen && lesson.solution_move && (
  <div className="mb-6">
    <h3 className="font-semibold mb-4">Interactive Exercise:</h3>
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

---

## 8. CSS Animations

**File:** `frontend/src/styles/chess-animations.css`

```css
/* Piece move with arc trajectory */
@keyframes piece-move-arc {
  0% {
    transform: translate(0, 0);
  }
  50% {
    transform: translate(var(--move-x-mid), calc(var(--move-y-mid) - 20px));
  }
  100% {
    transform: translate(var(--move-x), var(--move-y));
  }
}

.piece-move-arc {
  animation: piece-move-arc 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Correct move glow */
@keyframes piece-correct-glow {
  0%, 100% {
    filter: drop-shadow(0 0 0 transparent);
  }
  50% {
    filter: drop-shadow(0 0 20px rgba(34, 197, 94, 0.8));
  }
}

.piece-correct-glow {
  animation: piece-correct-glow 0.6s ease-in-out;
}

/* Incorrect move shake */
@keyframes piece-shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-8px); }
  75% { transform: translateX(8px); }
}

.piece-shake {
  animation: piece-shake 0.4s ease-in-out;
}

/* Square hint pulse */
@keyframes square-hint-pulse {
  0%, 100% {
    background-color: rgba(234, 179, 8, 0.3);
    transform: scale(1);
  }
  50% {
    background-color: rgba(234, 179, 8, 0.6);
    transform: scale(1.05);
  }
}

.square-hint-pulse {
  animation: square-hint-pulse 1s ease-in-out infinite;
}

/* Square correct flash */
@keyframes square-correct-flash {
  0%, 100% { background-color: transparent; }
  50% { background-color: rgba(34, 197, 94, 0.5); }
}

.square-correct-flash {
  animation: square-correct-flash 0.6s ease-in-out;
}

/* Board success celebration */
@keyframes board-success-celebration {
  0%, 100% { transform: scale(1); }
  25% { transform: scale(1.02); }
  75% { transform: scale(0.98); }
}

.board-success-celebration {
  animation: board-success-celebration 1.2s ease-in-out;
}

/* Board error shake */
@keyframes board-error-shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-10px); }
  75% { transform: translateX(10px); }
}

.board-error-shake {
  animation: board-error-shake 0.5s ease-in-out;
}
```

---

## 9. Package Dependencies

Update `frontend/package.json`:

```json
{
  "dependencies": {
    "chessground": "^9.0.0",
    "chess.js": "^1.0.0-beta.8",
    "react": "^19.0.0",
    "next": "^16.0.0"
  }
}
```

Install command:
```bash
cd frontend && npm install chessground chess.js
```

---

## 10. File Structure

```
frontend/
├── src/
│   ├── components/
│   │   └── chess/
│   │       ├── AnimatedChessBoard.tsx       ← Main component
│   │       ├── BoardControls.tsx            ← Hint/Reset buttons
│   │       └── FeedbackDisplay.tsx          ← Success/Error banner
│   ├── lib/
│   │   └── chess/
│   │       ├── chessgroundConfig.ts         ← Chessground setup
│   │       ├── moveValidator.ts             ← Move validation logic
│   │       └── animations.ts                ← Animation utilities
│   ├── styles/
│   │   └── chess-animations.css             ← CSS animations
│   └── app/
│       └── lessons/
│           └── [id]/
│               └── page.tsx                 ← Updated lesson page
└── public/
    └── pieces/
        ├── alpha/                           ← SVG pieces
        │   ├── wK.svg ... bP.svg
        └── lichess-brown-board.png          ← Board image
```

---

## Next Steps

1. ✅ Component architecture defined
2. ⏳ Define animation specifications and timing (detailed CSS)
3. ⏳ Plan lesson data schema updates for 1-move puzzles
4. ⏳ Implement AnimatedChessBoard component
5. ⏳ Integrate with lesson page
6. ⏳ Test and refine animations

---

## References

- [Chessground API Documentation](https://github.com/lichess-org/chessground/blob/master/src/config.ts)
- [chess.js Documentation](https://github.com/jhlywa/chess.js/blob/master/README.md)
- [React Hooks Best Practices](https://react.dev/reference/react)
- [ANIMATED_BOARD_PRD.md](ANIMATED_BOARD_PRD.md)
- [BOARD_DESIGN_FINALIZED.md](BOARD_DESIGN_FINALIZED.md)
