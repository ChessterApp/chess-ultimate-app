"""
Chess Scoresheet Scanner API - Convert scoresheet images to PGN

Uses OpenRouter's Gemini vision model to extract moves from handwritten chess
scoresheets and validates them with python-chess to produce valid PGN.

Two-pass pipeline:
  Pass 1: Vision model extracts all moves as structured JSON
  Pass 2: Validate each move sequentially. For failures, re-ask the LLM
          with the current board FEN + the original image for context.
"""

import os
import re
import json
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

# Model configuration
PRIMARY_MODEL = "google/gemini-3.1-pro-preview"  # Latest and best for vision
FALLBACK_MODEL = "google/gemini-2.5-pro"
CORRECTION_MODEL = "google/gemini-2.5-pro"  # For move corrections without image

# Common OCR substitution pairs for chess notation
OCR_SUBSTITUTIONS = [
    # Letter/digit confusions
    ('O', '0'), ('0', 'O'),
    ('l', '1'), ('1', 'l'),
    ('I', '1'), ('1', 'I'),
    ('B', '8'), ('8', 'B'),
    ('S', '5'), ('5', 'S'),
    ('G', '6'), ('6', 'G'),
    ('Z', '2'), ('2', 'Z'),
    ('T', '7'), ('7', 'T'),
    # Piece letter confusions
    ('N', 'K'), ('K', 'N'),  # Knight vs King
    ('R', 'B'), ('B', 'R'),  # Rook vs Bishop
    ('P', 'p'),  # uppercase/lowercase pawn
    ('Q', 'O'), ('O', 'Q'),  # Queen vs O (castling confusion)
    # Coordinate confusions
    ('a', 'e'), ('e', 'a'),  # similar in handwriting
    ('b', 'd'), ('d', 'b'),  # mirror confusion
    ('f', 't'), ('t', 'f'),  # similar in handwriting
    ('g', 'q'), ('q', 'g'),  # similar in handwriting
    ('h', 'b'), ('b', 'h'),  # similar in handwriting
    ('c', 'e'), ('e', 'c'),  # similar in handwriting
    # Lower to upper case pieces (common OCR error)
    ('n', 'N'), ('b', 'B'), ('r', 'R'), ('q', 'Q'), ('k', 'K'),
]


