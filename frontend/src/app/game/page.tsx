"use client";
import { useState, useEffect } from "react";
import {
  Box,
  Button,
  Stack,
  Typography,
  Divider,
  Card,
  CardContent,
  FormControlLabel,
  Switch,
  Tooltip,
} from "@mui/material";
import { Refresh as RefreshIcon, Save as SaveIcon, Speed as SpeedIcon } from "@mui/icons-material";
import { Chess } from "chess.js";
import useChesster from "@/hooks/useChesster";
import AiChessboardPanel from "@/components/analysis/AiChessboard";
// Clerk authentication disabled for local development
// import { useSession } from "@clerk/nextjs";
import UserGameSelect from "@/components/lichess/UserGameSelect";
import UserChessDotComGameSelect from "@/components/chessdotcom/UserChessDotComGameSelect";
import UserPGNUploader from "@/components/lichess/UserPGNUpload";
import GameDownloader from "@/components/gamedownloader/GameDownloader";
import PGNView from "@/components/tabs/PgnView";
import ResizableChapterSelector from "@/components/tabs/ChaptersTab";
import { extractMovesWithComments, extractGameInfo } from "@/libs/game/helper";
import { useGameTheme } from "@/hooks/useGameTheme";
import Loader from "@/components/loading/Loader";
import LoadingScreen from "@/components/LoadingScreen";
import Warning from "@/components/loading/SignUpWarning";
import SaveGameReviewDialog, {
  SavedGameReview,
} from "@/components/game/SaveGameReviewDialog";
import GamereviewHistory from "@/components/game/GameReviewHistory";
import LoadStudy, { Chapter } from "@/components/game/LoadStudy";
import LoadLichessGameUrl, {
  ParsedComment,
} from "@/components/game/LoadLichessGameUrl";
import LoadPGNGame from "@/components/game/LoadPGNGame";
import ChessterAnalysisView from "@/components/analysis/ChessterAnalysisView";
import ChatSidebar from "@/components/ChatSidebar";
import { useChatSessions } from "@/hooks/useChatSessions";

