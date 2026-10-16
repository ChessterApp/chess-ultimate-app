// Define the structure of your ECO data
interface EcoEntry {
  name: string;
  moves: string;
  eco?: string;
}

// Type for the entire ECO database
type EcoDatabase = Record<string, EcoEntry>;

/**
 * Check if a given FEN exists in the ECO database
 * @param fen - The FEN string to check
 * @param ecoDatabase - The ECO database object (defaults to imported data)
 * @returns The ECO entry if found, null if not found
 */
export function checkFenInEco(fen: string, ecoDatabase: EcoDatabase): EcoEntry | null {
  return ecoDatabase[fen] || null;
}

/**
 * Check if a FEN exists and return boolean
 * @param fen - The FEN string to check
 * @param ecoDatabase - The ECO database object (defaults to imported data)
 * @returns true if FEN exists, false otherwise
 */
export function fenExists(fen: string, ecoDatabase: EcoDatabase): boolean {
  return fen in ecoDatabase;
}

// Runtime-fetched ECO database cache (JSON files served from /data/eco/)
let _ecoCache: EcoDatabase[] | null = null;

const ECO_FILES = ['ecoA', 'ecoB', 'ecoC', 'ecoD', 'ecoE', 'eco_interpolated'] as const;

async function loadAllDatabases(): Promise<EcoDatabase[]> {
  if (_ecoCache) return _ecoCache;
  const results = await Promise.all(
    ECO_FILES.map(name =>
      fetch(`/data/eco/${name}.json`).then(r => r.json() as Promise<EcoDatabase>)
    )
  );
  _ecoCache = results;
  return _ecoCache;
}

export async function isFenInAllDatabases(fen: string): Promise<boolean> {
  const databases = await loadAllDatabases();
  return databases.some(db => fenExists(fen, db));
}

// Position key without the move clocks, so transpositions match.
const positionKey = (fen: string) => fen.split(' ').slice(0, 4).join(' ');

let _ecoByPosition: Map<string, EcoEntry> | null = null;

/** ECO code + name of the named opening at this exact position, if any. */
export async function findEcoOpening(fen: string): Promise<{ eco: string | null; name: string } | null> {
  if (!_ecoByPosition) {
    const index = new Map<string, EcoEntry>();
    for (const db of await loadAllDatabases()) {
      for (const [key, entry] of Object.entries(db)) {
        if (!index.has(positionKey(key))) index.set(positionKey(key), entry);
      }
    }
    _ecoByPosition = index;
  }
  const entry = _ecoByPosition.get(positionKey(fen));
  return entry ? { eco: entry.eco ?? null, name: entry.name } : null;
}