def fuzzy_correct_move(board: chess.Board, move_str: str) -> Optional[str]:
    """
    Attempt to fuzzy-correct an illegal move using multiple strategies:
    1. Common OCR character substitutions
    2. Handle incomplete moves (e.g., "Rab8" missing destination)
    3. Single-character edits
    4. Difflib closest match against legal moves
    5. Piece disambiguation fixes
    """
    # Pre-validation: check for obviously incomplete moves
    if not move_str or len(move_str) < 1:
        return None

    legal_moves_san = [board.san(move) for move in board.legal_moves]

    # Handle single-letter incomplete moves (e.g., "B", "R", "N")
    if len(move_str) == 1:
        # First, check if it's a misread pawn move (common: "B" might be "b6")
        # Try the lowercase version as a pawn file
        if move_str[0] in 'NBRQK':
            pawn_file = move_str[0].lower()
            # Try appending common ranks for pawn moves
            for rank in ['6', '7', '8', '5', '4', '3', '2']:
                candidate = pawn_file + rank
                if candidate in legal_moves_san:
                    return candidate

            # If no pawn move works, find legal moves with this piece
            matches = [m for m in legal_moves_san if m[0] == move_str[0]]
            if len(matches) == 1:
                return matches[0]
            # If multiple piece moves, can't disambiguate - return None
            return None
        elif move_str[0] in 'abcdefgh':
            # Single letter is a pawn file - try appending common ranks
            for rank in ['6', '7', '8', '5', '4', '3', '2']:
                candidate = move_str + rank
                if candidate in legal_moves_san:
                    return candidate
            return None

    # Handle incomplete piece moves like "R" or "Rab" (missing destination)
    if move_str[0] in 'NBRQK':
        # Check if it ends with a valid square (a-h followed by 1-8)
        has_valid_ending = len(move_str) >= 3 and move_str[-2] in 'abcdefgh' and move_str[-1] in '12345678'

        # If it doesn't have a valid ending, try prefix matching
        if not has_valid_ending:
            # Try to find a legal move starting with this prefix
            for legal_move in legal_moves_san:
                if legal_move.startswith(move_str):
                    return legal_move
            # Continue to other strategies if prefix matching fails

    # Strategy 1: Direct OCR substitutions
    for old, new in OCR_SUBSTITUTIONS:
        if old in move_str:
            corrected = move_str.replace(old, new, 1)
            try:
                board.parse_san(corrected)
                return corrected
            except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                pass

    # Strategy 2: Try all single-character mutations
    legal_moves_san = [board.san(move) for move in board.legal_moves]

    # Strategy 3: Try removing/adding piece prefix
    for piece in ['N', 'B', 'R', 'Q', 'K']:
        # Try adding piece prefix
        if not move_str[0].isupper() or move_str[0] not in 'NBRQK':
            prefixed = piece + move_str
            try:
                board.parse_san(prefixed)
                return prefixed
            except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                pass
        # Try removing piece prefix and adding different one
        if move_str and move_str[0] in 'NBRQK':
            swapped = piece + move_str[1:]
            try:
                board.parse_san(swapped)
                return swapped
            except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                pass

    # Strategy 4: Handle capture notation issues (missing 'x' or extra 'x')
    if 'x' not in move_str:
        # Try inserting 'x' at various positions
        for i in range(1, len(move_str)):
            with_capture = move_str[:i] + 'x' + move_str[i:]
            try:
                board.parse_san(with_capture)
                return with_capture
            except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                pass
    else:
        # Try removing 'x'
        without_capture = move_str.replace('x', '')
        try:
            board.parse_san(without_capture)
            return without_capture
        except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
            pass

    # Strategy 5: Castling normalization
    castling_variants = ['O-O', 'O-O-O', '0-0', '0-0-0', 'o-o', 'o-o-o']
    for castle in castling_variants:
        if move_str.lower().replace('0', 'o') == castle.lower().replace('0', 'o'):
            # Try both castling options
            for c in ['O-O-O', 'O-O']:
                try:
                    board.parse_san(c)
                    return c
                except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                    pass

    # Strategy 6: Column/rank swap (e.g., "Nf3" might be "Nc3")
    for i, ch in enumerate(move_str):
        if ch in 'abcdefgh':
            for col in 'abcdefgh':
                if col != ch:
                    variant = move_str[:i] + col + move_str[i+1:]
                    try:
                        board.parse_san(variant)
                        return variant
                    except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                        pass
        elif ch in '12345678':
            for rank in '12345678':
                if rank != ch:
                    variant = move_str[:i] + rank + move_str[i+1:]
                    try:
                        board.parse_san(variant)
                        return variant
                    except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                        pass

    # Strategy 7: Difflib closest match (last resort, lower cutoff)
    matches = difflib.get_close_matches(move_str, legal_moves_san, n=3, cutoff=0.5)
    if matches:
        return matches[0]

    return None


def parse_moves_from_structured(raw_text: str) -> List[Tuple[int, str, str]]:
    """
    Parse moves from structured text output.
    Returns list of (move_number, white_move, black_move) tuples.
    """
    moves = []

    # Try JSON parsing first
    try:
        data = json.loads(raw_text)
        if isinstance(data, list):
            for entry in data:
                num = entry.get('move_number', entry.get('n', 0))
                white = entry.get('white', entry.get('w', ''))
                black = entry.get('black', entry.get('b', ''))
                if num and (white or black):
                    moves.append((int(num), white.strip(), black.strip()))
            if moves:
                return moves
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    # Fallback: parse numbered move pairs from text
    # Handle both single-line format "1. e4 e5 2. Nf3 Nc6" and multi-line format
    text = raw_text.strip()

    # Remove [?] markers and asterisks
    text = re.sub(r'\[\?\]', '', text)
    text = re.sub(r'\*', '', text)

    # Find all move pairs with re.findall to handle single-line input
    # Handles: "1. e4 e5", "1.e4 e5", "1) e4 e5", "1 e4 e5"
    pattern = r'(\d+)[.)]\s*([A-Za-z0-9xO\-=+#]+)(?:\s+([A-Za-z0-9xO\-=+#]+))?'
    matches = re.findall(pattern, text)

    for match in matches:
        num = int(match[0])
        white = match[1].strip() if match[1] else ''
        black = match[2].strip() if match[2] else ''
        # Normalize castling
        white = white.replace('0-0-0', 'O-O-O').replace('0-0', 'O-O')
        black = black.replace('0-0-0', 'O-O-O').replace('0-0', 'O-O')
        if white or black:
            moves.append((num, white, black))

    return moves


