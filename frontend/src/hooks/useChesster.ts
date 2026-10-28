import { useEngine } from "@/stockfish/hooks/useEngine";
import { EngineName, PositionEval, LineEval } from "@/stockfish/engine/engine";
import {
  MasterGames,
  getOpeningStatSpeech,
  getOpeningStats,
  Moves,
  getLichessOpeningStats,
} from "@/lib/openingdatabase/helper";
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
// Clerk authentication for server-managed LLM
import { useAuth } from "@clerk/nextjs";
import { apiFetch, ApiError } from '@/lib/api';
import { Chess } from "chess.js";
import { CandidateMove, getChessDBSpeech, useChessDB } from "../components/tabs/Chessdb";
import { useLocalStorage } from "usehooks-ts";
import useGameReview, { MoveAnalysis, MoveQuality } from "./useGameReview";
import { ApiSettings } from "../components/tabs/ModelSetting";
import { DEFAULT_ENGINE_LINES, DEFAULT_ENGINE_DEPTH, MAX_PV_MOVES, ANALYSIS_DELAY } from "@/lib/setting/helper";
import {
  arrowsFromBoardActions,
  buildClickAnalysisRequest,
  buildFutureMoveRequest,
  readAnalysisReply,
  type ClickAnalysisType,
  type CoachArrowsOnBoard,
} from "@/lib/coach/click-analysis";
import type { CoachArrow } from "@/lib/coach/review-markup";

// Types
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  maxTokens?: number,
  provider?: string,
  fen?: string,
  model?: string,
  content: string;
  timestamp: Date;
  response_time_ms?: number;
}

export interface AgentMessage {
  message: string,
  maxTokens: number,
  // Hermes sends no model/provider/timing; left empty rather than invented (28.10).
  provider?: string,
  model?: string,
  response_time_ms?: number,
  arrows?: CoachArrow[],
}

interface ChessterState {
  llmAnalysisResult: string | null;
  stockfishAnalysisResult: PositionEval | null;
  openingData: MasterGames | null;
  lichessOpeningData: MasterGames | null;
  llmLoading: boolean;
  stockfishLoading: boolean;
  openingLoading: boolean;
  lichessOpeningLoading: boolean;
  moveSquares: { [square: string]: string };
  analysisTab: number;
  chatMessages: ChatMessage[];
  chatInput: string;
  chatLoading: boolean;
  isStreaming: boolean;
  sessionMode: boolean;
  /** Arrows of the last analysis answer and the position they are about. */
  coachArrows: CoachArrowsOnBoard | null;
}

// Analysis data types
interface EngineLineData {
  line: LineEval;
  lineIndex: number;
}

interface MoveCoachData {
  fen: string;
  notation: string;
  quality: MoveQuality;
  player: "w" | "b";
  plyNumber: number;
  sanNotation?: string;
}

type AnalysisData = EngineLineData | Moves | CandidateMove | MoveCoachData | MoveAnalysis;


// Utility functions
const isValidFEN = (fen: string): boolean => {
  if (!fen || typeof fen !== 'string') return false;
  const parts = fen.trim().split(' ');
  return parts.length === 6;
};

