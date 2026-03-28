"""
Chess Scoresheet Scanner API - Convert scoresheet images to PGN

Uses OpenRouter's Gemini vision model to extract moves from handwritten chess
scoresheets and validates them with python-chess to produce valid PGN.
"""

import os
import re
import logging
import difflib
from typing import List, Dict, Optional, Tuple
import requests
import chess
import chess.pgn
from io import StringIO
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

scoresheet_bp = Blueprint('scoresheet', __name__, url_prefix='/api/scoresheet')


def fuzzy_correct_move(board: chess.Board, move_str: str) -> Optional[str]:
    """
    Attempt to fuzzy-correct an illegal move using common OCR errors.

    Common OCR errors:
    - O vs 0 (oh vs zero)
    - l vs 1 (lowercase L vs one)
    - B vs 8
    - S vs 5
    - I vs 1
    - etc.

    Returns corrected move string if found, None otherwise.
    """
    # Common OCR substitutions
    substitutions = [
        ('O', '0'),
        ('0', 'O'),
        ('l', '1'),
        ('1', 'l'),
        ('B', '8'),
        ('8', 'B'),
        ('S', '5'),
        ('5', 'S'),
        ('I', '1'),
        ('1', 'I'),
    ]

    # Try each substitution
    for old, new in substitutions:
        if old in move_str:
            corrected = move_str.replace(old, new)
            try:
                board.parse_san(corrected)
                return corrected
            except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                continue

    # Try matching against legal moves using difflib
    legal_moves_san = [board.san(move) for move in board.legal_moves]
    matches = difflib.get_close_matches(move_str, legal_moves_san, n=1, cutoff=0.6)

    if matches:
        return matches[0]

    return None


def parse_moves_from_raw_text(raw_moves: str) -> List[str]:
    """
    Parse moves from raw text, handling multi-column scoresheets and move numbers.

    Returns list of individual moves in order (white, black, white, black, ...)
    Strips [?] markers for uncertain moves but preserves the move.
    """
    moves = []

    # Strip [?] markers but keep the moves
    cleaned = re.sub(r'\[\?\]', '', raw_moves)

    # Split by move numbers (e.g., "1.", "2.", "42.")
    # This pattern captures everything between move numbers
    move_sections = re.split(r'(?=\d+\.)', cleaned)

    for section in move_sections:
        section = section.strip()
        if not section:
            continue

        # Remove the move number prefix (e.g., "1. ")
        section = re.sub(r'^\d+\.?\s*', '', section)

        # Split remaining text into tokens (words/moves)
        # Match chess moves: piece letters, coordinates, captures, castling, promotions
        # Also match malformed moves (OCR errors) to allow fuzzy correction later
        move_tokens = re.findall(r'[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8B](?:=[QRBN])?[+#]?|O-O(?:-O)?[+#]?', section, re.IGNORECASE)

        # Take up to 2 moves (white + black)
        for token in move_tokens[:2]:
            token = token.strip()
            if token and token not in ['...', '--']:
                moves.append(token)

    return moves


