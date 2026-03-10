import React, { CSSProperties, JSX } from "react";
import { useTranslations } from "next-intl";
import { apiFetch, ApiError } from '@/lib/api';
import {
  Stack,
  Button,
  TextField,
  Paper,
  Switch,
  Slider,
  Box,
  Divider,
  Typography,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Chip,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from "@mui/material";
import {
  Settings as SettingsIcon,
  // NavigateBefore, NavigateNext removed — using ChessBase SVG icons
  RotateLeft,
  Upload,
  CameraAlt,
  Close,
  // SkipPrevious, SkipNext, Replay, SwapVert removed — using ChessBase SVG icons
} from "@mui/icons-material";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import ChessgroundBoard from "@/components/chess/ChessgroundBoard";
import { UciEngine } from "@/stockfish/engine/UciEngine";
import { SvgIcon, SvgIconProps } from "@mui/material";
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import type { Key } from 'chessground/types';

// ChessBase-style SVG icons (extracted from database.chessbase.com)
const CBResetIcon = (props: SvgIconProps) => (
  <SvgIcon {...props} viewBox="0 0 187.862 164">
    <path d="M82,135.848c-29.738,0-53.848-24.109-53.848-53.848S52.262,28.152,82,28.152c9.961,0,19.283,2.715,27.286,7.431 l14.266-24.269C111.364,4.135,97.168,0,82,0C36.713,0,0,36.713,0,82s36.713,82,82,82s82-36.713,82-82h-28.152 C135.848,111.738,111.738,135.848,82,135.848z" />
    <polygon points="111.124,82.652 149.493,16.195 187.862,82.652" />
  </SvgIcon>
);

const CBGoToStartIcon = (props: SvgIconProps) => (
  <SvgIcon {...props} viewBox="0 0 274.446 170">
    <path d="M274.446,150c0,11-7.794,15.5-17.32,10L144.543,95c-9.526-5.5-9.526-14.5,0-20l112.582-65c9.526-5.5,17.32-1,17.32,10V150z" />
    <path d="M147.223,150c0,11-7.794,15.5-17.32,10L17.32,95c-9.526-5.5-9.526-14.5,0-20l112.583-65c9.526-5.5,17.32-1,17.32,10V150z" />
    <path d="M28,10c0-5.5-4.5-10-10-10h-8C4.5,0,0,4.5,0,10v150c0,5.5,4.5,10,10,10h8c5.5,0,10-4.5,10-10V10z" />
  </SvgIcon>
);

const CBPreviousMoveIcon = (props: SvgIconProps) => (
  <SvgIcon {...props} viewBox="0 0 137.047 154.695">
    <path d="M137.047,142.347c0,11-7.794,15.5-17.32,10l-112.583-65c-9.526-5.5-9.526-14.5,0-20l112.583-65c9.526-5.5,17.32-1,17.32,10 V142.347z" />
  </SvgIcon>
);

const CBNextMoveIcon = (props: SvgIconProps) => (
  <SvgIcon {...props} viewBox="0 0 137.047 154.695">
    <path d="M0,12.347c0-11,7.794-15.5,17.32-10l112.583,65c9.526,5.5,9.526,14.5,0,20l-112.583,65c-9.526,5.5-17.32,1-17.32-10V12.347z" />
  </SvgIcon>
);

const CBGoToEndIcon = (props: SvgIconProps) => (
  <SvgIcon {...props} viewBox="0 0 274.446 170">
    <path d="M0,20C0,9,7.794,4.5,17.32,10l112.583,65c9.526,5.5,9.526,14.5,0,20L17.32,160C7.794,165.5,0,161,0,150V20z" />
    <path d="M127.223,20c0-11,7.794-15.5,17.32-10l112.582,65c9.526,5.5,9.526,14.5,0,20l-112.582,65c-9.526,5.5-17.32,1-17.32-10V20z" />
    <path d="M246.446,160c0,5.5,4.5,10,10,10h8c5.5,0,10-4.5,10-10V10c0-5.5-4.5-10-10-10h-8c-5.5,0-10,4.5-10,10V160z" />
  </SvgIcon>
);

const CBFlipBoardIcon = (props: SvgIconProps) => (
  <SvgIcon {...props} viewBox="0 0 303.866 170">
    <path d="M274.076,77.414c0-25.335-20.364-45.872-45.485-45.872V0c41.568,1.208,74.902,35.367,74.902,77.362 c0,41.993-33.334,76.154-74.902,77.362v-31.438C253.711,123.285,274.076,102.748,274.076,77.414z" />
    <polygon points="176.938,139.509 229.621,109.018 229.621,170" />
    <path d="M169.956,0v170H0.374V0H169.956z M22.818,147.5h62.346V85h62.346V22.5H85.165V85H22.818V147.5z" />
  </SvgIcon>
);
import { Chess, Square } from "chess.js";
import { PositionEval } from "@/stockfish/engine/engine";
import { MasterGames } from "../../libs/openingdatabase/helper";
import { MoveAnalysis } from "../../hooks/useGameReview";
import { getMoveClassificationStyle } from "../tabs/GameReviewTab";
import PGNView from "../tabs/PgnView";
import { Board } from "../../libs/tacticalboard/board";
import { useLocalStorage } from "usehooks-ts";
import {
  BOARD_THEMES,
  DEFAULT_BOARD_ANIMATION_DURATION,
  DEFAULT_BOARD_FLIPPED,
  DEFAULT_BOARD_HANGING_PIECE,
  DEFAULT_BOARD_PANEL_DIMENSIONS,
  DEFAULT_BOARD_SEMI_PROTECTED_PIECE,
  DEFAULT_BOARD_SHOW_COORDINATE,
  DEFAULT_BOARD_SHOW_FEN,
  DEFAULT_BOARD_SIZE,
  getCurrentThemeColors,
  PIECE_STYLE_TYPES,
} from "@/libs/setting/helper";
import PlayerInfoBar from "../tabs/PlayerInfoTab";
import { EvalBar } from "./EvalBar";
import BoardEditor from "@/components/editor/BoardEditor";
import { useSoundEffects } from "@/hooks/useSoundEffects";
import { useHaptic } from "@/hooks/useHaptic";

interface AiChessboardPanelProps {
  fen: string;
  moveSquares: { [square: string]: string };
  llmLoading: boolean;
  engine: UciEngine | undefined;
  analyzeWithStockfish: () => void;
  stockfishLoading: boolean;
  fetchOpeningData: () => void;
  openingLoading: boolean;
  setGame: (chess: Chess) => void;
  setFen: (fen: string) => void;
  setLlmAnalysisResult: (result: string | null) => void;
  setStockfishAnalysisResult: (result: PositionEval | null) => void;
  setOpeningData: (result: MasterGames | null) => void;
  puzzleMode?: boolean;
  playMode?: boolean;
  gameReviewMode?: boolean;
  onDropPuzzle?: (source: string, target: string) => boolean;
  handleSquarePuzzleClick?: (square: string) => void;
  reviewMove?: MoveAnalysis;
  puzzleCustomSquareStyle?: {
    [square: string]: CSSProperties;
  };
  game: Chess;
  side?: 'white' | 'black';
  moves?: string[];
  stockfishAnalysisResult?: PositionEval | null;
  gameInfo?: Record<string, string>;
  setMoveSquares: (square: { [square: string]: string }) => void;
  gameStatus?: string;
  playerSide?: "white" | "black";
  engineThinking?: boolean;
  editorMode?: boolean;
  onEditorModeChange?: (mode: boolean) => void;
  onEditorStateChange?: (state: import("@/components/editor/BoardEditor").EditorState) => void;
}

export default function AiChessboardPanel({
  fen,
  moveSquares,
  setGame,
  setFen,
  setLlmAnalysisResult,
  setStockfishAnalysisResult,
  setOpeningData,
  game,
  moves,
  stockfishAnalysisResult,
  puzzleMode,
  onDropPuzzle,
  handleSquarePuzzleClick,
  setMoveSquares,
  puzzleCustomSquareStyle,
  reviewMove,
  side,
  playMode,
  gameStatus = "waiting",
  playerSide = "white",
  gameReviewMode,
  gameInfo,
  engineThinking = false,
  editorMode = false,
  onEditorModeChange,
  onEditorStateChange,
}: AiChessboardPanelProps) {
  const tEditor = useTranslations("editor");
  const tBoard = useTranslations("board");
  const { play: playSound } = useSoundEffects();
  const haptic = useHaptic();
  // Fix hydration mismatch by ensuring client-only rendering
  const [mounted, setMounted] = useState(false);

  // Responsive board sizing
  const [windowWidth, setWindowWidth] = useState(typeof window !== 'undefined' ? window.innerWidth : 1024);

  const [customFen, setCustomFen] = useState("");
  const [isFlipped, setIsFlipped] = useLocalStorage<boolean>(
    "board_ui_flipped",
    DEFAULT_BOARD_FLIPPED
  );
  const [moveHistory, setMoveHistory] = useState<string[]>([]);
  const [currentMoveIndex, setCurrentMoveIndex] = useState(-1);
  const [showArrows, setShowArrows] = useState(
    puzzleMode || playMode ? false : true
  );
  const [boardSize, setBoardSize] = useLocalStorage<number>(
    "board_ui_size",
    DEFAULT_BOARD_SIZE
  );

  // Panel dimensions - moved here so it's available before responsivePanelDimensions
  const [panelDimensions, setPanelDimensions] = useLocalStorage<{
    width: number;
    height: number;
  }>("board_ui_show_panel_dimensions", DEFAULT_BOARD_PANEL_DIMENSIONS);

  // Calculate responsive board size based on window width
  const responsiveBoardSize = useMemo(() => {
    if (windowWidth < 400) return windowWidth - 8; // Very small phones — full width
    if (windowWidth < 600) return windowWidth - 12; // Small phones — near full width
    if (windowWidth < 768) return Math.min(windowWidth - 24, 440); // Large phones
    if (windowWidth < 1024) return Math.min(windowWidth - 48, 500); // Tablets
    return boardSize; // Desktop - use user preference
  }, [windowWidth, boardSize]);

  // Calculate responsive panel dimensions
  const responsivePanelDimensions = useMemo(() => {
    if (windowWidth < 400) return { width: windowWidth, height: 'auto' };
    if (windowWidth < 600) return { width: windowWidth, height: 'auto' };
    if (windowWidth < 768) return { width: windowWidth - 8, height: 'auto' };
    if (windowWidth < 1024) return { width: Math.min(windowWidth - 24, 540), height: 'auto' };
    return { width: panelDimensions.width, height: panelDimensions.height };
  }, [windowWidth, panelDimensions]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showCoordinates, setShowCoordinates] = useLocalStorage<boolean>(
    "board_show_coordinates",
    DEFAULT_BOARD_SHOW_COORDINATE
  );

  // Keep theme settings for UI even though chessground uses CSS theming
  const [pieceType, setPieceType] = useLocalStorage<string>(
    "board_piece_type",
    "Fritz"
  );
  const [boardTheme, setBoardTheme] = useLocalStorage<string>(
    "board_theme",
    "chessbase"
  );

  const [animationDuration, setAnimationDuration] = useLocalStorage<number>(
    "board_ui_animation_duration",
    DEFAULT_BOARD_ANIMATION_DURATION
  );

  const [showEvalBar, setEvalBar] = useLocalStorage<boolean>(
    "board_ui_show_eval_bar",
    true
  );

  const [showFen, setShowFen] = useLocalStorage<boolean>(
    "board_ui_show_fen",
    DEFAULT_BOARD_SHOW_FEN
  );

  // Piece highlighting settings
  const [showHangingPieces, setShowHangingPieces] = useLocalStorage<boolean>(
    "board_ui_show_hanging_piece",
    DEFAULT_BOARD_HANGING_PIECE
  );
  const [showSemiProtectedPieces, setShowSemiProtectedPieces] =
    useLocalStorage<boolean>(
      "board_ui_show_semiprotectedpiece",
      DEFAULT_BOARD_SEMI_PROTECTED_PIECE
    );

  // Note: This component is loaded with dynamic({ ssr: false }) from page.tsx
  // so useLocalStorage hydration mismatches are avoided at the import level.

  // One-time migration: switch existing users from old defaults to ChessBase/Fritz
  useEffect(() => {
    const migrated = localStorage.getItem('board_theme_migrated_v2');
    if (!migrated) {
      setPieceType('Fritz');
      setBoardTheme('chessbase');
      localStorage.setItem('board_theme_migrated_v2', '1');
    }
  }, []);

  // Resize functionality
  const [isResizing, setIsResizing] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const startPosRef = useRef({ x: 0, y: 0 });
  const startDimensionsRef = useRef({ width: 0, height: 0 });

  // Photo-to-FEN state
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [photoLoading, setPhotoLoading] = useState(false);
  const [photoError, setPhotoError] = useState<string>("");

  // Memoized Board analysis
  const boardAnalysis = useMemo(() => {
    if (!fen || (!showHangingPieces && !showSemiProtectedPieces)) {
      return null;
    }
    try {
      return new Board(fen);
    } catch (error) {
      console.error("Error analyzing board:", error);
      return null;
    }
  }, [fen, showHangingPieces, showSemiProtectedPieces]);

  // Memoized piece highlighting styles
  const pieceHighlightStyles = useMemo(() => {
    const styles: { [square: string]: React.CSSProperties } = {};

    if (!boardAnalysis) return styles;

    // Hanging pieces - Critical (red)
    if (showHangingPieces) {
      boardAnalysis.HangingPieceCoordinates.forEach((coord) => {
        styles[coord] = {
          backgroundColor: "rgba(244, 67, 54, 0.6)", // Red with transparency
          boxShadow: "inset 0 0 0 3px rgba(244, 67, 54, 0.8)",
        };
      });
    }

    // Semi-protected pieces - Medium priority (yellow)
    if (showSemiProtectedPieces) {
      boardAnalysis.SemiProtectedPieceCoordinates.forEach((coord) => {
        // Don't override hanging or unprotected pieces
        if (!styles[coord]) {
          styles[coord] = {
            backgroundColor: "rgba(255, 235, 59, 0.6)", // Yellow with transparency
            boxShadow: "inset 0 0 0 3px rgba(255, 235, 59, 0.8)",
          };
        }
      });
    }

    return styles;
  }, [boardAnalysis, showHangingPieces, showSemiProtectedPieces]);

  // Resize handler
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsResizing(true);
      startPosRef.current = { x: e.clientX, y: e.clientY };
      startDimensionsRef.current = { ...panelDimensions };

      const handleMouseMove = (e: MouseEvent) => {
        const deltaX = e.clientX - startPosRef.current.x;
        const deltaY = e.clientY - startPosRef.current.y;

        // Set min and max limits
        const minWidth = 400;
        const maxWidth = 900;
        const minHeight = 500;
        const maxHeight = 900;

        const newWidth = Math.min(
          maxWidth,
          Math.max(minWidth, startDimensionsRef.current.width + deltaX)
        );
        const newHeight = Math.min(
          maxHeight,
          Math.max(minHeight, startDimensionsRef.current.height + deltaY)
        );

        // Auto-adjust board size based on panel width
        const newBoardSize = Math.min(800, Math.max(300, newWidth - 70));
        setBoardSize(newBoardSize);

        setPanelDimensions({ width: newWidth, height: newHeight });
      };

      const handleMouseUp = () => {
        setIsResizing(false);
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
      };

      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    },
    [panelDimensions]
  );

  // Memoize the initial game setup to avoid recalculation
  const gameHistory = useMemo(() => {
    const baseGame = new Chess();
    const history: string[] = [baseGame.fen()];

    if (moves && moves.length > 0) {
      for (const move of moves) {
        try {
          baseGame.move(move);
          history.push(baseGame.fen());
        } catch (err) {
          console.warn("Invalid move in provided history:", move);
          break;
        }
      }
    }

    return history;
  }, [moves]);

  // Fix hydration mismatch - only render after client-side mount
  useEffect(() => {
    setMounted(true);
  }, []);

  // Responsive resize listener
  useEffect(() => {
    const handleResize = () => {
      setWindowWidth(window.innerWidth);
    };

    window.addEventListener('resize', handleResize);
    // Set initial width after mount
    handleResize();

    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Effect to update game state when moves change
  useEffect(() => {
    const startGame = new Chess(gameHistory[0]);

    setGame(startGame);
    setFen(gameHistory[0]);
    setMoveHistory(gameHistory);
    setCurrentMoveIndex(gameHistory.length - 1);
  }, [gameHistory, setGame, setFen]);

  // Fixed function to safely mutate game state with proper branching
  const safeGameMutate = useCallback(
    (modify: (game: Chess) => void) => {
      const currentFen = fen;
      if (!currentFen) return;

      const newGame = new Chess(currentFen);
      modify(newGame);

      const newFen = newGame.fen();

      const newHistory = [
        ...moveHistory.slice(0, currentMoveIndex + 1),
        newFen,
      ];

      setGame(newGame);
      setFen(newFen);
      setMoveHistory(newHistory);
      setCurrentMoveIndex(newHistory.length - 1);
      setOpeningData(null);
    },
    [fen, moveHistory, currentMoveIndex, setGame, setFen, setOpeningData]
  );

  // Memoized clear analysis callback
  const clearAnalysis = useCallback(() => {
    setLlmAnalysisResult(null);
    setStockfishAnalysisResult(null);
    setOpeningData(null);
  }, [setLlmAnalysisResult, setStockfishAnalysisResult, setOpeningData]);

  // Check if player can move in play mode
  const canPlayerMove = useCallback(() => {
    if (!playMode || gameStatus !== "playing") return true;

    const currentTurn = game.turn();
    return (
      ((side === "white" && currentTurn === "w") ||
        (side === "black" && currentTurn === "b")) &&
      !engineThinking
    );
  }, [playMode, gameStatus, game, playerSide, engineThinking]);

  // Custom onDrop handler for gameplay - adapted for chessground
  const handlePlayerMove = useCallback(
    (from: Key, to: Key) => {
      if (playMode) {
        if (!canPlayerMove()) return;

        try {
          const move = game.move({
            from,
            to,
            promotion: "q",
          });

          if (move) {
            playSound(move.captured ? 'capture' : 'move');
            haptic.vibrate(move.captured ? 'capture' : move.san.includes('+') ? 'check' : 'move');
            const newGame = new Chess(game.fen());
            setGame(newGame);
            setFen(newGame.fen());
            setMoveSquares({});
          }
        } catch (error) {
          // Invalid move - silently ignore
        }
      } else {
        safeGameMutate((gameInstance) => {
          const move = gameInstance.move({
            from,
            to,
            promotion: "q",
          });
          if (move) {
            playSound(move.captured ? 'capture' : 'move');
            haptic.vibrate(move.captured ? 'capture' : move.san.includes('+') ? 'check' : 'move');
            clearAnalysis();
          }
        });
        setMoveSquares({});
      }
    },
    [
      playMode,
      canPlayerMove,
      game,
      setGame,
      setFen,
      setMoveSquares,
      safeGameMutate,
      clearAnalysis,
      playSound,
      haptic,
    ]
  );

  const pgnMoves = useMemo(() => {
    if (moveHistory.length <= 1) return [];

    const moves: string[] = [];
    const tempGame = new Chess();

    // Start from the initial position and replay each move
    for (let i = 1; i < moveHistory.length; i++) {
      const prevFen = moveHistory[i - 1];
      const currentFen = moveHistory[i];

      tempGame.load(prevFen);
      const possibleMoves = tempGame.moves({ verbose: true });

      // Find which move leads to the current FEN
      for (const move of possibleMoves) {
        const testGame = new Chess(prevFen);
        testGame.move(move);

        if (testGame.fen() === currentFen) {
          moves.push(move.san);
          break;
        }
      }
    }

    return moves;
  }, [moveHistory]);

  const goToMoveFromPGN = useCallback(
    (moveNumber: number) => {
      // moveNumber is 1-based from PGN component
      // Convert to moveHistory index (moveHistory[0] is starting position)
      const historyIndex = moveNumber;

      if (historyIndex >= 0 && historyIndex < moveHistory.length) {
        const newFen = moveHistory[historyIndex];
        const newGame = new Chess(newFen);

        setGame(newGame);
        setFen(newFen);
        setCurrentMoveIndex(historyIndex);
        clearAnalysis();
      }
    },
    [moveHistory, setGame, setFen, clearAnalysis]
  );

  // Puzzle mode move handler - adapted for chessground
  const handlePuzzleMove = useCallback(
    (from: Key, to: Key) => {
      if (onDropPuzzle) {
        onDropPuzzle(from, to);
      }
    },
    [onDropPuzzle]
  );

  const qualityToBrush = (quality: string): string => {
    const map: Record<string, string> = {
      Best: "green",
      "Very Good": "blue",
      Good: "paleGreen",
      Dubious: "yellow",
      Mistake: "red",
      Blunder: "paleRed",
      Book: "yellow",
    };
    return map[quality] || "green";
  };

  const customArrows = useMemo((): Array<{ from: Key; to: Key; brush: string }> => {
    if (!showArrows) {
      return [];
    }

    const arrows: Array<{ from: Key; to: Key; brush: string }> = [];

    // Only show review arrow if reviewMove exists and corresponds to current position
    if (reviewMove) {
      const reviewArrow = {
        from: reviewMove.arrowMove.from as Key,
        to: reviewMove.arrowMove.to as Key,
        brush: qualityToBrush(reviewMove.quality),
      };
      arrows.push(reviewArrow);

      // Only add engine arrow if reviewMove quality is not "Best"
      if (reviewMove.quality !== "Best" && stockfishAnalysisResult?.lines) {
        const bestLine = stockfishAnalysisResult.lines[0]?.pv;
        if (bestLine && bestLine.length > 0) {
          const move = bestLine[0];
          if (move && move.length >= 4) {
            const from = move.substring(0, 2);
            const to = move.substring(2, 4);

            // Avoid duplicate arrows
            const arrowKey = `${from}-${to}`;
            const reviewArrowKey = `${reviewMove.arrowMove.from}-${reviewMove.arrowMove.to}`;

            if (arrowKey !== reviewArrowKey) {
              const engineArrow = {
                from: from as Key,
                to: to as Key,
                brush: "green",
              };
              arrows.push(engineArrow);
            }
          }
        }
      }
    } else if (!reviewMove && stockfishAnalysisResult?.lines) {
      // Only show engine arrow if no reviewMove is present
      const bestLine = stockfishAnalysisResult.lines[0]?.pv;
      if (bestLine && bestLine.length > 0) {
        const move = bestLine[0];
        if (move && move.length >= 4) {
          const from = move.substring(0, 2);
          const to = move.substring(2, 4);
          const engineArrow = { from: from as Key, to: to as Key, brush: "green" };
          arrows.push(engineArrow);
        }
      }
    }

    return arrows;
  }, [showArrows, reviewMove, stockfishAnalysisResult, currentMoveIndex]);

  // Navigation callbacks
  const goToPreviousMove = useCallback(() => {
    if (currentMoveIndex > 0) {
      const newIndex = currentMoveIndex - 1;
      const newFen = moveHistory[newIndex];
      const newGame = new Chess(newFen);

      setGame(newGame);
      setFen(newFen);
      setCurrentMoveIndex(newIndex);
    }
  }, [currentMoveIndex, moveHistory, setGame, setFen]);

  const goToNextMove = useCallback(() => {
    if (currentMoveIndex < moveHistory.length - 1) {
      const newIndex = currentMoveIndex + 1;
      const newFen = moveHistory[newIndex];
      const newGame = new Chess(newFen);

      setGame(newGame);
      setFen(newFen);
      setCurrentMoveIndex(newIndex);
    }
  }, [currentMoveIndex, moveHistory, setGame, setFen]);

  const goToStart = useCallback(() => {
    if (moveHistory.length > 0 && currentMoveIndex > 0) {
      const newFen = moveHistory[0];
      const newGame = new Chess(newFen);
      setGame(newGame);
      setFen(newFen);
      setCurrentMoveIndex(0);
    }
  }, [moveHistory, currentMoveIndex, setGame, setFen]);

  const goToEnd = useCallback(() => {
    if (moveHistory.length > 0 && currentMoveIndex < moveHistory.length - 1) {
      const lastIndex = moveHistory.length - 1;
      const newFen = moveHistory[lastIndex];
      const newGame = new Chess(newFen);
      setGame(newGame);
      setFen(newFen);
      setCurrentMoveIndex(lastIndex);
    }
  }, [moveHistory, currentMoveIndex, setGame, setFen]);

  const resetBoard = useCallback(() => {
    const startingFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
    const newGame = new Chess(startingFen);
    setGame(newGame);
    setFen(startingFen);
    setMoveHistory([startingFen]);
    setCurrentMoveIndex(0);
    clearAnalysis();
  }, [setGame, setFen, clearAnalysis]);

  // Load custom FEN callback
  const loadCustomFen = useCallback(() => {
    try {
      const newGame = new Chess(customFen);
      setGame(newGame);
      setFen(newGame.fen());
      setMoveHistory([newGame.fen()]);
      setCurrentMoveIndex(0);
      clearAnalysis();
      setCustomFen("");
    } catch (error) {
      alert("Invalid FEN string.");
    }
  }, [customFen, setGame, setFen, clearAnalysis]);

  // Photo-to-FEN handler
  const handlePhotoUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
      setPhotoError('Please select an image file');
      return;
    }

    // Create preview
    const reader = new FileReader();
    reader.onload = async (e) => {
      const base64Full = e.target?.result as string;
      const base64Data = base64Full.split(',')[1]; // Remove data:image/...;base64, prefix
      setPhotoPreview(base64Full);
      setPhotoError('');
      setPhotoLoading(true);

      try {
        let data: any;
        try {
          data = await apiFetch<any>('/api/convert-image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: base64Data }),
          });
        } catch (e) {
          if (e instanceof ApiError) {
            setPhotoError(e.message || 'Failed to convert image to FEN');
          } else {
            setPhotoError('Network error. Please try again.');
          }
          setPhotoLoading(false);
          return;
        }

        if (data.fen) {
          // Try to load the FEN into the board
          try {
            const newGame = new Chess(data.fen);
            setGame(newGame);
            setFen(newGame.fen());
            setMoveHistory([newGame.fen()]);
            setCurrentMoveIndex(0);
            clearAnalysis();
            setPhotoPreview(null);
            setSettingsOpen(false);
          } catch (fenError) {
            console.error('Invalid FEN from API:', data.fen, fenError);
            setPhotoError(`Invalid position detected. FEN: ${data.fen}`);
          }
        } else {
          setPhotoError(data.error || 'Failed to convert image to FEN');
        }
      } catch (error) {
        console.error('Photo-to-FEN error:', error);
        setPhotoError('Network error. Please try again.');
      } finally {
        setPhotoLoading(false);
      }
    };
    reader.readAsDataURL(file);
  }, [setGame, setFen, clearAnalysis]);

  const clearPhotoPreview = useCallback(() => {
    setPhotoPreview(null);
    setPhotoError('');
  }, []);

  // Flip board callback
  const flipBoard = useCallback(() => {
    setIsFlipped(!isFlipped);
  }, [isFlipped]);

  // Settings handlers
  const handleSettingsClose = () => {
    setSettingsOpen(false);
  };

  const handleBoardSizeChange = useCallback(
    (_: Event, newValue: number | number[]) => {
      setBoardSize(newValue as number);
    },
    []
  );

  const handleAnimationChange = useCallback(
    (_: Event, newValue: number | number[]) => {
      setAnimationDuration(newValue as number);
    },
    []
  );

  // Navigation button disabled states
  const isPreviousDisabled = currentMoveIndex <= 0;
  const isNextDisabled = currentMoveIndex >= moveHistory.length - 1;

  // Determine board orientation
  const getBoardOrientation = useCallback(() => {
    if (puzzleMode) return side;
    if (playMode) return side;
    return isFlipped ? "black" : "white";
  }, [puzzleMode, playMode, side, playerSide, isFlipped]);

  // Get mode display info
  const getModeInfo = () => {
    if (puzzleMode) return { label: "Puzzle Mode", color: "#ff9800" };
    if (playMode) return { label: "Play Mode", color: "#4caf50" };
    if (gameReviewMode)
      return { label: "Game Analysis Mode", color: "#eaeb96ff" };
    return { label: tEditor("analysisMode"), color: "#bc58ceff" };
  };

  const modeInfo = getModeInfo();

  // Determine if PGN should be shown
  const shouldShowPGN = !gameReviewMode && !puzzleMode && !playMode;

  const { TopPlayerBar, BottomPlayerBar } = PlayerInfoBar({
    gameInfo,
    boardOrientation: getBoardOrientation(),
  });

  // Get last move for chessground highlighting
  const getLastMove = useCallback((): [Key, Key] | null => {
    if (moveHistory.length < 2) return null;

    try {
      const prevFen = moveHistory[currentMoveIndex - 1];
      const currentFen = moveHistory[currentMoveIndex];

      if (!prevFen || !currentFen) return null;

      const prevGame = new Chess(prevFen);
      const possibleMoves = prevGame.moves({ verbose: true });

      for (const move of possibleMoves) {
        const testGame = new Chess(prevFen);
        testGame.move(move);

        if (testGame.fen() === currentFen) {
          return [move.from as Key, move.to as Key];
        }
      }
    } catch {
      return null;
    }

    return null;
  }, [moveHistory, currentMoveIndex]);

  // Prevent hydration mismatch - don't render until mounted
  if (!mounted) {
    return null;
  }

  return (
    <Box
      ref={containerRef}
      sx={{
        width: typeof responsivePanelDimensions.width === 'number'
          ? `${responsivePanelDimensions.width}px`
          : responsivePanelDimensions.width,
        height: responsivePanelDimensions.height === 'auto'
          ? 'auto'
          : `${responsivePanelDimensions.height}px`,
        maxWidth: '100%',
        position: "relative",
        border: 1,
        borderColor: "divider",
        borderRadius: 2,
        backgroundColor: "background.paper",
        overflow: "hidden",
        userSelect: isResizing ? "none" : "auto",
      }}
    >
      <Box
        sx={{
          height: "100%",
          overflowY: "auto",
          overflowX: "hidden",
          p: windowWidth < 600 ? 0.5 : 2,
          "&::-webkit-scrollbar": {
            width: "6px",
          },
          "&::-webkit-scrollbar-track": {
            background: "var(--surface-card)",
            borderRadius: "3px",
          },
          "&::-webkit-scrollbar-thumb": {
            background: "var(--text-secondary)",
            borderRadius: "3px",
            "&:hover": {
              background: "var(--text-secondary)",
            },
          },
        }}
      >
        {/* Header */}
        <Paper
          sx={{
            p: 1.5,
            backgroundColor: "background.paper",
            borderRadius: 2,
            mb: 2,
          }}
        >
          <Stack
            direction="row"
            alignItems="center"
            spacing={2}
            sx={{ mb: 1.5 }}
          >
            {/* Mode tabs — show Analysis/Editor toggle only in default analysis mode */}
            {!puzzleMode && !playMode && !gameReviewMode ? (
              <Stack direction="row" spacing={0.5}>
                <Chip
                  label={tEditor("analysisMode")}
                  size="small"
                  onClick={() => onEditorModeChange?.(false)}
                  sx={{
                    backgroundColor: !editorMode ? `${modeInfo.color}20` : "transparent",
                    color: !editorMode ? modeInfo.color : "text.disabled",
                    fontSize: "0.65rem",
                    fontWeight: 600,
                    cursor: "pointer",
                    border: editorMode ? 1 : "none",
                    borderColor: editorMode ? "divider" : undefined,
                    "&:hover": { backgroundColor: !editorMode ? `${modeInfo.color}30` : "action.hover" },
                  }}
                />
                <Chip
                  label={tEditor("editorMode")}
                  size="small"
                  onClick={() => onEditorModeChange?.(true)}
                  sx={{
                    backgroundColor: editorMode ? "#1b5e2030" : "transparent",
                    color: editorMode ? "success.light" : "text.disabled",
                    fontSize: "0.65rem",
                    fontWeight: 600,
                    cursor: "pointer",
                    border: !editorMode ? 1 : "none",
                    borderColor: !editorMode ? "divider" : undefined,
                    "&:hover": { backgroundColor: editorMode ? "rgba(27,94,32,0.25)" : "action.hover" },
                  }}
                />
              </Stack>
            ) : (
              <Chip
                label={modeInfo.label}
                size="small"
                sx={{
                  backgroundColor: `${modeInfo.color}20`,
                  color: modeInfo.color,
                  fontSize: "0.65rem",
                  fontWeight: 600,
                }}
              />
            )}
            <Box sx={{ flexGrow: 1 }} />
            <IconButton
              onClick={() => setSettingsOpen(true)}
              sx={{ color: "text.primary", p: 0.5 }}
              size="small"
            >
              <SettingsIcon fontSize="small" />
            </IconButton>
          </Stack>

          {/* Board Info */}
          <Stack direction="row" alignItems="center" spacing={2}>
            {(puzzleMode || playMode) && (
              <Typography variant="caption" sx={{ color: "grey.400" }}>
                {(getBoardOrientation() ?? 'white').charAt(0).toUpperCase() + (getBoardOrientation() ?? 'white').slice(1)} to Play
              </Typography>
            )}
          </Stack>
        </Paper>

        {/* Editor Mode: show BoardEditor instead of chessboard */}
        {editorMode && !puzzleMode && !playMode && !gameReviewMode ? (
          <BoardEditor
            embedded
            hideControls
            initialFen={fen}
            boardWidth={responsiveBoardSize}
            onEditorStateChange={onEditorStateChange}
            photoPreview={photoPreview}
            photoLoading={photoLoading}
            photoError={photoError}
            onPhotoUpload={handlePhotoUpload}
            onAnalyze={(newFen) => {
              // Switch back to analysis mode and load the editor's FEN
              try {
                const newGame = new Chess(newFen);
                setGame(newGame);
                setFen(newFen);
              } catch {
                // Invalid FEN from editor — just switch mode
              }
              onEditorModeChange?.(false);
            }}
          />
        ) : (
          <>
            {gameReviewMode && gameInfo && <TopPlayerBar />}
            {/* Chessboard + Control Bar */}
            <Box sx={{ display: "flex", justifyContent: "center", mb: 2, gap: 1 }}>
              {showEvalBar && !puzzleMode && (
                <EvalBar
                  lineEval={stockfishAnalysisResult?.lines[0]}
                  boardOrientation={getBoardOrientation()}
                  height={responsiveBoardSize} // Match the board height
                />
              )}
              <Box sx={{ width: responsiveBoardSize, flexShrink: 0 }}>
                <ChessgroundBoard
                  fen={fen}
                  orientation={getBoardOrientation()}
                  boardSize={responsiveBoardSize}
                  onMove={puzzleMode ? handlePuzzleMove : handlePlayerMove}
                  arrows={customArrows}
                  lastMove={getLastMove()}
                  showCoordinates={showCoordinates}
                  animationDuration={animationDuration}
                  movable={puzzleMode || playMode || !gameReviewMode}
                  viewOnly={gameReviewMode || false}
                  premovable={playMode}
                />
                {/* Board Control Bar — same width as board */}
                {!playMode && !gameReviewMode && !puzzleMode && (
                  <Box
                    sx={{
                      display: "flex",
                      flexDirection: "row",
                      alignItems: "center",
                      backgroundColor: "action.hover",
                      borderRadius: 0,
                      height: 38,
                      width: "100%",
                      overflow: "hidden",
                    }}
                  >
                {/* ChessBase proportions: reset/start/end/flip = flex 1, prev/next = flex 1.42 */}
                {/* Icon heights match CB originals: reset=60%, start/end=38%, prev/next=40%, flip=60% of button height */}
                {[
                  { icon: <CBResetIcon sx={{ width: 22, height: 22 }} />, onClick: resetBoard, disabled: false, title: "Reset board", flex: 1 },
                  { icon: <CBGoToStartIcon sx={{ width: 18, height: 14 }} />, onClick: goToStart, disabled: isPreviousDisabled, title: "Go to start", flex: 1 },
                  { icon: <CBPreviousMoveIcon sx={{ width: 14, height: 15 }} />, onClick: goToPreviousMove, disabled: isPreviousDisabled, title: "Previous move", flex: 1.42 },
                  { icon: <CBNextMoveIcon sx={{ width: 14, height: 15 }} />, onClick: goToNextMove, disabled: isNextDisabled, title: "Next move", flex: 1.42 },
                  { icon: <CBGoToEndIcon sx={{ width: 18, height: 14 }} />, onClick: goToEnd, disabled: isNextDisabled, title: "Go to end", flex: 1 },
                  { icon: <CBFlipBoardIcon sx={{ width: 26, height: 22 }} />, onClick: flipBoard, disabled: false, title: "Flip board", flex: 1 },
                ].map((btn, i) => (
                  <Box
                    key={i}
                    onClick={btn.disabled ? undefined : btn.onClick}
                    title={btn.title}
                    sx={{
                      flex: btn.flex,
                      height: 38,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      cursor: btn.disabled ? "default" : "pointer",
                      color: btn.disabled ? "rgba(160,160,160,0.3)" : "text.secondary",
                      padding: "5px",
                      transition: "background-color 0.15s, color 0.15s",
                      "&:hover": btn.disabled ? {} : {
                        backgroundColor: "rgba(255,255,255,0.08)",
                        color: "text.primary",
                      },
                    }}
                  >
                    {btn.icon}
                  </Box>
                ))}
              </Box>
                )}
              </Box>
            </Box>
            {gameReviewMode && gameInfo && <BottomPlayerBar />}
          </>
        )}

        {!puzzleMode && !playMode && (
          <Stack spacing={2} sx={{ mt: 2 }}>
            {/* Current FEN Display - Only show if showFen is true */}
            {showFen && (
              <Paper
                sx={{
                  p: 1.5,
                  backgroundColor: "background.paper",
                  borderRadius: 2,
                }}
              >
                <Typography variant="caption" sx={{ color: "text.secondary", mb: 1 }}>
                  Current Position (FEN)
                </Typography>
                <Typography
                  variant="caption"
                  sx={{
                    color: "text.primary",
                    fontFamily: "monospace",
                    backgroundColor: "action.hover",
                    p: 1,
                    borderRadius: 1,
                    wordBreak: "break-all",
                    fontSize: "0.75rem",
                    display: "block",
                  }}
                >
                  {fen}
                </Typography>
              </Paper>
            )}

            {/* Piece Analysis Display */}
            {(showHangingPieces || showSemiProtectedPieces) &&
              boardAnalysis && (
                <Paper
                  sx={{
                    p: 1.5,
                    backgroundColor: "background.paper",
                    borderRadius: 2,
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{ color: "text.secondary", mb: 1.5, display: "block" }}
                  >
                    Piece Analysis
                  </Typography>

                  {showHangingPieces &&
                    boardAnalysis.HangingPieceDescriptions.length > 0 && (
                      <Box sx={{ mb: 1 }}>
                        <Typography
                          variant="caption"
                          sx={{
                            color: "error.main",
                            fontWeight: 600,
                            fontSize: "0.7rem",
                          }}
                        >
                          Hanging Pieces (Critical):
                        </Typography>
                        {boardAnalysis.HangingPieceDescriptions.map(
                          (desc, index) => (
                            <Typography
                              key={index}
                              variant="caption"
                              sx={{
                                color: "white",
                                fontSize: "0.65rem",
                                display: "block",
                                ml: 1,
                              }}
                            >
                              • {desc} at{" "}
                              {boardAnalysis.HangingPieceCoordinates[index]}
                            </Typography>
                          )
                        )}
                      </Box>
                    )}

                  {showSemiProtectedPieces &&
                    boardAnalysis.SemiProtectedPieceDescriptions.length > 0 && (
                      <Box sx={{ mb: 1 }}>
                        <Typography
                          variant="caption"
                          sx={{
                            color: "warning.main",
                            fontWeight: 600,
                            fontSize: "0.7rem",
                          }}
                        >
                          Semi-Protected Pieces (Contested):
                        </Typography>
                        {boardAnalysis.SemiProtectedPieceDescriptions.map(
                          (desc, index) => (
                            <Typography
                              key={index}
                              variant="caption"
                              sx={{
                                color: "white",
                                fontSize: "0.65rem",
                                display: "block",
                                ml: 1,
                              }}
                            >
                              • {desc} at{" "}
                              {
                                boardAnalysis.SemiProtectedPieceCoordinates[
                                  index
                                ]
                              }
                            </Typography>
                          )
                        )}
                      </Box>
                    )}

                  {/* Legend */}
                  <Box
                    sx={{
                      mt: 1.5,
                      pt: 1,
                      borderTop: "1px solid rgba(255,255,255,0.1)",
                    }}
                  >
                    <Typography
                      variant="caption"
                      sx={{
                        color: "grey.400",
                        fontSize: "0.6rem",
                        display: "block",
                      }}
                    >
                      Legend:
                    </Typography>
                    <Stack direction="row" spacing={2} sx={{ mt: 0.5 }}>
                      {showHangingPieces && (
                        <Box
                          sx={{
                            display: "flex",
                            alignItems: "center",
                            gap: 0.5,
                          }}
                        >
                          <Box
                            sx={{
                              width: 8,
                              height: 8,
                              backgroundColor: "error.main",
                              borderRadius: 0.5,
                            }}
                          />
                          <Typography
                            variant="caption"
                            sx={{ color: "grey.400", fontSize: "0.6rem" }}
                          >
                            Critical
                          </Typography>
                        </Box>
                      )}

                      {showSemiProtectedPieces && (
                        <Box
                          sx={{
                            display: "flex",
                            alignItems: "center",
                            gap: 0.5,
                          }}
                        >
                          <Box
                            sx={{
                              width: 8,
                              height: 8,
                              backgroundColor: "warning.light",
                              borderRadius: 0.5,
                            }}
                          />
                          <Typography
                            variant="caption"
                            sx={{ color: "grey.400", fontSize: "0.6rem" }}
                          >
                            Contested
                          </Typography>
                        </Box>
                      )}
                    </Stack>
                  </Box>
                </Paper>
              )}

            {/* PGN View */}
            {shouldShowPGN && pgnMoves.length > 0 && (
              <PGNView
                moves={pgnMoves}
                moveAnalysis={null}
                goToMove={goToMoveFromPGN}
                currentMoveIndex={currentMoveIndex}
              />
            )}
          </Stack>
        )}

        {(puzzleMode || playMode) && <Divider sx={{ mt: 2 }} />}
      </Box>

      {/* Resize Handle - hidden on mobile */}
      {windowWidth >= 1024 && (
        <Box
          onMouseDown={handleMouseDown}
          sx={{
            position: "absolute",
            bottom: 0,
            left: 0,
            width: "16px",
            height: "16px",
            cursor: "nw-resize",
            backgroundColor: "action.active",
            borderTopRightRadius: "3px",
            opacity: 0.7,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            "&:hover": {
              opacity: 1,
              backgroundColor: "action.selected",
            },
          }}
        >
          <OpenInFullIcon
            sx={{
              fontSize: "10px",
              color: "text.secondary",
              transform: "rotate(180deg)",
            }}
          />
        </Box>
      )}

      {/* Settings Dialog */}
      <Dialog
        open={settingsOpen}
        onClose={handleSettingsClose}
        fullWidth
        maxWidth="sm"
        PaperProps={{
          sx: {
            backgroundColor: "background.paper",
            color: "text.primary",
            minWidth: { xs: "90vw", sm: 400, md: 450 },
            maxWidth: { xs: "95vw", sm: 500 },
            maxHeight: "90vh",
            m: { xs: 1, sm: 2 },
          },
        }}
      >
        <DialogTitle>{tBoard("settingsTitle")}</DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ pt: 1 }}>
            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                {tBoard("boardSize", { size: boardSize })}
              </Typography>
              <Slider
                value={boardSize}
                onChange={handleBoardSizeChange}
                min={300}
                max={800}
                step={25}
                sx={{
                  color: "secondary.main",
                }}
              />
            </Box>

            {/* Board Theme Selection */}
            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
                {tBoard("boardTheme")}
              </Typography>
              <FormControl size="small" fullWidth>
                <InputLabel sx={{ color: "grey.300" }}>{tBoard("themeLabel")}</InputLabel>
                <Select
                  value={boardTheme}
                  onChange={(e) => setBoardTheme(e.target.value)}
                  label="Voice"
                  sx={{
                    color: "white",
                    "& .MuiOutlinedInput-notchedOutline": {
                      borderColor: "rgba(255,255,255,0.2)",
                    },
                    "&:hover .MuiOutlinedInput-notchedOutline": {
                      borderColor: "rgba(255,255,255,0.3)",
                    },
                    "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
                      borderColor: "primary.main",
                    },
                  }}
                  MenuProps={{
                    PaperProps: {
                      sx: {
                        backgroundColor: "action.hover",
                        color: "white",
                      },
                    },
                  }}
                >
                  {Object.entries(BOARD_THEMES).map(([key, theme]) => (
                    <MenuItem key={key} value={key}>
                      {theme.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>

            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
                {tBoard("pieceStyle")}
              </Typography>
              <FormControl size="small" fullWidth>
                <InputLabel sx={{ color: "grey.300" }}>{tBoard("pieceStyleLabel")}</InputLabel>
                <Select
                  value={pieceType}
                  onChange={(e) => setPieceType(e.target.value)}
                  label="Pieces"
                  sx={{
                    color: "white",
                    "& .MuiOutlinedInput-notchedOutline": {
                      borderColor: "rgba(255,255,255,0.2)",
                    },
                    "&:hover .MuiOutlinedInput-notchedOutline": {
                      borderColor: "rgba(255,255,255,0.3)",
                    },
                    "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
                      borderColor: "primary.main",
                    },
                  }}
                  MenuProps={{
                    PaperProps: {
                      sx: {
                        backgroundColor: "action.hover",
                        color: "white",
                      },
                    },
                  }}
                >
                  {Object.entries(PIECE_STYLE_TYPES).map(
                    ([key, piece]) => (
                      <MenuItem key={key} value={key}>
                        {piece.name}
                      </MenuItem>
                    )
                  )}
                </Select>
              </FormControl>
            </Box>

            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                {tBoard("animationSpeed", { ms: animationDuration })}
              </Typography>
              <Slider
                value={animationDuration}
                onChange={handleAnimationChange}
                min={0}
                max={1000}
                step={50}
                sx={{
                  color: "secondary.main",
                }}
              />
            </Box>

            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
                {tBoard("displayOptions")}
              </Typography>
              <Stack spacing={2}>
                <Stack
                  direction="row"
                  justifyContent="space-between"
                  alignItems="center"
                >
                  <Typography variant="body2" sx={{ color: "grey.300" }}>
                    {tBoard("showCoordinates")}
                  </Typography>
                  <Switch
                    checked={showCoordinates}
                    onChange={(e) => setShowCoordinates(e.target.checked)}
                    sx={{
                      "& .MuiSwitch-switchBase.Mui-checked": {
                        color: "secondary.main",
                      },
                      "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track":
                        {
                          backgroundColor: "primary.main",
                        },
                    }}
                  />
                </Stack>

                <Stack
                  direction="row"
                  justifyContent="space-between"
                  alignItems="center"
                >
                  <Typography variant="body2" sx={{ color: "grey.300" }}>
                    {tBoard("showFenString")}
                  </Typography>
                  <Switch
                    checked={showFen}
                    onChange={(e) => setShowFen(e.target.checked)}
                    sx={{
                      "& .MuiSwitch-switchBase.Mui-checked": {
                        color: "secondary.main",
                      },
                      "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track":
                        {
                          backgroundColor: "primary.main",
                        },
                    }}
                  />
                </Stack>

                {!puzzleMode && !playMode && (
                  <Stack
                    direction="row"
                    justifyContent="space-between"
                    alignItems="center"
                  >
                    <Typography variant="body2" sx={{ color: "grey.300" }}>
                      {tBoard("showAnalysisArrows")}
                    </Typography>
                    <Switch
                      checked={showArrows}
                      onChange={(e) => setShowArrows(e.target.checked)}
                      sx={{
                        "& .MuiSwitch-switchBase.Mui-checked": {
                          color: "secondary.main",
                        },
                        "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track":
                          {
                            backgroundColor: "primary.main",
                          },
                      }}
                    />
                  </Stack>
                )}

                {!puzzleMode && (
                  <Stack
                    direction="row"
                    justifyContent="space-between"
                    alignItems="center"
                  >
                    <Typography variant="body2" sx={{ color: "grey.300" }}>
                      {tBoard("showEvalBar")}
                    </Typography>
                    <Switch
                      checked={showEvalBar}
                      onChange={(e) => setEvalBar(e.target.checked)}
                      sx={{
                        "& .MuiSwitch-switchBase.Mui-checked": {
                          color: "secondary.main",
                        },
                        "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track":
                          {
                            backgroundColor: "primary.main",
                          },
                      }}
                    />
                  </Stack>
                )}
              </Stack>
            </Box>

            {/* Piece Highlighting Options */}
            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
                {tBoard("pieceHighlighting")}
              </Typography>
              <Stack spacing={2}>
                <Stack
                  direction="row"
                  justifyContent="space-between"
                  alignItems="center"
                >
                  <Box>
                    <Typography variant="body2" sx={{ color: "grey.300" }}>
                      {tBoard("hangingPieces")}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{ color: "grey.500", fontSize: "0.7rem" }}
                    >
                      {tBoard("hangingPiecesDesc")}
                    </Typography>
                  </Box>
                  <Switch
                    checked={showHangingPieces}
                    onChange={(e) => setShowHangingPieces(e.target.checked)}
                    sx={{
                      "& .MuiSwitch-switchBase.Mui-checked": {
                        color: "error.main",
                      },
                      "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track":
                        {
                          backgroundColor: "error.main",
                        },
                    }}
                  />
                </Stack>

                <Stack
                  direction="row"
                  justifyContent="space-between"
                  alignItems="center"
                >
                  <Box>
                    <Typography variant="body2" sx={{ color: "grey.300" }}>
                      {tBoard("semiProtectedPieces")}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{ color: "grey.500", fontSize: "0.7rem" }}
                    >
                      {tBoard("semiProtectedDesc")}
                    </Typography>
                  </Box>
                  <Switch
                    checked={showSemiProtectedPieces}
                    onChange={(e) =>
                      setShowSemiProtectedPieces(e.target.checked)
                    }
                    sx={{
                      "& .MuiSwitch-switchBase.Mui-checked": {
                        color: "warning.main",
                      },
                      "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track":
                        {
                          backgroundColor: "warning.light",
                        },
                    }}
                  />
                </Stack>
              </Stack>
            </Box>

            {!puzzleMode && !playMode && (
              <>
                <Divider sx={{ borderColor: "rgba(255,255,255,0.1)" }} />

                <Box>
                  <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
                    {tBoard("boardControls")}
                  </Typography>

                  <Stack spacing={2}>
                    {/* Flip Board Button */}
                    <Button
                      variant="outlined"
                      onClick={flipBoard}
                      startIcon={<RotateLeft />}
                      fullWidth
                      sx={{
                        color: "secondary.main",
                        borderColor: "primary.main",
                        "&:hover": {
                          borderColor: "primary.dark",
                          backgroundColor: "rgba(156, 39, 176, 0.1)",
                        },
                      }}
                    >
                      {tBoard("flipBoard")}
                    </Button>

                    {/* FEN Input */}
                    <TextField
                      label={tBoard("loadFenLabel")}
                      variant="outlined"
                      value={customFen}
                      onChange={(e) => setCustomFen(e.target.value)}
                      size="small"
                      fullWidth
                      sx={{
                        "& .MuiOutlinedInput-root": {
                          backgroundColor: "rgba(255,255,255,0.05)",
                          "& fieldset": {
                            borderColor: "rgba(255,255,255,0.2)",
                          },
                          "&:hover fieldset": {
                            borderColor: "rgba(255,255,255,0.3)",
                          },
                          "&.Mui-focused fieldset": {
                            borderColor: "primary.main",
                          },
                        },
                      }}
                      slotProps={{
                        input: {
                          sx: { color: "white" },
                        },
                        inputLabel: {
                          sx: { color: "grey.400" },
                        },
                      }}
                      placeholder="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
                    />

                    <Button
                      variant="contained"
                      onClick={loadCustomFen}
                      startIcon={<Upload />}
                      disabled={!customFen.trim()}
                      fullWidth
                      sx={{
                        backgroundColor: "primary.main",
                        "&:hover": {
                          backgroundColor: "primary.dark",
                        },
                        "&:disabled": {
                          backgroundColor: "rgba(156, 39, 176, 0.3)",
                        },
                      }}
                    >
                      {tBoard("loadFen")}
                    </Button>

                    {/* Photo to FEN Section */}
                    <Divider sx={{ borderColor: "rgba(255,255,255,0.1)", my: 1 }} />

                    <Typography variant="caption" sx={{ color: "grey.500", display: "block", mb: 1 }}>
                      {tBoard("uploadPhotoHint")}
                    </Typography>

                    <Button
                      variant="outlined"
                      component="label"
                      startIcon={<CameraAlt />}
                      fullWidth
                      disabled={photoLoading}
                      sx={{
                        color: "info.main",
                        borderColor: "#00bcd4",
                        "&:hover": {
                          borderColor: "#0097a7",
                          backgroundColor: "rgba(0, 188, 212, 0.1)",
                        },
                      }}
                    >
                      {photoLoading ? tBoard("analyzing") : tBoard("uploadBoardPhoto")}
                      <input
                        type="file"
                        hidden
                        accept="image/*"
                        onChange={handlePhotoUpload}
                      />
                    </Button>

                    {/* Photo Preview */}
                    {photoPreview && (
                      <Box sx={{ position: "relative", mt: 1 }}>
                        <img
                          src={photoPreview}
                          alt="Chess board preview"
                          style={{
                            width: "100%",
                            maxHeight: "200px",
                            objectFit: "contain",
                            borderRadius: "8px",
                            border: "1px solid rgba(255,255,255,0.2)",
                          }}
                        />
                        <IconButton
                          size="small"
                          onClick={clearPhotoPreview}
                          sx={{
                            position: "absolute",
                            top: 4,
                            right: 4,
                            backgroundColor: "rgba(0,0,0,0.6)",
                            "&:hover": { backgroundColor: "rgba(0,0,0,0.8)" },
                          }}
                        >
                          <Close sx={{ color: "white", fontSize: 16 }} />
                        </IconButton>
                        {photoLoading && (
                          <Box
                            sx={{
                              position: "absolute",
                              top: 0,
                              left: 0,
                              right: 0,
                              bottom: 0,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              backgroundColor: "rgba(0,0,0,0.5)",
                              borderRadius: "8px",
                            }}
                          >
                            <Typography sx={{ color: "white" }}>
                              {tBoard("analyzingPosition")}
                            </Typography>
                          </Box>
                        )}
                      </Box>
                    )}

                    {/* Photo Error */}
                    {photoError && (
                      <Typography
                        variant="caption"
                        sx={{ color: "error.main", display: "block", mt: 1 }}
                      >
                        {photoError}
                      </Typography>
                    )}
                  </Stack>
                </Box>
              </>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleSettingsClose} sx={{ color: "secondary.main" }}>
            {tBoard("done")}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
