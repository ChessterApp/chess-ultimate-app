"use server";
import { Agent } from "@mastra/core/agent";
import { RequestContext } from "@mastra/core/request-context";
import {
  aginePuzzleSystemPrompt,
  agineQuestionMode,
  agineSystemPrompt,
  chessChessterAnnoPrompt,
} from "./prompt";
import { OpenAIModel, GoogleModel, AnthropicModel, OllamaModel, ChessterCloudModel } from "./types";
import { ChessterTools } from "../tools";

async function createModelFromRouter(requestContext: RequestContext) {
  const provider = requestContext.get("provider") as string;
  const modelName = requestContext.get("model") as string;
  const apiKey = requestContext.get("apiKey") as string;

  const { createOpenRouter } = await import("@openrouter/ai-sdk-provider");
  const openRouter = createOpenRouter({
    apiKey: apiKey,
  });

  return openRouter(`${provider}/${modelName}`);
}

async function createChessterCloudModel(requestContext: RequestContext) {
  const modelName = requestContext.get("model") as string;

  const apiKey = process.env.AGINE_KEY;

  const { createOpenRouter } = await import("@openrouter/ai-sdk-provider");
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

async function createModelFromContext(requestContext: RequestContext) {
  const provider = requestContext.get("provider") as string;
  const modelName = requestContext.get("model") as string;
  const apiKey = requestContext.get("apiKey") as string;
  const isRouted = requestContext.get("isRouted") as boolean;
  const ollamaBaseUrl = requestContext.get("ollamaBaseUrl") as
    | string
    | undefined;

  if(isRouted){
    return await createModelFromRouter(requestContext);
  }

  switch (provider) {
    case "openai":
      const { createOpenAI } = await import("@ai-sdk/openai");
      const openAi = createOpenAI({
        apiKey: apiKey,
      });
      return openAi(modelName as OpenAIModel);

    case "anthropic":
      const { createAnthropic } = await import("@ai-sdk/anthropic");
      const claude = createAnthropic({
        apiKey: apiKey,
      });
      return claude(modelName as AnthropicModel);

    case "google":
      const { createGoogleGenerativeAI } = await import("@ai-sdk/google");
      const gemini = createGoogleGenerativeAI({
        apiKey: apiKey,
      });
      return gemini(modelName as GoogleModel);

    case "ollama":
      const { createOllama } = await import("ollama-ai-provider-v2");
      const ollama = createOllama({
        baseURL: ollamaBaseUrl || "http://localhost:11434/api",
      });
      return ollama(modelName as OllamaModel);
    case "agineCloud":
      return await createChessterCloudModel(requestContext);

    default:
      const { openai } = await import("@ai-sdk/openai");
      return openai("gpt-4o-mini");
  }
}

export const chessChesster = new Agent({
  id: "chesster",
  name: "Chesster",
  instructions: ({ requestContext }) => createAgentInstruction(requestContext),
  model: async ({ requestContext }) => await createModelFromContext(requestContext),
  tools: ChessterTools,
});
