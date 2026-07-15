# Animation Specifications

## Overview

This document defines the detailed animation specifications, timing curves, and visual effects for the animated chess board. All animations are designed to be playful, beginner-friendly, and celebrate learning.

---

## Animation Philosophy

**Core Principles:**
1. **Celebrate Success** - Make correct moves feel rewarding
2. **Gentle Failure** - Make mistakes feel safe and recoverable
3. **Guide Learning** - Use animations to teach, not just decorate
4. **Smooth Performance** - 60fps on mobile devices
5. **Accessibility** - Support reduced motion preferences

---

## 1. Piece Movement Animations

### Arc Trajectory Movement
**Duration:** 400ms
**Easing:** `cubic-bezier(0.4, 0, 0.2, 1)` (ease-in-out)
**Description:** Pieces hop in a gentle arc when moved

```css
@keyframes piece-move-arc {
  0% {
    transform: translate(0, 0);
    opacity: 1;
  }
  50% {
    /* Arc peak - 20px upward */
    transform: translate(
      calc(var(--move-x) * 0.5),
      calc(var(--move-y) * 0.5 - 20px)
    );
    opacity: 1;
  }
  100% {
    transform: translate(var(--move-x), var(--move-y));
    opacity: 1;
  }
}

.piece-move-arc {
  animation: piece-move-arc 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
```

**Implementation Notes:**
- CSS custom properties `--move-x` and `--move-y` calculated in JS
- Arc height adjusts based on distance (shorter moves = lower arc)
- Piece remains visible throughout animation

---

### Capture Animation
**Duration:** 300ms
**Easing:** `ease-out`
**Description:** Captured piece shrinks and fades with a poof effect

```css
@keyframes piece-capture-poof {
  0% {
    transform: scale(1) rotate(0deg);
    opacity: 1;
  }
  50% {
    transform: scale(1.2) rotate(5deg);
    opacity: 0.7;
  }
  100% {
    transform: scale(0) rotate(15deg);
    opacity: 0;
  }
}

.piece-capture-poof {
  animation: piece-capture-poof 0.3s ease-out forwards;
}

/* Particle effect overlay */
@keyframes capture-particles {
  0% {
    transform: scale(0);
    opacity: 1;
  }
  50% {
    transform: scale(1);
    opacity: 0.8;
  }
  100% {
    transform: scale(1.5);
    opacity: 0;
  }
}

.capture-particles {
  position: absolute;
  width: 100%;
  height: 100%;
  background: radial-gradient(
    circle,
    rgba(234, 179, 8, 0.6) 0%,
    rgba(234, 179, 8, 0) 70%
  );
  animation: capture-particles 0.5s ease-out forwards;
}
```

---

## 2. Feedback Animations

### Correct Move - Success Glow
**Duration:** 600ms
**Easing:** `ease-in-out`
**Description:** Green glow pulses around the piece

```css
@keyframes piece-correct-glow {
  0%, 100% {
    filter: drop-shadow(0 0 0 transparent);
    transform: scale(1);
  }
  50% {
    filter: drop-shadow(0 0 20px rgba(34, 197, 94, 0.8))
            drop-shadow(0 0 10px rgba(34, 197, 94, 0.6));
    transform: scale(1.05);
  }
}

.piece-correct-glow {
  animation: piece-correct-glow 0.6s ease-in-out;
}

/* Square flash underneath */
@keyframes square-correct-flash {
  0%, 100% {
    background-color: transparent;
    box-shadow: none;
  }
  50% {
    background-color: rgba(34, 197, 94, 0.4);
    box-shadow: 0 0 20px rgba(34, 197, 94, 0.5);
  }
}

.square-correct-flash {
  animation: square-correct-flash 0.6s ease-in-out;
}
```

---

### Incorrect Move - Gentle Shake
**Duration:** 400ms
**Easing:** `ease-in-out`
**Description:** Piece shakes side-to-side (not aggressive)

```css
@keyframes piece-incorrect-shake {
  0%, 100% {
    transform: translateX(0) rotate(0deg);
  }
  25% {
    transform: translateX(-6px) rotate(-2deg);
  }
  75% {
    transform: translateX(6px) rotate(2deg);
  }
}

.piece-incorrect-shake {
  animation: piece-incorrect-shake 0.4s ease-in-out;
}

/* Square flash underneath */
@keyframes square-incorrect-flash {
  0%, 100% {
    background-color: transparent;
  }
  50% {
    background-color: rgba(239, 68, 68, 0.3);
  }
}

.square-incorrect-flash {
  animation: square-incorrect-flash 0.4s ease-in-out;
}
```

**Design Note:** Shake is gentle to avoid frustration - this is a learning tool, not a punishment.

---

## 3. Hint System Animations

### Hint Square Pulse
**Duration:** 1000ms (infinite loop)
**Easing:** `ease-in-out`
**Description:** Solution square pulses with yellow glow

