# Product Requirements Document: Animated Beginner Chess Board

## Executive Summary

Build a playful, hand-drawn animated chess board for absolute beginners in the Learning Course section, using the chessground library with custom styling and animations. This feature differentiates the platform by offering age-appropriate themed boards (starting with one bold, playful style for MVP).

**Timeline:** 1 week MVP
**Scope:** Replace FEN placeholder in lesson exercises with interactive animated board
**Platform:** Mobile-first responsive web app (works great on desktop too)

---

## 1. Product Vision

### 1.1 Problem Statement
Current lesson exercises show only FEN strings with a placeholder message. Absolute beginners (who may never have seen chess) need:
- Visual, interactive way to learn chess pieces and moves
- Immediate, playful feedback on their attempts
- Fun, game-like experience that reduces intimidation
- Mobile-friendly touch interface for learning on-the-go

### 1.2 Solution
An animated chess board that:
- Uses hand-drawn illustrated pieces with bold, vibrant colors
- Provides playful, silly feedback (celebrates mistakes as learning moments)
- Teaches through 1-move puzzles with immediate visual feedback
- Follows Duolingo's proven UX pattern for educational engagement
- Works seamlessly on mobile and desktop

### 1.3 Success Metrics
- **Lesson completion rate**: % of users who complete exercises
- **Time on task**: Engagement duration per lesson
- **Error recovery**: % of users who retry after wrong moves
- **User feedback**: Qualitative satisfaction with "fun factor"

### 1.4 Strategic Differentiation
**Future Vision:** Multiple themed boards for different age groups
- Kids theme (super playful, cartoonish)
- Teen theme (adventure/fantasy elements)
- Adult theme (elegant, sophisticated)
- **MVP:** Prove concept with one bold, hand-drawn style
- **Competitive edge:** Duolingo has one style; we'll offer personalized age-appropriate experiences

---

## 2. User Personas

### Primary: Complete Chess Beginner (All Ages)
- **Chess Knowledge:** Never played chess, may not know piece names
- **Learning Style:** Visual, interactive, needs immediate feedback
- **Motivation:** Wants to learn chess but finds it intimidating
- **Device:** Primarily mobile (phone/tablet), occasionally desktop
- **Pain Points:** Traditional chess boards feel too serious, complex, overwhelming

### Secondary: Casual Learner
- **Chess Knowledge:** Knows piece names, learning how they move
- **Learning Style:** Prefers gamified, bite-sized lessons
- **Motivation:** Fun hobby, mental exercise
- **Device:** Mixed mobile/desktop usage

---

## 3. Feature Requirements

### 3.1 Core Functionality

