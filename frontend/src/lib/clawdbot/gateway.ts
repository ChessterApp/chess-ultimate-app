// frontend/src/lib/clawdbot/gateway.ts
// Clawdbot Gateway client using HTTP Tools Invoke API
import type { CoachingRequest, CoachingResponse } from './types';
import { getSessionKey, getUserWorkspace } from './workspace';

const GATEWAY_URL = process.env.CLAWDBOT_GATEWAY_URL || 'http://127.0.0.1:19789';
const GATEWAY_TOKEN = process.env.CLAWDBOT_GATEWAY_TOKEN || '';

const DEFAULT_TIMEOUTS: Record<string, number> = {
  'chat': 60000,
  'review-game': 120000,
  'generate-lesson': 120000,
  'get-progress': 30000,
  'update-profile': 30000,
  'log-chat': 10000,
  'log-activity': 10000,
  'get-memory': 30000
};

interface GatewayInvokeResponse {
  ok: boolean;
  result?: {
    content?: Array<{ type: string; text: string }>;
    details?: {
      runId: string;
      status: string;
      reply?: string;
      error?: string;
      sessionKey: string;
    };
  };
  error?: {
    type: string;
    message: string;
  };
}

export async function callGateway(
  userId: string,
  request: CoachingRequest
): Promise<CoachingResponse> {
  const sessionKey = getSessionKey(userId);
  const workspace = getUserWorkspace(userId);
  const prompt = buildPrompt(request, workspace);
  const timeout = request.timeout || DEFAULT_TIMEOUTS[request.action] || 60000;

  // Normalize URL (remove ws:// if present, ensure http://)
  let baseUrl = GATEWAY_URL;
  if (baseUrl.startsWith('ws://')) {
    baseUrl = baseUrl.replace('ws://', 'http://');
  } else if (baseUrl.startsWith('wss://')) {
    baseUrl = baseUrl.replace('wss://', 'https://');
  }
  
  const invokeUrl = `${baseUrl}/tools/invoke`;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    const response = await fetch(invokeUrl, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${GATEWAY_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        tool: 'sessions_send',
        args: {
          sessionKey,
          message: prompt,
          timeoutSeconds: Math.floor(timeout / 1000)
        }
      }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      if (response.status === 401) {
        return {
          success: false,
          error: 'Gateway authentication failed'
        };
      }
      if (response.status === 404) {
        return {
          success: false,
          error: 'Gateway tool not available (sessions_send not allowlisted)'
        };
      }
      return {
        success: false,
        error: `Gateway HTTP error: ${response.status}`
      };
    }

    const data: GatewayInvokeResponse = await response.json();

    if (!data.ok) {
      return {
        success: false,
        error: data.error?.message || 'Gateway request failed'
      };
    }

    // Extract response from result
    const details = data.result?.details;
    if (details?.status === 'ok') {
      return {
        success: true,
        content: details.reply || '',
        sessionKey
      };
    }

    if (details?.status === 'forbidden' || details?.status === 'error') {
      return {
        success: false,
        error: details.error || 'Gateway request forbidden'
      };
    }

    // Fallback: try to extract from content array
    const textContent = data.result?.content?.find(c => c.type === 'text');
    if (textContent) {
      try {
        const parsed = JSON.parse(textContent.text);
        if (parsed.reply) {
          return {
            success: true,
            content: parsed.reply,
            sessionKey
          };
        }
        if (parsed.error) {
          return {
            success: false,
            error: parsed.error
          };
        }
      } catch {
        // Not JSON, use as-is
        return {
          success: true,
          content: textContent.text,
          sessionKey
        };
      }
    }

    return {
      success: false,
      error: 'Unexpected gateway response format'
    };

  } catch (error) {
    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        return {
          success: false,
          error: 'Request timed out'
        };
      }
      return {
        success: false,
        error: `Gateway error: ${error.message}`
      };
    }
    return {
      success: false,
      error: 'Unknown gateway error'
    };
  }
}

function getMemoryContext(workspace: ReturnType<typeof getUserWorkspace>): string {
  return `
## Player Context (READ THESE FIRST)
- Player profile: ${workspace.profilePath}
- Recent activity logs: ${workspace.activityPath}/ (read latest files for context)
- Chat history: ${workspace.chatsPath}/ (read recent conversations)
- Activity summary: ${workspace.activityPath}/summary.json

Use this context to personalize your response. Reference specific past activities when relevant (e.g., "I see you worked on pin tactics yesterday").
`.trim();
}

function buildPrompt(request: CoachingRequest, workspace: ReturnType<typeof getUserWorkspace>): string {
  const { action, payload } = request;
  const memoryCtx = getMemoryContext(workspace);

  switch (action) {
    case 'chat':
      return `
${memoryCtx}

You are a chess coach. Respond helpfully and remember this is a personalized coaching conversation.

Player message: ${payload.message}
Current position (FEN): ${payload.fen || 'No position provided'}
`.trim();

    case 'review-game':
      return `
${memoryCtx}

Review this chess game and provide detailed analysis.

Save analysis to: ${workspace.gamesPath}/analysis/${new Date().toISOString().split('T')[0]}.md

Game (PGN):
${payload.pgn}

Player color: ${payload.color || 'white'}
Focus areas: ${(payload.focusAreas as string[])?.join(', ') || 'general improvement'}

After analysis, update ${workspace.profilePath} with any new insights about player strengths/weaknesses.
`.trim();

    case 'generate-lesson':
      return `
${memoryCtx}

Create a personalized chess lesson.

Read progress data: ${workspace.progressPath}/themes.json

Topic: ${payload.topic}
Difficulty: ${payload.difficulty || 'appropriate for player level'}

Save the lesson to: ${workspace.lessonsPath}/${String(payload.topic).replace(/\s+/g, '-').toLowerCase()}.md

Include:
1. Clear explanation of the concept
2. 3-5 example positions with solutions
3. Practice exercises
`.trim();

    case 'get-progress':
      return `
${memoryCtx}

Generate a progress report for this chess player.

Read progress data: ${workspace.progressPath}/

Summarize:
- Recent improvements
- Areas still needing work  
- Recommended next steps
- Encouragement based on progress
`.trim();

    case 'update-profile':
      return `
Update the player profile with new information.

Profile path: ${workspace.profilePath}

Updates to make:
${JSON.stringify(payload.updates, null, 2)}

Preserve existing information while incorporating updates naturally.
`.trim();

    case 'get-memory':
      return `
Read the following files and provide a JSON summary of the player's recent activity:
- ${workspace.profilePath}
- ${workspace.activityPath}/ (all recent files)
- ${workspace.chatsPath}/ (all recent files)
- ${workspace.progressPath}/puzzles.json
- ${workspace.progressPath}/themes.json

Return a JSON object with this structure (no markdown, just raw JSON):
{
  "recentChats": [{"date": "...", "topic": "...", "summary": "..."}],
  "puzzleStats": {"totalSolved": 0, "totalAttempted": 0, "currentRating": 0},
  "recentGames": [{"date": "...", "result": "...", "opponent": "..."}],
  "lessonsCompleted": [{"date": "...", "topic": "..."}],
  "currentGoals": ["..."],
  "coachInsight": "A brief personalized insight about the player's recent progress"
}

If files don't exist or are empty, return sensible defaults (zeros, empty arrays).
`.trim();

    case 'log-chat':
    case 'log-activity':
      return payload.message as string || '';

    default:
      return payload.message as string || 'Hello, I need coaching help.';
  }
}