export default function PGNUploaderPage() {
  // const session = useSession();
  // Simulated session for no-auth mode
  const session = { isLoaded: true, isSignedIn: true };

  const [pgnText, setPgnText] = useState("");
  const [game, setGame] = useState(new Chess());
  const [fen, setFen] = useState(game.fen());
  const [moves, setMoves] = useState<string[]>([]);
  const [parsedMovesWithComments, setParsedMovesWithComments] = useState<
    ParsedComment[]
  >([]);
  const [currentMoveIndex, setCurrentMoveIndex] = useState(0);

  const [inputsVisible, setInputsVisible] = useState(true);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [comment, setComment] = useState("");
  const [gameInfo, setGameInfo] = useState<Record<string, string>>({});

  // Games database state
  const [allGames, setAllGames] = useState<GameMetadata[]>([]);
  const [fullPgnText, setFullPgnText] = useState("");
  const [autoAnalyzeEnabled, setAutoAnalyzeEnabled] = useState(false); // Performance optimization: disable auto-analysis by default

  // Game review history state
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [historyDialogOpen, setHistoryDialogOpen] = useState(false);

  // Chat sidebar state
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Chat session management
  const {
    sessions,
    currentSessionId,
    currentSession,
    createNewSession,
    addMessageToSession,
    switchToSession,
    deleteSession,
    renameSession,
    updateSessionFen,
    updateSessionPgn,
  } = useChatSessions();

  const {
    setLlmAnalysisResult,
    stockfishAnalysisResult,
    setStockfishAnalysisResult,
    openingData,
    setOpeningData,
    llmLoading,
    stockfishLoading,
    lichessOpeningData,
    lichessOpeningLoading,
    openingLoading,
    moveSquares,
    chatMessages,
    chatInput,
    setChatInput,
    chatLoading,
    sessionMode,
    setSessionMode,
    engineDepth,
    setEngineDepth,
    engineLines,
    setEngineLines,
    engine,
    gameReview,
    gameReviewProgress,
    setGameReview,
    generateGameReview,
    gameReviewLoading,
    fetchOpeningData,
    sendChatMessage,
    handleMoveAnnontateClick,
    handleChatKeyPress,
    setMoveSquares,
    clearChatHistory,
    analyzeWithStockfish,
    formatEvaluation,
    formatPrincipalVariation,
    handleEngineLineClick,
    handleOpeningMoveClick,
    handleMoveClick,
    abortChatMessage,
    handleMoveCoachClick,
    handleGameReviewSummaryClick,
    handleMovePGNAnnotateClick,
    chessdbdata,
    loading,
    queueing,
    error,
    refetch,
    requestAnalysis,
    legalMoves,
    handleFutureMoveLegalClick,
  } = useChesster(fen);

  const { gameReviewTheme, analyzeGameTheme } = useGameTheme();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft" && currentMoveIndex > 0) {
        goToMove(currentMoveIndex - 1);
      }
      if (e.key === "ArrowRight" && currentMoveIndex < moves.length) {
        goToMove(currentMoveIndex + 1);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [currentMoveIndex, moves]);

  // Game review history functions
  const saveGameReview = () => {
    if (!gameReview.length) {
      alert("No game review to save. Please generate a review first.");
      return;
    }
    setSaveDialogOpen(true);
  };

  const loadFromHistory = (savedGame: SavedGameReview) => {
    try {
      setPgnText(savedGame.pgn);
      setMoves(savedGame.moves);
      setGameInfo(savedGame.gameInfo);
      setGameReview(savedGame.gameReview);

      const parsed = extractMovesWithComments(savedGame.pgn);
      setParsedMovesWithComments(parsed);
      setCurrentMoveIndex(0);

      const resetGame = new Chess();
      setGame(resetGame);
      setFen(resetGame.fen());
      setLlmAnalysisResult(null);
      setComment("");

      setHistoryDialogOpen(false);
      setInputsVisible(false);
    } catch (err) {
      console.error("Error loading game from history:", err);
      alert("Error loading saved game");
    }
  };

  // Function to remove nested parenthetical variations
  const removeNestedVariations = (text: string): string => {
    let result = '';
    let depth = 0;

    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      if (char === '(') {
        depth++;
      } else if (char === ')') {
        depth--;
      } else if (depth === 0) {
        result += char;
      }
    }

    return result;
  };

  // Function to remove nested curly brace annotations (handles nested braces)
  const removeNestedBraces = (text: string): string => {
    let result = '';
    let depth = 0;

    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      if (char === '{') {
        depth++;
      } else if (char === '}') {
        depth--;
      } else if (depth === 0) {
        result += char;
      }
    }

    return result;
  };

  // Function to clean PGN by removing advanced annotations
  const cleanPGN = (pgnText: string) => {
    let cleaned = pgnText;

    // Remove all content within curly braces (annotations like {[%clk 1:00:00]}, {[%csl Gf4][%cal Gc1f4]})
    // Use character-by-character parsing to handle nested braces properly
    cleaned = removeNestedBraces(cleaned);

    // Remove parenthetical variations (nested moves in parentheses)
    // Use character-by-character parsing to handle nested parentheses like (1. c4 e5 (1... d5))
    cleaned = removeNestedVariations(cleaned);

    // Remove NAG (Numeric Annotation Glyphs) like $1, $2, etc.
    cleaned = cleaned.replace(/\$\d+/g, "");

    // Fix Chess.com format: "1. e4 {[%clk]} 1... e5" -> "1. e4 e5"
    // Remove redundant move numbers for black (e.g., "1... e5" -> "e5")
    cleaned = cleaned.replace(/(\d+)\.\.\./g, "");

    // Remove any trailing whitespace from lines
    const lines = cleaned.split("\n").map((line: string) => line.trim());

    // Separate headers from moves properly
    const headers: string[] = [];
    const moveLines: string[] = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      if (line.startsWith("[") && line.endsWith("]")) {
        // This is a header line
        headers.push(line);
      } else if (line.trim() === "") {
        // Empty line - skip
        continue;
      } else if (line.match(/^\d+\./)) {
        // This is a move line (starts with move number like "1.")
        moveLines.push(line);
      } else if (moveLines.length > 0 && !line.startsWith("[")) {
        // Continuation of moves on new line
        moveLines.push(line);
      }
    }

    // Join all move lines into one continuous string
    const movesText = moveLines.join(" ");

    // Clean up extra spaces and formatting
    const cleanedMoves = movesText
      .replace(/\s+/g, " ") // Multiple spaces to single space
      .replace(/\s*\.\s*/g, ". ") // Clean spaces around periods
      .replace(/\s+([01][-\/]?[01]|1-0|0-1|1\/2-1\/2|\*)/g, " $1") // Clean spaces before result
      .trim();

    // Reconstruct PGN with proper spacing
    // Headers, then blank line, then moves
    const result = headers.length > 0
      ? [...headers, "", cleanedMoves].join("\n")
      : cleanedMoves;

    return result.trim();
  };

  const loadPGN = (pgnInput?: string) => {
    try {
      const pgn = pgnInput ?? pgnText;
      if (!pgn.trim()) {
        alert("Please enter or paste PGN content");
        return;
      }

      // Extract only first game if multi-game file
      const firstGame = extractFirstGame(pgn);

      // Extract FEN from PGN headers if present (for puzzles/studies with custom positions)
      const fenMatch = firstGame.match(/\[FEN\s+"([^"]+)"\]/);
      const startingFen = fenMatch ? fenMatch[1] : undefined;

      // Create game from the correct starting position
      const tempGame = startingFen ? new Chess(startingFen) : new Chess();
      const cleanedPGN = cleanPGN(firstGame);

      // For PGN with custom FEN, we need to load moves differently
      // chess.js loadPgn should handle FEN headers, but let's be explicit
      if (startingFen) {
        // Extract just the moves part (after headers)
        // Using [\s\S] instead of /s flag for ES2015 compatibility
        const movesMatch = cleanedPGN.match(/\n\n([\s\S]+)$/) || cleanedPGN.match(/\]\s*\n([\s\S]+)$/);
        if (movesMatch) {
          const movesText = movesMatch[1].trim();
          // Parse moves manually from the moves text
          const moveTokens = movesText
            .replace(/\d+\.\s*/g, ' ') // Remove move numbers like "1."
            .replace(/\s+/g, ' ')
            .trim()
            .split(' ')
            .filter(token => token && !token.match(/^(\*|1-0|0-1|1\/2-1\/2)$/));

          for (const move of moveTokens) {
            try {
              tempGame.move(move);
            } catch (moveErr) {
              console.warn(`Skipping invalid move: ${move}`, moveErr);
              break;
            }
          }
        }
      } else {
        tempGame.loadPgn(cleanedPGN);
      }

      const moveList = tempGame.history();
      const parsed = extractMovesWithComments(firstGame);
      const info = extractGameInfo(firstGame);

      // Add FEN to game info if present
      if (startingFen) {
        info.FEN = startingFen;
      }

      setMoves(moveList);
      setParsedMovesWithComments(parsed);
      setGameInfo(info);
      setCurrentMoveIndex(0);
      setPgnText(pgn); // Update pgnText state with the loaded PGN

      // Reset to the starting position (either custom FEN or standard)
      const resetGame = startingFen ? new Chess(startingFen) : new Chess();
      setGame(resetGame);
      setFen(resetGame.fen());
      setLlmAnalysisResult(null);
      setComment("");
      setGameReview([]);
      generateGameReview(moveList);
      analyzeGameTheme(cleanedPGN);

      // Notify user if multiple games detected
      const gameMatches = pgn.match(/\[Event /g);
      if (gameMatches && gameMatches.length > 1) {
        setTimeout(() => {
          alert(`Note: Found ${gameMatches.length} games. Loaded first game only.\n\nTo analyze other games, please paste them individually.`);
        }, 500);
      }
    } catch (err) {
      console.error("PGN parsing error:", err);
      alert(`Invalid PGN input: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  // Game metadata interface
  interface GameMetadata {
    index: number;
    year: string;
    white: string;
    whiteElo: string;
    black: string;
    blackElo: string;
    result: string;
    eco: string;
    date: string;
    time: string;
    pgn: string;
  }

  // Extract first game from multi-game PGN file
  const extractFirstGame = (pgnText: string): string => {
    const lines = pgnText.split("\n");
    let firstGameLines: string[] = [];
    let inFirstGame = false;
    let gameCount = 0;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();

      // Detect start of a new game (starts with [Event header)
      if (line.startsWith("[Event ")) {
        gameCount++;
        if (gameCount === 1) {
          inFirstGame = true;
          firstGameLines.push(line);
        } else if (gameCount === 2) {
          // We've hit the second game, stop here
          break;
        }
      } else if (inFirstGame) {
        firstGameLines.push(line);
        // Check if game ended (result found after moves)
        if (line.match(/\s*(1-0|0-1|1\/2-1\/2|\*)\s*$/)) {
          // Game ended, stop reading
          break;
        }
      }
    }

    return firstGameLines.join("\n");
  };

  // Parse all games from multi-game PGN file
  const parseAllGames = (pgnText: string): GameMetadata[] => {
    const games: GameMetadata[] = [];
    const lines = pgnText.split("\n");
    let currentGame: string[] = [];
    let gameIndex = 0;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();

      // Start of a new game
      if (line.startsWith("[Event ")) {
        // Save previous game if exists
        if (currentGame.length > 0) {
          const gamePgn = currentGame.join("\n");
          const metadata = extractGameMetadata(gamePgn, gameIndex);
          games.push(metadata);
          gameIndex++;
        }
        currentGame = [line];
      } else if (currentGame.length > 0) {
        currentGame.push(line);
      }
    }

    // Save last game
    if (currentGame.length > 0) {
      const gamePgn = currentGame.join("\n");
      const metadata = extractGameMetadata(gamePgn, gameIndex);
      games.push(metadata);
    }

    return games;
  };

  // Extract metadata from single game PGN
  const extractGameMetadata = (pgn: string, index: number): GameMetadata => {
    const headers: Record<string, string> = {};
    const lines = pgn.split("\n");

    for (const line of lines) {
      const match = line.match(/\[(\w+)\s+"([^"]+)"\]/);
      if (match) {
        headers[match[1]] = match[2];
      }
    }

    // Extract year from date
    const date = headers.UTCDate || headers.Date || "";
    const year = date.split(".")[0] || "";
    const time = headers.UTCTime || "00:00:00"; // Default time if not present

    return {
      index,
      year,
      white: headers.White || "Unknown",
      whiteElo: headers.WhiteElo || "?",
      black: headers.Black || "Unknown",
      blackElo: headers.BlackElo || "?",
      result: headers.Result || "*",
      eco: headers.ECO || "",
      date,
      time,
      pgn,
    };
  };

  const loadUserPGN = (pgn: string) => {
    try {
      // Parse all games from the file
      const games = parseAllGames(pgn);
      setAllGames(games);
      setFullPgnText(pgn);

      // Load first game
      const firstGame = extractFirstGame(pgn);

      const tempGame = new Chess();
      const cleanedPGN = cleanPGN(firstGame);
      tempGame.loadPgn(cleanedPGN);
      const moveList = tempGame.history();
      const parsed = extractMovesWithComments(firstGame);
      const info = extractGameInfo(firstGame);

      setMoves(moveList);
      setParsedMovesWithComments(parsed);
      setGameInfo(info);
      setCurrentMoveIndex(0);
      setPgnText(firstGame);

      const resetGame = new Chess();
      setGame(resetGame);
      setFen(resetGame.fen());
      setLlmAnalysisResult(null);
      setComment("");
      setGameReview([]);
      generateGameReview(moveList);
      analyzeGameTheme(cleanedPGN);
      setInputsVisible(false);

      // Notify user if multiple games detected
      if (games.length > 1) {
        setTimeout(() => {
          alert(`Note: Found ${games.length} games in file. Loaded first game.\n\nUse the "Games Database" tab to browse and select other games.`);
        }, 500);
      }
    } catch (err) {
      console.error("PGN parsing error:", err);
      alert(`Invalid PGN input: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  // Function to load a selected game from the database
  const handleGameSelect = (selectedGame: GameMetadata) => {
    try {
      const tempGame = new Chess();
      const cleanedPGN = cleanPGN(selectedGame.pgn);
      tempGame.loadPgn(cleanedPGN);
      const moveList = tempGame.history();
      const parsed = extractMovesWithComments(selectedGame.pgn);
      const info = extractGameInfo(selectedGame.pgn);

      setMoves(moveList);
      setParsedMovesWithComments(parsed);
      setGameInfo(info);
      setCurrentMoveIndex(0);
      setPgnText(selectedGame.pgn);

      const resetGame = new Chess();
      setGame(resetGame);
      setFen(resetGame.fen());
      setLlmAnalysisResult(null);
      setComment("");
      setGameReview([]);

      // PERFORMANCE OPTIMIZATION: Only auto-analyze if enabled
      if (autoAnalyzeEnabled) {
        generateGameReview(moveList);
        analyzeGameTheme(cleanedPGN);
      }
    } catch (err) {
      console.error("Error loading game:", err);
      alert(`Error loading game: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  const goToMove = (index: number) => {
    // Use custom starting FEN if available (for puzzles/studies)
    const startingFen = gameInfo.FEN;
    const tempGame = startingFen ? new Chess(startingFen) : new Chess();
    for (let i = 0; i < index; i++) {
      try {
        tempGame.move(moves[i]);
      } catch (err) {
        console.warn(`Error playing move ${moves[i]}:`, err);
        break;
      }
    }
    setGame(tempGame);
    setFen(tempGame.fen());
    setCurrentMoveIndex(index);
    setComment(parsedMovesWithComments[index - 1]?.comment || "");
    setLlmAnalysisResult(null);
    setStockfishAnalysisResult(null);
  };

  // Chat session handlers
  const handleNewChat = () => {
    // Reset to starting position
    const startingFen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    const resetGame = new Chess();
    setGame(resetGame);
    setFen(startingFen);
    setMoves([]);
    setPgnText("");
    setCurrentMoveIndex(0);
    setComment("");
    setLlmAnalysisResult(null);
    setGameReview([]);

    // Create new session with starting position
    createNewSession(startingFen);
  };

  const handleSelectSession = (sessionId: string) => {
    switchToSession(sessionId);
    // Session FEN will be loaded via useEffect
  };

  // Sync board FEN with current session
  useEffect(() => {
    if (currentSession && currentSession.currentFen && currentSession.currentFen !== fen) {
      try {
        const sessionGame = new Chess();

        // If PGN exists, load it to preserve move history
        if (currentSession.currentPgn) {
          try {
            sessionGame.loadPgn(currentSession.currentPgn);
          } catch (pgnError) {
            console.warn('Failed to load PGN, falling back to FEN only:', pgnError);
            sessionGame.load(currentSession.currentFen);
          }
        } else {
          sessionGame.load(currentSession.currentFen);
        }

        setGame(sessionGame);
        setFen(sessionGame.fen());
        setMoves(sessionGame.history());
      } catch (error) {
        console.error('Invalid FEN in session, using default:', error);
        const defaultGame = new Chess();
        setGame(defaultGame);
        setFen(defaultGame.fen());
        updateSessionFen(defaultGame.fen());
      }
    }
  }, [currentSessionId, currentSession]);

  // Update session FEN when board changes
  useEffect(() => {
    if (currentSessionId && fen) {
      const timeoutId = setTimeout(() => {
        updateSessionFen(fen);
        updateSessionPgn(game.pgn());
      }, 300);

      return () => clearTimeout(timeoutId);
    }
  }, [fen, currentSessionId, updateSessionFen, updateSessionPgn, game]);

  if (!session.isLoaded) {
    return <LoadingScreen isVisible={true} />;
  }

  if (!session.isSignedIn) {
    return <Warning />;
  }

  return (
    <Box
      sx={{
        display: "flex",
        backgroundColor: 'var(--surface-page)',
        minHeight: "100vh",
        position: "relative",
      }}
    >
      {/* Chat Sidebar */}
      {!inputsVisible && (
        <Box
          sx={{
            flexShrink: 0,
            transition: "all 0.3s ease",
          }}
        >
          <ChatSidebar
            sessions={sessions}
            currentSessionId={currentSessionId}
            onNewChat={handleNewChat}
            onSelectSession={handleSelectSession}
            onDeleteSession={deleteSession}
            onRenameSession={renameSession}
            onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
            isCollapsed={isSidebarCollapsed}
            currentBoardFen={fen}
          />
        </Box>
      )}

      {/* Main Content Area */}
      <Box
        sx={{
          flex: 1,
          p: { xs: 1, sm: 2, md: 3, lg: 4 },
          minWidth: 0,
          overflow: "hidden",
        }}
      >
        {inputsVisible && (
        <Card
          sx={{
            mb: { xs: 2, sm: 3, md: 4 },
            backgroundColor: 'var(--surface-card)',
            borderRadius: { xs: 2, md: 3 },
            boxShadow: 'var(--shadow-lg)',
          }}
        >
          <CardContent sx={{ p: { xs: 2, sm: 3, md: 4 } }}>
            <Box sx={{ textAlign: "center", mb: { xs: 2, sm: 3, md: 4 } }}>
              <Typography
                variant="h3"
                gutterBottom
                sx={{
                  color: 'var(--text-primary)',
                  fontWeight: 700,
                  fontSize: { xs: "1.5rem", sm: "2rem", md: "2.5rem", lg: "3rem" },
                  background: 'linear-gradient(45deg, #8B5CF6, #A78BFA)',
                  backgroundClip: "text",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                }}
              >
                Chess Analysis with Chesster
              </Typography>
              <Typography
                variant="h6"
                sx={{
                  color: 'var(--text-secondary)',
                  mb: { xs: 2, sm: 3 },
                  maxWidth: 600,
                  mx: "auto",
                  fontSize: { xs: "0.875rem", sm: "1rem", md: "1.125rem" },
                  px: { xs: 1, sm: 0 },
                }}
              >
                Get detailed AI insights on your games! Paste your PGN, Lichess
                game URL, or study URL to begin analysis.
              </Typography>
            </Box>

            <Stack spacing={3}>
              <GamereviewHistory setHistoryDialogOpen={setHistoryDialogOpen} />

              <LoadStudy
                setChapters={setChapters}
                setInputsVisible={setInputsVisible}
              />

              <Divider sx={{ borderColor: 'var(--border-default)' }} />

              <LoadLichessGameUrl
                setComment={setComment}
                setCurrentMoveIndex={setCurrentMoveIndex}
                setFen={setFen}
                setGame={setGame}
                setGameInfo={setGameInfo}
                setGameReview={setGameReview}
                setInputsVisible={setInputsVisible}
                setMoves={setMoves}
                setParsedMovesWithComments={setParsedMovesWithComments}
                setPgnText={setPgnText}
                setLlmAnalysisResult={setLlmAnalysisResult}
                generateGameReview={generateGameReview}
                analyzeGameTheme={analyzeGameTheme}
              />

              <Divider sx={{ borderColor: 'var(--border-default)' }} />

              <LoadPGNGame
                pgnText={pgnText}
                setPgnText={setPgnText}
                loadPGN={loadPGN}
                setInputsVisible={setInputsVisible}
              />

              <Divider sx={{ borderColor: 'var(--border-default)' }} />

              <Box>
                <Typography
                  variant="h6"
                  sx={{ color: 'var(--accent-purple-text)', mb: 2 }}
                >
                  Your Lichess Games
                </Typography>
                <UserGameSelect loadPGN={loadUserPGN} />
                <Box sx={{ mt: 2 }}>
                  <UserPGNUploader loadPGN={loadUserPGN} />
                </Box>
              </Box>

              <Divider sx={{ borderColor: 'var(--border-default)' }} />

              <Box>
                <Typography
                  variant="h6"
                  sx={{ color: 'var(--accent-purple-text)', mb: 2 }}
                >
                  Your Chess.com Games
                </Typography>
                <UserChessDotComGameSelect loadPGN={loadUserPGN} />
              </Box>

              <Divider sx={{ borderColor: 'var(--border-default)' }} />

              <Box>
                <Typography
                  variant="h6"
                  sx={{ color: 'var(--accent-purple-text)', mb: 2 }}
                >
                  Download Games Database
                </Typography>
                <GameDownloader
                  onGamesLoaded={(pgn) => {
                    loadUserPGN(pgn);
                    setInputsVisible(false);
                  }}
                />
              </Box>
            </Stack>
          </CardContent>
        </Card>
      )}

      <Stack direction={{ xs: "column", lg: "row" }} spacing={{ xs: 2, sm: 3, lg: 4 }}>
        {!inputsVisible && (
          <Box sx={{ flex: "0 0 auto", width: { xs: "100%", lg: "auto" }, display: "flex", justifyContent: "center" }}>
            <Stack spacing={3} alignItems="center">
              <AiChessboardPanel
                game={game}
                fen={fen}
                moveSquares={moveSquares}
                engine={engine}
                setMoveSquares={setMoveSquares}
                setFen={setFen}
                gameInfo={gameInfo}
                setGame={setGame}
                reviewMove={gameReview[currentMoveIndex]}
                gameReviewMode={true}
                setLlmAnalysisResult={setLlmAnalysisResult}
                setOpeningData={setOpeningData}
                setStockfishAnalysisResult={setStockfishAnalysisResult}
                stockfishAnalysisResult={stockfishAnalysisResult}
                fetchOpeningData={fetchOpeningData}
                analyzeWithStockfish={analyzeWithStockfish}
                llmLoading={llmLoading}
                stockfishLoading={stockfishLoading}
                openingLoading={openingLoading}
              />

              <PGNView
                moves={moves}
                moveAnalysis={gameReview}
                onAnnotateMove={handleMovePGNAnnotateClick}
                gamePgn={pgnText}
                goToMove={goToMove}
                gameResult={gameInfo.Result}
                currentMoveIndex={currentMoveIndex}
              />

              <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
                <Button
                  variant="contained"
                  onClick={saveGameReview}
                  startIcon={<SaveIcon />}
                  disabled={!gameReview.length}
                  sx={{
                    backgroundColor: 'primary.main',
                    "&:hover": {
                      backgroundColor: 'primary.dark',
                    },
                    "&:disabled": {
                      backgroundColor: 'action.disabled',
                      color: 'var(--text-secondary)',
                    },
                    borderRadius: 2,
                    px: 3,
                    py: 1.5,
                    textTransform: "none",
                  }}
                >
                  Save Game
                </Button>

                <Button
                  variant="outlined"
                  onClick={() => {
                    setInputsVisible(true);
                    setMoves([]);
                    setPgnText("");
                    setGameInfo({});
                    setLlmAnalysisResult(null);
                    setComment("");
                    const reset = new Chess();
                    setGame(reset);
                    setFen(reset.fen());
                  }}
                  startIcon={<RefreshIcon />}
                  sx={{
                    borderColor: 'var(--border-default)',
                    color: 'var(--text-primary)',
                    "&:hover": {
                      borderColor: 'primary.main',
                      backgroundColor: 'var(--accent-purple-bg)',
                    },
                    borderRadius: 2,
                    px: 3,
                    py: 1.5,
                    textTransform: "none",
                  }}
                >
                  Load New Game
                </Button>

                <Tooltip title="Enable auto-analysis when selecting games from the database. Disable for faster browsing (2-40s per game saved).">
                  <FormControlLabel
                    control={
                      <Switch
                        checked={autoAnalyzeEnabled}
                        onChange={(e) => setAutoAnalyzeEnabled(e.target.checked)}
                        sx={{
                          "& .MuiSwitch-switchBase.Mui-checked": {
                            color: 'primary.main',
                          },
                          "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track": {
                            backgroundColor: 'primary.main',
                          },
                        }}
                      />
                    }
                    label={
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                        <SpeedIcon sx={{ fontSize: 18, color: 'var(--text-secondary)' }} />
                        <Typography variant="body2" sx={{ color: 'var(--text-secondary)' }}>
                          Auto-Analyze
                        </Typography>
                      </Box>
                    }
                    sx={{ ml: 2 }}
                  />
                </Tooltip>
              </Stack>
            </Stack>
          </Box>
        )}

        {!inputsVisible && (
          <Box sx={{ flex: 1, minWidth: 0, width: "100%" }}>
            <Stack spacing={{ xs: 2, sm: 3 }}>
              {moves.length > 0 && (
                <ChessterAnalysisView
                  isGameReviewMode={true}
                  stockfishAnalysisResult={stockfishAnalysisResult}
                  stockfishLoading={stockfishLoading}
                  handleEngineLineClick={handleEngineLineClick}
                  engineDepth={engineDepth}
                  engineLines={engineLines}
                  engine={engine}
                  analyzeWithStockfish={analyzeWithStockfish}
                  formatEvaluation={formatEvaluation}
                  formatPrincipalVariation={formatPrincipalVariation}
                  setEngineDepth={setEngineDepth}
                  setEngineLines={setEngineLines}
                  openingLoading={openingLoading}
                  openingData={openingData}
                  lichessOpeningData={lichessOpeningData}
                  lichessOpeningLoading={lichessOpeningLoading}
                  handleOpeningMoveClick={handleOpeningMoveClick}
                  chessdbdata={chessdbdata}
                  handleMoveClick={handleMoveClick}
                  queueing={queueing}
                  error={error}
                  loading={loading}
                  refetch={refetch}
                  requestAnalysis={requestAnalysis}
                  legalMoves={legalMoves}
                  handleFutureMoveLegalClick={handleFutureMoveLegalClick}
                  chatMessages={chatMessages}
                  chatInput={chatInput}
                  setChatInput={setChatInput}
                  sendChatMessage={sendChatMessage}
                  chatLoading={chatLoading}
                  abortChatMessage={abortChatMessage}
                  handleChatKeyPress={handleChatKeyPress}
                  clearChatHistory={clearChatHistory}
                  sessionMode={sessionMode}
                  setSessionMode={setSessionMode}
                  llmLoading={llmLoading}
                  moves={moves}
                  currentMoveIndex={currentMoveIndex}
                  goToMove={goToMove}
                  comment={comment}
                  gameInfo={gameInfo}
                  gameReviewTheme={gameReviewTheme}
                  generateGameReview={generateGameReview}
                  gameReviewLoading={gameReviewLoading}
                  gameReviewProgress={gameReviewProgress}
                  handleGameReviewSummaryClick={handleGameReviewSummaryClick}
                  handleMoveAnnontateClick={handleMoveAnnontateClick}
                  handleMoveCoachClick={handleMoveCoachClick}
                  gameReview={gameReview}
                  pgnText={pgnText}
                  currentMove={moves[currentMoveIndex]}
                  allGames={allGames}
                  onGameSelect={handleGameSelect}
                />
              )}
              {chapters.length > 0 && (
                <ResizableChapterSelector
                  chapters={chapters}
                  onChapterSelect={(pgn) => {
                    loadPGN(pgn);
                  }}
                />
              )}
            </Stack>
          </Box>
        )}
      </Stack>

        <SaveGameReviewDialog
          saveDialogOpen={saveDialogOpen}
          setSaveDialogOpen={setSaveDialogOpen}
          historyDialogOpen={historyDialogOpen}
          setHistoryDialogOpen={setHistoryDialogOpen}
          gameInfo={gameInfo}
          gameReview={gameReview}
          moves={moves}
          pgnText={pgnText}
          loadFromHistory={loadFromHistory}
        />
      </Box>
    </Box>
  );
}
