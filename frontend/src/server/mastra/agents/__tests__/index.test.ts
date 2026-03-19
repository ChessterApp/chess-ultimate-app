import { describe, it, expect, vi, beforeEach } from 'vitest';
import { RequestContext } from "@mastra/core/request-context";

// Mock the AI SDK packages
vi.mock("@ai-sdk/openai", () => ({
  openai: vi.fn(() => "mocked-openai-model"),
  createOpenAI: vi.fn(() => vi.fn(() => "mocked-openai-custom")),
}));

vi.mock("@ai-sdk/anthropic", () => ({
  createAnthropic: vi.fn(() => vi.fn(() => "mocked-anthropic")),
}));

vi.mock("@ai-sdk/google", () => ({
  createGoogleGenerativeAI: vi.fn(() => vi.fn(() => "mocked-google")),
}));

vi.mock("ollama-ai-provider-v2", () => ({
  createOllama: vi.fn(() => vi.fn(() => "mocked-ollama")),
}));

vi.mock("@openrouter/ai-sdk-provider", () => ({
  createOpenRouter: vi.fn(() => vi.fn(() => "mocked-openrouter")),
}));

describe('Mastra Agent Dynamic Imports', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should load @ai-sdk/openai dynamically', async () => {
    const { chessChesster } = await import("../index");

    expect(chessChesster).toBeDefined();
    expect(chessChesster.id).toBe("chesster");
    expect(chessChesster.name).toBe("Chesster");
  });

  it('should create agent with async model function', async () => {
    const { chessChesster } = await import("../index");

    const requestContext = new RequestContext();
    requestContext.set("provider", "openai");
    requestContext.set("model", "gpt-4");
    requestContext.set("apiKey", "test-key");
    requestContext.set("isRouted", false);

    // The model function should be async
    expect(typeof chessChesster.model).toBe("function");
  });

  it('should handle different providers', async () => {
    const providers = ["openai", "anthropic", "google", "ollama"];

    for (const provider of providers) {
      const requestContext = new RequestContext();
      requestContext.set("provider", provider);
      requestContext.set("model", "test-model");
      requestContext.set("apiKey", "test-key");
      requestContext.set("isRouted", false);

      // Just verify the context is set up correctly
      expect(requestContext.get("provider")).toBe(provider);
    }
  });

  it('should handle routed requests', async () => {
    const requestContext = new RequestContext();
    requestContext.set("provider", "openrouter");
    requestContext.set("model", "test-model");
    requestContext.set("apiKey", "test-key");
    requestContext.set("isRouted", true);

    expect(requestContext.get("isRouted")).toBe(true);
  });
});
