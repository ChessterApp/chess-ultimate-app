/**
 * Animation controller for chess board
 */

/**
 * CSS class names for board animations
 */
export const ANIMATION_CLASSES = {
  // Piece animations
  PIECE_MOVE: 'piece-move-arc',
  PIECE_CAPTURE: 'piece-capture-poof',
  PIECE_CORRECT: 'piece-correct-glow',
  PIECE_INCORRECT: 'piece-incorrect-shake',

  // Square animations
  SQUARE_HINT: 'square-hint-pulse',
  SQUARE_CORRECT: 'square-correct-flash',
  SQUARE_INCORRECT: 'square-incorrect-flash',

  // Board feedback
  BOARD_SUCCESS: 'board-success-celebration',
  BOARD_ERROR: 'board-error-shake',

  // UI elements
  BANNER_SLIDE_IN: 'banner-slide-in',
  BUTTON_PRESS: 'button-press',
} as const;

/**
 * Animation durations in milliseconds
 * Note: PIECE_MOVE duration is now controlled via CSS variable --cg-animation-duration
 * See animationConfig.ts for piece movement animation configuration
 */
export const ANIMATION_DURATIONS = {
  PIECE_CAPTURE: 300,
  PIECE_CORRECT_GLOW: 600,
  PIECE_INCORRECT_SHAKE: 400,

  SQUARE_HINT_PULSE: 1000,
  SQUARE_FLASH: 600,

  BOARD_CELEBRATION: 1200,
  BOARD_ERROR_SHAKE: 500,

  BANNER_SLIDE_IN: 300,
  BUTTON_PRESS: 150,

  // Delays
  FEEDBACK_DELAY: 200,
  HINT_APPEAR_DELAY: 100,
  CELEBRATION_START_DELAY: 300,

  // Total sequences
  TOTAL_MOVE_SEQUENCE: 1000,
  TOTAL_CELEBRATION_SEQUENCE: 2000,
} as const;

/**
 * Apply animation to an element
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
 * Show success celebration animation
 */
export async function showSuccessCelebration(
  boardElement: HTMLElement
): Promise<void> {
  return animateElement(
    boardElement,
    ANIMATION_CLASSES.BOARD_SUCCESS,
    ANIMATION_DURATIONS.BOARD_CELEBRATION
  );
}

/**
 * Show error feedback animation
 */
export async function showErrorFeedback(
  boardElement: HTMLElement
): Promise<void> {
  return animateElement(
    boardElement,
    ANIMATION_CLASSES.BOARD_ERROR,
    ANIMATION_DURATIONS.BOARD_ERROR_SHAKE
  );
}

/**
 * Pulse hint on a square element
 */
export function pulseHintSquare(squareElement: HTMLElement): void {
  squareElement.classList.add(ANIMATION_CLASSES.SQUARE_HINT);
}

/**
 * Remove hint pulse from square
 */
export function removeHintPulse(squareElement: HTMLElement): void {
  squareElement.classList.remove(ANIMATION_CLASSES.SQUARE_HINT);
}

/**
 * Flash square with correct feedback
 */
export async function flashCorrectSquare(
  squareElement: HTMLElement
): Promise<void> {
  return animateElement(
    squareElement,
    ANIMATION_CLASSES.SQUARE_CORRECT,
    ANIMATION_DURATIONS.SQUARE_FLASH
  );
}

/**
 * Flash square with incorrect feedback
 */
export async function flashIncorrectSquare(
  squareElement: HTMLElement
): Promise<void> {
  return animateElement(
    squareElement,
    ANIMATION_CLASSES.SQUARE_INCORRECT,
    ANIMATION_DURATIONS.SQUARE_FLASH
  );
}

/**
 * Create confetti particles for celebration
 */
export function spawnConfetti(containerElement: HTMLElement, count: number = 30): void {
  const colors = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6'];

  for (let i = 0; i < count; i++) {
    const confetti = document.createElement('div');
    confetti.className = 'confetti-particle';
    confetti.style.setProperty('--confetti-color', colors[i % colors.length]);
    confetti.style.setProperty('--confetti-delay', `${i * 50}ms`);
    confetti.style.left = `${Math.random() * 100}%`;

    containerElement.appendChild(confetti);

    // Remove after animation completes
    setTimeout(() => {
      confetti.remove();
    }, 1500 + i * 50);
  }
}

/**
 * Check if user prefers reduced motion
 */
export function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Get animation duration (respects reduced motion preference)
 */
export function getAnimationDuration(baseDuration: number): number {
  return prefersReducedMotion() ? 1 : baseDuration;
}
