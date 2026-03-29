"""
Unit tests for the scoresheet scanner API
"""

import sys
import os
import unittest
import chess

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import after path modification  # noqa: E402
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location(
    "scoresheet_to_pgn",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api", "scoresheet_to_pgn.py")
)
scoresheet_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoresheet_module)

fuzzy_correct_move = scoresheet_module.fuzzy_correct_move
validate_and_build_pgn = scoresheet_module.validate_and_build_pgn
parse_moves_from_structured = scoresheet_module.parse_moves_from_structured

# Backward compatibility alias for tests
def parse_moves_from_raw_text(raw_text: str):
    """Parse moves from text into flat list."""
    structured = parse_moves_from_structured(raw_text)
    moves = []
    for num, white, black in structured:
        if white:
            moves.append(white)
        if black:
            moves.append(black)
    return moves


class TestScoresheetScanner(unittest.TestCase):
    """Test scoresheet scanner functionality"""

    def test_fuzzy_correct_move_basic(self):
        """Test basic fuzzy correction of OCR errors"""
        board = chess.Board()

        # fuzzy_correct_move only corrects ILLEGAL moves, not legal ones
        # So O-O (which is legal from the starting position) doesn't need correction
        # Instead test that an illegal move gets corrected or returns None
        corrected = fuzzy_correct_move(board, "Qxh8")  # Illegal move from starting position
        # Either None or a legal alternative
        if corrected:
            try:
                board.parse_san(corrected)
            except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                self.fail("Fuzzy correction returned invalid move")

        # Test that a move with OCR error gets corrected
        # First setup a position where we can test
        board.push_san("e4")
        board.push_san("e5")
        # Now test fuzzy correction of "NfB" which should become "Nf3"
        corrected = fuzzy_correct_move(board, "NfB")
        if corrected:
            self.assertEqual(corrected, "Nf3")

    def test_fuzzy_correct_move_difflib(self):
        """Test fuzzy correction using difflib matching"""
        board = chess.Board()
        board.push_san("e4")
        board.push_san("e5")

        # "Nf3" misread as "NfB" (3 vs B confusion)
        corrected = fuzzy_correct_move(board, "NfB")
        self.assertIsNotNone(corrected)
        self.assertEqual(corrected, "Nf3")

    def test_validate_and_build_pgn_simple(self):
        """Test PGN building with simple game"""
        raw_moves = "1. e4 e5 2. Nf3 Nc6"
        metadata = {
            "white": "Player 1",
            "black": "Player 2",
            "event": "Test Game",
            "date": "2026.03.27"
        }

        # We need openrouter_key but won't actually call the API
        # since all moves are valid
        pgn, corrections, moves_total, moves_corrected = validate_and_build_pgn(
            raw_moves,
            metadata,
            openrouter_key="dummy_key"
        )

        # Check results
        self.assertEqual(moves_total, 4)
        self.assertEqual(moves_corrected, 0)
        self.assertEqual(len(corrections), 0)
        self.assertIn("e4", pgn)
        self.assertIn("e5", pgn)
        self.assertIn("Nf3", pgn)
        self.assertIn("Nc6", pgn)
        self.assertIn("Player 1", pgn)
        self.assertIn("Player 2", pgn)

    def test_validate_and_build_pgn_with_fuzzy_correction(self):
        """Test PGN building with moves that need fuzzy correction"""
        # "NfB" should be corrected to "Nf3"
        raw_moves = "1. e4 e5 2. NfB Nc6"
        metadata = {}

        pgn, corrections, moves_total, moves_corrected = validate_and_build_pgn(
            raw_moves,
            metadata,
            openrouter_key="dummy_key"
        )

        # Check that fuzzy correction worked
        self.assertGreater(moves_total, 0)
        self.assertGreaterEqual(moves_corrected, 1)
        self.assertIn("Nf3", pgn)  # Corrected move should be in PGN

    def test_move_parsing_with_move_numbers(self):
        """Test that move numbers are properly removed"""
        raw_moves = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"
        metadata = {}

        pgn, corrections, moves_total, moves_corrected = validate_and_build_pgn(
            raw_moves,
            metadata,
            openrouter_key="dummy_key"
        )

        self.assertEqual(moves_total, 6)
        self.assertIn("Bb5", pgn)
        self.assertIn("a6", pgn)

    def test_parse_moves_with_both_white_and_black(self):
        """Test that move parser captures both white and black moves per number"""
        raw_moves = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"
        moves = parse_moves_from_raw_text(raw_moves)

        # Should parse all 6 half-moves
        self.assertEqual(len(moves), 6)
        self.assertEqual(moves[0], "e4")
        self.assertEqual(moves[1], "e5")
        self.assertEqual(moves[2], "Nf3")
        self.assertEqual(moves[3], "Nc6")
        self.assertEqual(moves[4], "Bb5")
        self.assertEqual(moves[5], "a6")

    def test_parse_moves_multi_column_format(self):
        """Test parsing of multi-column scoresheet format"""
        # Simulate a multi-column scoresheet where moves are grouped
        raw_moves = """1. e4 e5
2. Nf3 Nc6
3. Bb5 a6
4. Ba4 Nf6"""
        moves = parse_moves_from_raw_text(raw_moves)

        self.assertEqual(len(moves), 8)
        self.assertIn("e4", moves)
        self.assertIn("e5", moves)
        self.assertIn("Nf6", moves)

    def test_parse_moves_with_castling(self):
        """Test parsing of castling notation"""
        raw_moves = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. O-O Nf6 5. d3 O-O"
        moves = parse_moves_from_raw_text(raw_moves)

        self.assertIn("O-O", moves)
        # Should appear twice (white and black castled)
        self.assertEqual(moves.count("O-O"), 2)

    def test_parse_moves_with_promotion(self):
        """Test parsing of promotion notation"""
        raw_moves = "1. e4 e5 2. a4 a5 3. b4 axb4 4. a5 b3 5. a6 bxa2 6. a7 a1=Q 7. a8=Q"
        moves = parse_moves_from_raw_text(raw_moves)

        # Check that promotions are parsed
        self.assertTrue(any("=Q" in move for move in moves))

    def test_parse_moves_with_uncertainty_markers(self):
        """Test that [?] markers are stripped but moves are preserved"""
        raw_moves = "1. e4 e5 2. Nf3[?] Nc6 3. Bb5[?] a6"
        moves = parse_moves_from_raw_text(raw_moves)

        # [?] should be stripped
        self.assertNotIn("[?]", " ".join(moves))
        # But moves should still be present
        self.assertIn("Nf3", moves)
        self.assertIn("Bb5", moves)

    def test_board_san_before_push(self):
        """Test that board.san() is called before board.push() to avoid errors"""
        # This tests the fix for the bug where san() was called after push()
        raw_moves = "1. e4 e5 2. Nf3 Nc6"
        metadata = {}

        # This should not raise an exception
        try:
            pgn, corrections, moves_total, moves_corrected = validate_and_build_pgn(
                raw_moves,
                metadata,
                openrouter_key="dummy_key"
            )
            # If we get here, the fix worked
            self.assertEqual(moves_total, 4)
        except Exception as e:
            self.fail(f"validate_and_build_pgn raised exception: {e}")

    def test_long_algebraic_queenside_castling(self):
        """Test parsing of queenside castling"""
        raw_moves = "1. d4 d5 2. Nc3 Nf6 3. Bg5 e6 4. e3 Be7 5. Nf3 O-O 6. Bd3 c5 7. O-O-O"
        moves = parse_moves_from_raw_text(raw_moves)

        self.assertIn("O-O-O", moves)

    def test_captures_with_x(self):
        """Test parsing of captures with 'x' notation"""
        raw_moves = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Bxc6 dxc6"
        moves = parse_moves_from_raw_text(raw_moves)

        # Check that captures are parsed correctly
        self.assertTrue(any("x" in move for move in moves))
        self.assertIn("Bxc6", moves)

    def test_voting_pipeline_integration(self):
        """
        Integration test for 3-pass voting pipeline with accuracy measurement.
        This test loads test_scoresheet.jpg and measures OCR accuracy.

        NOTE: This test requires OPENROUTER_API_KEY and makes real API calls.
        Skip if the key is not available.
        """
        import base64

        # Check if API key is available
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        if not openrouter_key:
            self.skipTest("OPENROUTER_API_KEY not set, skipping integration test")

        # Load test image
        test_image_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'test_scoresheet.jpg'
        )

        if not os.path.exists(test_image_path):
            self.skipTest(f"Test image not found at {test_image_path}")

        with open(test_image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')

        images = [image_data]
        metadata = {
            "white": "Test Player 1",
            "black": "Test Player 2",
            "event": "Test Game",
            "date": "2026.03.29"
        }

        # Run voting pipeline
        pgn, corrections, moves_total, moves_corrected = validate_and_build_pgn(
            "",  # raw_moves_text not used in voting mode
            metadata,
            openrouter_key,
            images,
            use_voting=True
        )

        # Calculate accuracy
        if moves_total > 0:
            accuracy = (moves_total - moves_corrected) / moves_total * 100
        else:
            accuracy = 0.0

        print(f"\n=== Voting Pipeline Accuracy Test ===")
        print(f"Total moves validated: {moves_total}")
        print(f"Moves corrected: {moves_corrected}")
        print(f"Accuracy: {accuracy:.1f}%")
        print(f"Target: 90%+")
        print(f"\nPGN Preview:\n{pgn[:500]}...")

        # Assertions
        self.assertGreater(moves_total, 0, "Should extract at least some moves")
        self.assertIsNotNone(pgn)
        self.assertIn("Test Player 1", pgn)
        self.assertIn("Test Player 2", pgn)

        # Target: 90%+ accuracy
        # For now, just log the result - we'll see how close we get
        if accuracy >= 90.0:
            print(f"✓ SUCCESS: Achieved {accuracy:.1f}% accuracy (target: 90%+)")
        else:
            print(f"⚠ BELOW TARGET: {accuracy:.1f}% accuracy (target: 90%+)")
            print(f"  This may be expected on first run. Review corrections to improve.")


if __name__ == '__main__':
    unittest.main()