def extract_moves_from_images(
    images: List[str],
    openrouter_key: str,
    model: str = PRIMARY_MODEL,
    temperature: float = 0.1
) -> str:
    """
    Extract moves from scoresheet images using Gemini vision model.
    Uses a detailed, structured prompt optimized for handwritten chess scoresheets.

    Args:
        images: List of base64-encoded images
        openrouter_key: OpenRouter API key
        model: Model to use for extraction
        temperature: Sampling temperature (0.0-1.0)
    """
    content = [
        {
            "type": "text",
            "text": """You are an expert chess scoresheet transcription specialist. Extract ALL moves from this handwritten chess scoresheet with maximum accuracy.

SCORESHEET LAYOUT:
- Usually 3 column pairs (moves 1-25, 26-50, 51-75)
- Each row: move number | White's move | Black's move
- Read all pairs left-to-right across the page

CHESS NOTATION - STRICT RULES:
1. PIECES (uppercase): K Q R B N
2. PAWNS (no prefix): just coordinates (e4, d5, c6)
3. SQUARES: file (a-h) + rank (1-8), e.g. e4, d7
4. CAPTURES: piece + x + square (Nxf6, exd5)
5. CASTLING: O-O (kingside) OR O-O-O (queenside) - letter O NOT zero
6. DISAMBIGUATION: Add file/rank when needed (Nbd7, Rad1, R1e1)
7. PROMOTION: move + = + piece (e8=Q, a1=R)

VALIDATION CHECKLIST - Every move MUST:
✓ Have a destination square (e.g. Nf3, Rd1) - NOT just "N" or "R"
✓ Have piece letter if not a pawn (Rook=R, Bishop=B, Knight=N)
✓ Include 'x' for captures (Bxc6 not Bc6 if it's a capture)
✓ Use O-O for castling (letter O, not zero 0)

COMMON HANDWRITING ISSUES:
- R vs B: Look at piece behavior (Rooks move straight, Bishops diagonal)
- N vs K: Knights jump, Kings move 1 square
- 1 vs l: context matters (e1 not el)
- Incomplete moves: If you see "Ra" that's incomplete - need "Rad1" or similar

EXAMPLES OF COMPLETE MOVES:
✓ GOOD: e4, Nf3, Bxc6, Rad1, O-O, Qh4e1, e8=Q, Rxf7+
✗ BAD: N, Bx, R, O-0, Ra, Qh4e, e8

Read EVERY move from ALL columns. Extract exactly what you see - don't skip unclear moves, transcribe them as best you can.

OUTPUT FORMAT (one line per number):
1. e4 e5
2. Nf3 Nc6
...

Return ONLY the numbered moves. NO explanations, NO notes, NO markdown blocks."""
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

    # Fallback chain
    models_to_try = [model, FALLBACK_MODEL]

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
                    ],
                    "temperature": temperature,
                    "max_tokens": 32000,
                    "reasoning": {"effort": "low"},  # Minimize reasoning tokens, maximize output
                },
                timeout=120
            )

            response_data = response.json()

            if response_data.get('usage'):
                logger.info(f"Scoresheet OCR (model={current_model}) token usage: {response_data['usage']}")

            if response.ok and response_data.get('choices'):
                raw_text = response_data['choices'][0]['message']['content'].strip()
                # Clean markdown code block wrappers if present
                raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text)
                raw_text = re.sub(r'\s*```$', '', raw_text)
                logger.info(f"Raw moves extracted with {current_model}: {raw_text[:300]}...")
                return raw_text
            else:
                error_msg = response_data.get('error', {}).get('message', 'Failed to extract moves')
                logger.warning(f"Model {current_model} failed: {error_msg}")
                continue

        except requests.Timeout:
            logger.warning(f"Model {current_model} timed out, trying fallback...")
            continue
        except Exception as e:
            logger.warning(f"Model {current_model} error: {str(e)}, trying fallback...")
            continue

    logger.error("All vision models failed")
    raise Exception("Scoresheet analysis failed with all available models. Please try again.")


