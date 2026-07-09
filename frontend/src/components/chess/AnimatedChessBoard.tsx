/**
 * AnimatedChessBoard Component
 *
 * Interactive chess board with animations for beginner-friendly learning.
 * Integrates Chessground for board rendering, chess.js for move validation,
 * and custom animations for feedback and celebration.
 */

'use client';

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Chessground } from 'chessground';
import type { Api } from 'chessground/api';
import type { Key } from 'chessground/types';
import { MoveValidator } from '@/lib/chess/moveValidator';
import { getChessgroundConfig } from '@/lib/chess/chessgroundConfig';
import { evaluateLineMove, colorToMove } from '@/lib/chess/solutionLine';
import {
  showSuccessCelebration,
  showErrorFeedback,
  pulseHintSquare,
  removeHintPulse,
  ANIMATION_DURATIONS,
} from '@/lib/chess/animations';
import FeedbackDisplay, { FeedbackType } from './FeedbackDisplay';
import BoardControls from './BoardControls';
import TargetStar from './TargetStar';
import { useHaptic } from '@/hooks/useHaptic';
import { useSoundEffects } from '@/hooks/useSoundEffects';
import ArrowOverlay from './ArrowOverlay';
import LottieCelebration from './LottieCelebration';
import { useLocalStorage } from 'usehooks-ts';
import { DEFAULT_BOARD_ANIMATION_DURATION } from '@/libs/setting/helper';

// Import chessground CSS
import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import 'chessground/assets/chessground.cburnett.css';

interface AnimatedChessBoardProps {
  /** Initial position in FEN notation */
  fen: string;
  /** Solution move in UCI notation (e.g., "e2e4", "e7e8q") - for single-star mode */
  solutionMove?: string;
  /**
   * Full solution line for multi-move puzzles (mate-in-2/3, etc.) as an ordered
   * array of UCI moves: user move, opponent reply, user move, ...
   * When present (length > 0) the board runs in multi-move mode: it validates
   * each user move against the line, auto-plays the opponent's reply, and only
   * fires success once the whole line is completed. `solutionMove` continues to
   * work for old single-move callers when this is absent.
   */
  solutionLine?: string[];
  /** Target squares for multi-star mode (e.g., ["h3", "b5", "h6"]) */
  targetSquares?: string[];
  /** Callback when user makes correct move */
  onCorrectMove: () => void;
  /** Callback when user makes incorrect move */
  onIncorrectMove?: (attemptedMove: string) => void;
  /** Board orientation */
  orientation?: 'white' | 'black';
  /** Enable/disable move hints */
  showHints?: boolean;
  /** Enable/disable animations */
  enableAnimations?: boolean;
  /** Optional CSS class name */
  className?: string;
  /** Starting square for arrow path (e.g., "e3") */
  arrowFromSquare?: string;
  /** Intermediate squares for multi-move arrow path (e.g., ["f4"]) */
  arrowPath?: string[];
  /** Whether to show arrows */
  showArrowsOverlay?: boolean;
  /** Whether to show target star on solution square (default: true) */
  showStar?: boolean;
  /**
   * When true, only the exact solution move is accepted (for one_move_puzzle).
   * When false, intermediate moves toward the target are allowed.
   * Default: false (allowing intermediate moves for multi-step exercises)
   */
  strictValidation?: boolean;
}

interface BoardState {
  /** Current position FEN */
  currentFen: string;
  /** Feedback state */
  feedback: FeedbackType;
  /** Whether hint is currently shown */
  hintShown: boolean;
  /** Whether move is being validated */
  isValidating: boolean;
  /** Whether puzzle is solved */
  isSolved: boolean;
  /** Whether to show arrow path overlay */
  showArrows: boolean;
  /** Current step in the path (0 = start, increments as user progresses) */
  pathStep: number;
  /** Set of captured star squares (for multi-star mode) */
  capturedStars: Set<string>;
  /** Whether to show Lottie celebration animation */
  showCelebration: boolean;
}

/**
 * AnimatedChessBoard - Interactive chess board with animations
 */
/** Delay before auto-playing the opponent's reply in a multi-move line (ms). */
const OPPONENT_REPLY_DELAY = 500;

