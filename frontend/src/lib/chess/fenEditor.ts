// Piece representation used by the board editor (colour + piece letter)
export type PieceCode =
  | "wP" | "wN" | "wB" | "wR" | "wQ" | "wK"
  | "bP" | "bN" | "bB" | "bR" | "bQ" | "bK";

export type EditorPieces = Record<string, PieceCode>;

export interface CastlingRights {
  whiteOO: boolean;   // White O-O (kingside)
  whiteOOO: boolean;  // White O-O-O (queenside)
  blackOO: boolean;   // Black O-O (kingside)
  blackOOO: boolean;  // Black O-O-O (queenside)
}

export interface EditorState {
  pieces: EditorPieces;
  turn: "w" | "b";
  castling: CastlingRights;
  enPassant: string; // "-" or square like "e3"
  orientation: "white" | "black";
  selected: "pointer" | "trash" | PieceCode;
}

// Map from piece letter in FEN to editor piece code
const FEN_TO_PIECE: Record<string, PieceCode> = {
  P: "wP", N: "wN", B: "wB", R: "wR", Q: "wQ", K: "wK",
  p: "bP", n: "bN", b: "bB", r: "bR", q: "bQ", k: "bK",
};

const PIECE_TO_FEN: Record<string, string> = {
  wP: "P", wN: "N", wB: "B", wR: "R", wQ: "Q", wK: "K",
  bP: "p", bN: "n", bB: "b", bR: "r", bQ: "q", bK: "k",
};

const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"];
const RANKS = ["8", "7", "6", "5", "4", "3", "2", "1"];

export const STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
export const EMPTY_FEN = "8/8/8/8/8/8/8/8 w - - 0 1";

export const PRESET_POSITIONS: Record<string, string> = {
  startingPosition: STARTING_FEN,
  emptyBoard: EMPTY_FEN,
  kingPawnVsKing: "8/8/8/8/4P3/8/8/4K2k w - - 0 1",
  rookEndgame: "8/8/8/8/8/8/4K3/R6k w - - 0 1",
  queenVsRook: "8/8/8/8/8/8/4K3/Q5rk w - - 0 1",
};

/**
 * Parse a FEN string into an EditorPieces map and metadata
 */
export function fenToPieces(fen: string): {
  pieces: EditorPieces;
  turn: "w" | "b";
  castling: CastlingRights;
  enPassant: string;
} {
  const parts = fen.trim().split(/\s+/);
  const placement = parts[0] || "8/8/8/8/8/8/8/8";
  const turn = (parts[1] === "b" ? "b" : "w") as "w" | "b";
  const castlingStr = parts[2] || "-";
  const enPassant = parts[3] || "-";

  const pieces: EditorPieces = {};
  const ranks = placement.split("/");

  for (let rankIdx = 0; rankIdx < 8; rankIdx++) {
    const rankStr = ranks[rankIdx] || "8";
    let fileIdx = 0;
    for (const ch of rankStr) {
      if (ch >= "1" && ch <= "8") {
        fileIdx += parseInt(ch);
      } else {
        const square = `${FILES[fileIdx]}${RANKS[rankIdx]}`;
        const piece = FEN_TO_PIECE[ch];
        if (piece) {
          pieces[square] = piece;
        }
        fileIdx++;
      }
    }
  }

  const castling: CastlingRights = {
    whiteOO: castlingStr.includes("K"),
    whiteOOO: castlingStr.includes("Q"),
    blackOO: castlingStr.includes("k"),
    blackOOO: castlingStr.includes("q"),
  };

  return { pieces, turn, castling, enPassant };
}

/**
 * Generate a FEN string from editor state
 */
export function piecesToFen(
  pieces: EditorPieces,
  turn: "w" | "b",
  castling: CastlingRights,
  enPassant: string
): string {
  const rankStrs: string[] = [];

  for (let rankIdx = 0; rankIdx < 8; rankIdx++) {
    let rankStr = "";
    let emptyCount = 0;

    for (let fileIdx = 0; fileIdx < 8; fileIdx++) {
      const square = `${FILES[fileIdx]}${RANKS[rankIdx]}`;
      const piece = pieces[square];

      if (piece) {
        if (emptyCount > 0) {
          rankStr += emptyCount;
          emptyCount = 0;
        }
        rankStr += PIECE_TO_FEN[piece] || "?";
      } else {
        emptyCount++;
      }
    }

    if (emptyCount > 0) {
      rankStr += emptyCount;
    }
    rankStrs.push(rankStr);
  }

  let castlingStr = "";
  if (castling.whiteOO) castlingStr += "K";
  if (castling.whiteOOO) castlingStr += "Q";
  if (castling.blackOO) castlingStr += "k";
  if (castling.blackOOO) castlingStr += "q";
  if (!castlingStr) castlingStr = "-";

  return `${rankStrs.join("/")} ${turn} ${castlingStr} ${enPassant || "-"} 0 1`;
}