def multi_pass_extract(
    images: List[str],
    openrouter_key: str,
    model: str = PRIMARY_MODEL
) -> List[List[Tuple[int, str, str]]]:
    """
    Run 3 independent extractions with varied temperatures for voting.

    Returns:
        List of 3 parsed move lists, each containing [(move_num, white, black), ...]
    """
    temperatures = [0.1, 0.3, 0.5]
    results = []

    for i, temp in enumerate(temperatures):
        logger.info(f"Pass {i+1}/3: Extracting with temperature={temp}")
        raw_text = extract_moves_from_images(images, openrouter_key, model, temperature=temp)
        parsed = parse_moves_from_structured(raw_text)
        results.append(parsed)
        logger.info(f"Pass {i+1} extracted {len(parsed)} move pairs")

    return results


def vote_on_moves(
    extractions: List[List[Tuple[int, str, str]]],
    board: chess.Board
) -> Tuple[List[str], List[Dict]]:
    """
    Perform per-move majority voting across 3 extractions.

    Args:
        extractions: List of 3 parsed move lists from multi_pass_extract()
        board: Starting chess board position

    Returns:
        (validated_moves, corrections) where:
        - validated_moves: List of SAN moves that passed voting
        - corrections: List of correction metadata dicts
    """
    # Flatten all extractions to sequential moves
    flattened = []
    for extraction in extractions:
        moves = []
        for num, white, black in extraction:
            if white and white not in ['...', '--', '']:
                moves.append((num, 'white', white))
            if black and black not in ['...', '--', '']:
                moves.append((num, 'black', black))
        flattened.append(moves)

    # Determine max length across all extractions
    max_len = max(len(m) for m in flattened)

    validated_moves = []
    corrections = []
    move_index = 0

    for pos in range(max_len):
        # Gather the 3 candidates for this position
        candidates = []
        for extraction in flattened:
            if pos < len(extraction):
                move_num, color, move_str = extraction[pos]
                candidates.append((move_num, color, move_str.strip()))

        if not candidates:
            continue

        # Use the first candidate's metadata as reference
        move_num, color, _ = candidates[0]

        # Clean candidates
        cleaned_candidates = []
        for _, _, move_str in candidates:
            move_str = move_str.replace('0-0-0', 'O-O-O').replace('0-0', 'O-O')
            move_str = re.sub(r'[.!?]$', '', move_str)
            cleaned_candidates.append(move_str)

        # Voting logic
        from collections import Counter
        vote_count = Counter(cleaned_candidates)
        most_common = vote_count.most_common()

        selected_move = None
        confidence = "unknown"

        # Case 1: All 3 agree (high confidence)
        if len(most_common) == 1 and most_common[0][1] == 3:
            selected_move = most_common[0][0]
            confidence = "high"
        # Case 2: 2/3 agree (medium confidence)
        elif len(most_common) >= 1 and most_common[0][1] >= 2:
            selected_move = most_common[0][0]
            confidence = "medium"
        # Case 3: All different - try all through fuzzy correction
        else:
            for candidate in cleaned_candidates:
                # Try direct validation
                try:
                    move = board.parse_san(candidate)
                    selected_move = candidate
                    confidence = "low"
                    break
                except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                    # Try fuzzy correction
                    corrected = fuzzy_correct_move(board, candidate)
                    if corrected:
                        try:
                            board.parse_san(corrected)
                            selected_move = corrected
                            confidence = "low_corrected"
                            corrections.append({
                                'move_number': move_num,
                                'color': color,
                                'original': candidate,
                                'corrected': corrected,
                                'reason': 'fuzzy_match_voting'
                            })
                            break
                        except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                            continue

        # If we found a move, try to validate and push it
        if selected_move:
            try:
                move = board.parse_san(selected_move)
                san = board.san(move)
                board.push(move)
                validated_moves.append(san)
                move_index += 1

                # Log correction if it wasn't unanimous
                if confidence in ["medium", "low", "low_corrected"] and confidence != "low_corrected":
                    corrections.append({
                        'move_number': move_num,
                        'color': color,
                        'original': f"votes: {vote_count}",
                        'corrected': san,
                        'reason': f'majority_vote_{confidence}'
                    })

                logger.debug(f"Move {move_index} validated: {san} (confidence: {confidence})")
                continue
            except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError) as e:
                logger.warning(f"Move {move_num} ({color}) '{selected_move}' failed validation: {e}")

        # Move failed - try re-sync
        logger.warning(f"Move {move_num} ({color}) failed all voting strategies, attempting re-sync")

        # Try the next position's moves from each extraction to re-sync
        resync_success = False
        for next_offset in range(1, min(3, max_len - pos)):
            next_pos = pos + next_offset
            for extraction in flattened:
                if next_pos < len(extraction):
                    _, _, next_move = extraction[next_pos]
                    next_move = next_move.replace('0-0-0', 'O-O-O').replace('0-0', 'O-O')
                    next_move = re.sub(r'[.!?]$', '', next_move)
                    try:
                        move = board.parse_san(next_move)
                        san = board.san(move)
                        board.push(move)
                        validated_moves.append(san)
                        move_index += 1
                        logger.info(f"Re-synced at position {next_pos} with move: {san}")
                        resync_success = True
                        break
                    except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                        continue
            if resync_success:
                break

        if not resync_success:
            # Could not re-sync, skip this move
            logger.error(f"Failed to re-sync after move {move_num}, continuing to next position")

    return validated_moves, corrections


