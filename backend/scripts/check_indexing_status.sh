#!/bin/bash
# Check current indexing status

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

python3 index_positions_chunked.py --status
