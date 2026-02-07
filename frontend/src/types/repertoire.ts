/**
 * Opening Repertoire Types
 * Defines data structures for user opening collections
 */

/**
 * User's saved opening in their repertoire
 */
export interface RepertoireOpening {
  id: string;
  user_id: string;
  opening_id: string;
  opening_name: string;
  eco_code?: string;
  color: 'white' | 'black' | 'both';
  first_moves?: string;
  notes?: string;
  tags?: string[];
  favorite: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * Custom variation for an opening
 */
export interface OpeningVariation {
  id: string;
  repertoire_id: string;
  variation_name: string;
  moves: string;
  notes?: string;
  created_at: string;
}

/**
 * Opening search result from backend database
 */
export interface OpeningSearchResult {
  id: string;
  name: string;
  eco_code: string;
  moves: string;
  description?: string;
  popularity?: number;
}

/**
 * API request/response for adding opening
 */
export interface AddOpeningRequest {
  opening_id: string;
  opening_name: string;
  color: 'white' | 'black' | 'both';
  eco_code?: string;
  first_moves?: string;
  notes?: string;
  tags?: string[];
}

/**
 * API request/response for updating opening
 */
export interface UpdateOpeningRequest {
  notes?: string;
  tags?: string[];
  favorite?: boolean;
}

/**
 * API request/response for adding variation
 */
export interface AddVariationRequest {
  variation_name: string;
  moves: string;
  notes?: string;
}

/**
 * Repertoire state and operations
 */
export interface RepertoireState {
  repertoire: RepertoireOpening[];
  loading: boolean;
  error: string | null;
}

/**
 * Repertoire API operations
 */
export interface RepertoireOperations {
  fetchRepertoire: (color?: 'white' | 'black') => Promise<void>;
  addToRepertoire: (opening: AddOpeningRequest) => Promise<RepertoireOpening>;
  updateOpening: (openingId: string, updates: UpdateOpeningRequest) => Promise<void>;
  removeFromRepertoire: (openingId: string) => Promise<void>;
  addVariation: (repertoireId: string, variation: AddVariationRequest) => Promise<OpeningVariation>;
  getVariations: (repertoireId: string) => Promise<OpeningVariation[]>;
}

/**
 * Combined hook interface
 */
export interface UseRepertoireReturn extends RepertoireState, RepertoireOperations {}