def re_ask_llm_for_moves(
    board_fen: str,
    failed_moves: List[Dict],
    images: List[str],
    openrouter_key: str,
    model: str = CORRECTION_MODEL
) -> Dict[int, str]:
    """
    Second pass: re-ask the LLM for specific moves that failed validation.
    Sends the image again with the current board state for context.

    Returns dict of {move_number: corrected_move_san}
    """
    if not failed_moves:
        return {}

    failed_desc = "\n".join([
        f"- Move {m['move_number']} ({m['color']}): OCR read \"{m['original']}\" but it's illegal"
        for m in failed_moves
    ])

    content = [
        {
            "type": "text",
            "text": f"""I'm reading a chess scoresheet and some moves were illegible or misread by OCR.

CURRENT BOARD POSITION (FEN): {board_fen}

The following moves need correction — they were read from the scoresheet but are illegal in this position:
{failed_desc}

Please look at the scoresheet image again and tell me what these moves should be.
Use the current board position to verify your answers are legal.

For each move, output ONLY the corrected move in standard algebraic notation.

OUTPUT FORMAT — JSON object mapping move numbers to corrected moves:
{{"move_number": "corrected_move", ...}}

Example: {{"15": "bxc3", "16": "e4"}}

Output ONLY the JSON. No explanation."""
        }
    ]

    for image_base64 in images:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}"
            }
        })

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
                "messages": [{"role": "user", "content": content}],
                "temperature": 0.1,
                "max_tokens": 2048,
            },
            timeout=90
        )

        response_data = response.json()

        if response.ok and response_data.get('choices'):
            raw = response_data['choices'][0]['message']['content'].strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            try:
                corrections = json.loads(raw)
                return {int(k): v for k, v in corrections.items()}
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse LLM correction response: {e}")
                return {}

        return {}

    except Exception as e:
        logger.error(f"Error in second-pass LLM correction: {e}")
        return {}


def re_ask_llm_for_move(
    fen: str,
    move_number: int,
    illegal_move: str,
    openrouter_key: str,
    model: str = CORRECTION_MODEL
) -> Optional[str]:
    """
    Re-ask LLM to correct a specific illegal move given the current position.
    """
    board = chess.Board(fen)
    legal_moves = [board.san(m) for m in board.legal_moves]

    prompt = f"""Given this chess position (FEN): {fen}

Move {move_number} was transcribed as "{illegal_move}" but this is illegal.

Legal moves in this position: {', '.join(legal_moves[:30])}

What should move {move_number} be? Consider:
1. Which legal move looks most similar to "{illegal_move}" in handwriting?
2. Which legal move makes the most chess sense in this position?

Output ONLY the move in standard algebraic notation (e.g., Nf3, e4, O-O).
No move numbers, no explanation."""

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
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            },
            timeout=30
        )

        response_data = response.json()

        if response.ok and response_data.get('choices'):
            corrected_move = response_data['choices'][0]['message']['content'].strip()
            corrected_move = re.sub(r'^\d+\.?\s*', '', corrected_move)
            corrected_move = corrected_move.split('\n')[0].strip()
            corrected_move = corrected_move.split(' ')[0].strip()
            return corrected_move

        return None

    except Exception as e:
        logger.error(f"Error re-asking LLM: {e}")
        return None


