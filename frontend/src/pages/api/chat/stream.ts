import type { NextApiRequest, NextApiResponse } from "next";
import { chessChesster } from "@/server/mastra/agents";
import { getBoardState } from "@/server/mastra/tools/protocol/state";
import { RequestContext } from "@mastra/core/request-context";
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

/**
 * Simple language detection based on character scripts.
 * Returns language name for the Mastra system prompt.
 */
function detectLanguage(text: string): string {
  const cyrillic = (text.match(/[\u0400-\u04FF]/g) || []).length;
  const latin = (text.match(/[a-zA-Z]/g) || []).length;
  const total = cyrillic + latin;
  if (total === 0) return MASTRA_LANGUAGE;
  if (cyrillic / total > 0.5) return 'Russian';
  return MASTRA_LANGUAGE;
}

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

  // Helper functions for route metadata
  const getModelForRoute = (r: string) => {
    switch(r) {
      case 'mastra': return `${MASTRA_PROVIDER}/${MASTRA_MODEL}`;
      case 'chesster': case 'clawdbot': return 'anthropic/claude-sonnet-4-0';
      case 'python-backend': return 'openrouter/auto';
      default: return 'unknown';
    }
  };
  const getProviderForRoute = (r: string) => {
    switch(r) {
      case 'mastra': return MASTRA_IS_ROUTED ? 'openrouter' : MASTRA_PROVIDER;
      case 'chesster': case 'clawdbot': return 'chesster';
      case 'python-backend': return 'python-backend';
      default: return 'unknown';
    }
  };

  // Track which route actually answers (may change on fallback)
  let actualRoute: string = route;

  try {
    let fullResponse = "";

    // Always use Mastra (fast Gemini Flash), Clawdbot is fallback only
    fullResponse = await handleMastra(fen, query, context_type, sendEvent);

    // Save conversation to Python backend (fire-and-forget)
    saveConversation(authHeader, fen, query, fullResponse, conversation_id, context_type).catch(
      (err) => console.error("[chat/stream] Failed to save conversation:", err)
    );

    // Send completion with route metadata
    const tokensUsed = Math.ceil(fullResponse.length / 4);
    sendEvent({
      done: true,
      conversation_id: conversation_id || null,
      tokens_used: tokensUsed,
      route: actualRoute,
      model: getModelForRoute(actualRoute),
      provider: getProviderForRoute(actualRoute)
    });
  } catch (error) {
    console.error(`[chat/stream] ${route} failed:`, error);

    // Try fallback chain
    try {
      const fallbackResult = await handleFallback(route, userId, fen, query, context_type, authHeader, sendEvent);
      if (fallbackResult) {
        actualRoute = fallbackResult.route;
        const tokensUsed = Math.ceil(fallbackResult.text.length / 4);
        sendEvent({
          done: true,
          conversation_id: conversation_id || null,
          tokens_used: tokensUsed,
          route: actualRoute,
          model: getModelForRoute(actualRoute),
          provider: getProviderForRoute(actualRoute)
        });

        saveConversation(authHeader, fen, query, fallbackResult.text, conversation_id, context_type).catch(
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
  const requestContext = new RequestContext();
  requestContext.set("provider", MASTRA_PROVIDER);
  requestContext.set("model", MASTRA_MODEL);
  requestContext.set("apiKey", MASTRA_API_KEY);
  requestContext.set("mode", mode);
  requestContext.set("isRouted", MASTRA_IS_ROUTED);
  const detectedLang = detectLanguage(query);
  requestContext.set("lang", detectedLang);

  console.log(`[chat/stream] Mastra: provider=${MASTRA_PROVIDER}, model=${MASTRA_MODEL}, isRouted=${MASTRA_IS_ROUTED}, lang=${detectedLang}`);

  // Stream from Mastra agent
  const streamResult = await chessChesster.stream(
    [{ role: "user", content: enrichedQuery }],
    { requestContext }
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

  const detectedLang = detectLanguage(query);
  console.log(`[chat/stream] Routing to Clawdbot for user ${userId.substring(0, 8)}..., lang=${detectedLang}`);

  const langHint = detectedLang !== 'English'
    ? `\n[User is writing in ${detectedLang}. Please respond in ${detectedLang}.]`
    : '';
  const response = await callGateway(userId, {
    action: "chat",
    payload: { message: query + langHint, fen },
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
): Promise<{ text: string; route: string } | null> {
  // Mastra failed, try Clawdbot as fallback
  if (isChessterAvailable()) {
    try {
      console.log("[chat/stream] Mastra failed, falling back to Clawdbot...");
      const text = await handleClawdbot(userId, fen, query, sendEvent);
      return { text, route: 'clawdbot' };
    } catch (err) {
      console.warn("[chat/stream] Clawdbot fallback also failed:", err);
    }
  }

  // Python backend removed from fallback chain — requires Clerk auth
  // which is fragile, and its LLM capabilities are worse than Clawdbot/Mastra.

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