#### 3.1.1 Board Display
- **Library:** chessground (Lichess's chess board engine)
- **Visual Style:** Hand-drawn illustrated pieces
- **Color Scheme:** Bold & playful (bright greens, blues, oranges, purples)
- **Piece Assets:** Open-source hand-drawn chess sets, customized to vibrant palette
- **Layout:** Full-width on mobile, centered on desktop
- **Orientation:** Always show from student's perspective (configurable per lesson)

#### 3.1.2 Interactive Puzzle Mode (1-Move Exercises)
```typescript
// Lesson data structure
interface Lesson {
  id: string
  title: string
  content: string // Markdown lesson content
  lesson_type: 'theory' | 'exercise' | 'practice'
  exercise_fen: string | null // Starting position
  solution_move: string | null // e.g., "e2e4" (UCI notation)
  exercise_type: 'one_move_puzzle' // MVP only supports this
}
```

**Flow:**
1. Load position from `exercise_fen`
2. Student clicks/taps piece to move
3. Validate move against `solution_move`
4. Show feedback animation (correct/incorrect)
5. If correct → show success banner + "Continue" button
6. If incorrect → shake animation + allow retry

#### 3.1.3 Animation Requirements

**MUST-HAVE Animations (MVP):**

1. **Piece Movement - Arc/Hop Trajectory**
   - Pieces jump in playful curved arc (not straight line)
   - Duration: 400-600ms
   - Easing: ease-out for natural feel
   - Implementation: CSS transform + translate with keyframes

2. **Correct Move Feedback**
   - Green glow around piece/destination square
   - Sparkle/particle effect (subtle confetti)
   - Success sound (optional for MVP)
   - Duration: 800ms
   - Celebration completes before "Continue" button appears

3. **Wrong Move Feedback**
   - Shake animation (piece vibrates back to original square)
   - Red flash on destination square (subtle, not harsh)
   - Duration: 500ms
   - Piece returns to original position
   - Hint: "Try again!" message or tooltip

4. **Hint System**
   - "Need Help?" button shows glowing squares for valid moves
   - Pulsing animation on correct destination square
   - Toggle on/off without penalty
   - Duration: Continuous pulse until move made

5. **Capture Animation (if puzzle involves capture)**
   - Poof/explosion effect (particle burst)
   - Captured piece fades out during explosion
   - Duration: 600ms
   - Special celebration for important captures (queen, checkmate)

6. **Check Indicator (if relevant to puzzle)**
   - Subtle highlight on threatened king square
   - Red border or glow (not flashing)
   - Persistent until check resolved
   - Educational: helps student understand threat

**DEFERRED Animations (Post-MVP):**
- Checkmate celebration (full-screen confetti)
- Piece rotation/wobble on landing
- Board flip animation
- Tutorial arrows/overlays
- Mascot character reactions

### 3.2 UI Layout (Mobile-First)

**Reference:** Duolingo chess screenshot provided

```
┌─────────────────────────────────────┐
│ [X]  Progress Bar          [❤️ 21]  │ ← Top bar
├─────────────────────────────────────┤
│                                     │
│  Solve the Puzzle / Решите задачу  │ ← Title
│                                     │
│  ┌───────────────────────────┐     │
│  │   Character Avatar        │     │
│  │   Speech Bubble:          │     │ ← Mascot (future)
│  │   "Hint text here"        │     │
│  └───────────────────────────┘     │
│                                     │
│  ┌─────────────────────────────┐   │
│  │                             │   │
│  │      CHESS BOARD            │   │ ← Main board
│  │      (8x8 squares)          │   │
│  │                             │   │
│  └─────────────────────────────┘   │
│                                     │
│  [Need Help?] button (optional)    │ ← Hint button
│                                     │
├─────────────────────────────────────┤
│  ✓ Great! / Здорово!                │ ← Success banner
│  ┌─────────────────────────────┐   │   (appears on
│  │      CONTINUE               │   │    correct move)
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

**Component Breakdown:**
- **TopBar**: Progress indicator, lives/gems count, close button
- **LessonTitle**: "Solve the Puzzle" (i18n supported)
- **MascotSection**: Character avatar + speech bubble (placeholder for MVP)
- **AnimatedChessBoard**: Chessground instance with custom styling
- **HintButton**: Toggle hint highlights (optional)
- **SuccessBanner**: Green slide-up banner with "Continue" button
- **ErrorFeedback**: Inline message or toast (not blocking)

### 3.3 Lesson Integration

**Current Implementation:**
File: `chess-ultimate-app/frontend/src/app/lessons/[id]/page.tsx` (lines 191-199)

**MVP Changes:**
1. Replace placeholder `<div>` with `<AnimatedChessBoard>` component
2. Pass props: `fen`, `solutionMove`, `onCorrectMove`, `onWrongMove`
3. Handle success state: Show "Continue" button → mark lesson complete → redirect

**Code Example:**
```tsx
// In lessons/[id]/page.tsx
{lesson.exercise_fen && lesson.solution_move && (
  <AnimatedChessBoard
    fen={lesson.exercise_fen}
    solutionMove={lesson.solution_move}
    onCorrectMove={handleCorrectMove}
    onWrongMove={handleWrongMove}
    showHints={showHints}
    disabled={puzzleSolved}
  />
)}

{puzzleSolved && (
  <SuccessBanner onContinue={completeLesson} />
)}
```

### 3.4 Data Schema Updates

**Lessons Table (Supabase):**
```sql
-- Add new columns to lessons table
ALTER TABLE lessons
ADD COLUMN solution_move VARCHAR(10), -- UCI notation: "e2e4"
ADD COLUMN exercise_type VARCHAR(50) DEFAULT 'one_move_puzzle';

-- Example lesson data
INSERT INTO lessons (title, exercise_fen, solution_move, exercise_type)
VALUES (
  'Checkmate in One',
  'r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 0 1',
  'f3f7', -- Qxf7# checkmate
  'one_move_puzzle'
);
```

### 3.5 Accessibility (Post-MVP)
**Deferred to v2:**
- Colorblind mode (alternative color schemes)
- Reduced motion option (disable animations)
- Keyboard navigation
- Screen reader support

**MVP Approach:** Focus on core visual experience, add accessibility in follow-up sprint.

---

## 4. Technical Specifications

### 4.1 Technology Stack

**Library:** chessground v8+
- **Why:** Highly customizable, proven by Lichess, excellent animation API
- **Installation:** `npm install chessground`
- **Documentation:** https://github.com/lichess-org/chessground

**Chess Logic:** chess.js
- **Why:** Validate moves, generate legal moves for hints
- **Already in project:** ✅ (used in analysis board)

**Animation Framework:** CSS Animations + React Spring (optional)
- **CSS:** Keyframes for piece movements, transforms
- **React Spring:** (Optional) For more complex physics-based animations

### 4.2 Component Architecture

```
src/components/AnimatedChessBoard/
├── index.tsx                    # Main component export
├── AnimatedChessBoard.tsx       # Chessground wrapper + game logic
├── SuccessBanner.tsx            # Green celebration banner
├── HintButton.tsx               # Show/hide hint system
├── useChessPuzzle.ts            # Custom hook for puzzle state
├── animations.ts                # Animation config & utilities
├── chessboard.css               # Chessground custom styles
└── assets/
    └── pieces/                  # Hand-drawn piece SVGs
        ├── wK.svg               # White King
        ├── wQ.svg               # White Queen
        ├── bK.svg               # Black King
        └── ... (12 pieces total)
```

**Key Files:**

**`AnimatedChessBoard.tsx`:**
```tsx
import { Chessground } from 'chessground'
import { Chess } from 'chess.js'
import './chessboard.css'

interface AnimatedChessBoardProps {
  fen: string
  solutionMove: string // UCI: "e2e4"
  onCorrectMove: () => void
  onWrongMove: () => void
  showHints?: boolean
  disabled?: boolean
}

export const AnimatedChessBoard: React.FC<AnimatedChessBoardProps> = ({
  fen,
  solutionMove,
  onCorrectMove,
  onWrongMove,
  showHints = false,
  disabled = false,
}) => {
  // Implementation details in development phase
  // - Initialize chessground
  // - Set custom piece theme (hand-drawn SVGs)
  // - Handle move validation
  // - Trigger animations
  // - Emit events (correct/wrong)
}
```

**`useChessPuzzle.ts`:**
```tsx
export const useChessPuzzle = (fen: string, solution: string) => {
  const [game, setGame] = useState(() => new Chess(fen))
  const [solved, setSolved] = useState(false)
  const [attempts, setAttempts] = useState(0)

  const validateMove = (from: string, to: string) => {
    const moveUCI = from + to
    if (moveUCI === solution) {
      setSolved(true)
      return 'correct'
    } else {
      setAttempts(prev => prev + 1)
      return 'incorrect'
    }
  }

  return { game, solved, attempts, validateMove }
}
```

### 4.3 Animation Implementation

**CSS Keyframes:**
```css
/* Arc trajectory for piece movement */
@keyframes piece-hop {
  0% {
    transform: translate(0, 0) scale(1);
  }
  50% {
    transform: translate(var(--mid-x), var(--mid-y)) translateY(-30px) scale(1.1);
  }
  100% {
    transform: translate(var(--end-x), var(--end-y)) scale(1);
  }
}

/* Shake on wrong move */
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-10px); }
  75% { transform: translateX(10px); }
}

