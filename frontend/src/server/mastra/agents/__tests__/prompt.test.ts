/**
 * @vitest-environment node
 */
import { describe, it, expect, vi } from 'vitest';
import { RequestContext } from '@mastra/core/request-context';

vi.mock('@ai-sdk/openai', () => ({
  openai: vi.fn(() => 'mocked-openai-model'),
  createOpenAI: vi.fn(() => vi.fn(() => 'mocked-openai-custom')),
}));
vi.mock('@ai-sdk/anthropic', () => ({
  createAnthropic: vi.fn(() => vi.fn(() => 'mocked-anthropic')),
}));
vi.mock('@ai-sdk/google', () => ({
  createGoogleGenerativeAI: vi.fn(() => vi.fn(() => 'mocked-google')),
}));
vi.mock('ollama-ai-provider-v2', () => ({
  createOllama: vi.fn(() => vi.fn(() => 'mocked-ollama')),
}));
vi.mock('@openrouter/ai-sdk-provider', () => ({
  createOpenRouter: vi.fn(() => vi.fn(() => 'mocked-openrouter')),
}));

describe('createAgentInstruction — APP_NAME substitution', () => {
  it('renders "Sir Chesster" on apex (no orgName)', async () => {
    const { createAgentInstruction } = await import('../index');
    const ctx = new RequestContext();
    ctx.set('mode', 'position');
    ctx.set('lang', 'English');
    const prompt = createAgentInstruction(ctx);
    expect(prompt).toContain('You are Sir Chesster');
    expect(prompt).not.toContain('{APP_NAME}');
  });

  it('renders "<Brand> Coach" on tenants (orgName set)', async () => {
    const { createAgentInstruction } = await import('../index');
    const ctx = new RequestContext();
    ctx.set('mode', 'position');
    ctx.set('lang', 'English');
    ctx.set('orgName', 'Chess Empire');
    const prompt = createAgentInstruction(ctx);
    expect(prompt).toContain('You are Chess Empire Coach');
    expect(prompt).not.toContain('{APP_NAME}');
    expect(prompt).not.toContain('Sir Chesster');
  });

  it('falls back to "Sir Chesster" when orgName is literally "Chesster"', async () => {
    const { createAgentInstruction } = await import('../index');
    const ctx = new RequestContext();
    ctx.set('mode', 'position');
    ctx.set('lang', 'English');
    ctx.set('orgName', 'Chesster');
    const prompt = createAgentInstruction(ctx);
    expect(prompt).toContain('You are Sir Chesster');
  });

  it('applies APP_NAME substitution in Q/A (question) mode too', async () => {
    const { createAgentInstruction } = await import('../index');
    const ctx = new RequestContext();
    ctx.set('mode', 'question');
    ctx.set('lang', 'English');
    ctx.set('orgName', 'Chess Empire');
    const prompt = createAgentInstruction(ctx);
    expect(prompt).toContain('You are Chess Empire Coach in Q/A training mode');
    expect(prompt).not.toContain('{APP_NAME}');
  });
});
