import type { NextApiRequest, NextApiResponse } from "next";
import { chessChesster } from "@/server/mastra/agents";
import { getBoardState } from "@/server/mastra/tools/protocol/state";
import { RuntimeContext } from "@mastra/core/di";
import { PositionPrompter } from "@/server/mastra/tools/protocol/positionPrompter";
import { isClawdbotAvailable, routeRequest, isChessterAvailable } from "@/lib/router";
import { callGateway } from "@/lib/clawdbot/gateway";
import { getAuth } from "@clerk/nextjs/server";

const PYTHON_BACKEND_URL =
  process.env.INTERNAL_BACKEND_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "http://localhost:5001";

// Server-side Mastra agent config from env
const MASTRA_PROVIDER = process.env.MASTRA_PROVIDER || "google";
const MASTRA_MODEL = process.env.MASTRA_MODEL || "gemini-2.5-flash";
const MASTRA_API_KEY = process.env.OPENROUTER_API_KEY || "";
const MASTRA_IS_ROUTED = process.env.MASTRA_IS_ROUTED !== "false";
const MASTRA_LANGUAGE = process.env.MASTRA_LANGUAGE || "English";

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  // Authenticate via Clerk
  const { userId } = getAuth(req);
  if (!userId) {
    return res.status(401).json({ error: "Unauthorized" });
  }

  const { fen, query, conversation_id, context_type } = req.body;
  const authHeader = req.headers.authorization || "";

  if (!query || typeof query !== "string") {
    return res.status(400).json({ error: "Missing query" });
  }

  if (!fen || typeof fen !== "string") {
    return res.status(400).json({ error: "Missing FEN" });
  }

  // Set up SSE headers
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");

  // Helper to send SSE events
  const sendEvent = (data: Record<string, unknown>) => {
    res.write(`data: ${JSON.stringify(data)}\n\n`);
  };

  // Intelligent routing: use router to decide between Mastra and Chesster
  const route = routeRequest(query, { fen, hasGameHistory: !!conversation_id });
  console.log(`[chat/stream] route=${route}, query="${query.substring(0, 50)}..."`);

  try {
    let fullResponse = "";

    // Route based on intelligent decision
    if (route === 'chesster' && isChessterAvailable()) {
      fullResponse = await handleClawdbot(userId, fen, query, sendEvent);
    } else {
      fullResponse = await handleMastra(fen, query, context_type, sendEvent);
    }

    // Save conversation to Python backend (fire-and-forget)
    saveConversation(authHeader, fen, query, fullResponse, conversation_id, context_type).catch(
      (err) => console.error("[chat/stream] Failed to save conversation:", err)
    );

    // Send completion
    const tokensUsed = Math.ceil(fullResponse.length / 4);
    sendEvent({ done: true, conversation_id: conversation_id || null, tokens_used: tokensUsed });
  } catch (error) {
    console.error(`[chat/stream] ${route} failed:`, error);

    // Try fallback chain
    try {
      const fallbackResponse = await handleFallback(route, userId, fen, query, context_type, authHeader, sendEvent);
      if (fallbackResponse) {
        const tokensUsed = Math.ceil(fallbackResponse.length / 4);
        sendEvent({ done: true, conversation_id: conversation_id || null, tokens_used: tokensUsed });

        saveConversation(authHeader, fen, query, fallbackResponse, conversation_id, context_type).catch(
          (err) => console.error("[chat/stream] Failed to save fallback conversation:", err)
        );
      } else {
        sendEvent({ error: "All response methods failed. Please try again." });
      }
    } catch (fallbackError) {
      console.error("[chat/stream] Fallback also failed:", fallbackError);
      sendEvent({ error: "All response methods failed. Please try again." });
    }
  }

  res.end();
}

/**
 * Handle via Mastra agent (with tools like Stockfish)
 */