```css
@keyframes square-hint-pulse {
  0%, 100% {
    background-color: rgba(234, 179, 8, 0.2);
    box-shadow: 0 0 0 rgba(234, 179, 8, 0);
    transform: scale(1);
  }
  50% {
    background-color: rgba(234, 179, 8, 0.5);
    box-shadow: 0 0 20px rgba(234, 179, 8, 0.6);
    transform: scale(1.03);
  }
}

.square-hint-pulse {
  animation: square-hint-pulse 1s ease-in-out infinite;
}

/* Hint arrow pointing to destination */
@keyframes hint-arrow-bounce {
  0%, 100% {
    transform: translateY(0);
    opacity: 0.8;
  }
  50% {
    transform: translateY(-8px);
    opacity: 1;
  }
}

.hint-arrow {
  position: absolute;
  top: -30px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 24px;
  color: #eab308;
  animation: hint-arrow-bounce 0.8s ease-in-out infinite;
}
```

---

## 4. Board Celebration Animations

### Success Celebration (Correct Move)
**Duration:** 1200ms
**Easing:** `cubic-bezier(0.68, -0.55, 0.265, 1.55)` (bounce)
**Description:** Board bounces with confetti effect

```css
@keyframes board-success-celebration {
  0% {
    transform: scale(1) rotate(0deg);
  }
  25% {
    transform: scale(1.03) rotate(-1deg);
  }
  50% {
    transform: scale(0.98) rotate(1deg);
  }
  75% {
    transform: scale(1.02) rotate(-0.5deg);
  }
  100% {
    transform: scale(1) rotate(0deg);
  }
}

.board-success-celebration {
  animation: board-success-celebration 1.2s cubic-bezier(0.68, -0.55, 0.265, 1.55);
}

/* Confetti particles */
@keyframes confetti-fall {
  0% {
    transform: translateY(-50px) rotate(0deg);
    opacity: 1;
  }
  100% {
    transform: translateY(200px) rotate(360deg);
    opacity: 0;
  }
}

.confetti-particle {
  position: absolute;
  width: 8px;
  height: 8px;
  background: var(--confetti-color);
  animation: confetti-fall 1.5s ease-in forwards;
  animation-delay: var(--confetti-delay);
}
```

---

### Error Feedback (Wrong Move)
**Duration:** 500ms
**Easing:** `ease-in-out`
**Description:** Gentle board shake (horizontal)

```css
@keyframes board-error-shake {
  0%, 100% {
    transform: translateX(0);
  }
  25% {
    transform: translateX(-8px);
  }
  75% {
    transform: translateX(8px);
  }
}

.board-error-shake {
  animation: board-error-shake 0.5s ease-in-out;
}
```

---

## 5. UI Element Animations

### Feedback Banner Slide In
**Duration:** 300ms
**Easing:** `ease-out`
**Description:** Success/error banner slides down from top

```css
@keyframes banner-slide-in {
  0% {
    transform: translateY(-100%);
    opacity: 0;
  }
  100% {
    transform: translateY(0);
    opacity: 1;
  }
}

.feedback-banner {
  animation: banner-slide-in 0.3s ease-out forwards;
}
```

---

### Button Press Effect
**Duration:** 150ms
**Easing:** `ease-in-out`
**Description:** Button scales down on press

```css
@keyframes button-press {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(0.95);
  }
}

.button-press {
  animation: button-press 0.15s ease-in-out;
}
```

---

## 6. Loading States

### Board Loading Shimmer
**Duration:** 1500ms (infinite loop)
**Easing:** `linear`
**Description:** Shimmer effect while board loads

```css
@keyframes board-loading-shimmer {
  0% {
    background-position: -1000px 0;
  }
  100% {
    background-position: 1000px 0;
  }
}

.board-loading {
  background: linear-gradient(
    90deg,
    #f0d9b5 0%,
    #e8d5ad 20%,
    #f0d9b5 40%,
    #f0d9b5 100%
  );
  background-size: 1000px 100%;
  animation: board-loading-shimmer 1.5s linear infinite;
}
```

---

## 7. Accessibility - Reduced Motion