def validate_and_build_pgn(
    raw_moves_text: str,
    metadata: Dict[str, str],
    openrouter_key: str,
    images: Optional[List[str]] = None,
    use_voting: bool = False
) -> Tuple[str, List[Dict], int, int]:
    """
    Validation pipeline with optional 3-pass voting.

    When use_voting=True:
      - Ignores raw_moves_text and uses images instead
      - Runs 3 independent extractions with different temperatures
      - Uses majority voting for each move position
      - Never breaks on failure, attempts re-sync instead

    When use_voting=False (legacy):
      - Uses raw_moves_text with single-pass fuzzy correction
      - Breaks on first unrecoverable failure

    Returns: (pgn_string, corrections, moves_total, moves_corrected)
    """
    if use_voting and images:
        # NEW: 3-pass voting pipeline
        logger.info("Using 3-pass voting pipeline")

        # Step 1: Run 3 extractions
        extractions = multi_pass_extract(images, openrouter_key)

        # Step 2: Vote on moves
        board = chess.Board()
        validated_moves, corrections = vote_on_moves(extractions, board)

        logger.info(f"Voting pipeline: {len(validated_moves)} moves validated, {len(corrections)} corrections")

    else:
        # LEGACY: Single-pass with fuzzy correction
        board = chess.Board()
        corrections = []
        validated_moves = []

        # Parse structured moves
        structured_moves = parse_moves_from_structured(raw_moves_text)

        if not structured_moves:
            logger.warning("No structured moves found, trying legacy text parsing")
            # Fallback to legacy text parsing
            return _validate_legacy(raw_moves_text, metadata, openrouter_key)

        # Flatten to sequential move list: [(move_num, color, move_str), ...]
        flat_moves = []
        for num, white, black in structured_moves:
            if white and white not in ['...', '--', '']:
                flat_moves.append((num, 'white', white))
            if black and black not in ['...', '--', '']:
                flat_moves.append((num, 'black', black))

        # Pass 1: Validate each move with fuzzy correction
        failed_in_pass1 = []
        move_index = 0

        for move_num, color, move_str in flat_moves:
            move_str = move_str.strip()
            if not move_str:
                continue

            # Clean common formatting issues
            move_str = move_str.replace('0-0-0', 'O-O-O').replace('0-0', 'O-O')
            move_str = re.sub(r'[.!?]$', '', move_str)  # Remove trailing punctuation

            try:
                move = board.parse_san(move_str)
                san = board.san(move)
                board.push(move)
                validated_moves.append(san)
                move_index += 1
            except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                # Try fuzzy correction
                corrected = fuzzy_correct_move(board, move_str)

                if corrected:
                    try:
                        move = board.parse_san(corrected)
                        san = board.san(move)
                        board.push(move)
                        validated_moves.append(san)
                        corrections.append({
                            'move_number': move_num,
                            'color': color,
                            'original': move_str,
                            'corrected': corrected,
                            'reason': 'fuzzy_match'
                        })
                        move_index += 1
                        continue
                    except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                        pass

                # All correction attempts failed — log and stop
                logger.error(f"Move {move_num} ({color}) '{move_str}' — all corrections failed, skipping")
                failed_in_pass1.append({
                    'move_number': move_num,
                    'color': color,
                    'original': move_str,
                    'board_fen': board.fen()
                })
                # Legacy behavior: break on first failure
                break

    # Build PGN
    game = chess.pgn.Game()
    game.headers["Event"] = metadata.get("event", "Casual Game")
    game.headers["Site"] = "Chesster Scoresheet Scanner"
    game.headers["Date"] = metadata.get("date", "????.??.??")
    game.headers["White"] = metadata.get("white", "?")
    game.headers["Black"] = metadata.get("black", "?")
    game.headers["Result"] = metadata.get("result", "*")
    game.headers["Round"] = metadata.get("round", "?")

    temp_board = chess.Board()
    node = game
    for move_san in validated_moves:
        move = temp_board.parse_san(move_san)
        node = node.add_variation(move)
        temp_board.push(move)

    pgn_string = str(game)
    return pgn_string, corrections, len(validated_moves), len(corrections)