async function handleMastra(
  fen: string,
  query: string,
  contextType: string,
  sendEvent: (data: Record<string, unknown>) => void
): Promise<string> {
  // Build position context
  let positionPrompt = "";
  try {
    const boardState = getBoardState(fen);
    if (boardState && boardState.validfen) {
      const prompter = new PositionPrompter(boardState);
      positionPrompt = prompter.generatePrompt();
    }
  } catch (err) {
    console.warn("[chat/stream] Could not generate position prompt:", err);
  }

  const enrichedQuery = positionPrompt
    ? `${query}\n\n${positionPrompt}`
    : query;

  // Determine mode from context_type
  const mode = contextType === "puzzle" ? "puzzle" : contextType === "game" ? "position" : "position";

  // Build RuntimeContext
  const runtimeContext = new RuntimeContext();
  runtimeContext.set("provider", MASTRA_PROVIDER);
  runtimeContext.set("model", MASTRA_MODEL);
  runtimeContext.set("apiKey", MASTRA_API_KEY);
  runtimeContext.set("mode", mode);
  runtimeContext.set("isRouted", MASTRA_IS_ROUTED);
  runtimeContext.set("lang", MASTRA_LANGUAGE);

  console.log(`[chat/stream] Mastra: provider=${MASTRA_PROVIDER}, model=${MASTRA_MODEL}, isRouted=${MASTRA_IS_ROUTED}`);

  // Stream from Mastra agent
  const streamResult = await chessChesster.stream(
    [{ role: "user", content: enrichedQuery }],
    { runtimeContext }
  );

  // Read the text stream and pipe as SSE
  let fullResponse = "";
  const reader = streamResult.textStream.getReader();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) {
      fullResponse += value;
      sendEvent({ delta: value });
    }
  }

  return fullResponse;
}

/**
 * Handle via Clawdbot gateway (personalized coaching)
 */
async function handleClawdbot(
  userId: string,
  fen: string,
  query: string,
  sendEvent: (data: Record<string, unknown>) => void
): Promise<string> {
  if (!isClawdbotAvailable()) {
    throw new Error("Clawdbot gateway not configured");
  }

  console.log(`[chat/stream] Routing to Clawdbot for user ${userId.substring(0, 8)}...`);

  const response = await callGateway(userId, {
    action: "chat",
    payload: { message: query, fen },
    timeout: 60000,
  });

  if (!response.success || !response.content) {
    throw new Error(response.error || "Clawdbot returned no content");
  }

  // Clawdbot is request-response, send full content as one chunk
  sendEvent({ delta: response.content });
  return response.content;
}

/**
 * Fallback chain: if primary route fails, try alternative routes
 */
async function handleFallback(
  failedRoute: string,
  userId: string,
  fen: string,
  query: string,
  contextType: string,
  authHeader: string,
  sendEvent: (data: Record<string, unknown>) => void
): Promise<string | null> {
  // If Chesster failed, try Mastra
  if (failedRoute === 'chesster') {
    try {
      console.log("[chat/stream] Chesster failed, falling back to Mastra...");
      return await handleMastra(fen, query, contextType, sendEvent);
    } catch (err) {
      console.warn("[chat/stream] Mastra fallback failed:", err);
    }
  }

  // If Mastra failed, try Chesster
  if (failedRoute === 'mastra' && isChessterAvailable()) {
    try {
      console.log("[chat/stream] Mastra failed, falling back to Chesster...");
      return await handleClawdbot(userId, fen, query, sendEvent);
    } catch (err) {
      console.warn("[chat/stream] Chesster fallback failed:", err);
    }
  }

  // Final fallback: Python backend (raw LLM, no tools)
  try {
    console.log("[chat/stream] Falling back to Python backend...");
    return await handlePythonBackend(fen, query, contextType, authHeader, sendEvent);
  } catch (err) {
    console.error("[chat/stream] Python backend fallback failed:", err);
  }

  return null;
}

/**
 * Fallback to Python backend (raw LLM, no tools)
 */
async function handlePythonBackend(
  fen: string,
  query: string,
  contextType: string,
  authHeader: string,
  sendEvent: (data: Record<string, unknown>) => void
): Promise<string> {
  const response = await fetch(`${PYTHON_BACKEND_URL}/api/chat/analysis/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authHeader ? { Authorization: authHeader } : {}),
    },
    body: JSON.stringify({ fen, query, context_type: contextType }),
  });

  if (!response.ok) {
    throw new Error(`Python backend returned ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body from Python backend");

  const decoder = new TextDecoder();
  let fullResponse = "";
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const data = JSON.parse(line.slice(6));
          if (data.delta) {
            fullResponse += data.delta;
            sendEvent({ delta: data.delta });
          }
          // Don't forward 'done' — the caller handles that
        } catch {
          // skip malformed lines
        }
      }
    }
  }

  return fullResponse;
}

/**
 * Save conversation to Python backend for persistence in Supabase
 */
async function saveConversation(
  _authHeader: string,
  _fen: string,
  _query: string,
  _response: string,
  _conversationId: string | null,
  _contextType: string
): Promise<void> {
  // TODO: Add lightweight save-only endpoint to Python backend
  // For now, conversation persistence happens when Python backend is used as fallback.
  // Mastra/Clawdbot responses are not persisted to Supabase yet.
  // This is acceptable as the primary goal is routing through tools.
}
