"""
Unit tests for the scoresheet scanner API
"""

import sys
import os
import unittest
import chess

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import after path modification
import importlib.util
spec = importlib.util.spec_from_file_location(
    "scoresheet_to_pgn",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api", "scoresheet_to_pgn.py")
)
scoresheet_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoresheet_module)

fuzzy_correct_move = scoresheet_module.fuzzy_correct_move
validate_and_build_pgn = scoresheet_module.validate_and_build_pgn


class TestScoresheetScanner(unittest.TestCase):
    """Test scoresheet scanner functionality"""

    def test_fuzzy_correct_move_basic(self):
        """Test basic fuzzy correction of OCR errors"""
        board = chess.Board()

        # Test O vs 0 (oh vs zero)
        corrected = fuzzy_correct_move(board, "O-O")  # Should work as castling
        self.assertIsNotNone(corrected)

        # Test illegal move returns None
        corrected = fuzzy_correct_move(board, "Qxh8")  # Illegal move
        # Either None or a legal alternative
        if corrected:
            try:
                board.parse_san(corrected)
            except:
                self.fail("Fuzzy correction returned invalid move")

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


if __name__ == '__main__':
    unittest.main()