export default function AnimatedChessBoard({
  fen,
  solutionMove,
  solutionLine,
  targetSquares,
  onCorrectMove,
  onIncorrectMove,
  orientation: orientationProp,
  showHints = true,
  enableAnimations = true,
  className = '',
  arrowFromSquare,
  arrowPath = [],
  showArrowsOverlay = true,
  showStar = true,
  strictValidation = false,
}: AnimatedChessBoardProps) {
  // Auto-derive orientation from FEN active color if not explicitly provided
  const orientation = orientationProp ?? (fen.split(' ')[1] === 'b' ? 'black' : 'white');
  const haptic = useHaptic();
  const { play: playSound } = useSoundEffects();
  const [animationDuration] = useLocalStorage<number>('board_ui_animation_duration', DEFAULT_BOARD_ANIMATION_DURATION);
  const boardRef = useRef<HTMLDivElement>(null);
  const groundRef = useRef<Api | null>(null);
  const validatorRef = useRef<MoveValidator>(new MoveValidator(fen));
  const hintSquareRef = useRef<HTMLElement | null>(null);
  // Multi-move (solution line) playback state, held in refs to avoid stale closures.
  const isLineMode = !!(solutionLine && solutionLine.length > 0);
  const lineIndexRef = useRef<number>(0);
  const lineFenRef = useRef<string>(fen);
  // Ref to hold the latest handleMove function - used to avoid stale closures in board init
  const handleMoveRef = useRef<(orig: Key, dest: Key) => void>(() => {});

  const [state, setState] = useState<BoardState>({
    currentFen: fen,
    feedback: 'idle',
    hintShown: false,
    isValidating: false,
    isSolved: false,
    showArrows: true,
    pathStep: 0,
    capturedStars: new Set<string>(),
    showCelebration: false,
  });

  /**
   * Initialize chessground instance
   * Note: Chessground requires the container to have dimensions before initialization.
   * We poll until the container has real dimensions (width/height > 0).
   */
  useEffect(() => {
    if (!boardRef.current) return;

    // Destroy existing instance before creating new one
    if (groundRef.current) {
      groundRef.current.destroy();
      groundRef.current = null;
    }

    let timeoutId: NodeJS.Timeout;
    let animationFrameId: number;

    // Poll until container has real dimensions
    const initializeBoard = () => {
      if (!boardRef.current) return;

      const rect = boardRef.current.getBoundingClientRect();

      // Check if container has real dimensions (width and height > 0)
      if (rect.width > 0 && rect.height > 0) {
        const ground = Chessground(boardRef.current, {
          ...getChessgroundConfig({
            fen,
            onMove: (orig, dest) => {
              // This will be immediately overwritten, but needed for initial config
            },
            orientation,
            movable: true,
            premovable: false,
            animationDuration,
          }),
        });

        groundRef.current = ground;

        // CRITICAL: Attach a wrapper that delegates to handleMoveRef.current
        // This ensures the handler always uses the latest handleMove function,
        // even if the board is created before handleMove is fully initialized
        ground.set({
          movable: {
            events: {
              after: (orig: Key, dest: Key) => {
                handleMoveRef.current(orig, dest);
              },
            },
          },
        });
      } else {
        // Container not ready yet, retry on next frame
        animationFrameId = requestAnimationFrame(initializeBoard);
      }
    };

    // Start initialization after a short delay to allow CSS to compute
    timeoutId = setTimeout(() => {
      animationFrameId = requestAnimationFrame(initializeBoard);
    }, 10);

    return () => {
      clearTimeout(timeoutId);
      cancelAnimationFrame(animationFrameId);
      if (groundRef.current) {
        groundRef.current.destroy();
        groundRef.current = null;
      }
    };
  }, [fen, orientation]);

  /**
   * Reset state when FEN changes (e.g., switching between puzzles)
   * This ensures each puzzle starts fresh with hints available and no solved state
   */
  useEffect(() => {
    // Reset validator with new FEN
    validatorRef.current.reset(fen);

    // Reset multi-move line playback to the start of the new puzzle
    lineIndexRef.current = 0;
    lineFenRef.current = fen;

    // Remove any existing hint overlay
    if (hintSquareRef.current) {
      hintSquareRef.current.remove();
      hintSquareRef.current = null;
    }

    // Reset board state for new puzzle
    setState({
      currentFen: fen,
      feedback: 'idle',
      hintShown: false,
      isValidating: false,
      isSolved: false,
      showArrows: true,
      pathStep: 0,
      capturedStars: new Set<string>(),
      showCelebration: false,
    });

    // Update chessground with new position
    if (groundRef.current) {
      groundRef.current.set({
        fen,
        turnColor: orientation,
        lastMove: undefined,
        check: undefined,
        movable: {
          free: true,
          color: orientation,
        },
      });
    }
  }, [fen, orientation]);

  /**
   * Calculate chess distance between two squares (Chebyshev distance - max of file/rank difference)
   * This is the minimum number of King moves needed to get from one square to another
   */
  const getChessDistance = useCallback((from: string, to: string): number => {
    const fromFile = from.charCodeAt(0) - 'a'.charCodeAt(0);
    const fromRank = parseInt(from[1]) - 1;
    const toFile = to.charCodeAt(0) - 'a'.charCodeAt(0);
    const toRank = parseInt(to[1]) - 1;

    return Math.max(Math.abs(toFile - fromFile), Math.abs(toRank - fromRank));
  }, []);

  /**
   * Check if a move brings the piece closer to the target
   * Returns true if the new position is closer to target than the original position
   */
  const isMovingTowardTarget = useCallback((orig: string, dest: string, target: string): boolean => {
    const originalDistance = getChessDistance(orig, target);
    const newDistance = getChessDistance(dest, target);
    return newDistance < originalDistance;
  }, [getChessDistance]);

  /**
   * Handle user move attempt
   */
  const handleMove = useCallback(
    (orig: Key, dest: Key) => {
      if (state.isSolved || state.isValidating) {
        return;
      }

      // Hide arrows after first move attempt
      setState((prev) => ({ ...prev, isValidating: true, showArrows: false }));

      const validator = validatorRef.current;
      const moveUci = `${orig}${dest}`;

      // Check if move is legal
      if (!validator.isLegalMove(orig, dest)) {
        // Illegal move - revert
        groundRef.current?.set({ fen: state.currentFen });
        setState((prev) => ({ ...prev, isValidating: false }));
        return;
      }

      // Multi-move solution line mode (mate-in-2/3, tactical lines): validate
      // against the stored line and auto-play the opponent's replies.
      if (isLineMode) {
        handleLineMove(orig, dest);
        return;
      }

      // Multi-star mode: check if move lands on any uncaptured target
      if (targetSquares && targetSquares.length > 0) {
        if (targetSquares.includes(dest) && !state.capturedStars.has(dest)) {
          // Landed on a new star!
          handleStarCapture(orig, dest);
          return;
        } else {
          // Move doesn't capture a star - treat as intermediate move
          handleIntermediateMove(orig, dest);
          return;
        }
      }

      // Single-star mode (original behavior)
      if (solutionMove) {
        const solutionOrigin = solutionMove.slice(0, 2);
        const targetSquare = solutionMove.slice(2, 4);

        // Strict validation mode (for one_move_puzzle like mate-in-1):
        // Only the exact solution move is accepted
        if (strictValidation) {
          if (orig === solutionOrigin && dest === targetSquare) {
            handleCorrectMove(orig, dest);
          } else {
            // Any move that is not the exact solution is incorrect
            handleIncorrectMove(moveUci, orig, dest);
          }
          return;
        }

        // Non-strict mode: allow intermediate moves toward target
        // Check if this move reaches the target (puzzle solved!)
        if (dest === targetSquare) {
          handleCorrectMove(orig, dest);
          return;
        }

        // Check if this move brings the piece closer to the target (valid intermediate move)
        // Any legal move that reduces distance to target is acceptable
        if (isMovingTowardTarget(orig, dest, targetSquare)) {
          handleIntermediateMove(orig, dest);
        } else {
          // Incorrect move - moving away from or not toward the target
          handleIncorrectMove(moveUci, orig, dest);
        }
      }
    },
    [state.isSolved, state.isValidating, state.currentFen, state.capturedStars, solutionMove, solutionLine, isLineMode, targetSquares, isMovingTowardTarget, strictValidation]
  );

  // Keep handleMoveRef in sync with handleMove - update synchronously during render
  // This ensures the board init effect always has access to the latest handler
  handleMoveRef.current = handleMove;

  /**
   * Update move handler when handleMove changes
   */
  useEffect(() => {
    if (groundRef.current) {
      groundRef.current.set({
        movable: {
          events: {
            after: handleMove,
          },
        },
      });
    }
  }, [handleMove]);

  /**
   * Fire the success celebration and notify the parent once a solution line is
   * fully completed (either on the user's final move or after the auto-played
   * opponent reply that ends the line).
   */
  const fireLineSuccess = async (finalFen: string, lastMove: [Key, Key]) => {
    setState((prev) => ({
      ...prev,
      currentFen: finalFen,
      feedback: 'correct',
      isSolved: true,
      hintShown: false,
      showCelebration: enableAnimations,
    }));
    playSound('success');

    if (hintSquareRef.current) {
      removeHintPulse(hintSquareRef.current);
      hintSquareRef.current = null;
    }

    groundRef.current?.set({
      fen: finalFen,
      turnColor: colorToMove(finalFen),
      lastMove,
      movable: { free: false },
    });

    if (enableAnimations && boardRef.current) {
      await showSuccessCelebration(boardRef.current);
    }

    haptic.onPuzzleCorrect();
    setTimeout(() => {
      onCorrectMove();
    }, ANIMATION_DURATIONS.CELEBRATION_START_DELAY);

    setState((prev) => ({ ...prev, isValidating: false }));
  };

  /**
   * Handle a user move in multi-move solution line mode.
   * Validates against the current expected line move; on success either fires
   * the celebration (line complete) or auto-plays the opponent's reply and waits
   * for the next user move.
   */
  const handleLineMove = async (orig: Key, dest: Key) => {
    const validator = validatorRef.current;
    const line = solutionLine || [];
    const result = evaluateLineMove(line, lineIndexRef.current, orig, dest);

    if (result.kind === 'incorrect') {
      await handleLineIncorrect(`${orig}${dest}`);
      return;
    }

    // Apply the user's (canonical) move, including any promotion from the line
    const uOrig = result.userMove.slice(0, 2) as Key;
    const uDest = result.userMove.slice(2, 4) as Key;
    const newFen = validator.makeMove(uOrig, uDest, result.userPromotion);
    if (!newFen) {
      setState((prev) => ({ ...prev, isValidating: false }));
      return;
    }

    if (result.kind === 'solved') {
      // User's move was the final move of the line — celebrate
      lineIndexRef.current = result.nextIndex;
      await fireLineSuccess(newFen, [uOrig, uDest]);
      return;
    }

    // Progress — show the user's move, freeze the board, then auto-play the reply
    groundRef.current?.set({
      fen: newFen,
      turnColor: colorToMove(newFen),
      lastMove: [uOrig, uDest],
      movable: { free: false },
    });
    setState((prev) => ({ ...prev, currentFen: newFen }));

    setTimeout(() => {
      const oOrig = result.opponentMove.slice(0, 2) as Key;
      const oDest = result.opponentMove.slice(2, 4) as Key;
      const replyFen = validator.makeMove(oOrig, oDest, result.opponentPromotion);
      if (!replyFen) {
        setState((prev) => ({ ...prev, isValidating: false }));
        return;
      }

      // Advance to the next user move and remember this position for wrong-move resets
      lineIndexRef.current = result.nextIndex;
      lineFenRef.current = replyFen;

      // Some lines (e.g. win-material tactics) end on the opponent's reply.
      if (result.completesAfterReply) {
        fireLineSuccess(replyFen, [oOrig, oDest]);
        return;
      }

      const color = colorToMove(replyFen);
      groundRef.current?.set({
        fen: replyFen,
        turnColor: color,
        lastMove: [oOrig, oDest],
        movable: {
          free: true,
          color,
          events: { after: handleMove },
        },
      });

      setState((prev) => ({ ...prev, currentFen: replyFen, isValidating: false }));
    }, OPPONENT_REPLY_DELAY);
  };

  /**
   * Handle an incorrect move in multi-move mode: show feedback and reset the
   * board to the position before the wrong move, preserving the line index.
   */
  const handleLineIncorrect = async (moveUci: string) => {
    setState((prev) => ({ ...prev, feedback: 'incorrect' }));

    if (enableAnimations && boardRef.current) {
      await showErrorFeedback(boardRef.current);
    }

    const lineFen = lineFenRef.current;
    validatorRef.current.reset(lineFen);

    const color = colorToMove(lineFen);
    groundRef.current?.set({
      fen: lineFen,
      turnColor: color,
      lastMove: undefined,
      check: undefined,
      movable: {
        free: true,
        color,
        events: { after: handleMove },
      },
    });

    haptic.onPuzzleWrong();
    if (onIncorrectMove) {
      onIncorrectMove(moveUci);
    }

    setState((prev) => ({ ...prev, currentFen: lineFen, isValidating: false }));

    setTimeout(() => {
      setState((prev) => ({ ...prev, feedback: 'idle' }));
    }, 2000);
  };

  /**
   * Handle correct move
   */
  const handleCorrectMove = async (orig: Key, dest: Key) => {
    const validator = validatorRef.current;
    const newFen = validator.makeMove(orig, dest);

    if (!newFen) {
      setState((prev) => ({ ...prev, isValidating: false }));
      return;
    }

    // Update board state and show Lottie celebration
    setState((prev) => ({
      ...prev,
      currentFen: newFen,
      feedback: 'correct',
      isSolved: true,
      hintShown: false,
      showCelebration: enableAnimations,
    }));
    playSound('success');

    // Remove hint if shown
    if (hintSquareRef.current) {
      removeHintPulse(hintSquareRef.current);
      hintSquareRef.current = null;
    }

    // Play success celebration animation (board glow)
    if (enableAnimations && boardRef.current) {
      await showSuccessCelebration(boardRef.current);
    }

    // Call success callback
    haptic.onPuzzleCorrect();
    setTimeout(() => {
      onCorrectMove();
    }, ANIMATION_DURATIONS.CELEBRATION_START_DELAY);

    setState((prev) => ({ ...prev, isValidating: false }));
  };

  /**
   * Handle star capture in multi-star mode
   */
  const handleStarCapture = async (orig: Key, dest: Key) => {
    const validator = validatorRef.current;
    const newFen = validator.makeMove(orig, dest);

    if (!newFen) {
      setState((prev) => ({ ...prev, isValidating: false }));
      return;
    }

    // Add captured star to set
    const newCapturedStars = new Set(state.capturedStars);
    newCapturedStars.add(dest);

    // Check if all stars are captured
    const allCaptured = targetSquares && newCapturedStars.size === targetSquares.length;

    if (allCaptured) {
      // All stars captured - puzzle complete!
      setState((prev) => ({
        ...prev,
        currentFen: newFen,
        feedback: 'correct',
        isSolved: true,
        capturedStars: newCapturedStars,
        hintShown: false,
        showCelebration: enableAnimations,
      }));
      playSound('success');

      // Remove hint if shown
      if (hintSquareRef.current) {
        removeHintPulse(hintSquareRef.current);
        hintSquareRef.current = null;
      }

      // Play success celebration animation (board glow)
      if (enableAnimations && boardRef.current) {
        await showSuccessCelebration(boardRef.current);
      }

      // Call success callback
      setTimeout(() => {
        onCorrectMove();
      }, ANIMATION_DURATIONS.CELEBRATION_START_DELAY);

      setState((prev) => ({ ...prev, isValidating: false }));
    } else {
      // Star captured but more to go - continue playing
      // Modify FEN to keep the same player's turn
      const fenParts = newFen.split(' ');
      fenParts[1] = orientation === 'white' ? 'w' : 'b';
      const modifiedFen = fenParts.join(' ');

      // Reset validator with modified FEN
      validator.reset(modifiedFen);

      // Update board with new position (event handlers will be updated automatically by useEffect)
      groundRef.current?.set({
        fen: modifiedFen,
        turnColor: orientation,
        lastMove: [orig, dest],
        movable: {
          free: true,
          color: orientation,
        },
      });

      // Update state - star captured, keep playing
      // The useEffect hook will automatically update event handlers with fresh closure
      setState((prev) => ({
        ...prev,
        currentFen: modifiedFen,
        capturedStars: newCapturedStars,
        isValidating: false,
      }));
    }
  };

  /**
   * Handle intermediate move (correct move along the path, but not the final target)
   */
  const handleIntermediateMove = (orig: Key, dest: Key) => {
    const validator = validatorRef.current;
    const newFen = validator.makeMove(orig, dest);

    if (!newFen) {
      setState((prev) => ({ ...prev, isValidating: false }));
      return;
    }

    // Modify FEN to keep the same player's turn (for beginner exercises where
    // the same player makes multiple consecutive moves)
    // FEN format: "pieces turn castling en_passant halfmove fullmove"
    const fenParts = newFen.split(' ');
    fenParts[1] = orientation === 'white' ? 'w' : 'b'; // Keep the same player's turn
    const modifiedFen = fenParts.join(' ');

    // Reset validator with modified FEN so next isLegalMove check works
    validator.reset(modifiedFen);

    // Update board with new position and advance path step
    groundRef.current?.set({
      fen: modifiedFen,
      turnColor: orientation,
      lastMove: [orig, dest],
      movable: {
        free: true,
        color: orientation,
        events: {
          after: handleMove,
        },
      },
    });

    // Update state - advance to next step, keep playing
    setState((prev) => ({
      ...prev,
      currentFen: modifiedFen,
      pathStep: prev.pathStep + 1,
      isValidating: false,
    }));
  };

  /**
   * Handle incorrect move
   */
  const handleIncorrectMove = async (moveUci: string, orig: Key, dest: Key) => {
    // Update feedback immediately
    setState((prev) => ({
      ...prev,
      feedback: 'incorrect',
    }));

    // Play error animation if enabled
    if (enableAnimations && boardRef.current) {
      await showErrorFeedback(boardRef.current);
    }

    // Reset the validator to the original position (important: undo any internal state changes)
    validatorRef.current.reset(fen);

    // Revert move - fully reset the board to initial position with proper movable config
    groundRef.current?.set({
      fen,
      turnColor: orientation,
      lastMove: undefined,
      check: undefined,
      movable: {
        free: true,
        color: orientation,
        events: {
          after: handleMove,
        },
      },
    });

    // Call incorrect callback
    haptic.onPuzzleWrong();
    if (onIncorrectMove) {
      onIncorrectMove(moveUci);
    }

    // Reset validation state so user can try again
    setState((prev) => ({
      ...prev,
      currentFen: fen,
      isValidating: false,
      pathStep: 0,
    }));

    // Clear feedback after 2 seconds so user can read the message
    setTimeout(() => {
      setState((prev) => ({
        ...prev,
        feedback: 'idle',
      }));
    }, 2000);
  };

  /**
   * Show hint for solution move
   */
  const handleShowHint = useCallback(() => {
    // In multi-move mode, hint the current expected line move; otherwise the single move.
    const hintMove = isLineMode
      ? (solutionLine ? solutionLine[lineIndexRef.current] : undefined)
      : solutionMove;

    if (state.isSolved || state.hintShown || !showHints || !boardRef.current || !hintMove) {
      return;
    }

    // Extract destination square from the hint move (last 2 characters)
    const destSquare = hintMove.slice(2, 4);

    // Calculate position: squares are indexed 0-7 for files (a-h) and ranks (1-8)
    const file = destSquare.charCodeAt(0) - 'a'.charCodeAt(0); // 0-7
    const rank = 8 - parseInt(destSquare[1]); // 0-7 (top to bottom)

    // Create a hint overlay div
    const hintDiv = document.createElement('div');
    hintDiv.className = 'hint-overlay';
    hintDiv.style.cssText = `
      position: absolute;
      width: 12.5%;
      height: 12.5%;
      left: ${file * 12.5}%;
      top: ${rank * 12.5}%;
      background-color: rgba(255, 255, 0, 0.4);
      border: 3px solid #f59e0b;
      border-radius: 50%;
      pointer-events: none;
      z-index: 10;
      animation: pulse 1s ease-in-out infinite;
    `;

    const boardContainer = boardRef.current.querySelector('.cg-wrap') || boardRef.current;
    boardContainer.appendChild(hintDiv);
    hintSquareRef.current = hintDiv;

    setState((prev) => ({
      ...prev,
      feedback: 'hint',
      hintShown: true,
    }));

    // Clear hint feedback and overlay after delay
    setTimeout(() => {
      if (hintSquareRef.current) {
        hintSquareRef.current.remove();
        hintSquareRef.current = null;
      }
      setState((prev) => ({
        ...prev,
        feedback: 'idle',
      }));
    }, ANIMATION_DURATIONS.HINT_APPEAR_DELAY + 3000);
  }, [state.isSolved, state.hintShown, showHints, solutionMove, solutionLine, isLineMode]);

  /**
   * Reset board to initial position
   */
  const handleReset = useCallback(() => {
    // Reset validator
    validatorRef.current.reset(fen);

    // Reset multi-move line playback back to the start
    lineIndexRef.current = 0;
    lineFenRef.current = fen;

    // Reset board with full movable configuration to re-enable piece movement
    groundRef.current?.set({
      fen,
      turnColor: orientation,
      movable: {
        free: true,
        color: orientation,
        events: {
          after: handleMove,
        },
      },
      lastMove: undefined,
      check: undefined,
    });

    // Remove hint overlay if shown
    if (hintSquareRef.current) {
      hintSquareRef.current.remove();
      hintSquareRef.current = null;
    }

    // Reset state
    setState({
      currentFen: fen,
      feedback: 'idle',
      hintShown: false,
      isValidating: false,
      isSolved: false,
      showArrows: true,
      pathStep: 0,
      capturedStars: new Set<string>(),
      showCelebration: false,
    });
  }, [fen, orientation, handleMove]);

  return (
    <div className={`animated-chess-board ${className}`}>
      {/* Chess board container with star overlay */}
      <div
        style={{
          width: '100%',
          maxWidth: '500px',
          aspectRatio: '1 / 1',
          position: 'relative', // Required for absolute positioning of star overlay
        }}
      >
        {/* Chessground board */}
        <div
          ref={boardRef}
          className="chessground-wrapper"
          style={{
            width: '100%',
            height: '100%',
          }}
        />
        {/* Multi-star mode: render multiple stars */}
        {targetSquares && targetSquares.length > 0 && targetSquares.map((square) => (
          <TargetStar
            key={square}
            square={square}
            orientation={orientation}
            visible={!state.capturedStars.has(square)}
          />
        ))}
        {/* Single-star mode: render single star (if showStar is true) */}
        {showStar && solutionMove && !targetSquares && !isLineMode && (
          <TargetStar
            square={solutionMove.slice(2, 4)}
            orientation={orientation}
            visible={!state.isSolved}
          />
        )}
        {/* Arrow overlay showing path from piece to target (only for single-star mode) */}
        {showArrowsOverlay && arrowFromSquare && solutionMove && !targetSquares && !isLineMode && (
          <ArrowOverlay
            fromSquare={arrowFromSquare}
            toSquare={solutionMove.slice(2, 4)}
            orientation={orientation}
            visible={state.showArrows && !state.isSolved}
            intermediateSquares={arrowPath}
          />
        )}
        {/* Lottie celebration animation */}
        <LottieCelebration
          visible={state.showCelebration}
          onComplete={() => setState((prev) => ({ ...prev, showCelebration: false }))}
        />
      </div>

      {/* Board controls */}
      <BoardControls
        onHint={handleShowHint}
        onReset={handleReset}
        hintDisabled={state.isSolved || state.hintShown || !showHints}
        resetDisabled={state.isValidating}
      />

      {/* Feedback display */}
      <FeedbackDisplay feedback={state.feedback} />
    </div>
  );
}