def validate_and_build_pgn(
    raw_moves: str,
    metadata: Dict[str, str],
    openrouter_key: str
) -> Tuple[str, List[Dict], int, int]:
    """
    Validate moves sequentially with python-chess and build PGN.

    Returns:
        - pgn: Complete PGN string
        - corrections: List of correction dicts
        - moves_total: Total number of moves
        - moves_corrected: Number of corrected moves
    """
    board = chess.Board()
    corrections = []
    move_number = 0

    # Parse raw moves into individual move strings
    matches = parse_moves_from_raw_text(raw_moves)

    validated_moves = []

    for move_str in matches:
        move_number += 1
        move_str = move_str.strip()

        # Skip empty moves or markers
        if not move_str or move_str in ['...', '--']:
            continue

        try:
            # Try to parse the move as-is
            move = board.parse_san(move_str)
            # Get SAN BEFORE pushing (board.san needs the move to be legal on current board)
            san = board.san(move)
            board.push(move)
            validated_moves.append(san)
        except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError) as e:
            logger.warning(f"Move {move_number} '{move_str}' is illegal: {e}")

            # Try fuzzy correction
            corrected = fuzzy_correct_move(board, move_str)

            if corrected:
                logger.info(f"Fuzzy-corrected move {move_number}: '{move_str}' -> '{corrected}'")
                move = board.parse_san(corrected)
                # Get SAN BEFORE pushing
                san = board.san(move)
                board.push(move)
                validated_moves.append(san)
                corrections.append({
                    'move_number': move_number,
                    'original': move_str,
                    'corrected': corrected,
                    'reason': 'fuzzy_match'
                })
            else:
                # Re-ask LLM with current FEN
                logger.info(f"Fuzzy correction failed, re-asking LLM for move {move_number}")
                corrected_move = re_ask_llm_for_move(
                    board.fen(),
                    move_number,
                    move_str,
                    openrouter_key
                )

                if corrected_move:
                    try:
                        move = board.parse_san(corrected_move)
                        # Get SAN BEFORE pushing
                        san = board.san(move)
                        board.push(move)
                        validated_moves.append(san)
                        corrections.append({
                            'move_number': move_number,
                            'original': move_str,
                            'corrected': corrected_move,
                            'reason': 'llm_correction'
                        })
                    except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                        logger.error(f"LLM correction also failed for move {move_number}")
                        # Skip this move and continue
                        continue
                else:
                    logger.error(f"Could not correct move {move_number}, skipping")
                    continue

    # Build PGN
    game = chess.pgn.Game()
    game.headers["Event"] = metadata.get("event", "Casual Game")
    game.headers["Site"] = "Chesster Scoresheet Scanner"
    game.headers["Date"] = metadata.get("date", "????.??.??")
    game.headers["White"] = metadata.get("white", "?")
    game.headers["Black"] = metadata.get("black", "?")
    game.headers["Result"] = "*"

    # Add moves to game
    # We need to replay the moves on a fresh board to build the PGN correctly
    temp_board = chess.Board()
    node = game
    for move_san in validated_moves:
        move = temp_board.parse_san(move_san)
        node = node.add_variation(move)
        temp_board.push(move)

    # Convert to PGN string
    pgn_string = str(game)

    return pgn_string, corrections, len(validated_moves), len(corrections)


def re_ask_llm_for_move(
    fen: str,
    move_number: int,
    illegal_move: str,
    openrouter_key: str,
    model: str = "google/gemini-2.5-pro"
) -> Optional[str]:
    """
    Re-ask LLM to correct a specific illegal move given the current position.
    """
    prompt = f"""Given this chess position (FEN): {fen}

Move {move_number} was transcribed as "{illegal_move}" but this is illegal.

What should move {move_number} be? Output ONLY the move in standard algebraic notation (e.g., Nf3, e4, O-O).
Do not include move numbers or explanations."""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://chesster.io",
                "X-Title": "Chesster - Scoresheet Scanner"
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            },
            timeout=30
        )

        response_data = response.json()

        if response.ok and response_data.get('choices'):
            corrected_move = response_data['choices'][0]['message']['content'].strip()
            # Clean up the response (remove move numbers, periods, etc.)
            corrected_move = re.sub(r'^\d+\.?\s*', '', corrected_move)
            return corrected_move

        return None

    except Exception as e:
        logger.error(f"Error re-asking LLM: {e}")
        return None


