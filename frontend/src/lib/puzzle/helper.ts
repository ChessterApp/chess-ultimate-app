export interface PuzzleData {
  lichessId: string;
  previousFEN: string;
  FEN: string;
  moves: string;
  preMove: string;
  rating: number;
  themes: string[];
  gameURL: string;
}

export interface PuzzleQuery {
  themes: string[];
  solution: string[];
}

export interface PuzzleTheme {
  tag: string;
  description: string;
}

// Popular chess puzzle themes
export const PUZZLE_THEMES: PuzzleTheme[] = [
  { tag: "advancedPawn", description: "Advanced Pawn" },
  { tag: "advantage", description: "Advantage" },
  { tag: "anastasiaMate", description: "Anastasia's Mate" },
  { tag: "arabianMate", description: "Arabian Mate" },
  { tag: "attackingF2F7", description: "Attacking f2/f7" },
  { tag: "attraction", description: "Attraction" },
  { tag: "backRankMate", description: "Back Rank Mate" },
  { tag: "bishopEndgame", description: "Bishop Endgame" },
  { tag: "bodenMate", description: "Boden Mate" },
  { tag: "capturingDefender", description: "Capturing Defender" },
  { tag: "castling", description: "Castling" },
  { tag: "clearance", description: "Clearance" },
  { tag: "crushing", description: "Crushing" },
  { tag: "defensiveMove", description: "Defensive Move" },
  { tag: "deflection", description: "Deflection" },
  { tag: "discoveredAttack", description: "Discovered Attack" },
  { tag: "doubleBishopMate", description: "Double Bishop Mate" },
  { tag: "doubleCheck", description: "Double Check" },
  { tag: "dovetailMate", description: "Dovetail Mate" },
  { tag: "endgame", description: "Endgame" },
  { tag: "enPassant", description: "En Passant" },
  { tag: "equality", description: "Equality" },
  { tag: "exposedKing", description: "Exposed King" },
  { tag: "fork", description: "Fork" },
  { tag: "hangingPiece", description: "Hanging Piece" },
  { tag: "hookMate", description: "Hook Mate" },
  { tag: "interference", description: "Interference" },
  { tag: "intermezzo", description: "Intermezzo" },
  { tag: "killBoxMate", description: "Kill Box Mate" },
  { tag: "kingsideAttack", description: "Kingside Attack" },
  { tag: "knightEndgame", description: "Knight Endgame" },
  { tag: "long", description: "Long" },
  { tag: "master", description: "Master" },
  { tag: "masterVsMaster", description: "Master vs Master" },
  { tag: "mate", description: "Mate" },
  { tag: "mateIn1", description: "Mate In 1" },
  { tag: "mateIn2", description: "Mate In 2" },
  { tag: "mateIn3", description: "Mate In 3" },
  { tag: "mateIn4", description: "Mate In 4" },
  { tag: "mateIn5", description: "Mate In 5" },
  { tag: "middlegame", description: "Middlegame" },
  { tag: "oneMove", description: "One Move" },
  { tag: "opening", description: "Opening" },
  { tag: "pawnEndgame", description: "Pawn Endgame" },
  { tag: "pin", description: "Pin" },
  { tag: "promotion", description: "Promotion" },
  { tag: "queenEndgame", description: "Queen Endgame" },
  { tag: "queenRookEndgame", description: "Queen Rook Endgame" },
  { tag: "queensideAttack", description: "Queenside Attack" },
  { tag: "quietMove", description: "Quiet Move" },
  { tag: "rookEndgame", description: "Rook Endgame" },
  { tag: "sacrifice", description: "Sacrifice" },
  { tag: "short", description: "Short" },
  { tag: "skewer", description: "Skewer" },
  { tag: "smotheredMate", description: "Smothered Mate" },
  { tag: "superGM", description: "Super GM" },
  { tag: "trappedPiece", description: "Trapped Piece" },
  { tag: "underPromotion", description: "Under Promotion" },
  { tag: "veryLong", description: "Very Long" },
  { tag: "vukovicMate", description: "Vukovic's Mate" },
  { tag: "xRayAttack", description: "X Ray Attack" },
  { tag: "zugzwang", description: "Zugzwang" },
];

export const DIFFICULTY_THEMES = [
  { value: "mateIn1", label: "Mate in 1", difficulty: "Beginner" },
  { value: "mateIn2", label: "Mate in 2", difficulty: "Intermediate" },
  { value: "mateIn3", label: "Mate in 3", difficulty: "Advanced" },
  { value: "short", label: "Short Puzzles", difficulty: "Quick" },
  { value: "veryLong", label: "Long Puzzles", difficulty: "Complex" },
];
