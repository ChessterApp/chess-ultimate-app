"use client";

import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useTranslations } from "next-intl";
import {
  Box,
  CircularProgress,
  Paper,
  Stack,
  Typography,
  Tabs,
  Tab,
  Button,
  Card,
  CardContent,
  Alert,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Autocomplete,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  SelectChangeEvent,
} from "@mui/material";
import type { Chess, Square } from "chess.js";
import dynamic from "next/dynamic";
import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import '@/styles/chessground-theme.css';
import { TabPanel } from "@/components/tabs/tab";
import StockfishAnalysisTab from "@/components/tabs/StockfishTab";
import ChatTab from "@/components/tabs/ChatTab";
import useChesster from "@/hooks/useChesster";
import { useSoundEffects } from "@/hooks/useSoundEffects";
import { apiFetch, ApiError } from '@/lib/api';
import { useToast } from '@/components/ToastProvider';
import RateLimitNotice from '@/components/RateLimitNotice';

// Dynamic import for code splitting
const AiChessboardPanel = dynamic(() => import("@/components/analysis/AiChessboard"), {
  ssr: false,
  loading: () => <div className="animate-pulse h-80 bg-gray-200 rounded-xl" />
});
// Clerk authentication disabled for local development
// import { useSession } from "@clerk/nextjs";
import {
  Lightbulb,
  Star,
  Eye,
  SkipForwardIcon as SkipNextIcon,
  SkipBackIcon,
  Settings,
  Filter,
} from "lucide-react";
import { Refresh, SkipNext } from "@mui/icons-material";
import Slider from "@/components/stockfish/Slider";
import { useLocalStorage } from "usehooks-ts";
import { PuzzleData, PuzzleQuery, PUZZLE_THEMES, DIFFICULTY_THEMES } from "@/libs/puzzle/helper";
import Loader from "@/components/loading/Loader";
import Warning from "@/components/loading/SignUpWarning";
import Breadcrumbs from "@/components/Breadcrumbs";

