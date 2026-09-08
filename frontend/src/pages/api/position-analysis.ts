import type { NextApiRequest, NextApiResponse } from "next";
import { getBoardState } from "@/server/mastra/tools/protocol/state";
import { PositionPrompter } from "@/server/mastra/tools/protocol/positionPrompter";

/**
 * Position analysis service — exposes Mastra's CCP (PositionPrompter) over HTTP
 * so external callers (e.g. Hermes) can reuse the exact same `<detailed_board_analysis>`
 * fusion that the in-app coach uses. Purely additive; reuses Mastra's
 * PositionPrompter directly.
 *
 * POST { fen: string } -> { valid: boolean, board_analysis: string }
 */
export default function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ error: "Method not allowed" });
  }

  const fen = (req.body as { fen?: unknown } | undefined)?.fen;
  if (typeof fen !== "string" || fen.trim() === "") {
    return res.status(400).json({ error: "fen is required and must be a non-empty string" });
  }

  try {
    const boardState = getBoardState(fen);
    if (!boardState || !boardState.validfen) {
      return res.status(200).json({ valid: false, board_analysis: "" });
    }
    const board_analysis = new PositionPrompter(boardState).generatePrompt();
    return res.status(200).json({ valid: true, board_analysis });
  } catch (err) {
    return res.status(500).json({
      error: "Failed to generate position analysis",
      details: err instanceof Error ? err.message : String(err),
    });
  }
}
