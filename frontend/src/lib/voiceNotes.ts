/**
 * Per-move voice notes: a note belongs to one move of a saved game, addressed by
 * the move's node_path — its SAN path from the start position joined by single
 * spaces ('e4 e5 Nf3'). SAN never contains spaces, and the path survives PGN
 * re-parsing and main-line promotion, so the PGN itself never carries audio.
 */
import type { OpeningNode } from '@/hooks/useOpeningRepertoire';

export const VOICE_NOTE_MAX_SEC = 120;

/** node id → node_path for every move in the tree (the root has none). */
export function nodePathMap(root: OpeningNode): Map<string, string> {
  const paths = new Map<string, string>();
  const walk = (node: OpeningNode, prefix: string) => {
    for (const child of node.children || []) {
      if (!child.move_san) continue;
      const path = prefix ? `${prefix} ${child.move_san}` : child.move_san;
      paths.set(child.id, path);
      walk(child, path);
    }
  };
  walk(root, '');
  return paths;
}

/** True if `path` is the move at `prefix` or any move after it in its line. */
export function pathCovers(prefix: string, path: string): boolean {
  return path === prefix || path.startsWith(`${prefix} `);
}

export function formatDuration(totalSec: number): string {
  const sec = Math.max(0, Math.floor(totalSec));
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
}
