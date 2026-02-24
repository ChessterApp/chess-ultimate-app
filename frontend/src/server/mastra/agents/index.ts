"use server";
import { openai } from "@ai-sdk/openai";
import { Agent } from "@mastra/core/agent";
import { createAnthropic } from "@ai-sdk/anthropic";
import { createGoogleGenerativeAI } from "@ai-sdk/google";
import { createOpenAI } from "@ai-sdk/openai";
import { createOllama } from "ollama-ai-provider-v2";
import { RequestContext } from "@mastra/core/request-context";
import { createOpenRouter} from "@openrouter/ai-sdk-provider";
import {
  aginePuzzleSystemPrompt,
  agineQuestionMode,
  agineSystemPrompt,
  chessChessterAnnoPrompt,
} from "./prompt";
import { OpenAIModel, GoogleModel, AnthropicModel, OllamaModel, ChessterCloudModel } from "./types";
import { ChessterTools } from "../tools";

function createModelFromRouter(requestContext: RequestContext) {
  const provider = requestContext.get("provider") as string;
  const modelName = requestContext.get("model") as string;
  const apiKey = requestContext.get("apiKey") as string;

  const openRouter = createOpenRouter({
    apiKey: apiKey,
  });

  return openRouter(`${provider}/${modelName}`);
}

function createChessterCloudModel(requestContext: RequestContext) {
  const modelName = requestContext.get("model") as string;

  const apiKey = process.env.AGINE_KEY;

  const agineCloudRouter = createOpenRouter({
    apiKey: apiKey
  })

  return agineCloudRouter(`${modelName}:free` as ChessterCloudModel);
}

function createAgentInstruction(requestContext: RequestContext) {
  const lang = (requestContext.get("lang") as string) || "English";
  const mode = (requestContext.get("mode") as string) || "position";

  switch (mode) {
    case "position":
      return agineSystemPrompt.replace("ENGLISH", lang);
    case "puzzle":
      return aginePuzzleSystemPrompt.replace("ENGLISH", lang);
    case "annotation":
      return chessChessterAnnoPrompt.replace("ENGLISH", lang);
    case "question":
      return agineQuestionMode.replace("ENGLISH", lang);
    default:
      return agineSystemPrompt.replace("ENGLISH", lang);
  }
}

function createModelFromContext(requestContext: RequestContext) {
  const provider = requestContext.get("provider") as string;
  const modelName = requestContext.get("model") as string;
  const apiKey = requestContext.get("apiKey") as string;
  const isRouted = requestContext.get("isRouted") as boolean;
  const ollamaBaseUrl = requestContext.get("ollamaBaseUrl") as
    | string
    | undefined;

  if(isRouted){
    return createModelFromRouter(requestContext);
  }     

  switch (provider) {
    case "openai":
      const openAi = createOpenAI({
        apiKey: apiKey,
      });
      return openAi(modelName as OpenAIModel);

    case "anthropic":
      const claude = createAnthropic({
        apiKey: apiKey,
      });
      return claude(modelName as AnthropicModel);

    case "google":
      const gemini = createGoogleGenerativeAI({
        apiKey: apiKey,
      });
      return gemini(modelName as GoogleModel);

    case "ollama":
      const ollama = createOllama({
        baseURL: ollamaBaseUrl || "http://localhost:11434/api",
      });
      return ollama(modelName as OllamaModel);
    case "agineCloud": 
      return createChessterCloudModel(requestContext);

    default:
      return openai("gpt-4o-mini");
  }
}

export const chessChesster = new Agent({
  id: "chesster",
  name: "Chesster",
  instructions: ({ requestContext }) => createAgentInstruction(requestContext),
  model: ({ requestContext }) => createModelFromContext(requestContext),
  tools: ChessterTools,
});