def extract_moves_from_images(
    images: List[str],
    openrouter_key: str,
    model: str = "google/gemini-2.5-pro"
) -> str:
    """
    Extract moves from scoresheet images using Gemini vision model.

    Args:
        images: List of base64-encoded image strings
        openrouter_key: OpenRouter API key
        model: Model to use (defaults to gemini-2.5-pro)

    Returns:
        Raw move text extracted by LLM
    """
    # Build multi-image prompt with detailed instructions for multi-column scoresheets
    content = [
        {
            "type": "text",
            "text": """You are a chess scoresheet OCR expert. Extract all moves from this handwritten chess scoresheet.

SCORESHEET LAYOUT:
Typical scoresheets have 3 column pairs:
- Columns 1-2: Moves 1-25 (White | Black)
- Columns 3-4: Moves 26-50 (White | Black)
- Columns 5-6: Moves 51-75 (White | Black)

INSTRUCTIONS:
1. Identify the White and Black columns for each move number
2. Read moves sequentially: 1.White, 1.Black, 2.White, 2.Black, etc.
3. Output as numbered move pairs in standard format

OUTPUT FORMAT:
1. e4 e5
2. Nf3 Nc6
3. Bb5 a6

NOTATION RULES:
- Use standard algebraic notation (SAN)
- Pieces: K=King, Q=Queen, R=Rook, B=Bishop, N=Knight
- Castling: O-O (kingside), O-O-O (queenside)
- Promotion: e8=Q
- Captures: use 'x' (e.g., Nxe4)
- Check: + suffix, Checkmate: # suffix

COMMON HANDWRITING ERRORS TO WATCH FOR:
- 1 vs l (one vs lowercase L)
- 0 vs O (zero vs letter O, especially in castling O-O)
- 5 vs S
- 8 vs B
- If a move is uncertain, mark it with [?] but still include your best guess

IMPORTANT:
- Extract ALL moves from the scoresheet, across all columns
- Preserve move order (sequential numbering)
- Do NOT add explanations or commentary
- Output ONLY the moves

Extract all moves now:"""
        }
    ]

    # Add each image
    for image_base64 in images:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}"
            }
        })

    # Fallback chain: try primary model, then fallback
    models_to_try = [model, "google/gemini-3-pro-image-preview"]

    for current_model in models_to_try:
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://chesster.io",
                    "X-Title": "Chesster - Scoresheet Scanner"
                },
                json={
                    "model": current_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": content
                        }
                    ]
                },
                timeout=90
            )

            response_data = response.json()

            # Log usage for monitoring
            if response_data.get('usage'):
                logger.info(f"Scoresheet OCR (model={current_model}) token usage: {response_data['usage']}")

            if response.ok and response_data.get('choices'):
                raw_moves = response_data['choices'][0]['message']['content'].strip()
                logger.info(f"Raw moves extracted with {current_model}: {raw_moves[:200]}...")
                return raw_moves
            else:
                error_msg = response_data.get('error', {}).get('message', 'Failed to extract moves')
                logger.warning(f"Model {current_model} failed: {error_msg}")
                # Try next model in fallback chain
                continue

        except requests.Timeout:
            logger.warning(f"Model {current_model} timed out, trying fallback...")
            continue
        except Exception as e:
            logger.warning(f"Model {current_model} error: {str(e)}, trying fallback...")
            continue

    # If all models failed
    logger.error("All vision models failed")
    raise Exception("Scoresheet analysis failed with all available models. Please try again.")


@scoresheet_bp.route('/convert', methods=['POST'])
def convert_scoresheet_to_pgn():
    """
    Convert scoresheet images to PGN notation.

    Expects JSON body with:
    - images: list of base64 encoded image strings
    - metadata: optional dict with white, black, event, date

    Returns:
    - pgn: PGN string
    - moves_total: total number of moves
    - moves_corrected: number of corrected moves
    - corrections: list of correction details
    - confidence: estimated confidence score
    - fen_final: final board position FEN
    """
    try:
        data = request.get_json()

        if not data or 'images' not in data:
            return jsonify({'error': 'No images provided'}), 400

        images = data['images']
        metadata = data.get('metadata', {})

        if not isinstance(images, list) or len(images) == 0:
            return jsonify({'error': 'Images must be a non-empty list'}), 400

        if len(images) > 2:
            return jsonify({'error': 'Maximum 2 images allowed'}), 400

        # Get OpenRouter API key
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        if not openrouter_key:
            logger.error("OPENROUTER_API_KEY not configured")
            return jsonify({'error': 'OpenRouter API key not configured'}), 500

        # Step 1: Extract moves from images
        logger.info(f"Extracting moves from {len(images)} image(s)")
        raw_moves = extract_moves_from_images(images, openrouter_key)

        # Step 2: Validate and build PGN
        logger.info("Validating moves and building PGN")
        pgn, corrections, moves_total, moves_corrected = validate_and_build_pgn(
            raw_moves,
            metadata,
            openrouter_key
        )

        # Calculate confidence score
        confidence = 1.0 if moves_corrected == 0 else max(0.5, 1.0 - (moves_corrected / max(moves_total, 1)) * 0.5)

        # Get final FEN
        board = chess.Board()
        game = chess.pgn.read_game(StringIO(pgn))
        if game:
            for move in game.mainline_moves():
                board.push(move)
        fen_final = board.fen()

        logger.info(f"Scoresheet conversion complete: {moves_total} moves, {moves_corrected} corrected")

        return jsonify({
            'pgn': pgn,
            'moves_total': moves_total,
            'moves_corrected': moves_corrected,
            'corrections': corrections,
            'confidence': confidence,
            'fen_final': fen_final
        })

    except Exception as e:
        logger.error(f"Scoresheet conversion error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@scoresheet_bp.route('/health', methods=['GET'])
def scoresheet_health():
    """Health check for scoresheet scanner service."""
    openrouter_key = os.getenv('OPENROUTER_API_KEY')
    return jsonify({
        'status': 'healthy' if openrouter_key else 'degraded',
        'openrouter_configured': bool(openrouter_key)
    })
