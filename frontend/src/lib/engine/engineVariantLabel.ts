import type { EngineVariant } from '@/hooks/useReplayStockfish';

const ENGINE_LABELS: Record<Exclude<EngineVariant, null>, string> = {
  'sf17.1': 'Stockfish 17.1',
  sf17: 'Stockfish 17',
  sf16: 'Stockfish 16',
  sf11: 'Stockfish 11',
};

/** Display label for an engine variant ("Stockfish" until one is active). */
export function engineVariantLabel(variant: EngineVariant): string {
  return variant ? ENGINE_LABELS[variant] : 'Stockfish';
}