All animations respect `prefers-reduced-motion` media query:

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }

  /* Still show feedback, just without animation */
  .piece-correct-glow {
    filter: drop-shadow(0 0 10px rgba(34, 197, 94, 0.6));
  }

  .square-hint-pulse {
    background-color: rgba(234, 179, 8, 0.4);
  }
}
```

---

## 8. Animation Timing Constants

**JavaScript constants for animation control:**

```typescript
export const ANIMATION_TIMING = {
  // Piece animations
  PIECE_MOVE: 400,
  PIECE_CAPTURE: 300,
  PIECE_CORRECT_GLOW: 600,
  PIECE_INCORRECT_SHAKE: 400,

  // Square animations
  SQUARE_HINT_PULSE: 1000,
  SQUARE_FLASH: 600,

  // Board animations
  BOARD_CELEBRATION: 1200,
  BOARD_ERROR_SHAKE: 500,

  // UI animations
  BANNER_SLIDE_IN: 300,
  BUTTON_PRESS: 150,

  // Delays
  FEEDBACK_DELAY: 200, // Delay before showing feedback
  HINT_APPEAR_DELAY: 100, // Delay before hint appears
  CELEBRATION_START_DELAY: 300, // Delay before celebration starts

  // Durations for sequencing
  TOTAL_MOVE_SEQUENCE: 1000, // Move + feedback
  TOTAL_CELEBRATION_SEQUENCE: 2000, // Celebration + banner
} as const;
```

---

## 9. Animation Sequences

### Complete Move Sequence (Correct Move)

```
Timeline:
0ms     - User releases piece
0-400ms - Piece moves with arc trajectory
400ms   - Move completes
600ms   - Correct glow starts on piece
600ms   - Square flash starts
1000ms  - Board celebration begins
1000ms  - Success banner slides in
1200ms  - Confetti particles spawn
2200ms  - All animations complete
```

**JavaScript orchestration:**

```typescript
async function playCorrectMoveSequence(
  pieceElement: HTMLElement,
  squareElement: HTMLElement,
  boardElement: HTMLElement
) {
  // 1. Move piece (400ms)
  await animatePieceMove(pieceElement);

  // 2. Success feedback (600ms) - starts immediately after move
  await Promise.all([
    animateElement(pieceElement, 'piece-correct-glow', 600),
    animateElement(squareElement, 'square-correct-flash', 600),
  ]);

  // 3. Board celebration (1200ms) - starts 300ms after feedback
  setTimeout(() => {
    animateBoardCelebration(boardElement);
    showSuccessBanner();
    spawnConfetti(boardElement);
  }, 300);
}
```

---

### Complete Move Sequence (Incorrect Move)

```
Timeline:
0ms     - User releases piece
0-200ms - Piece moves back to original position (faster)
200ms   - Shake animation starts
200ms   - Square flash starts (red)
600ms   - Error banner slides in
1100ms  - All animations complete
```

**JavaScript orchestration:**

```typescript
async function playIncorrectMoveSequence(
  pieceElement: HTMLElement,
  squareElement: HTMLElement
) {
  // 1. Move piece back (200ms - faster than normal move)
  await animatePieceMove(pieceElement, { duration: 200, return: true });

  // 2. Error feedback (400ms)
  await Promise.all([
    animateElement(pieceElement, 'piece-incorrect-shake', 400),
    animateElement(squareElement, 'square-incorrect-flash', 400),
  ]);

  // 3. Show error banner (after 200ms delay)
  setTimeout(() => {
    showErrorBanner();
  }, 200);
}
```

---

## 10. Performance Optimization

### GPU Acceleration
Only animate properties that trigger GPU acceleration:
- `transform` ✅
- `opacity` ✅
- `filter` ⚠️ (use sparingly)

Avoid animating:
- `width`, `height` ❌
- `top`, `left` ❌
- `margin`, `padding` ❌

### Will-Change Hints

```css
.piece {
  will-change: transform, opacity;
}

.square {
  will-change: background-color, box-shadow;
}

/* Remove will-change after animation completes */
.piece.animation-complete {
  will-change: auto;
}
```

### Frame Rate Target
- **Desktop:** 60fps
- **Mobile:** 60fps (30fps acceptable on low-end devices)
- **Animation budget per frame:** 16.67ms (60fps) or 33.33ms (30fps)

---

## 11. Mobile Optimizations

### Touch Feedback
```css
/* Immediate visual feedback on touch */
.piece:active {
  transform: scale(0.95);
  transition: transform 0.1s ease-out;
}

/* Reset after touch */
.piece:not(:active) {
  transform: scale(1);
  transition: transform 0.2s ease-out;
}
```

### Reduced Particle Effects on Mobile
```typescript
const PARTICLE_COUNT = {
  desktop: 30,
  tablet: 15,
  mobile: 8,
};

function getParticleCount(): number {
  if (window.innerWidth >= 1024) return PARTICLE_COUNT.desktop;
  if (window.innerWidth >= 768) return PARTICLE_COUNT.tablet;
  return PARTICLE_COUNT.mobile;
}
```

---

## 12. Animation Testing Checklist

- [ ] All animations run at 60fps on desktop
- [ ] All animations run at 30fps+ on mobile
- [ ] Reduced motion preference is respected
- [ ] Touch feedback is immediate (<100ms)
- [ ] Animations don't block user input
- [ ] Success celebration feels rewarding
- [ ] Error feedback feels gentle, not punishing
- [ ] Hint animation is clear and obvious
- [ ] Animations work on all supported browsers
- [ ] No layout shifts during animations

---

## Next Steps

1. ✅ Animation specifications defined
2. ⏳ Plan lesson data schema updates for 1-move puzzles
3. ⏳ Implement AnimatedChessBoard component with animations
4. ⏳ Test animations on devices
5. ⏳ Optimize performance
6. ⏳ Add sound effects (future enhancement)

---

## References

- [Web Animations API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Animations_API)
- [CSS Animation Performance](https://web.dev/animations-guide/)
- [Reduced Motion Media Query](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion)
- [Duolingo UX Patterns](https://blog.duolingo.com/chess-course/)
- [COMPONENT_ARCHITECTURE.md](COMPONENT_ARCHITECTURE.md)
- [ANIMATED_BOARD_PRD.md](ANIMATED_BOARD_PRD.md)
