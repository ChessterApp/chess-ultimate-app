"""
Photo to FEN API - Convert chessboard images to FEN notation

Uses OpenRouter's Gemini vision model to analyze chess board images
and extract FEN (Forsyth-Edwards Notation) strings.
"""

import os
import re
import logging
import requests
from services.usage_ledger import record_openrouter_usage
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

# Vision model (OpenRouter id). gemini-3-flash-preview was a preview; the
# released 3.8 Flash accepts images at the same price class.
PHOTO_FEN_MODEL = os.getenv("PHOTO_FEN_MODEL", "google/gemini-3.8-flash")

photo_fen_bp = Blueprint('photo_fen', __name__, url_prefix='/api')


# Gemini 3 Flash thinks for 4–16k tokens on a board photo by default (28–131 s
# on 2026-10-06); "minimal" reads the same position in 14–21 s. Empty → the
# model's default.
PHOTO_FEN_REASONING = os.getenv("PHOTO_FEN_REASONING", "minimal").strip()
PHOTO_FEN_ATTEMPTS = max(1, int(os.getenv("PHOTO_FEN_ATTEMPTS", "2")))

PHOTO_FEN_PROMPT = (
    "Read the chess position in this image and write it as FEN.\n"
    "- Use the coordinates printed around the board, if any, to tell which side is at the bottom. "
    "If Black is at the bottom (rank 1 at the top, file h on the left), still write the FEN the usual "
    "way: rank 8 first, from file a to file h.\n"
    "- Side to move: write w or b only if the image shows it — a highlighted last move (then the other "
    "side is to move), a caption such as \"White to move\" / \"Ход белых\", a turn indicator or a clock. "
    "Otherwise write ?.\n"
    "Output exactly one line: <piece placement> <w|b|?>. Nothing else."
)

_PLACEMENT = re.compile(r"((?:[rnbqkpRNBQKP1-8]+/){7}[rnbqkpRNBQKP1-8]+)(?:\s+([wb?]))?")


def position_from_reply(text: str):
    """(fen, turn_known) from the vision model's reply, or None.

    The model gives the placement and, when the image shows it, the side to
    move. A photo never shows castling rights or en passant: castling is
    granted where king and rook stand on their home squares, en passant never.
    Without a visible side to move White moves (turn_known False) — unless
    only Black can be to move (White's king in check).
    """
    m = _PLACEMENT.search(text or "")
    if not m:
        return None
    placement, side = m.group(1), (m.group(2) or "?")
    try:
        import chess
    except ImportError:  # pragma: no cover — python-chess is in requirements.txt
        turn = side if side in "wb" else "w"
        return f"{placement} {turn} - - 0 1", side in "wb"

    def build(turn: str):
        try:
            board = chess.Board(f"{placement} {turn} KQkq - 0 1")
        except ValueError:
            return None
        board.castling_rights = board.clean_castling_rights()
        return board if board.is_valid() else None

    known = side in "wb"
    first = side if known else "w"
    board = build(first)
    if board is None:
        other = build("b" if first == "w" else "w")
        if other is None:
            return None
        board, known = other, True  # only one side can be to move
    return board.fen(), known


@photo_fen_bp.route('/convert-image', methods=['POST'])
def convert_image_to_fen():
    """
    Convert a chessboard image to FEN notation.

    Expects JSON body with:
    - image: base64 encoded image string

    Returns:
    - fen: FEN string representation of the chess position
    """
    try:
        data = request.get_json()

        if not data or 'image' not in data:
            return jsonify({'error': 'No image provided'}), 400

        image_base64 = data['image']

        # Get OpenRouter API key
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        if not openrouter_key:
            logger.error("OPENROUTER_API_KEY not configured")
            return jsonify({'error': 'OpenRouter API key not configured'}), 500

        # Prepare the prompt for vision model
        prompt = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": PHOTO_FEN_PROMPT
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ]

        # A reply that is not a legal position (a misread piece: two kings of one
        # colour) is asked once more — the model reads the same photo right most
        # of the time (2026-10-06: 1 failure in 8 tries on one board).
        fen_response = None
        for attempt in range(PHOTO_FEN_ATTEMPTS):
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://chessempire.com",
                    "X-Title": "Chess Empire - Photo to FEN"
                },
                json={
                    "model": PHOTO_FEN_MODEL,
                    "messages": prompt,
                    **({"reasoning": {"effort": PHOTO_FEN_REASONING}} if PHOTO_FEN_REASONING else {}),
                },
                timeout=60
            )

            response_data = response.json()

            # Log usage for monitoring and record it in the token_usage ledger
            if response_data.get('usage'):
                logger.info(f"Photo-to-FEN token usage: {response_data['usage']}")
                record_openrouter_usage(
                    response_data,
                    model=PHOTO_FEN_MODEL,
                    surface="vision",
                    user_id=request.headers.get("X-User-Id"),
                )

            if not (response.ok and response_data.get('choices')):
                error_msg = response_data.get('error', {}).get('message', 'Failed to analyze image')
                logger.error(f"OpenRouter API error: {error_msg}")
                return jsonify({'error': error_msg}), response.status_code or 500

            fen_response = response_data['choices'][0]['message']['content'].strip()
            logger.info(f"Raw FEN response from model (attempt {attempt + 1}): {fen_response}")

            parsed = position_from_reply(fen_response)
            if parsed:
                fen, turn_known = parsed
                logger.info(f"Returning FEN: {fen} (turn known: {turn_known})")
                return jsonify({'fen': fen, 'turn_known': turn_known})
            logger.warning(f"Invalid FEN response (attempt {attempt + 1}): {fen_response}")

        return jsonify({
            'error': 'Could not extract valid FEN from image analysis',
            'raw_response': fen_response
        }), 500

    except requests.Timeout:
        logger.error("OpenRouter API timeout")
        return jsonify({'error': 'Image analysis timed out. Please try again.'}), 504
    except Exception as e:
        logger.error(f"Photo-to-FEN error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@photo_fen_bp.route('/convert-image/health', methods=['GET'])
def photo_fen_health():
    """Health check for photo-to-FEN service."""
    openrouter_key = os.getenv('OPENROUTER_API_KEY')
    return jsonify({
        'status': 'healthy' if openrouter_key else 'degraded',
        'openrouter_configured': bool(openrouter_key)
    })
