"""
Root conftest.py — ensures backend/ is on sys.path for all tests.

This replaces the per-file sys.path.insert() hack in each test module.
"""

import os
import sys

# Add backend directory to sys.path so imports like `from api.X import Y` work
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
