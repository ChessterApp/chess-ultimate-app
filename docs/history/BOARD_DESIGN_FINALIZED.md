# Finalized Board Design

## Design Decision

**Approved Design:** Lichess Standard Brown Theme + Alpha Pieces

This is the authentic Lichess design with no modifications - proven, tested, and familiar to millions of chess players worldwide.

---

## Assets

### Board
- **File:** `frontend/public/pieces/lichess-brown-board.png`
- **Resolution:** 2048x2048px
- **Source:** [Lichess Official Repository](https://github.com/lichess-org/lila/blob/master/public/images/board/brown.png)
- **Colors:**
  - Light squares: `#f0d9b5`
  - Dark squares: `#b58863`

### Pieces (Alpha Set)
- **Directory:** `frontend/public/pieces/alpha/`
- **Format:** SVG (scalable vector graphics)
- **Total Size:** 48KB (12 pieces)
- **Average Size:** 4KB per piece
- **Source:** [Lichess Alpha Pieces](https://github.com/lichess-org/lila/tree/master/public/piece/alpha)
- **Colors:**
  - White pieces: `#f9f9f9` (off-white fill) + `#101010` (black outline)
  - Black pieces: `#101010` (black fill) + `#101010` (outline)

**Piece Inventory:**
```
wK.svg - White King
wQ.svg - White Queen
wR.svg - White Rook
wB.svg - White Bishop
wN.svg - White Knight
wP.svg - White Pawn

bK.svg - Black King
bQ.svg - Black Queen
bR.svg - Black Rook
bB.svg - Black Bishop
bN.svg - Black Knight
bP.svg - Black Pawn
```

---

## Lichess Official Colors

From official Lichess SCSS source code:

### Board Theme: Brown
```scss
'brown': (
  file-ext: 'png',
  coord-color-white: #f0d9b5,
  coord-color-black: #946f51,
)
```

### Square Highlights
```scss
// Move highlights (last move made)
background-color: rgba(155, 199, 0, 0.41); // Greenish-yellow

// Selected square
background-color: rgba(20, 85, 30, 0.5); // Green

// Move destination hint
background: radial-gradient(rgba(20, 85, 30, 0.5) 19%, rgba(0, 0, 0, 0) 20%);

// Check indicator
background: radial-gradient(
  ellipse at center,
  rgba(255, 0, 0, 1) 0%,
  rgba(231, 0, 0, 1) 25%,
  rgba(169, 0, 0, 0) 89%,
  rgba(158, 0, 0, 0) 100%
); // Red radial gradient
```

---

## Why This Design?

1. **Production-Ready:** Used by 150M+ players on Lichess.org
2. **Proven UX:** Years of user testing and refinement
3. **Accessibility:** Clear contrast, easy to read
4. **Mobile-Optimized:** Works perfectly on touch devices
5. **Zero Design Debt:** No need to create custom assets
6. **Instant Recognition:** Familiar to chess players
7. **MIT Licensed:** Free to use, modify, and distribute

---

## Preview Files

- **[pieces-preview-lichess-original.html](frontend/public/pieces-preview-lichess-original.html)** - Interactive preview with full board

---

## Integration Notes

### Chessground Configuration
```typescript
{
  coordinates: true, // Show a-h, 1-8 coordinates
  orientation: 'white', // white or black
  fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR', // Starting position
  highlight: {
    lastMove: true, // Highlight last move with green-yellow
    check: true, // Highlight king in check with red
  },
  movable: {
    free: false, // Only allow legal moves
    color: 'white', // Which side can move
    showDests: true, // Show move destination hints
  },
  premovable: {
    enabled: false, // Disable premoves for beginners
  },
  drawable: {
    enabled: false, // No drawing arrows for MVP
  },
}
```

### Asset Paths
```typescript
const pieceSet = {
  baseUrl: '/pieces/alpha/',
  pieces: {
    wK: '/pieces/alpha/wK.svg',
    wQ: '/pieces/alpha/wQ.svg',
    // ... etc
  }
};

const boardImage = '/pieces/lichess-brown-board.png';
```

---

## Next Steps

1. ✅ Design finalized
2. 🔄 Design component architecture for chessground integration
3. ⏳ Define animation specifications and timing
4. ⏳ Plan lesson data schema updates for 1-move puzzles
5. ⏳ Implement AnimatedChessBoard component
6. ⏳ Integrate with lesson page

---

## References

- [Lichess GitHub Repository](https://github.com/lichess-org/lila)
- [Chessground Library](https://github.com/lichess-org/chessground)
- [Chessground Documentation](https://github.com/lichess-org/chessground/tree/master/doc)
- [Board Design PRD](ANIMATED_BOARD_PRD.md)
- [Board Design Research](BOARD_DESIGN_RESEARCH.md)
