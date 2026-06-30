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

// Resolve the persona name the agent introduces itself with.
// Apex (orgName="Chesster" or unset) keeps the "Sir Chesster" persona;
// tenants render as "<Brand> Coach" per the locked decision.
export function resolveAgentAppName(orgName?: string | null): string {
  if (!orgName || orgName === "Chesster") return "Sir Chesster";
  return `${orgName} Coach`;
}

export function createAgentInstruction(requestContext: RequestContext) {
  const lang = (requestContext.get("lang") as string) || "English";
  const mode = (requestContext.get("mode") as string) || "position";
  const orgName = (requestContext.get("orgName") as string | undefined) || undefined;
  const appName = resolveAgentAppName(orgName);

  const fillPlaceholders = (prompt: string) =>
    prompt.split("{APP_NAME}").join(appName).replace("ENGLISH", lang);

  switch (mode) {
    case "position":
      return fillPlaceholders(agineSystemPrompt);
    case "puzzle":
      return fillPlaceholders(aginePuzzleSystemPrompt);
    case "annotation":
      return fillPlaceholders(chessChessterAnnoPrompt);
    case "question":
      return fillPlaceholders(agineQuestionMode);
    default:
      return fillPlaceholders(agineSystemPrompt);
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