/* Success glow */
@keyframes success-glow {
  0% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }
  100% { box-shadow: 0 0 0 20px rgba(34, 197, 94, 0); }
}

/* Particle explosion */
@keyframes particle-burst {
  0% {
    transform: translate(0, 0) scale(1);
    opacity: 1;
  }
  100% {
    transform: translate(var(--x), var(--y)) scale(0);
    opacity: 0;
  }
}
```

**Chessground Config:**
```tsx
const config = {
  fen: fen,
  orientation: 'white',
  movable: {
    free: false,
    color: 'white',
    events: {
      after: handleMove, // Validate on move complete
    },
  },
  animation: {
    enabled: true,
    duration: 500, // Arc animation duration
  },
  highlight: {
    lastMove: true,
    check: true, // Highlight king in check
  },
  drawable: {
    enabled: showHints, // Allow hint overlays
  },
}
```

### 4.4 Hand-Drawn Piece Assets

**Open-Source Options to Evaluate:**

1. **Merida (Classic hand-drawn style)**
   - License: GPL
   - Style: Traditional, sketch-like
   - Customization: Recolor to vibrant palette

2. **Adventurer (Playful cartoon style)**
   - License: MIT
   - Style: Fun, whimsical characters
   - Customization: Already colorful, adjust brightness

3. **Alpha (Minimalist artistic)**
   - License: Creative Commons
   - Style: Clean, modern illustrated
   - Customization: Add bold colors

4. **Custom AI Generation (Fallback)**
   - Tool: Midjourney/DALL-E
   - Prompt: "Hand-drawn chess pieces, vibrant colors, playful style, SVG-ready"
   - Process: Generate → vectorize → optimize

**MVP Decision:** Select 1 set (Merida or Adventurer), customize colors in SVG editor, integrate with chessground.

**Color Palette (Bold & Playful):**
```css
:root {
  /* Piece colors */
  --piece-light: #FFD93D; /* Bright yellow/gold */
  --piece-dark: #6BCB77;  /* Vibrant green */

  /* Board colors */
  --square-light: #F8F9FA; /* Off-white */
  --square-dark: #95D5B2;  /* Soft green */

  /* Feedback colors */
  --success: #22C55E;  /* Green */
  --error: #EF4444;    /* Red */
  --hint: #3B82F6;     /* Blue */

  /* Accent colors */
  --accent-orange: #FB923C;
  --accent-purple: #A855F7;
}
```

### 4.5 Performance Optimization

**Mobile-First Considerations:**
- **Asset Size:** Optimize SVGs (< 5KB per piece, ~60KB total)
- **Animation FPS:** Target 60fps, use CSS transforms (GPU-accelerated)
- **Bundle Size:** Chessground (~50KB gzipped), lazy load component
- **Touch Responsiveness:** < 100ms tap-to-move latency

**Implementation:**
- Lazy load: `const AnimatedChessBoard = lazy(() => import('./AnimatedChessBoard'))`
- Preload piece SVGs on lesson page load
- Use `will-change: transform` for animated elements
- Debounce hint toggles to avoid re-renders

---

## 5. User Flows

### 5.1 Happy Path: Solve Puzzle on First Try

```
1. Student navigates to lesson with exercise
2. Lesson content loads (markdown theory)
3. AnimatedChessBoard renders with starting position
4. Student reads hint from mascot (future) or title
5. Student taps piece → sees valid move highlights (if hints enabled)
6. Student taps destination square
7. Piece animates with arc trajectory (600ms)
8. Move validated: CORRECT ✓
9. Success animation plays (glow + sparkles, 800ms)
10. Green banner slides up: "Great! 🎉"
11. "Continue" button appears
12. Student taps "Continue"
13. Lesson marked complete, redirect to course page
```

### 5.2 Alternate Path: Wrong Move → Retry → Success

```
1-6. [Same as happy path]
7. Piece animates toward wrong square
8. Move validated: INCORRECT ✗
9. Shake animation plays (500ms)
10. Red flash on destination square
11. Piece returns to original position
12. Message: "Try again!" (toast or inline)
13. Student taps "Need Help?" button
14. Hint highlights appear (glowing correct square)
15. Student makes correct move
16. [Continue with steps 7-13 from happy path]
```

### 5.3 Edge Cases

**Case 1: Multiple valid solutions**
- MVP: Only support single-solution puzzles
- Data validation: Ensure `solution_move` is unique best move

**Case 2: Student makes legal but suboptimal move**
- Treat as incorrect (shake animation)
- Hint: "That's legal, but there's a better move!"

**Case 3: Touch drag vs tap-tap**
- Support both interaction modes
- Chessground handles this natively

**Case 4: Student leaves lesson before solving**
- Save progress state to backend
- On return, load previous position (not MVP, manual complete button exists)

---

## 6. Development Plan (1-Week Sprint)

### Day 1-2: Setup & Integration
- [ ] Install chessground library
- [ ] Create `AnimatedChessBoard` component structure
- [ ] Integrate with lesson page (replace placeholder)
- [ ] Basic board rendering (no animations yet)
- [ ] Load FEN from lesson data

### Day 3-4: Core Animations
- [ ] Implement arc trajectory for piece movement
- [ ] Add correct move feedback (glow + sparkles)
- [ ] Add wrong move feedback (shake + return)
- [ ] CSS keyframes for all animations
- [ ] Test on mobile devices

### Day 5: Assets & Styling
- [ ] Source open-source hand-drawn piece set
- [ ] Customize SVGs to bold color palette
- [ ] Integrate pieces with chessground theme
- [ ] Style board squares (light/dark colors)
- [ ] Responsive layout adjustments

### Day 6: Hint System & Polish
- [ ] Implement "Need Help?" button
- [ ] Highlight valid moves on hint toggle
- [ ] Success banner component
- [ ] "Continue" button → complete lesson flow
- [ ] Error handling (invalid FEN, missing solution)

### Day 7: Testing & Deployment
- [ ] Cross-browser testing (Chrome, Safari, Firefox)
- [ ] Mobile testing (iOS Safari, Android Chrome)
- [ ] Performance profiling (FPS, bundle size)
- [ ] Update lesson seed data with `solution_move`
- [ ] Deploy to staging, user testing

---

## 7. Success Criteria

### 7.1 Functional Requirements ✅
- [ ] Board renders correctly from FEN
- [ ] Pieces move with arc animation (smooth 60fps)
- [ ] Correct move triggers success animation + banner
- [ ] Wrong move triggers shake + allows retry
- [ ] Hint system highlights valid moves
- [ ] "Continue" button completes lesson
- [ ] Works on mobile (touch) and desktop (mouse)

### 7.2 Performance Requirements ✅
- [ ] Initial load < 2 seconds on 3G
- [ ] Animation frame rate: 60fps
- [ ] Bundle size increase < 100KB
- [ ] Touch latency < 100ms

### 7.3 User Experience Requirements ✅
- [ ] Intuitive for absolute beginners (no instructions needed)
- [ ] Playful, fun, celebratory feedback
- [ ] No frustrating dead ends (always can retry)
- [ ] Mobile-friendly tap targets (min 44x44px)

---

## 8. Future Enhancements (Post-MVP)

### Phase 2: Mascot Character & Storytelling
- Design tutor character (wise owl? friendly knight?)
- Animated speech bubbles with contextual hints
- Character reactions to student moves
- Narrative progression through lessons

### Phase 3: Multi-Move Puzzles
- Support puzzle sequences (3-5 moves)
- Branching logic for opponent responses
- Progressive difficulty

### Phase 4: Multiple Board Themes
- **Kids Theme:** Super playful, cartoonish pieces, bright primary colors
- **Teen Theme:** Fantasy/adventure style, magical effects
- **Adult Theme:** Elegant, sophisticated, minimalist
- Theme selector in user settings

### Phase 5: Advanced Animations
- Checkmate celebrations (confetti, fanfare)
- Piece rotation/physics on landing
- Tutorial overlays (arrows, highlights)
- Animated opening theory demonstrations

### Phase 6: Accessibility
- Colorblind modes (multiple palettes)
- Reduced motion option
- Keyboard navigation
- Screen reader support (ARIA labels)

---

## 9. Open Questions & Risks

### 9.1 Questions for Stakeholders
- **Mascot Design:** Start mascot design in parallel, or wait for MVP feedback?
- **Sound Effects:** Add success/error sounds in MVP, or defer to Phase 2?
- **Lesson Content:** Who creates 1-move puzzles for seed data? (Need ~20 for testing)

### 9.2 Technical Risks
- **Chessground Learning Curve:** Team unfamiliar with library (mitigation: allocate extra time Day 1-2)
- **Animation Performance on Low-End Devices:** May need to reduce complexity (mitigation: test early, Day 4)
- **SVG Asset Quality:** Open-source sets may not match desired style (mitigation: have AI generation fallback)

### 9.3 Dependencies
- **Backend:** Lesson data must include `solution_move` field (migration script needed)
- **Design:** Final piece assets must be ready by Day 5 (start sourcing Day 1)
- **Testing Devices:** Need iOS and Android devices for mobile testing (borrow/rent if needed)

---

## 10. Appendix

### 10.1 References
- **Duolingo Chess:** https://blog.duolingo.com/chess-course/
- **Chessground Docs:** https://github.com/lichess-org/chessground
- **Lichess Piece Themes:** https://github.com/lichess-org/lila/tree/master/public/piece
- **Design Inspiration:** Attached screenshot (Duolingo puzzle layout)

### 10.2 Related Documents
- [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) - Overall project architecture
- [README.md](README.md) - Project setup and tech stack
- Lesson seed script: `backend/seed_courses.py`

### 10.3 Glossary
- **FEN:** Forsyth-Edwards Notation (chess position string)
- **UCI:** Universal Chess Interface notation for moves (e.g., "e2e4")
- **Chessground:** Lichess's open-source chess board library
- **1-Move Puzzle:** Exercise where student makes single correct move to solve

---

**Document Version:** 1.0
**Last Updated:** 2025-01-19
**Author:** Product Team
**Approval Status:** Ready for Development