/**
 * Compute valid en passant squares based on pawn positions and turn
 */
export function getEnPassantOptions(pieces: EditorPieces, turn: "w" | "b"): string[] {
  const options: string[] = [];

  if (turn === "w") {
    // White to move: en passant target is on rank 6 (black pawn on rank 5)
    for (let f = 0; f < 8; f++) {
      const pawnSquare = `${FILES[f]}5`;
      const targetSquare = `${FILES[f]}6`;
      if (pieces[pawnSquare] === "bP") {
        // Check adjacent files for white pawns
        if (f > 0 && pieces[`${FILES[f - 1]}5`] === "wP") {
          options.push(targetSquare);
          continue;
        }
        if (f < 7 && pieces[`${FILES[f + 1]}5`] === "wP") {
          options.push(targetSquare);
        }
      }
    }
  } else {
    // Black to move: en passant target is on rank 3 (white pawn on rank 4)
    for (let f = 0; f < 8; f++) {
      const pawnSquare = `${FILES[f]}4`;
      const targetSquare = `${FILES[f]}3`;
      if (pieces[pawnSquare] === "wP") {
        if (f > 0 && pieces[`${FILES[f - 1]}4`] === "bP") {
          options.push(targetSquare);
          continue;
        }
        if (f < 7 && pieces[`${FILES[f + 1]}4`] === "bP") {
          options.push(targetSquare);
        }
      }
    }
  }

  return options;
}

/**
 * Auto-detect castling rights from piece positions.
 * Only enable castling if king and rook are on starting squares.
 */
export function computeCastlingAvailability(pieces: EditorPieces): {
  whiteOOPossible: boolean;
  whiteOOOPossible: boolean;
  blackOOPossible: boolean;
  blackOOOPossible: boolean;
} {
  return {
    whiteOOPossible: pieces["e1"] === "wK" && pieces["h1"] === "wR",
    whiteOOOPossible: pieces["e1"] === "wK" && pieces["a1"] === "wR",
    blackOOPossible: pieces["e8"] === "bK" && pieces["h8"] === "bR",
    blackOOOPossible: pieces["e8"] === "bK" && pieces["a8"] === "bR",
  };
}

/**
 * Validate board position for basic legality
 */
export function validatePosition(pieces: EditorPieces): {
  valid: boolean;
  errors: string[];
} {
  const errors: string[] = [];
  let whiteKings = 0;
  let blackKings = 0;

  for (const [square, piece] of Object.entries(pieces)) {
    if (piece === "wK") whiteKings++;
    if (piece === "bK") blackKings++;

    // Pawns cannot be on rank 1 or 8
    const rank = square[1];
    if ((piece === "wP" || piece === "bP") && (rank === "1" || rank === "8")) {
      errors.push(`Pawn on illegal rank: ${square}`);
    }
  }

  if (whiteKings !== 1) errors.push(`White must have exactly 1 king (found ${whiteKings})`);
  if (blackKings !== 1) errors.push(`Black must have exactly 1 king (found ${blackKings})`);

  return { valid: errors.length === 0, errors };
}

/**
 * Toggle piece color: white ↔ black
 */
export function togglePieceColor(piece: PieceCode): PieceCode {
  const color = piece[0] === "w" ? "b" : "w";
  return `${color}${piece[1]}` as PieceCode;
}

/**
 * Build-time asset version for cache-busting piece image URLs.
 * Changes on every build, ensuring stale cached responses (e.g. from before
 * CORP headers were added) are invalidated.
 */
const ASSET_VERSION = process.env.NEXT_PUBLIC_ASSET_VERSION || 'dev';

/**
 * Get the piece image source path for a given piece code and piece set.
 * Appends a build-time version query param to bust stale browser caches.
 */
export function getPieceImageSrc(pieceCode: PieceCode, pieceSet: string): string {
  const svgSets = ['cburnett', 'fritz'];
  // Map piece set keys to actual folder names (filesystem is case-sensitive)
  const folderMap: Record<string, string> = { cburnett: 'Cburnett', fritz: 'Fritz', Fritz: 'Fritz' };
  let src: string;
  if (!pieceSet || svgSets.includes(pieceSet.toLowerCase())) {
    const folder = folderMap[pieceSet] || pieceSet || 'Cburnett';
    src = `/static/pieces/${folder}/${pieceCode}.svg`;
  } else {
    src = `/static/pieces/${pieceSet}/${pieceCode}.png`;
  }
  return `${src}?v=${ASSET_VERSION}`;
}