const createChatMessage = (
  role: "user" | "assistant",
  fen: string,
  content: string,
  maxTokens?: number,
  provider?: string,
  model?: string,
  id?: string,
  response_time_ms?: number
): ChatMessage => ({
  id: id || `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
  role,
  maxTokens,
  provider,
  fen,
  model,
  content,
  timestamp: new Date(),
  response_time_ms,
});

export default function useChesster(fen: string) {
  // ==================== STATE MANAGEMENT ====================
  const [state, setState] = useState<ChessterState>({
    llmAnalysisResult: null,
    stockfishAnalysisResult: null,
    openingData: null,
    lichessOpeningData: null,
    llmLoading: false,
    stockfishLoading: false,
    openingLoading: false,
    lichessOpeningLoading: false,
    moveSquares: {},
    analysisTab: 0,
    chatMessages: [],
    chatInput: "",
    chatLoading: false,
    isStreaming: false,
    sessionMode: true,
    coachArrows: null,
  });

  // Engine settings with localStorage
  const [engineDepth, setEngineDepth] = useLocalStorage<number>(
    "engineDepth",
    DEFAULT_ENGINE_DEPTH
  );
  const [engineLines, setEngineLines] = useLocalStorage<number>(
    "engineLines", 
    DEFAULT_ENGINE_LINES
  );

  const [enginePicked] = useLocalStorage<EngineName>(
    "stockfish-engine-picked",
    EngineName.Stockfish17Point
  )

  // Hooks
  // Enable Clerk authentication for server-managed LLM
  const { getToken } = useAuth();
  const session = { getToken };
  const engine = useEngine(true, enginePicked);
  const { data: chessdbdata, loading, error, queueing, refetch, requestAnalysis } = useChessDB(fen);
  const {
    gameReview,
    setGameReview,
    gameReviewLoading,
    gameReviewProgress,
    setGameReviewLoading,
    generateGameReview,
  } = useGameReview(engine, engineDepth);

  // Refs
  const currentFenRef = useRef(fen);
  const abortControllerRef = useRef<AbortController | null>(null);
  const conversationIdRef = useRef<string | null>(null); // Track conversation for context
  const hasLoadedHistoryRef = useRef(false); // Track if we've loaded history on mount

  // Update ref when fen changes
  useEffect(() => {
    currentFenRef.current = fen;
  }, [fen]);

  // ==================== COMPUTED VALUES ====================
  const legalMoves = useMemo(() => {
    return isValidFEN(fen) ? new Chess(fen).moves() : [];
  }, [fen]);

  // ==================== UTILITY FUNCTIONS ====================
  const formatEvaluation = useCallback((line: LineEval): string => {
    if (line.mate !== undefined) {
      return `M${line.mate}`;
    }
    if (line.cp !== undefined) {
      const eval1 = line.cp / 100;
      return eval1 > 0 ? `+${eval1.toFixed(2)}` : eval1.toFixed(2);
    }
    return "0.00";
  }, []);

  const formatPrincipalVariation = useCallback(
    (pv: string[], startFen: string): string => {
      const tempGame = new Chess(startFen);
      const moves: string[] = [];

      for (const uciMove of pv.slice(0, MAX_PV_MOVES)) {
        try {
          const move = tempGame.move({
            from: uciMove.slice(0, 2),
            to: uciMove.slice(2, 4),
            promotion: uciMove.length > 4 ? (uciMove[4] as string) : undefined,
          });
          if (move) {
            moves.push(move.san);
          } else {
            break;
          }
        } catch {
          break;
        }
      }

      return moves.join(" ");
    },
    []
  );

  const formatLineForLLM = useCallback(
    (line: LineEval, lineIndex: number): string => {
      const evaluation = formatEvaluation(line);
      const moves = formatPrincipalVariation(line.pv, line.fen);

      let formattedLine = `Line ${lineIndex + 1}: ${evaluation} - ${moves}`;

      if (line.resultPercentages) {
        formattedLine += ` (Win: ${line.resultPercentages.win}%, Draw: ${line.resultPercentages.draw}%, Loss: ${line.resultPercentages.loss}%)`;
      }

      return formattedLine;
    },
    [formatEvaluation, formatPrincipalVariation]
  );

  // ==================== STATE UPDATERS ====================
  const updateState = useCallback((updates: Partial<ChessterState>) => {
    setState(prev => ({ ...prev, ...updates }));
  }, []);

  const addChatMessage = useCallback((message: ChatMessage) => {
    updateState({ 
      chatMessages: [...state.chatMessages, message] 
    });
  }, [state.chatMessages, updateState]);

  // ==================== API FUNCTIONS ====================

  // Load conversation history from backend
  const loadConversationHistory = useCallback(async (conversationId: string): Promise<void> => {
    try {
      const token = await session?.getToken();
      if (!token) {
        console.warn('No auth token, skipping conversation history load');
        return;
      }

      let data: any;
      try {
        data = await apiFetch<any>(`/api/coach/history/${conversationId}`, {
          method: "GET",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
      } catch (e) {
        console.warn(`Failed to load conversation history: ${e instanceof ApiError ? e.status : e}`);
        return;
      }

      // Convert backend messages to ChatMessage format
      const loadedMessages: ChatMessage[] = data.messages.map((msg: any) => ({
        id: msg.id || `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        role: msg.role as "user" | "assistant",
        content: msg.content,
        fen: msg.fen || "",
        timestamp: new Date(msg.timestamp),
        maxTokens: msg.tokens_used,
        model: msg.model,
        provider: msg.model?.includes('claude') ? 'anthropic' : 'openai',
        response_time_ms: msg.response_time_ms
      }));

      // Update state with loaded messages
      updateState({ chatMessages: loadedMessages });
      conversationIdRef.current = conversationId;
    } catch (error) {
      console.error('Error loading conversation history:', error);
    }
  }, [session, updateState]);

  const makeApiRequest = useCallback(
  async (fen: string, query: string, mode: string, contextNote?: string): Promise<AgentMessage> => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    // A new answer replaces the last one's arrows.
    setState(prev => (prev.coachArrows ? { ...prev, coachArrows: null } : prev));

    try {
      const token = await session?.getToken();

      // Check if user is authenticated
      if (!token) {
        throw new Error('Please sign in to use AI chat features');
      }

      // Determine context type based on mode
      const contextType = mode === 'position' ? 'position' :
                          mode === 'game' ? 'game' :
                          mode === 'puzzle' ? 'puzzle' : 'general';

      let data: any;
      try {
        data = await apiFetch<any>(`/api/coach/analysis`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            fen,
            query,
            // Master stats / engine lines: apart from the query, which Hermes caps at 2000 (28.10).
            context_note: contextNote,
            conversation_id: conversationIdRef.current, // Maintain conversation context
            context_type: contextType
          }),
          signal: controller.signal,
        });
      } catch (e) {
        if (e instanceof ApiError) {
          let errorMessage = e.message;
          if (errorMessage.length > 500) {
            errorMessage = errorMessage.substring(0, 500) + '...';
          }
          if (e.status === 401) {
            errorMessage = 'Please sign in to use AI chat features';
          } else if (e.status === 429) {
            errorMessage = 'Rate limit exceeded. Please try again in a few minutes.';
          }
          throw new Error(errorMessage);
        }
        throw e;
      }

      // Save conversation ID for follow-up messages
      if (data.conversation_id) {
        conversationIdRef.current = data.conversation_id;
        // Persist to localStorage so it survives page refreshes
        try {
          localStorage.setItem('current_conversation_id', data.conversation_id);
        } catch (e) {
          console.warn('Failed to save conversation ID to localStorage:', e);
        }
      }

      // Clean text plus the arrows the answer drew (they showed raw as
      // «[[arrows: …]]», 28.10); the arrows go on the board for that position.
      const reply = readAnalysisReply(data);
      setState(prev => ({
        ...prev,
        coachArrows: reply.arrows.length ? { fen, arrows: reply.arrows } : null,
      }));
      return { message: reply.message, maxTokens: reply.maxTokens, arrows: reply.arrows };
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        throw new Error("Request cancelled");
      }
      throw error;
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
    }
  },
  [session]
);

  // Streaming API request for real-time token display (like ChatGPT/Claude)
  const makeApiRequestStreaming = useCallback(
    async (
      fen: string,
      query: string,
      mode: string,
      onToken: (token: string) => void,
      onComplete: (data: { conversation_id: string; tokens_used: number }) => void,
      onError: (error: string) => void
    ): Promise<void> => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;
      setState(prev => (prev.coachArrows ? { ...prev, coachArrows: null } : prev));

      try {
        const token = await session?.getToken();

        if (!token) {
          throw new Error('Please sign in to use AI chat features');
        }

        const contextType = mode === 'position' ? 'position' :
                            mode === 'game' ? 'game' :
                            mode === 'puzzle' ? 'puzzle' : 'general';

        // Route through the Hermes coach analysis stream proxy
        const response = await fetch(`/api/coach/analysis/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            fen,
            query,
            conversation_id: conversationIdRef.current,
            context_type: contextType
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          let errorMessage = 'Failed to get AI response';
          try {
            const error = await response.json();
            errorMessage = error.error || errorMessage;
          } catch {
            errorMessage = `Request failed with status ${response.status}`;
          }
          throw new Error(errorMessage);
        }

        // Read the SSE stream
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) {
          throw new Error('No response body');
        }

        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');

          // Keep the last incomplete line in the buffer
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.delta) {
                  onToken(data.delta);
                }
                // The coach's arrows: drawn on the board for this position (28.10).
                if (data.board_actions) {
                  const arrows = arrowsFromBoardActions(data.board_actions);
                  if (arrows.length) {
                    setState(prev => ({ ...prev, coachArrows: { fen, arrows } }));
                  }
                }
                if (data.done) {
                  // Save conversation ID
                  if (data.conversation_id) {
                    conversationIdRef.current = data.conversation_id;
                    try {
                      localStorage.setItem('current_conversation_id', data.conversation_id);
                    } catch (e) {
                      console.warn('Failed to save conversation ID:', e);
                    }
                  }
                  onComplete({
                    conversation_id: data.conversation_id,
                    tokens_used: data.tokens_used,
                  });
                }
                if (data.error) {
                  onError(data.error);
                }
              } catch (parseError) {
                console.warn('Failed to parse SSE data:', line);
              }
            }
          }
        }
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
          onError("Request cancelled");
        } else {
          onError(error instanceof Error ? error.message : "Unknown error");
        }
      } finally {
        if (abortControllerRef.current === controller) {
          abortControllerRef.current = null;
        }
      }
    },
    [session]
  );

  const fetchOpeningData = useCallback(async (): Promise<void> => {
    const currentFen = currentFenRef.current;
    updateState({ openingLoading: true });

    try {
      const data = await getOpeningStats(currentFen);
      if (currentFenRef.current === currentFen) {
        updateState({ openingData: data, openingLoading: false });
      }
    } catch (error) {
      console.error("Error fetching opening data:", error);
      if (currentFenRef.current === currentFen) {
        updateState({ openingData: null, openingLoading: false });
      }
    }
  }, [updateState]);

  const fetchLichessOpeningData = useCallback(async (): Promise<void> => {
    const currentFen = currentFenRef.current;
    updateState({ lichessOpeningLoading: true });

    try {
      const data = await getLichessOpeningStats(currentFen);
      if (currentFenRef.current === currentFen) {
        updateState({ lichessOpeningData: data, lichessOpeningLoading: false });
      }
    } catch (error) {
      console.error("Error fetching Lichess opening data:", error);
      if (currentFenRef.current === currentFen) {
        updateState({ lichessOpeningData: null, lichessOpeningLoading: false });
      }
    }
  }, [updateState]);

  const analyzeWithStockfish = useCallback(async (): Promise<void> => {
    if (!engine) {
      console.warn("Stockfish engine not ready");
      return;
    }

    const currentFen = currentFenRef.current;
    updateState({ stockfishLoading: true });

    try {
      const result = await engine.evaluatePositionWithUpdate({
        fen: currentFen,
        depth: engineDepth,
        multiPv: engineLines,
        setPartialEval: (partialEval: PositionEval) => {
          if (currentFenRef.current === currentFen) {
            updateState({ stockfishAnalysisResult: partialEval });
          }
        },
      });

      if (currentFenRef.current === currentFen) {
        updateState({ stockfishAnalysisResult: result, stockfishLoading: false });
      }
    } catch (error) {
      console.error("Error analyzing position with Stockfish:", error);
      if (currentFenRef.current === currentFen) {
        updateState({ stockfishAnalysisResult: null, stockfishLoading: false });
      }
    }
  }, [engine, engineDepth, engineLines, updateState]);

  // ==================== CHAT FUNCTIONS ====================
  const abortChatMessage = useCallback((): void => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;

      updateState({ chatLoading: false });
      addChatMessage(createChatMessage("assistant", "","Message generation was cancelled.", ));
    }
  }, [updateState, addChatMessage]);

  const buildChatQuery = useCallback(
    (
      currentInput: string,
      currentFen: string,
      sideToMove: string,
      gameInfo?: string,
      currentMove?: string,
      puzzleMode?: boolean,
      puzzleQuery?: string,
      playMode?: boolean
    ): string => {
      let query = `<chess_coaching_request>

<user_query>
${currentInput}
</user_query>

<position_context>
Current FEN: ${currentFen}
Side to Move: ${sideToMove}
</position_context>`;

      // Add mode-specific instructions
      if (puzzleMode === true) {
        query += `

<mode>
Type: Puzzle Mode
Instructions: 
- Act as an interactive chess puzzle coach
- Do not reveal the solution immediately
- Guide the user through the puzzle one step at a time
- If the user asks for a hint, provide a subtle clue about the best move or tactical idea
- If the user requests the solution directly, explain the correct sequence of moves and the reasoning behind them
- Encourage the user to consider candidate moves, threats, and tactical motifs in the position
- Always wait for the user's input before revealing the next step or answer, unless the user explicitly asks for the solution
</mode>`;
      } else if (playMode === true) {
        query += `

<mode>
Type: Play Mode
Instructions:
- Act as a supportive chess coach during live gameplay
- Provide real-time strategic advice and tactical guidance
- Help identify threats and opportunities in the current position
- Suggest candidate moves and explain their benefits
- Focus on practical, actionable advice for the current game situation
- Be encouraging and supportive while providing accurate analysis
</mode>`;
      } else {
        query += `

<mode>
Type: ${state.sessionMode ? 'Analysis Mode' : 'Chat Mode'}
</mode>`;
      }

      // Add additional context
      if (puzzleQuery) {
        query += `

<puzzle_information>
${puzzleQuery}
</puzzle_information>`;
      }

      if (gameInfo) {
        query += `

<game_history>
PGN:
${gameInfo}
</game_history>`;
      }

      if (currentMove) {
        query += `

<current_move>
${currentMove}
</current_move>`;
      }

      // Add game review if available
      if (gameReview && gameReview.length > 0) {
        const generateGameReviewSummary = (moves: MoveAnalysis[]): string => {
          const movesByQuality: Record<MoveQuality, MoveAnalysis[]> = {
            "Best": [], "Very Good": [], "Good": [], "Dubious": [], 
            "Mistake": [], "Blunder": [], "Book": []
          };

          moves.forEach(move => {
            movesByQuality[move.quality].push(move);
          });

          const whiteMoves = moves.filter(move => move.player === 'w');
          const blackMoves = moves.filter(move => move.player === 'b');

          const formatMoveList = (moveList: MoveAnalysis[]): string => {
            return moveList
              .map(move => `Move ${Math.ceil(move.plyNumber / 2)}${move.player === 'w' ? '' : '...'} ${move.notation}`)
              .join(', ');
          };

          let summary = `Game Review Summary:\n\n`;

          if (whiteMoves.length > 0) {
            const whiteBlunders = whiteMoves.filter(m => m.quality === "Blunder");
            const whiteMistakes = whiteMoves.filter(m => m.quality === "Mistake");
            const whiteDubious = whiteMoves.filter(m => m.quality === "Dubious");
            
            summary += `White's Performance:
- Blunders: ${whiteBlunders.length}${whiteBlunders.length > 0 ? ` (${formatMoveList(whiteBlunders)})` : ''}
- Mistakes: ${whiteMistakes.length}${whiteMistakes.length > 0 ? ` (${formatMoveList(whiteMistakes)})` : ''}
- Dubious moves: ${whiteDubious.length}${whiteDubious.length > 0 ? ` (${formatMoveList(whiteDubious)})` : ''}\n\n`;
          }

          if (blackMoves.length > 0) {
            const blackBlunders = blackMoves.filter(m => m.quality === "Blunder");
            const blackMistakes = blackMoves.filter(m => m.quality === "Mistake");
            const blackDubious = blackMoves.filter(m => m.quality === "Dubious");
            
            summary += `Black's Performance:
- Blunders: ${blackBlunders.length}${blackBlunders.length > 0 ? ` (${formatMoveList(blackBlunders)})` : ''}
- Mistakes: ${blackMistakes.length}${blackMistakes.length > 0 ? ` (${formatMoveList(blackMistakes)})` : ''}
- Dubious moves: ${blackDubious.length}${blackDubious.length > 0 ? ` (${formatMoveList(blackDubious)})` : ''}\n\n`;
          }

          const criticalMoments = [
            ...movesByQuality["Blunder"],
            ...movesByQuality["Mistake"],
            ...movesByQuality["Dubious"]
          ].sort((a, b) => {
            const qualityOrder = { "Blunder": 0, "Mistake": 1, "Dubious": 2, "Best": 3, "Good": 4, "Very Good": 5, "Book": 6 };
            return qualityOrder[a.quality] - qualityOrder[b.quality];
          });

          if (criticalMoments.length > 0) {
            summary += `Key Moments to Review:\n`;
            criticalMoments.slice(0, 8).forEach((move, index) => {
              const moveNumber = Math.ceil(move.plyNumber / 2);
              const playerSymbol = move.player === 'w' ? '♔' : '♚';
              summary += `${index + 1}. ${playerSymbol} Move ${moveNumber}${move.player === 'w' ? '' : '...'} ${move.notation} - ${move.quality} Best Was ${move.sanNotation}\n`;
            });
          }

          return summary;
        };

        query += `

<game_review_analysis>
${generateGameReviewSummary(gameReview)}

Detailed Move Analysis:
${gameReview.map(move => {
  const moveNumber = Math.ceil(move.plyNumber / 2);
  const playerName = move.player === 'w' ? 'White' : 'Black';
  return `Move ${moveNumber}${move.player === 'w' ? '' : '...'} ${move.notation} (${playerName}) - Quality: ${move.quality} Best was ${move.sanNotation}`;
}).join('\n')}
</game_review_analysis>`;
      }

      // Add engine analysis for non-play modes
      if (state.sessionMode && !playMode && state.stockfishAnalysisResult) {
        const formattedEngineLines = state.stockfishAnalysisResult.lines
          .map((line, index) => {
            const evaluation = formatEvaluation(line);
            const moves = formatPrincipalVariation(line.pv, line.fen);
            let formattedLine = `  Line ${index + 1}: ${evaluation}
    Moves: ${moves}`;

            if (line.resultPercentages) {
              formattedLine += `
    Win Rate: ${line.resultPercentages.win}% | Draw: ${line.resultPercentages.draw}% | Loss: ${line.resultPercentages.loss}%`;
            }

            return formattedLine;
          })
          .join("\n\n");

        query += `

<engine_analysis>
Depth: ${engineDepth}
${formattedEngineLines}
</engine_analysis>`;
      }

      // Add opening information
      if (state.openingData) {
        const openingSpeech = getOpeningStatSpeech(state.openingData);
        query += `

<opening_information>
${openingSpeech}
</opening_information>`;
      }

      // Add chess database information
      if (chessdbdata) {
        const candidateMoves = getChessDBSpeech(chessdbdata);
        query += `

<database_analysis>
${candidateMoves}
</database_analysis>`;
      }

     
      query += `

</chess_coaching_request>`;

      return query;
    },
    [state.sessionMode, state.stockfishAnalysisResult, state.openingData, gameReview, chessdbdata, engineDepth, formatEvaluation, formatPrincipalVariation]
  );

  const sendChatMessage = useCallback(
    async (
      gameInfo?: string,
      currentMove?: string,
      puzzleMode?: boolean,
      puzzleQuery?: string,
      playMode?: boolean,
      questionMode?: boolean,
    ): Promise<void> => {
      if (!state.chatInput.trim()) return;
      const userMessage = createChatMessage("user", fen, state.chatInput);
      const currentInput = state.chatInput;
      const assistantMessageId = (Date.now() + 1).toString();

      // Create empty assistant message placeholder for streaming
      const assistantMessage = createChatMessage(
        "assistant",
        fen,
        "", // Start with empty content
        undefined,
        undefined,
        undefined,
        assistantMessageId
      );

      // Add both messages immediately - user message and empty assistant placeholder
      updateState({
        chatMessages: [...state.chatMessages, userMessage, assistantMessage],
        chatInput: "",
        chatLoading: true
      });

      const currentFen = currentFenRef.current;

      // Determine the context type for the new server-managed API
      let mode = "position";
      if (questionMode) {
        mode = "question";
      } else {
        mode = puzzleMode === true || puzzleQuery ? "puzzle" : "position";
      }

      // Use streaming API for real-time token display
      await makeApiRequestStreaming(
        currentFen,
        currentInput,
        mode,
        // onToken - append each token to the assistant message
        (token: string) => {
          setState(prev => {
            const updatedMessages = [...prev.chatMessages];
            const lastMsg = updatedMessages[updatedMessages.length - 1];
            if (lastMsg && lastMsg.id === assistantMessageId) {
              lastMsg.content += token;
            }
            // Set isStreaming on first token arrival
            return { ...prev, chatMessages: updatedMessages, isStreaming: true };
          });
        },
        // onComplete - update metadata and stop loading
        (data: { conversation_id: string; tokens_used: number }) => {
          setState(prev => {
            const updatedMessages = [...prev.chatMessages];
            const lastMsg = updatedMessages[updatedMessages.length - 1];
            if (lastMsg && lastMsg.id === assistantMessageId) {
              lastMsg.maxTokens = data.tokens_used;
            }
            return { ...prev, chatMessages: updatedMessages, chatLoading: false, isStreaming: false };
          });
        },
        // onError - show error message
        (error: string) => {
          console.error("Error sending chat message:", error);
          if (error !== "Request cancelled") {
            setState(prev => {
              const updatedMessages = [...prev.chatMessages];
              const lastMsg = updatedMessages[updatedMessages.length - 1];
              if (lastMsg && lastMsg.id === assistantMessageId) {
                lastMsg.content = error || "An error occurred";
              }
              return { ...prev, chatMessages: updatedMessages, chatLoading: false, isStreaming: false };
            });
          }
        }
      );
    },
    [fen, state.chatInput, state.chatMessages, makeApiRequestStreaming, updateState]
  );

  const handleChatKeyPress = useCallback(
    (e: React.KeyboardEvent): void => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    },
    [sendChatMessage]
  );

  const clearChatHistory = useCallback((): void => {
    updateState({ chatMessages: [] });
    // Clear conversation ID to start a new conversation
    conversationIdRef.current = null;
    try {
      localStorage.removeItem('current_conversation_id');
    } catch (e) {
      console.warn('Failed to clear conversation ID from localStorage:', e);
    }
  }, [updateState]);

  // ==================== CLICK HANDLERS ====================
  const createAnalysisHandler = useCallback(
    (analysisType: string) => async (data: AnalysisData, customQuery?: string): Promise<void | AgentMessage> => {
      if (state.llmLoading || state.chatLoading) return;

      updateState({ chatLoading: true, analysisTab: 1 });

      try {
        // The request goes in the query, the grounding (master stats, ChessDB,
        // engine lines) in context_note: glued together they passed Hermes'
        // 2000-character cap and every click got 400 (28.10).
        const type = analysisType as ClickAnalysisType;
        const reviewData = type === "moveCoach" || type === "annotation" ? (data as MoveAnalysis) : undefined;
        const requestFen = reviewData ? reviewData.fen : currentFenRef.current;

        let engineAnalysis: string | null = null;
        if (state.stockfishAnalysisResult || engine) {
          let engineResult = state.stockfishAnalysisResult;
          if (!engineResult && engine) {
            engineResult = await engine.evaluatePositionWithUpdate({
              fen: requestFen,
              depth: engineDepth,
              multiPv: engineLines,
              setPartialEval: () => {},
            });
          }

          if (engineResult) {
            const formattedEngineLines = engineResult.lines
              .map((line, index) => {
                const evaluation = formatEvaluation(line);
                const moves = formatPrincipalVariation(line.pv, line.fen);
                let formattedLine = `  Line ${index + 1}: ${evaluation}
    Moves: ${moves}`;

                if (line.resultPercentages) {
                  formattedLine += `
    Win Rate: ${line.resultPercentages.win}% | Draw: ${line.resultPercentages.draw}% | Loss: ${line.resultPercentages.loss}%`;
                }

                return formattedLine;
              })
              .join("\n\n");
            engineAnalysis = `Depth: ${engineDepth}\n${formattedEngineLines}`;
          }
        }

        const engineLineData = type === "engineLine" ? (data as EngineLineData) : undefined;
        const request = buildClickAnalysisRequest({
          type,
          currentFen: currentFenRef.current,
          engineLineText: engineLineData ? formatLineForLLM(engineLineData.line, engineLineData.lineIndex) : undefined,
          move: type === "openingMove" ? (data as Moves) : undefined,
          openingData: state.openingData,
          candidate: type === "candidateMove" ? (data as CandidateMove) : undefined,
          review: reviewData,
          customQuery,
          grounding: {
            openingSpeech: state.openingData ? getOpeningStatSpeech(state.openingData) : null,
            databaseSpeech: chessdbdata ? getChessDBSpeech(chessdbdata) : null,
            engineAnalysis,
          },
        });

        // Determine message content based on analysis type
        let messageContent = "";
        switch (analysisType) {
          case "engineLine":
            const engineLineData = data as EngineLineData;
            messageContent = `Analyze engine line: ${formatLineForLLM(engineLineData.line, engineLineData.lineIndex)}`;
            break;
          case "openingMove":
            const openingMove = data as Moves;
            messageContent = `Analyze opening move: ${openingMove.san}`;
            break;
          case "candidateMove":
            const candidateMoveData = data as CandidateMove;
            messageContent = `Analyze move: ${candidateMoveData.san}`;
            break;
          case "moveCoach":
            const coachMove = data as MoveAnalysis
            messageContent = `Chesster, analyze move: ${coachMove.sanNotation}`
          case "annotation":
            const reviewData = data as MoveAnalysis;
            const moveNotationDisplay = reviewData.plyNumber % 2 === 0 ? 
              `${Math.floor(reviewData.plyNumber / 2) + 1}.` : 
              `${Math.floor(reviewData.plyNumber / 2) + 1}...`;
            messageContent = analysisType === "annotation" 
              ? `Chesster, annotate this move: ${reviewData.notation} (${reviewData.quality})`
              : `Chesster, analyze move: ${moveNotationDisplay} ${reviewData.notation} (${reviewData.quality}) for ${reviewData.player === "w" ? "White" : "Black"}`;
            break;
        }

        const userMessage = createChatMessage("user", fen, messageContent);
        const result = await makeApiRequest(request.fen, request.query, analysisType === "annotation" ? "annotation" : "position", request.context_note);
        const assistantMessage = createChatMessage("assistant", fen, result.message, result.maxTokens, result.provider, result.model, (Date.now() + 1).toString(), result.response_time_ms);


        if(analysisType === "moveCoach"){
          const chathistory: ChatMessage[] = state.chatMessages;
          chathistory.push(userMessage);
          chathistory.push(assistantMessage);
          updateState({ chatMessages: chathistory });
        }

        updateState({ 
          chatMessages: [...state.chatMessages, userMessage, assistantMessage],
          chatLoading: false 
        });

        return analysisType === "annotation" ? result : undefined;
      } catch (error) {
        console.error(`Error in ${analysisType} analysis:`, error);
        if (!(error instanceof Error && error.message === "Request cancelled")) {
          const errorMessage = createChatMessage(
            "assistant",
            "",
            `Sorry, there was an error analyzing the ${analysisType}. Please try again.`,
            undefined,
            undefined,
            undefined,
            (Date.now() + 1).toString()
          );
          updateState({ 
            chatMessages: [...state.chatMessages, errorMessage],
            chatLoading: false 
          });
        }
        
      }
    },
    [
      fen,
      state.llmLoading, 
      state.chatLoading, 
      state.chatMessages, 
      state.openingData, 
      state.stockfishAnalysisResult,
      chessdbdata, 
      engine, 
      engineDepth, 
      engineLines,
      formatLineForLLM,
      formatEvaluation,
      formatPrincipalVariation,
      makeApiRequest,
      updateState
    ]
  );

  // Specific handlers using the generic analysis handler
  const handleEngineLineClick = useCallback(
    (line: LineEval, lineIndex: number) => 
      createAnalysisHandler("engineLine")({ line, lineIndex } as EngineLineData),
    [createAnalysisHandler]
  );

  const handleOpeningMoveClick = useCallback(
    (move: Moves) => createAnalysisHandler("openingMove")(move),
    [createAnalysisHandler]
  );

  const handleMoveClick = useCallback(
    (move: CandidateMove) => createAnalysisHandler("candidateMove")(move),
    [createAnalysisHandler]
  );

  const handleMoveCoachClick = useCallback(
    (review: MoveAnalysis) => createAnalysisHandler("moveCoach")(review),
    [createAnalysisHandler]
  );

  // ==================== SPECIALIZED HANDLERS ====================
  const handleFutureMoveLegalClick = useCallback(
    async (move: string): Promise<void> => {
      if (state.llmLoading || state.chatLoading) return;

      updateState({ chatLoading: true, analysisTab: 1 });

      try {
        const currentFen = currentFenRef.current;
        const chessInstance = new Chess(currentFen);
        chessInstance.move(move);
        const futureFen = chessInstance.fen();
        const sideToMove = chessInstance.turn() === "w" ? "White" : "Black";
        const newOpeningData = await getOpeningStats(futureFen);

        let engineAnalysis: string | null = null;
        if (engine) {
          const engineResult = await engine.evaluatePositionWithUpdate({
            fen: futureFen,
            depth: engineDepth,
            multiPv: engineLines,
            setPartialEval: () => {},
          });

          if (engineResult) {
            engineAnalysis = engineResult.lines
              .map((line, index) => formatLineForLLM(line, index))
              .join("\n");
          }
        }

        // Stats and engine lines in context_note, under Hermes' query cap (28.10).
        const request = buildFutureMoveRequest(move, futureFen, {
          openingSpeech: newOpeningData ? getOpeningStatSpeech(newOpeningData) : null,
          engineAnalysis,
        });

        const userMessage = createChatMessage("user", fen, `Analyze move: ${move}`);
        const result = await makeApiRequest(request.fen, request.query, "position", request.context_note);
        const assistantMessage = createChatMessage("assistant", fen, result.message, result.maxTokens, result.provider, result.model, (Date.now() + 1).toString(), result.response_time_ms);


        updateState({ 
          chatMessages: [...state.chatMessages, userMessage, assistantMessage],
          chatLoading: false 
        });
      } catch (error) {
        console.error("Error analyzing future move:", error);
        if (!(error instanceof Error && error.message === "Request cancelled")) {
          const errorMessage = createChatMessage(
            "assistant",
            "",
            "Sorry, there was an error analyzing the move. Please try again."
          );
          updateState({ 
            chatMessages: [...state.chatMessages, errorMessage],
            chatLoading: false 
          });
        }
      }
    },
    [
      state.llmLoading, 
      state.chatLoading, 
      state.chatMessages,
      engine, 
      engineDepth, 
      engineLines,
      formatLineForLLM,
      makeApiRequest,
      updateState
    ]
  );

  const handleMoveAnnontateClick = useCallback(
    async (review: MoveAnalysis, customQuery?: string): Promise<void> => {
      return createAnalysisHandler("annotation")(review, customQuery) as Promise<void>;
    },
    [createAnalysisHandler]
  );

  const handleMovePGNAnnotateClick = useCallback(
    async (review: MoveAnalysis, customQuery?: string): Promise<AgentMessage | null> => {
      return createAnalysisHandler("annotation")(review, customQuery) as Promise<AgentMessage | null>;
    },
    [createAnalysisHandler]
  );

  const handleGameReviewSummaryClick = useCallback(
    async (review: MoveAnalysis[], gameInfo: string): Promise<void> => {
      if (state.chatLoading) return;

      const findMovesByQuality = (quality: MoveQuality, player: "w" | "b") => {
        return review.filter(move => move.quality === quality && move.player === player);
      };

      const keyMoves: MoveAnalysis[] = [];

      // Collect key moves (first blunder, mistake, dubious for each player)
      ["Blunder", "Mistake", "Dubious"].forEach(quality => {
        const whiteMove = findMovesByQuality(quality as MoveQuality, "w")[0];
        const blackMove = findMovesByQuality(quality as MoveQuality, "b")[0];
        if (whiteMove) keyMoves.push(whiteMove);
        if (blackMove) keyMoves.push(blackMove);
      });

      keyMoves.sort((a, b) => a.plyNumber - b.plyNumber);

      updateState({ analysisTab: 1 });

      const summaryMessage = createChatMessage(
        "user",
        fen,
        `Starting game review analysis for ${keyMoves.length} key moves from: ${gameInfo}`
      );
      const chathistory: ChatMessage[] = state.chatMessages;
      chathistory.push(summaryMessage);
      updateState({ chatMessages: chathistory });

      // Process each key move sequentially
      for (let i = 0; i < keyMoves.length; i++) {
        const move = keyMoves[i];
        
        if (i > 0) {
          await new Promise(resolve => setTimeout(resolve, 1000));
        }

        try {
          await handleMoveCoachClick(move);
        } catch (error) {
          console.error(`Error analyzing move ${i + 1}:`, error);
        }
      }

      const finalMessage = createChatMessage(
        "assistant",
        "",
        `Game review complete! Analyzed ${keyMoves.length} key moves. The analysis above covers the most important moments in your game, focusing on critical mistakes and excellent moves. Review each analysis to understand the key concepts and improve your play.`,
        undefined,
        undefined,
        undefined,
        (Date.now() + keyMoves.length + 1).toString()
      );

      updateState({ 
        chatMessages: [...state.chatMessages, finalMessage]
      });
    },
    [state.chatLoading, state.chatMessages, handleMoveCoachClick, updateState]
  );

  // ==================== LOAD CONVERSATION ON MOUNT ====================
  useEffect(() => {
    // Only run on client side (not during SSR)
    if (typeof window === 'undefined') return;

    // Always start with a fresh chat on mount (new session).
    // Past conversations are accessible via the sidebar.
    if (hasLoadedHistoryRef.current) return;
    hasLoadedHistoryRef.current = true;

    conversationIdRef.current = null;
    try {
      localStorage.removeItem('current_conversation_id');
    } catch {
      // ignore
    }
  }, []);

  // ==================== AUTO ANALYSIS EFFECT ====================
  useEffect(() => {
    if (!engine || !fen) return;

    // Clear previous results
    updateState({
      stockfishAnalysisResult: null,
      llmAnalysisResult: null,
      openingData: null,
    });

    // Cancel any pending API requests
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // Auto-analyze with delay to avoid rapid fire requests
    const timeoutId = setTimeout(() => {
      if (currentFenRef.current === fen) {
        analyzeWithStockfish();
        fetchOpeningData();
        fetchLichessOpeningData();
      }
    }, ANALYSIS_DELAY);

    return () => clearTimeout(timeoutId);
  }, [fen, engine, engineDepth, engineLines, analyzeWithStockfish, fetchOpeningData, fetchLichessOpeningData, updateState]);

  // ==================== CLEANUP EFFECT ====================
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // ==================== MEMOIZED RETURN OBJECT ====================
  return useMemo(
    () => ({
      // Analysis Results
      llmAnalysisResult: state.llmAnalysisResult,
      setLlmAnalysisResult: (result: string | null) => updateState({ llmAnalysisResult: result }),
      stockfishAnalysisResult: state.stockfishAnalysisResult,
      setStockfishAnalysisResult: (result: PositionEval | null) => updateState({ stockfishAnalysisResult: result }),
      openingData: state.openingData,
      setOpeningData: (data: MasterGames | null) => updateState({ openingData: data }),
      chessdbdata,
      loading,
      error,
      queueing,
      legalMoves,
      refetch,
      requestAnalysis,

      // Loading States
      llmLoading: state.llmLoading,
      setLlmLoading: (loading: boolean) => updateState({ llmLoading: loading }),
      stockfishLoading: state.stockfishLoading,
      setStockfishLoading: (loading: boolean) => updateState({ stockfishLoading: loading }),
      openingLoading: state.openingLoading,
      setOpeningLoading: (loading: boolean) => updateState({ openingLoading: loading }),
      lichessOpeningData: state.lichessOpeningData,
      lichessOpeningLoading: state.lichessOpeningLoading,
      setLichessOpeningLoading: (loading: boolean) => updateState({ lichessOpeningLoading: loading }),

      // UI State
      moveSquares: state.moveSquares,
      setMoveSquares: (squares: { [square: string]: string }) => updateState({ moveSquares: squares }),
      analysisTab: state.analysisTab,
      setAnalysisTab: (tab: number) => updateState({ analysisTab: tab }),

      // Chat State
      chatMessages: state.chatMessages,
      setChatMessages: (messages: ChatMessage[]) => updateState({ chatMessages: messages }),
      chatInput: state.chatInput,
      setChatInput: (input: string) => updateState({ chatInput: input }),
      chatLoading: state.chatLoading,
      setChatLoading: (loading: boolean) => updateState({ chatLoading: loading }),
      isStreaming: state.isStreaming,
      sessionMode: state.sessionMode,
      coachArrows: state.coachArrows,
      setSessionMode: (mode: boolean) => updateState({ sessionMode: mode }),

      // Engine Settings
      engineDepth,
      setEngineDepth,
      engineLines,
      setEngineLines,
      engine,

      // Game Review
      gameReview,
      setGameReview,
      gameReviewLoading,
      gameReviewProgress,
      setGameReviewLoading,
      generateGameReview,

      // Functions
      fetchOpeningData,
      fetchLichessOpeningData,
      analyzeWithStockfish,
      sendChatMessage,
      abortChatMessage,
      handleChatKeyPress,
      clearChatHistory,
      handleEngineLineClick,
      handleOpeningMoveClick,
      handleMoveClick,
      handleMoveCoachClick,
      handleMoveAnnontateClick,
      handleGameReviewSummaryClick,
      handleMovePGNAnnotateClick,
      handleFutureMoveLegalClick,

      // Utility Functions
      formatEvaluation,
      formatPrincipalVariation,
      formatLineForLLM,
    }),
    [
      state,
      chessdbdata,
      loading,
      error,
      queueing,
      legalMoves,
      refetch,
      requestAnalysis,
      engineDepth,
      setEngineDepth,
      engineLines,
      setEngineLines,
      engine,
      gameReview,
      setGameReview,
      gameReviewLoading,
      gameReviewProgress,
      setGameReviewLoading,
      generateGameReview,
      fetchOpeningData,
      fetchLichessOpeningData,
      analyzeWithStockfish,
      sendChatMessage,
      abortChatMessage,
      handleChatKeyPress,
      clearChatHistory,
      handleEngineLineClick,
      handleOpeningMoveClick,
      handleMoveClick,
      handleMoveCoachClick,
      handleMoveAnnontateClick,
      handleGameReviewSummaryClick,
      handleMovePGNAnnotateClick,
      handleFutureMoveLegalClick,
      formatEvaluation,
      formatPrincipalVariation,
      formatLineForLLM,
      updateState,
    ]
  );
}