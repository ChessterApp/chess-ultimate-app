"use client";

import { useState, useEffect, useRef } from "react";
import { Box, Stack } from "@mui/material";
import { Chess } from "chess.js";
import dynamic from "next/dynamic";
import useChesster from "@/hooks/useChesster";
// Clerk authentication disabled for local development
// import { useSession } from "@clerk/nextjs";
import { purpleTheme } from "@/theme/theme";
import Loader from "@/components/loading/Loader";
import Warning from "@/components/loading/SignUpWarning";
import { useChatSessions } from "@/hooks/useChatSessions";

import type { EditorState } from "@/components/editor/BoardEditor";

// Dynamic imports — ssr:false prevents hydration mismatches from useLocalStorage
const AiChessboardPanel = dynamic(() => import("@/components/analysis/AiChessboard"), { ssr: false });
const ChessterAnalysisView = dynamic(() => import("@/components/analysis/ChessterAnalysisView"), { ssr: false });
const ChatSidebar = dynamic(() => import("@/components/ChatSidebar"), { ssr: false });
const EditorControls = dynamic(() => import("@/components/editor/EditorControls"), { ssr: false });

export default function PositionPage() {
  // const session = useSession();
  // Simulated session for no-auth mode
  const session = { isLoaded: true, isSignedIn: true };

  // Client-side only flag
  const [mounted, setMounted] = useState(false);

  // Lazy initialization to avoid SSR issues with chess.js
  const [game, setGame] = useState<Chess | null>(null);
  const [fen, setFen] = useState('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');

  // Initialize chess on client only
  useEffect(() => {
    setGame(new Chess());
    setMounted(true);
  }, []);

  // Ref to track if we're loading messages from session (prevent save loop)
  const isLoadingFromSession = useRef(false);

  // Editor mode state (lifted from AiChessboard for right-panel control)
  const [editorMode, setEditorMode] = useState(false);
  const [editorState, setEditorState] = useState<EditorState | null>(null);

  // Chat sidebar state
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Chat session management
  const {
    sessions,
    currentSessionId,
    currentSession,
    createNewSession,
    switchToSession,
    deleteSession,
    renameSession,
    updateSessionFen,
    addMessageToSession,
    updateSessionMessages,
  } = useChatSessions();

  const {
    setLlmAnalysisResult,
    stockfishAnalysisResult,
    setStockfishAnalysisResult,
    openingData,
    setOpeningData,
    llmLoading,
    stockfishLoading,
    openingLoading,
    legalMoves,
    handleFutureMoveLegalClick,
    moveSquares,
    setMoveSquares,
    chatMessages,
    setChatMessages,
    chatInput,
    setChatInput,
    chatLoading,
    sessionMode,
    lichessOpeningData,
    lichessOpeningLoading,
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
    formatPrincipalVariation,
    handleEngineLineClick,
    abortChatMessage,
    handleOpeningMoveClick,
    handleMoveClick,
    chessdbdata,
    loading,
    queueing,
    error,
    refetch,
    requestAnalysis,
  } = useChesster(fen);

  // Chat session handlers
  const handleNewChat = () => {
    // Reset to starting position
    const startingFen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    const resetGame = new Chess();
    setGame(resetGame);
    setFen(startingFen);
    setLlmAnalysisResult(null);

    // Clear chat messages
    setChatMessages([]);

    // Create new session with starting position
    createNewSession(startingFen);
  };

  const handleSelectSession = (sessionId: string) => {
    switchToSession(sessionId);
  };

  // Sync board FEN with current session
  useEffect(() => {
    if (currentSession && currentSession.currentFen && currentSession.currentFen !== fen) {
      try {
        const sessionGame = new Chess();
        sessionGame.load(currentSession.currentFen);
        setGame(sessionGame);
        setFen(sessionGame.fen());
      } catch (error) {
        console.error('Invalid FEN in session, using default:', error);
        const defaultGame = new Chess();
        setGame(defaultGame);
        setFen(defaultGame.fen());
        updateSessionFen(defaultGame.fen());
      }
    }
  }, [currentSessionId, currentSession]);

  // Load chat messages from current session when session changes
  useEffect(() => {
    if (currentSession) {
      isLoadingFromSession.current = true;
      setChatMessages(currentSession.messages || []);
      // Reset flag after a short delay
      setTimeout(() => {
        isLoadingFromSession.current = false;
      }, 100);
    } else if (chatMessages.length > 0) {
      setChatMessages([]);
    }
  }, [currentSessionId]);

  // Save chat messages to current session when they change (with debounce)
  useEffect(() => {
    // Don't save if we're currently loading from session
    if (isLoadingFromSession.current) {
      return;
    }

    if (currentSessionId && chatMessages.length > 0) {
      const timeoutId = setTimeout(() => {
        updateSessionMessages(currentSessionId, chatMessages);
      }, 300);

      return () => clearTimeout(timeoutId);
    }
  }, [chatMessages, currentSessionId, updateSessionMessages]);

  // Update session FEN when board changes (with debounce)
  useEffect(() => {
    if (currentSessionId && fen) {
      const timeoutId = setTimeout(() => {
        updateSessionFen(fen);
      }, 300);

      return () => clearTimeout(timeoutId);
    }
  }, [fen, currentSessionId, updateSessionFen]);

  if (!session.isLoaded || !mounted || !game) {
    return <Loader />;
  }

  if (!session.isSignedIn) {
    return <Warning />;
  }

  return (
    <Box
      sx={{
        display: "flex",
        backgroundColor: purpleTheme.background.main,
        minHeight: "100vh",
        position: "relative",
      }}
    >
      {/* Chat Sidebar */}
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

      {/* Main Content Area */}
      <Box
        sx={{
          flex: 1,
          p: { xs: 1, sm: 2, md: 3, lg: 4 },
          minWidth: 0,
          overflow: "hidden",
        }}
      >
        <Stack direction={{ xs: "column", lg: "row" }} spacing={{ xs: 2, sm: 3, lg: 4 }}>
        {/* Chessboard Section */}
        <Box sx={{ flex: "0 0 auto", width: { xs: "100%", lg: "auto" }, display: "flex", justifyContent: "center" }}>
          <AiChessboardPanel
            game={game}
            fen={fen}
            moveSquares={moveSquares}
            setMoveSquares={setMoveSquares}
            engine={engine}
            setFen={setFen}
            setGame={setGame}
            setLlmAnalysisResult={setLlmAnalysisResult}
            setOpeningData={setOpeningData}
            setStockfishAnalysisResult={setStockfishAnalysisResult}
            fetchOpeningData={fetchOpeningData}
            analyzeWithStockfish={analyzeWithStockfish}
            llmLoading={llmLoading}
            stockfishLoading={stockfishLoading}
            stockfishAnalysisResult={stockfishAnalysisResult}
            openingLoading={openingLoading}
            editorMode={editorMode}
            onEditorModeChange={setEditorMode}
            onEditorStateChange={setEditorState}
          />
        </Box>

        <Box sx={{ flex: 1, minWidth: 0, width: "100%" }}>
          {editorMode && editorState ? (
            <EditorControls
              turn={editorState.turn}
              castling={editorState.castling}
              enPassant={editorState.enPassant}
              pieces={editorState.pieces}
              onTurnChange={editorState.onTurnChange}
              onCastlingChange={editorState.onCastlingChange}
              onEnPassantChange={editorState.onEnPassantChange}
              onPreset={editorState.onPreset}
              onStartingPosition={editorState.onStartingPosition}
              onClearBoard={editorState.onClearBoard}
              onFlipBoard={editorState.onFlipBoard}
              onAnalysisBoard={editorState.onAnalysisBoard}
              onContinueFromHere={editorState.onContinueFromHere}
              onStudy={editorState.onStudy}
              photoPreview={editorState.photoPreview}
              photoLoading={editorState.photoLoading}
              photoError={editorState.photoError}
              onUploadPhoto={editorState.onUploadPhoto}
            />
          ) : (
          <ChessterAnalysisView
            isGameReviewMode={false}
            stockfishAnalysisResult={stockfishAnalysisResult}
            stockfishLoading={stockfishLoading}
            handleEngineLineClick={handleEngineLineClick}
            engineDepth={engineDepth}
            fen={fen}
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
            gameReviewTheme={null}
            setSessionMode={setSessionMode}
            llmLoading={llmLoading}
          />
          )}
        </Box>
      </Stack>
      </Box>
    </Box>
  );
}