export default function PuzzlePage() {
  // const session = useSession();
  // Simulated session for no-auth mode
  const session = { isLoaded: true, isSignedIn: true };
  const t = useTranslations('puzzle');
  const { showToast } = useToast();
  const { play: playSound } = useSoundEffects();
  const [rateLimited, setRateLimited] = useState(false);

  // Client-side only flag
  const [mounted, setMounted] = useState(false);

  const [puzzleData, setPuzzleData] = useState<PuzzleData | null>(null);
  const [puzzleQuery, setPuzzleQuery] = useState<PuzzleQuery | null>(null);

  const [puzzleQueryString, setPuzzleQueryString] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Theme selection state
  const [themeDialogOpen, setThemeDialogOpen] = useState(false);
  const [selectedThemes, setSelectedThemes] = useState<string[]>([]);
  const [quickTheme, setQuickTheme] = useState<string>("");

  // Game state - lazy initialization
  const [game, setGame] = useState<Chess | null>(null);
  const [fen, setFen] = useState("");

  // Store Chess constructor after dynamic import
  const ChessRef = useRef<typeof Chess | null>(null);

  // Initialize chess on client only (dynamic import to avoid SSR issues)
  useEffect(() => {
    import('chess.js').then(({ Chess }) => {
      ChessRef.current = Chess;
      setGame(new ChessRef.current!());
      setMounted(true);
    });
  }, []);
  const [selectedSquare, setSelectedSquare] = useState<string | null>(null);
  const [legalMoves, setLegalMoves] = useState<string[]>([]);

  // Puzzle solving state
  const [solutionMoves, setSolutionMoves] = useState<string[]>([]);
  const [currentSolutionIndex, setCurrentSolutionIndex] = useState(0);
  const [puzzleComplete, setPuzzleComplete] = useState(false);
  const [puzzleFailed, setPuzzleFailed] = useState(false);
  const [hintUsed, setHintUsed] = useState(false);
  const [showHint, setShowHint] = useState(false);
  const [puzzleLevel, setPuzzleLevel] =  useLocalStorage<number>(
    "puzzleLevel",
    1500
  );

  // Solution viewing state
  const [showingSolution, setShowingSolution] = useState(false);
  const [solutionViewIndex, setSolutionViewIndex] = useState(0);
  const [solutionGameState, setSolutionGameState] = useState<Chess | null>(
    null
  );

  // Helper function to convert PuzzleQuery to prompt string
  const createPuzzlePrompt = useCallback((query: PuzzleQuery): string => {
    const themesText =
      query.themes.length > 0
        ? `This puzzle focuses on: ${query.themes.join(", ")}. themes`
        : "";

    const solutionText =
      query.solution.length > 0
        ? `The solution is: ${query.solution.join(" ")}.`
        : "";

    // Determine side to move from the FEN if available in puzzleData
    let sideToMove = "";
    if (puzzleData && puzzleData.FEN) {
      const fenParts = puzzleData.FEN.split(" ");
      if (fenParts.length > 1) {
        sideToMove =
          fenParts[1] === "w"
            ? "White to move."
            : fenParts[1] === "b"
            ? "Black to move."
            : "";
      }
    }

    return `Current chess puzzle context: ${themesText} ${sideToMove} ${solutionText}`.trim();
  }, [puzzleData]);

  // Helper function to convert algebraic notation moves to SAN format
  const convertMovesToSAN = useCallback(
    (moves: string[], startingFEN: string): string[] => {
      const tempGame = new ChessRef.current!(startingFEN);
      const sanMoves: string[] = [];

      moves.forEach((move) => {
        try {
          const moveObj = tempGame.move({
            from: move.substring(0, 2),
            to: move.substring(2, 4),
            promotion: move.substring(4) || undefined,
          });

          if (moveObj) {
            sanMoves.push(moveObj.san);
          }
        } catch (error) {
          console.error("Error converting move to SAN:", move, error);
        }
      });

      return sanMoves;
    },
    []
  );

  const fetchPuzzle = useCallback(
  async (themes: string[] = [], ratingFrom?: number, ratingTo?: number) => {
    setLoading(true);
    setError(null);
    try {
      // Use your Next.js API endpoint instead
      let url = "/api/puzzle";
      const params = new URLSearchParams();
      
      // Add themes parameter if provided
      if (themes.length > 0) {
        params.append("themes", themes.join(","));
      }
      
      // Add rating parameters if provided
      if (ratingFrom !== undefined && ratingTo !== undefined) {
        params.append("ratingFrom", ratingFrom.toString());
        params.append("ratingTo", ratingTo.toString());
      }
      
      // Append parameters to URL if any exist
      if (params.toString()) {
        url += `?${params.toString()}`;
      }
      
      const result = await apiFetch<any>(url);
      
      if (!result.success) {
        throw new Error(result.error || "Failed to fetch puzzle");
      }

      const data: PuzzleData = result.data;

      if (!data || !data.FEN) {
        throw new Error("Invalid puzzle data received");
      }

      setPuzzleData(data);

      // Set up game
      const newGame = new ChessRef.current!(data.FEN);
      setGame(newGame);
      setFen(data.FEN);
      
      // Parse solution moves
      const moves = data.moves.split(" ");
      setSolutionMoves(moves);
      setCurrentSolutionIndex(0);
      
      // Convert moves to SAN format for puzzle query
      const sanMoves = convertMovesToSAN(moves, data.FEN);
      
      // Create puzzle query object
      const newPuzzleQuery: PuzzleQuery = {
        themes: data.themes,
        solution: sanMoves,
      };
      setPuzzleQuery(newPuzzleQuery);
      
      // Create puzzle query string for ChatTab
      const queryString = createPuzzlePrompt(newPuzzleQuery);
      setPuzzleQueryString(queryString);
      
      // Reset puzzle state
      setPuzzleComplete(false);
      setPuzzleFailed(false);
      setHintUsed(false);
      setShowHint(false);
      setShowingSolution(false);
      setSolutionViewIndex(0);
      setSolutionGameState(null);
      setMoveSquares({});
      setSelectedSquare(null);
      setLegalMoves([]);
      
    } catch (err) {
      console.error("Error fetching puzzle:", err);
      if (err instanceof ApiError) {
        if (err.status === 429) {
          setRateLimited(true);
          showToast('Too many requests — please slow down', 'error');
        } else if (err.status === 408) {
          showToast('Request timed out — try again', 'error');
        } else if (err.status === 0) {
          showToast('Network error — check your connection', 'error');
        }
      }
      setError("Failed to load puzzle. Please try again.");
    } finally {
      setLoading(false);
    }
  },
  [convertMovesToSAN, createPuzzlePrompt, showToast]
);
  // Initialize with first puzzle
  useEffect(() => {
    fetchPuzzle([], puzzleLevel, puzzleLevel + 500); // Use puzzleLevel as base with 500 point range
  }, []);

  const {
    setLlmAnalysisResult,
    stockfishAnalysisResult,
    setStockfishAnalysisResult,
    setOpeningData,
    llmLoading,
    stockfishLoading,
    openingLoading,
    moveSquares,
    setMoveSquares,
    analysisTab,
    setAnalysisTab,
    chatMessages,
    chatInput,
    setChatInput,
    chatLoading,
    isStreaming,
    sessionMode,
    setSessionMode,
    engineDepth,
    setEngineDepth,
    engineLines,
    setEngineLines,
    engine,
    fetchOpeningData,
    sendChatMessage,
    handleChatKeyPress,
    clearChatHistory,
    analyzeWithStockfish,
    formatEvaluation,
    abortChatMessage,
    formatPrincipalVariation,
    handleEngineLineClick,
  } = useChesster(fen);

  
  const handleQuickThemeChange = useCallback(
    (event: SelectChangeEvent<string>) => {
      const theme = event.target.value;
      setQuickTheme(theme);
    },
    []
  );

  // Show solution
  const showSolution = useCallback(() => {
    if (!puzzleData) return;

    setShowingSolution(true);
    setSolutionViewIndex(0);

    // Create a game state from the starting position
    const solutionGame = new ChessRef.current!(puzzleData.FEN);
    setSolutionGameState(solutionGame);
    setGame(solutionGame);
    setFen(solutionGame.fen());

    // Clear any existing move highlights
    setMoveSquares({});
  }, [puzzleData]);

  // Navigate through solution
  const navigateSolution = useCallback(
    (direction: "prev" | "next") => {
      if (!puzzleData || !solutionGameState) return;

      if (direction === "next" && solutionViewIndex < solutionMoves.length) {
        const move = solutionMoves[solutionViewIndex];
        const newGame = new ChessRef.current!(solutionGameState.fen());

        try {
          const moveObj = newGame.move({
            from: move.substring(0, 2),
            to: move.substring(2, 4),
            promotion: move.substring(4) || undefined,
          });

          if (moveObj) {
            setSolutionGameState(newGame);
            setGame(newGame);
            setFen(newGame.fen());
            setSolutionViewIndex(solutionViewIndex + 1);

            // Highlight the move
            setMoveSquares({
              [moveObj.from]: "rgba(155, 199, 0, 0.41)",
              [moveObj.to]: "rgba(155, 199, 0, 0.41)",
            });
          }
        } catch (error) {
          console.error("Solution navigation error:", error);
        }
      } else if (direction === "prev" && solutionViewIndex > 0) {
        // Rebuild game state up to previous move
        const newGame = new ChessRef.current!(puzzleData.FEN);
        const targetIndex = solutionViewIndex - 1;

        for (let i = 0; i < targetIndex; i++) {
          const move = solutionMoves[i];
          try {
            newGame.move({
              from: move.substring(0, 2),
              to: move.substring(2, 4),
              promotion: move.substring(4) || undefined,
            });
          } catch (error) {
            console.error("Solution rebuild error:", error);
            break;
          }
        }

        setSolutionGameState(newGame);
        setGame(newGame);
        setFen(newGame.fen());
        setSolutionViewIndex(targetIndex);

        // Highlight the last move if there was one
        if (targetIndex > 0) {
          const lastMove = solutionMoves[targetIndex - 1];
          setMoveSquares({
            [lastMove.substring(0, 2)]: "rgba(155, 199, 0, 0.41)",
            [lastMove.substring(2, 4)]: "rgba(155, 199, 0, 0.41)",
          });
        } else {
          setMoveSquares({});
        }
      }
    },
    [puzzleData, solutionGameState, solutionViewIndex, solutionMoves]
  );

  // Handle piece drop
  const onDrop = useCallback(
    (source: string, target: string) => {
      if (puzzleComplete || puzzleFailed || showingSolution) return false;

      try {
        const gameCopy = new ChessRef.current!(fen);
        const move = gameCopy.move({
          from: source,
          to: target,
          promotion: "q",
        });

        if (!move) return false;

        const moveNotation = move.from + move.to + (move.promotion || "");
        const expectedMove = solutionMoves[currentSolutionIndex];

        if (moveNotation === expectedMove) {
          // Correct move
          playSound(move.captured ? 'capture' : 'move');
          setGame(gameCopy);
          setFen(gameCopy.fen());
          setMoveSquares({
            [source]: "rgba(155, 199, 0, 0.41)",
            [target]: "rgba(155, 199, 0, 0.41)",
          });

          if (currentSolutionIndex === solutionMoves.length - 1) {
            // Puzzle complete!
            setTimeout(() => playSound('success'), 300);
            setPuzzleComplete(true);
          } else {
            // Make opponent's move
            setTimeout(() => {
              const nextMove = solutionMoves[currentSolutionIndex + 1];
              if (nextMove) {
                const opponentMove = gameCopy.move({
                  from: nextMove.substring(0, 2),
                  to: nextMove.substring(2, 4),
                  promotion: nextMove.substring(4) || undefined,
                });

                if (opponentMove) {
                  setGame(new ChessRef.current!(gameCopy.fen()));
                  setFen(gameCopy.fen());
                  setCurrentSolutionIndex(currentSolutionIndex + 2);
                }
              }
            }, 500);
          }
        } else {
          // Wrong move
          playSound('error');
          setPuzzleFailed(true);
          setMoveSquares({
            [source]: "rgba(255, 0, 0, 0.41)",
            [target]: "rgba(255, 0, 0, 0.41)",
          });
        }

        return true;
      } catch (error) {
        console.error("Move error:", error);
        return false;
      }
    },
    [
      fen,
      solutionMoves,
      currentSolutionIndex,
      puzzleComplete,
      puzzleFailed,
      showingSolution,
      playSound,
    ]
  );

  // Handle square click
  const handleSquareClick = useCallback(
    (square: string) => {
      if (puzzleComplete || puzzleFailed || showingSolution || !game) return;

      if (selectedSquare === square) {
        setSelectedSquare(null);
        setLegalMoves([]);
        return;
      }

      if (selectedSquare && legalMoves.includes(square)) {
        onDrop(selectedSquare, square);
        setSelectedSquare(null);
        setLegalMoves([]);
        return;
      }

      const piece = game.get(square as Square);
      if (!piece || piece.color !== game.turn()) {
        setSelectedSquare(null);
        setLegalMoves([]);
        return;
      }

      const moves = game.moves({ square: square as Square, verbose: true });
      const targetSquares = moves.map((move) => move.to);

      setSelectedSquare(square);
      setLegalMoves(targetSquares);
    },
    [
      selectedSquare,
      legalMoves,
      game,
      onDrop,
      puzzleComplete,
      puzzleFailed,
      showingSolution,
    ]
  );

  // Custom square styles - Fixed to avoid background/backgroundColor conflict
  const customSquareStyles = useMemo(() => {
    const styles: { [square: string]: React.CSSProperties } = {};

    // Apply move highlights first
    Object.entries(moveSquares).forEach(([square, color]) => {
      styles[square] = { backgroundColor: color };
    });

    // Apply selected square highlight
    if (selectedSquare && !showingSolution) {
      styles[selectedSquare] = {
        backgroundColor: "rgba(255, 255, 0, 0.4)",
      };
    }

    // Apply legal move indicators
    if (!showingSolution && game) {
      legalMoves.forEach((square) => {
        const piece = game.get(square as Square);
        // Use backgroundImage instead of background to avoid conflict
        const backgroundImage = piece
          ? "radial-gradient(circle, rgba(255,0,0,0.8) 85%, transparent 85%)"
          : "radial-gradient(circle, rgba(0,0,0,0.3) 25%, transparent 25%)";

        styles[square] = {
          ...styles[square],
          backgroundImage,
        };
      });
    }

    return styles;
  }, [moveSquares, selectedSquare, legalMoves, game, showingSolution]);

  // Show hint
  const showHintMove = useCallback(() => {
    if (!solutionMoves[currentSolutionIndex] || showingSolution) return;

    const move = solutionMoves[currentSolutionIndex];
    const from = move.substring(0, 2);
    const to = move.substring(2, 4);

    setMoveSquares({
      [from]: "rgba(255, 215, 0, 0.6)",
      [to]: "rgba(255, 215, 0, 0.6)",
    });

    setHintUsed(true);
    setShowHint(true);

    setTimeout(() => {
      setMoveSquares({});
      setShowHint(false);
    }, 3000);
  }, [solutionMoves, currentSolutionIndex, showingSolution]);

  // Reset puzzle
  const resetPuzzle = useCallback(() => {
    if (!puzzleData) return;

    const newGame = new ChessRef.current!(puzzleData.FEN);
    setGame(newGame);
    setFen(puzzleData.FEN);
    setCurrentSolutionIndex(0);
    setPuzzleComplete(false);
    setPuzzleFailed(false);
    setHintUsed(false);
    setShowHint(false);
    setShowingSolution(false);
    setSolutionViewIndex(0);
    setSolutionGameState(null);
    setMoveSquares({});
    setSelectedSquare(null);
    setLegalMoves([]);
  }, [puzzleData]);

  // Exit solution view
  const exitSolutionView = useCallback(() => {
    if (!puzzleData) return;

    setShowingSolution(false);
    setSolutionViewIndex(0);
    setSolutionGameState(null);

    // Return to original puzzle state
    const newGame = new ChessRef.current!(puzzleData.FEN);
    setGame(newGame);
    setFen(puzzleData.FEN);
    setMoveSquares({});
  }, [puzzleData]);


   if (!session.isLoaded || !mounted || !game) {
      return <Loader />;
    }

    if (!session.isSignedIn) {
      return <Warning />;
    }
  

  return (
    <>
      <Box sx={{ p: { xs: 1, sm: 2, md: 3, lg: 4 }, backgroundColor: 'var(--surface-page)', minHeight: "100vh" }} >
        <Box sx={{ px: { xs: 1, sm: 2 }, mb: 1 }}><Breadcrumbs /></Box>
        <Stack direction={{ xs: "column", lg: "row" }} spacing={{ xs: 2, sm: 3, lg: 4 }} >
           <Box sx={{ flex: '0 0 auto', width: { xs: "100%", lg: "auto" }, display: "flex", justifyContent: "center" }}>
             <AiChessboardPanel
            game={game}
            fen={fen}
            moveSquares={moveSquares}
            setMoveSquares={setMoveSquares}
            engine={engine}
            puzzleMode={true}
            onDropPuzzle={onDrop}
            handleSquarePuzzleClick={handleSquareClick}
            setFen={setFen}
            setGame={setGame}
            setLlmAnalysisResult={setLlmAnalysisResult}
            setOpeningData={setOpeningData}
            setStockfishAnalysisResult={setStockfishAnalysisResult}
            fetchOpeningData={fetchOpeningData}
            analyzeWithStockfish={analyzeWithStockfish}
            puzzleCustomSquareStyle={customSquareStyles}
            llmLoading={llmLoading}
            side={
              puzzleData
                ? new ChessRef.current!(puzzleData.FEN).turn() === "w"
                  ? "white"
                  : "black"
                : "white"
            }
            stockfishLoading={stockfishLoading}
            stockfishAnalysisResult={stockfishAnalysisResult}
            openingLoading={openingLoading}
          />
           </Box>
         

          <Paper
            elevation={3}
            sx={{
              p: { xs: 1.5, sm: 2, md: 3 },
              flex: 1,
              minHeight: { xs: 200, sm: 300 },
              color: "var(--text-primary)",
              backgroundColor: 'var(--surface-card)',
              maxHeight: { xs: "none", lg: "100vh" },
              overflow: "auto",
              width: "100%",
              minWidth: 0,
            }}
          >
            <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
              <Tabs
                value={analysisTab}
                onChange={(_, newValue) => setAnalysisTab(newValue)}
                variant="scrollable"
                scrollButtons="auto"
                allowScrollButtonsMobile
                sx={{
                  "& .MuiTab-root": {
                    color: "var(--text-secondary)",
                    fontSize: { xs: "0.7rem", sm: "0.8rem", md: "0.875rem" },
                    minWidth: { xs: "auto", sm: 90 },
                    px: { xs: 1, sm: 2 },
                  },
                  "& .Mui-selected": { color: "var(--text-primary) !important" },
                }}
              >
                <Tab label={t('tabs.puzzleInfo')} />
                <Tab label={t('tabs.stockfishAnalysis')} />
                <Tab label={t('tabs.aiChat')} />
              </Tabs>
            </Box>
            <TabPanel value={analysisTab} index={0}>
              <Stack spacing={3} sx={{ px: 2, py: 3 }}>
              {/* Show loading animation if loading */}
              {loading ? (
                <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 200 }}>
                <CircularProgress color="info" />
                </Box>
              ) : (
                <>
                {/* Theme Selection Card */}
                <Card sx={{ backgroundColor: 'var(--surface-raised)' }}>
                  <CardContent>
                  <Typography variant="h6" sx={{ mb: 2, color: "var(--text-secondary)" }}>
                    {t('themes.title')}
                  </Typography>
                  <Stack spacing={2}>
                    {/* Quick Theme Selection */}
                    <FormControl fullWidth>
                    <InputLabel sx={{ color: "var(--text-secondary)" }}>
                      {t('themes.quickSelect')}
                    </InputLabel>
                    <Select
                      value={quickTheme}
                      onChange={handleQuickThemeChange}
                      label={t('themes.quickSelect')}
                      sx={{
                      backgroundColor: 'var(--surface-card)',
                      color: "var(--text-secondary)",
                      ".MuiOutlinedInput-notchedOutline": {
                        borderColor: "var(--border-default)",
                      },
                      "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
                        borderColor: "var(--border-default)",
                      },
                      "&:hover .MuiOutlinedInput-notchedOutline": {
                        borderColor: "var(--border-default)",
                      },
                      ".MuiSvgIcon-root": {
                        color: "var(--text-secondary)",
                      },
                      }}
                    >
                      <MenuItem value="">
                      <em>{t('themes.randomPuzzle')}</em>
                      </MenuItem>
                      {DIFFICULTY_THEMES.map((theme) => (
                      <MenuItem key={theme.value} value={theme.value}>
                        {theme.label} ({theme.difficulty})
                      </MenuItem>
                      ))}
                    </Select>
                    </FormControl>

                    {/* Advanced Theme Selection Button */}
                    <Button
                    variant="outlined"
                    startIcon={<Filter />}
                    onClick={() => setThemeDialogOpen(true)}
                    fullWidth
                    color="info"
                    >
                    {t('themes.advancedSelection')}
                    </Button>

                    {/* Current Selected Themes */}
                    {selectedThemes.length > 0 && (
                    <Stack
                      direction="row"
                      spacing={1}
                      flexWrap="wrap"
                      useFlexGap
                    >
                      <Typography
                      variant="body2"
                      sx={{ color: "var(--text-secondary)", alignSelf: "center" }}
                      >
                      {t('themes.activeThemes')}:
                      </Typography>
                      {selectedThemes.map((theme) => (
                      <Chip
                        key={theme}
                        label={
                        PUZZLE_THEMES.find((t) => t.tag === theme)
                          ?.description || theme
                        }
                        size="small"
                        sx={{
                        color: "var(--text-secondary)",
                        borderColor: "var(--border-default)",
                        backgroundColor: 'var(--surface-raised)',
                        "& .MuiChip-label": { color: "var(--text-secondary)" },
                        }}
                        variant="outlined"
                      />
                      ))}
                    </Stack>
                    )}

                    {/* Current Puzzle Themes */}
                    {showingSolution &&
                    puzzleData?.themes &&
                    puzzleData.themes.length > 0 && (
                      <Stack
                      direction="row"
                      spacing={1}
                      flexWrap="wrap"
                      useFlexGap
                      >
                      <Typography
                        variant="body2"
                        sx={{ color: "var(--text-secondary)", alignSelf: "center" }}
                      >
                        {t('themes.thisPuzzle')}:
                      </Typography>
                      {puzzleData.themes.map((theme) => (
                        <Chip
                        key={theme}
                        label={
                          PUZZLE_THEMES.find((t) => t.tag === theme)
                          ?.description || theme
                        }
                        size="small"
                        sx={{
                          color: "var(--text-secondary)",
                          borderColor: "var(--border-default)",
                          backgroundColor: 'var(--surface-raised)',
                          "& .MuiChip-label": { color: "var(--text-secondary)" },
                        }}
                        variant="outlined"
                        />
                      ))}
                      </Stack>
                    )}
                  </Stack>
                  </CardContent>
                </Card>
                {/* Action Buttons Card */}
                <Card sx={{ backgroundColor: 'var(--surface-raised)' }}>
                  <CardContent>
                  {showingSolution ? (
                    <Stack spacing={2}>
                    <Typography
                      variant="h6"
                      sx={{ textAlign: "center", color: "var(--text-primary)" }}
                    >
                      {t('solution.title')} ({solutionViewIndex}/
                      {solutionMoves.length})
                    </Typography>
                    <Stack
                      direction={{ xs: "column", sm: "row" }}
                      spacing={2}
                      sx={{ width: "100%" }}
                    >
                      <Button
                      variant="outlined"
                      startIcon={<SkipBackIcon />}
                      onClick={() => navigateSolution("prev")}
                      disabled={solutionViewIndex === 0}
                      fullWidth
                      color="info"
                      >
                      {t('solution.previous')}
                      </Button>
                      <Button
                      variant="outlined"
                      startIcon={<SkipNextIcon />}
                      onClick={() => navigateSolution("next")}
                      disabled={solutionViewIndex >= solutionMoves.length}
                      fullWidth
                      color="info"
                      >
                      {t('solution.next')}
                      </Button>
                      <Button
                      variant="contained"
                      onClick={exitSolutionView}
                      fullWidth
                      color="warning"
                      >
                      {t('solution.exit')}
                      </Button>
                    </Stack>
                    </Stack>
                  ) : (
                    <Stack
                    direction={{ xs: "column", sm: "row" }}
                    spacing={2}
                    sx={{ width: "100%" }}
                    >
                    <Button
                      variant="outlined"
                      startIcon={<Lightbulb />}
                      onClick={showHintMove}
                      disabled={puzzleComplete || showHint}
                      fullWidth
                      color="info"
                    >
                      {t('actions.hint')}
                    </Button>
                    {puzzleFailed && (
                      <Button
                      variant="outlined"
                      startIcon={<Eye />}
                      onClick={showSolution}
                      fullWidth
                      color="secondary"
                      >
                      {t('actions.showSolution')}
                      </Button>
                    )}
                    <Button
                      variant="outlined"
                      startIcon={<Refresh />}
                      onClick={resetPuzzle}
                      disabled={!puzzleData}
                      fullWidth
                      color="warning"
                    >
                      {t('actions.reset')}
                    </Button>
                    <Button
                      variant="contained"
                      startIcon={<SkipNext />}
                      onClick={() =>
                      fetchPuzzle(
                        selectedThemes.length > 0 ? selectedThemes : [],
                        puzzleLevel,
                        puzzleLevel + 500
                      )
                      }
                      disabled={loading}
                      fullWidth
                      color="success"
                    >
                      {t('actions.nextPuzzle')}
                    </Button>
                    </Stack>
                  )}
                  </CardContent>
                </Card>

                {/* Rating & Themes Card */}
                <Card sx={{ backgroundColor: 'var(--surface-raised)' }}>
                  <CardContent>
                  <Stack spacing={2}>
                    <Stack
                    direction="row"
                    spacing={2}
                    justifyContent="center"
                    alignItems="center"
                    >
                    <Chip
                      icon={<Star />}
                      label={`${t('rating')}: ${puzzleData?.rating || "N/A"}`}
                      color="primary"
                      variant="outlined"
                      sx={{
                      fontSize: "1.2rem",
                      px: 2,
                      py: 1.5,
                      height: "auto",
                      }}
                    />
                    </Stack>
                  </Stack>
                  </CardContent>
                </Card>

                {/* Status Alerts Card */}
                {(puzzleComplete ||
                  puzzleFailed ||
                  showHint ||
                  error ||
                  showingSolution) && (
                  <Card sx={{ backgroundColor: 'var(--surface-card)' }}>
                  <CardContent>
                    <Stack spacing={2}>
                    {puzzleComplete && (
                      <Alert severity="success">
                      🎉 {t('status.complete')}{" "}
                      {hintUsed ? `(${t('status.hintUsed')})` : t('status.perfectSolve')}
                      </Alert>
                    )}
                    {puzzleFailed && !showingSolution && (
                      <Alert severity="error">
                      ❌ {t('status.wrongMove')}
                      </Alert>
                    )}
                    {showHint && (
                      <Alert severity="info">
                      💡 {t('status.hintShown')}
                      </Alert>
                    )}
                    {showingSolution && (
                      <Alert severity="info">
                      👁️ {t('status.viewingSolution')}
                      </Alert>
                    )}
                    {rateLimited && (
                      <RateLimitNotice onRetry={() => {
                        setRateLimited(false);
                        setError(null);
                        fetchPuzzle(
                          selectedThemes.length > 0 ? selectedThemes : [],
                          puzzleLevel,
                          puzzleLevel + 500
                        );
                      }} />
                    )}
                    {error && !rateLimited && <Alert severity="error">{t('status.notFound')}</Alert>}
                    </Stack>
                  </CardContent>
                  </Card>
                )}
                </>
              )}
              </Stack>
            </TabPanel>

            <TabPanel value={analysisTab} index={1}>
              <Typography variant="h6" gutterBottom>
                {t('stockfish.title')}
              </Typography>
              <StockfishAnalysisTab
                stockfishAnalysisResult={stockfishAnalysisResult}
                stockfishLoading={stockfishLoading}
                handleEngineLineClick={handleEngineLineClick}
                engineDepth={engineDepth}
                engineLines={engineLines}
                engine={engine}
                llmLoading={llmLoading}
                analyzeWithStockfish={analyzeWithStockfish}
                formatEvaluation={formatEvaluation}
                formatPrincipalVariation={formatPrincipalVariation}
                setEngineDepth={setEngineDepth}
                setEngineLines={setEngineLines}
              />
            </TabPanel>

            <TabPanel value={analysisTab} index={2}>
              <ChatTab
                chatMessages={chatMessages}
                chatInput={chatInput}
                setChatInput={setChatInput}
                abortChatMessage={abortChatMessage}
                sendChatMessage={sendChatMessage}
                chatLoading={chatLoading}
                isStreaming={isStreaming}
                puzzleMode={true}
                puzzleQuery={puzzleQueryString}
                handleChatKeyPress={handleChatKeyPress}
                clearChatHistory={clearChatHistory}
                sessionMode={sessionMode}
                setSessionMode={setSessionMode}
              />
            </TabPanel>
          </Paper>
        </Stack>
      </Box>

      {/* Advanced Theme Selection Dialog */}
      <Dialog
        open={themeDialogOpen}
        onClose={() => setThemeDialogOpen(false)}
        maxWidth="md"
        fullWidth
        PaperProps={{
          sx: {
            backgroundColor: 'var(--surface-card)',
            color: "var(--text-primary)",
          },
        }}
      >
        <DialogTitle>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Settings />
            <Typography variant="h6">{t('dialog.selectThemes')}</Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ mt: 2 }}>
            <Typography variant="body2" color="wheat">
              {t('dialog.selectThemesDesc')}
            </Typography>

            <Autocomplete
              multiple
              options={PUZZLE_THEMES}
              getOptionLabel={(option) => option.description}
              value={PUZZLE_THEMES.filter((theme) =>
                selectedThemes.includes(theme.tag)
              )}
              onChange={(_, newValue) => {
                setSelectedThemes(newValue.map((theme) => theme.tag));
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={t('dialog.selectThemesLabel')}
                  placeholder={t('dialog.searchPlaceholder')}
                />
              )}
              renderTags={(value, getTagProps) =>
                value.map((option, index) => (
                  <Chip
                    {...getTagProps({ index })}
                    key={option.tag}
                    label={option.description}
                    color="primary"
                    size="small"
                  />
                ))
              }
              renderOption={(props, option) => {
                const { key, ...otherProps } = props;
                return (
                  <Box component="li" key={key} {...otherProps}>
                    <Stack>
                      <Typography variant="body2">
                        {option.description}
                      </Typography>
                    </Stack>
                  </Box>
                );
              }}
              sx={{
                "& .MuiAutocomplete-popupIndicator": { color: "var(--text-secondary)" },
                "& .MuiAutocomplete-clearIndicator": { color: "var(--text-secondary)" },
              }}
            />

            {/* Popular Theme Quick Selects */}
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1, color: "var(--text-secondary)" }}>
                {t('dialog.popularThemes')}:
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {[
                  "mateIn2",
                  "fork",
                  "pin",
                  "skewer",
                  "sacrifice",
                  "backRankMate",
                  "discoveredAttack",
                ].map((theme) => {
                  const themeObj = PUZZLE_THEMES.find((t) => t.tag === theme);
                  if (!themeObj) return null;

                  const isSelected = selectedThemes.includes(theme);
                  return (
                    <Chip
                      key={theme}
                      label={themeObj.description}
                      color={isSelected ? "primary" : "warning"}
                      variant={isSelected ? "filled" : "outlined"}
                      onClick={() => {
                        if (isSelected) {
                          setSelectedThemes((prev) =>
                            prev.filter((t) => t !== theme)
                          );
                        } else {
                          setSelectedThemes((prev) => [...prev, theme]);
                        }
                      }}
                      sx={{ cursor: "pointer" }}
                    />
                  );
                })}
              </Stack>
            </Box>

            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1, color: "var(--text-secondary)" }}>
                {t('dialog.byDifficulty')}:
              </Typography>
              <Slider
                min={1200}
                max={3500}
                value={puzzleLevel}
                setValue={(val: number) => {
                  setPuzzleLevel(val);
                }}
              />
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setThemeDialogOpen(false)} color="inherit">
            {t('dialog.cancel')}
          </Button>
          <Button
            onClick={() => setSelectedThemes([])}
            color="warning"
            variant="outlined"
          >
            {t('dialog.clearAll')}
          </Button>
          <Button
            onClick={() => {
              fetchPuzzle(
                selectedThemes.length > 0 ? selectedThemes : [],
                puzzleLevel,
                puzzleLevel + 500
              );
              setThemeDialogOpen(false);
            }}
            color="primary"
            variant="contained"
          >
            {t('dialog.applyGetPuzzle')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
