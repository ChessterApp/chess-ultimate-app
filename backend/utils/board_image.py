"""board_image — render the final position of a PGN game to a PNG.

Used by the PUBLIC share-link thumbnail endpoints (Share Game Phase 3b) so a
shared game unfurls in WhatsApp/Telegram with an actual chessboard image of the
game's FINAL position. The rendered image reveals only the position — never the
PGN text, move list, or any owner identity.

Rendering is pure (PGN string in → PNG bytes out) so it can be unit-tested
without a Flask app or a database.
"""

import io
import logging

import chess
import chess.pgn
import chess.svg

try:  # cairosvg pulls in native cairo; degrade gracefully if unavailable.
    import cairosvg
except Exception:  # pragma: no cover - import guard
    cairosvg = None

logger = logging.getLogger(__name__)

# Square board, white point of view. 800px is plenty for a link unfurl and
# keeps the SVG→PNG rasterisation fast.
BOARD_SIZE = 800


def render_final_position_png(pgn_text: str, size: int = BOARD_SIZE):
    """Replay a PGN to its final position and return a PNG of the board.

    Returns PNG bytes on success, or None when the PGN is empty/unparseable or
    the renderer is unavailable. White point of view, last move highlighted.
    """
    if not pgn_text or not pgn_text.strip():
        return None
    if cairosvg is None:
        logger.warning("cairosvg unavailable — cannot render board thumbnail")
        return None

    try:
        game = chess.pgn.read_game(io.StringIO(pgn_text))
        if game is None:
            return None

        board = game.board()
        last_move = None
        for move in game.mainline_moves():
            board.push(move)
            last_move = move

        svg = chess.svg.board(board, lastmove=last_move, size=size)
        return cairosvg.svg2png(
            bytestring=svg.encode("utf-8"),
            output_width=size,
            output_height=size,
        )
    except Exception as e:  # malformed PGN, illegal move, render failure
        logger.debug(f"Failed to render board thumbnail: {e}")
        return None


# Brand colours for the logo-card fallback (match the dark board square tone).
_LOGO_CARD_BG = "#2b2b2b"
_LOGO_CARD_FG = "#f5f5f0"


def render_logo_card_png(size: int = BOARD_SIZE):
    """Render a branded Chesster logo card as a PNG.

    Used as the OG thumbnail fallback when there is no position to show — e.g. a
    shared but empty game collection. Returns PNG bytes, or None when the
    renderer is unavailable.
    """
    if cairosvg is None:
        logger.warning("cairosvg unavailable — cannot render logo card")
        return None

    try:
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" '
            f'height="{size}" viewBox="0 0 {size} {size}">'
            f'<rect width="{size}" height="{size}" fill="{_LOGO_CARD_BG}"/>'
            f'<text x="50%" y="48%" fill="{_LOGO_CARD_FG}" '
            f'font-family="Georgia, serif" font-size="{size // 8}" '
            f'font-weight="bold" text-anchor="middle" '
            f'dominant-baseline="middle">&#9822; Chesster</text>'
            f'<text x="50%" y="60%" fill="{_LOGO_CARD_FG}" '
            f'font-family="Georgia, serif" font-size="{size // 20}" '
            f'text-anchor="middle" dominant-baseline="middle" '
            f'opacity="0.8">My Games</text>'
            f'</svg>'
        )
        return cairosvg.svg2png(
            bytestring=svg.encode("utf-8"),
            output_width=size,
            output_height=size,
        )
    except Exception as e:  # pragma: no cover - render failure
        logger.debug(f"Failed to render logo card: {e}")
        return None
