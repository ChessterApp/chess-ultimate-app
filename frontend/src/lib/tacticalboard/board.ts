// Re-export of the canonical tactical-board implementation.
//
// This file previously held a standalone `Board` class that was a copy-paste
// fork of `TacticlBoard` (src/server/mastra/tools/themes/tacticalBoard.ts —
// the superset, additionally exposing calculateTacticalScore). Both were pure
// chess.js with no server-only deps, so we keep the single mastra version and
// alias it here as `Board` to preserve the existing client import path used by
// AiChessboard.
export { TacticlBoard as Board } from "@/server/mastra/tools/themes/tacticalBoard";
