import type { NextApiRequest, NextApiResponse } from "next";
import { chessChesster } from "@/server/mastra/agents";
import { getBoardState } from "@/server/mastra/tools/protocol/state";
import { RequestContext } from "@mastra/core/request-context";
import { PositionPrompter } from "@/server/mastra/tools/protocol/positionPrompter";
// Clerk authentication disabled for local development
// import { getAuth } from "@clerk/nextjs/server";
import { ApiSetting } from "@/server/mastra/agents/types";

interface ResponseData {
  message: string;
  maxTokens?: number;
  provider?: string;
  model?: string;
}

interface ErrorResponseData {
  message: string;
  maxTokens?: number;
  provider?: string;
  model?: string;
  stack?: string;
}

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  if (
    typeof error === "object" &&
    error !== null &&
    "message" in error &&
    typeof error.message === "string"
  ) {
    return error.message;
  }

  if (
    typeof error === "object" &&
    error !== null &&
    "responseBody" in error &&
    typeof error.responseBody === "string"
  ) {
    try {
      const parsed = JSON.parse(error.responseBody) as {
        error?: { message?: string };
      };
      if (parsed?.error?.message) {
        return parsed.error.message;
      }
    } catch {}
  }

  if (
    typeof error === "object" &&
    error !== null &&
    "error" in error &&
    typeof error.error === "object" &&
    error.error !== null &&
    "message" in error.error &&
    typeof error.error.message === "string"
  ) {
    return error.error.message;
  }

  return String(error);
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<ResponseData | ErrorResponseData>
) {
  if (req.method !== "POST") {
    return res.status(405).json({
      message: "Method not allowed",
    });
  }

  try {
    // const { isAuthenticated } = getAuth(req);
    // Simulated authentication for no-auth mode
    const isAuthenticated = true;

    if (!isAuthenticated) {
      return res.status(401).json({ message: "Unauthorized" });

    }



    const { query, fen, mode, apiSettings } = req.body;

    const rawApiSettings = apiSettings as ApiSetting;

    if (!rawApiSettings || !rawApiSettings.provider || !rawApiSettings.model) {
      return res.status(400).json({
        message: "API settings are required (provider, model)",
      });
    }

    if (rawApiSettings.provider !== "ollama" && !rawApiSettings.apiKey) {
      return res.status(400).json({
        message: "API key is required for non-Ollama providers",
      });
    }

    if (rawApiSettings.provider == "ollama" && !rawApiSettings.ollamaBaseUrl) {
      return res.status(400).json({
        message: "Ollama base ngrok endpoint required, please set up the url",
      });
    }

    if (!query || typeof query !== "string") {
      return res.status(400).json({
        message:
          'Missing or invalid "query" field in body (must be a non-empty string)',
      });
    }

    if (!fen || typeof fen !== "string") {
      return res.status(400).json({
        message:
          'Missing or invalid "fen" field in body (must be a non-empty string)',
      });
    }

    if (!mode || typeof mode !== "string") {
      return res.status(400).json({
        message:
          'Missing or invalid "mode" field in body (must be a non-empty string)',
      });
    }

    console.log("Processing FEN:", fen);

    let boardState;
    try {
      boardState = getBoardState(fen);
    } catch (boardStateError) {
      console.error("Error getting board state:", boardStateError);
      return res.status(400).json({
        message: "Error processing FEN string",
      });
    }

    if (!boardState || !boardState.validfen) {
      console.log("Invalid FEN provided:", fen);
      return res.status(400).json({
        message: "Invalid FEN string provided",
      });
    }

    let positionPrompt;
    try {
      const prompter = new PositionPrompter(boardState);
      positionPrompt = prompter.generatePrompt();
    } catch (promptError) {
      console.error("Error generating state prompt:", promptError);
      return res.status(500).json({
        message: "Error processing board state",
      });
    }

    const aginePromptInject = `${query} \n ${positionPrompt}`;
    const requestContext = new RequestContext();
    requestContext.set("provider", apiSettings.provider);
    requestContext.set("model", apiSettings.model);
    requestContext.set("apiKey", apiSettings.apiKey || "");
    requestContext.set("mode", mode);
    requestContext.set("isRouted", apiSettings.isRouted)
    requestContext.set("lang", apiSettings.language);

    if (apiSettings.provider === "ollama") {
      if (apiSettings.ollamaBaseUrl) {
        requestContext.set("ollamaBaseUrl", apiSettings.ollamaBaseUrl);
      }
    }

    let response;
    let maxTokens;

    try {
      response = await chessChesster.generate(
        [{ role: "user", content: aginePromptInject }],
        {
          requestContext,
        }
      );
      maxTokens = response.usage.totalTokens || 0;
    } catch (agentError) {
      console.error("Error from chess agent:", agentError);

      const errorMessage = extractErrorMessage(agentError);

      return res.status(500).json({
        message: errorMessage,
        maxTokens,
        provider: apiSettings.provider,
        model: apiSettings.model,
      });
    }

    return res.status(200).json({
      message: response.text,
      maxTokens,
      provider: apiSettings.provider,
      model: apiSettings.model,
    });
  } catch (error) {
    console.error("Unexpected error in API route:", error);

    return res.status(500).json({
      message: "Internal server error",
      ...(process.env.NODE_ENV === "development" && { stack: String(error) }),
    });
  }
}