def _validate_legacy(
    raw_moves: str,
    metadata: Dict[str, str],
    openrouter_key: str
) -> Tuple[str, List[Dict], int, int]:
    """Legacy text-based move parsing fallback."""
    board = chess.Board()
    corrections = []
    validated_moves = []

    # Simple regex to find move-like tokens
    tokens = re.findall(
        r'[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?|O-O(?:-O)?[+#]?',
        raw_moves, re.IGNORECASE
    )

    move_number = 0
    for move_str in tokens:
        move_number += 1
        move_str = move_str.strip()
        if not move_str:
            continue

        try:
            move = board.parse_san(move_str)
            san = board.san(move)
            board.push(move)
            validated_moves.append(san)
        except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
            corrected = fuzzy_correct_move(board, move_str)
            if corrected:
                try:
                    move = board.parse_san(corrected)
                    san = board.san(move)
                    board.push(move)
                    validated_moves.append(san)
                    corrections.append({
                        'move_number': move_number,
                        'original': move_str,
                        'corrected': corrected,
                        'reason': 'fuzzy_match'
                    })
                    continue
                except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                    pass
            # Skip
            break

    game = chess.pgn.Game()
    game.headers["Event"] = metadata.get("event", "Casual Game")
    game.headers["Site"] = "Chesster Scoresheet Scanner"
    game.headers["Date"] = metadata.get("date", "????.??.??")
    game.headers["White"] = metadata.get("white", "?")
    game.headers["Black"] = metadata.get("black", "?")
    game.headers["Result"] = "*"

    temp_board = chess.Board()
    node = game
    for move_san in validated_moves:
        move = temp_board.parse_san(move_san)
        node = node.add_variation(move)
        temp_board.push(move)

    return str(game), corrections, len(validated_moves), len(corrections)


@scoresheet_bp.route('/convert', methods=['POST'])
def convert_scoresheet_to_pgn():
    """
    Convert scoresheet images to PGN notation.

    Expects JSON body with:
    - images: list of base64 encoded image strings
    - metadata: optional dict with white, black, event, date, result, round

    Returns:
    - pgn: PGN string
    - moves_total: total number of moves
    - moves_corrected: number of corrected moves
    - corrections: list of correction details
    - confidence: estimated confidence score
    - fen_final: final board position FEN
    - model_used: which model was used for extraction
    """
    try:
        data = request.get_json()

        if not data or 'images' not in data:
            return jsonify({'error': 'No images provided'}), 400

        images = data['images']
        metadata = data.get('metadata', {})

        if not isinstance(images, list) or len(images) == 0:
            return jsonify({'error': 'Images must be a non-empty list'}), 400

        if len(images) > 4:
            return jsonify({'error': 'Maximum 4 images allowed'}), 400

        # Get OpenRouter API key
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        if not openrouter_key:
            logger.error("OPENROUTER_API_KEY not configured")
            return jsonify({'error': 'OpenRouter API key not configured'}), 500

        # Use 3-pass voting pipeline for better accuracy
        logger.info(f"Starting 3-pass voting pipeline with {len(images)} image(s)")
        pgn, corrections, moves_total, moves_corrected = validate_and_build_pgn(
            "",  # raw_moves_text not needed for voting
            metadata,
            openrouter_key,
            images,
            use_voting=True
        )

        # Calculate confidence score
        if moves_total == 0:
            confidence = 0.0
        elif moves_corrected == 0:
            confidence = 1.0
        else:
            confidence = max(0.3, 1.0 - (moves_corrected / moves_total) * 0.7)

        # Get final FEN
        board = chess.Board()
        game = chess.pgn.read_game(StringIO(pgn))
        if game:
            for move in game.mainline_moves():
                board.push(move)
        fen_final = board.fen()

        logger.info(f"Scoresheet conversion complete: {moves_total} moves, {moves_corrected} corrected, confidence={confidence:.2f}")

        return jsonify({
            'pgn': pgn,
            'moves_total': moves_total,
            'moves_corrected': moves_corrected,
            'corrections': corrections,
            'confidence': confidence,
            'fen_final': fen_final,
            'model_used': PRIMARY_MODEL
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
        'openrouter_configured': bool(openrouter_key),
        'primary_model': PRIMARY_MODEL,
        'fallback_model': FALLBACK_MODEL,
        'correction_model': CORRECTION_MODEL
    })
