# Chess Companion Scripts

This directory contains utility scripts for working with the Chess Companion application.

## Available Scripts

- **run_fastapi.py**: Run the FastAPI server
- **import_games.py**: Import chess games from PGN files
- **import_openings.py**: Import chess openings from JSON files
- **import_lessons.py**: Import chess lessons from document files (DOCX, PDF)
- **healthcheck.py**: Check the health of all repositories and services
- **protect_position_db.sh**: Enable immutable protection on `data/twic/games_index.db` and sidecar files
- **unprotect_position_db.sh**: Disable immutable protection for maintenance operations
- **delete_position_db.sh**: Controlled delete flow with explicit YES confirmation + audit log

## Usage Examples

### Running the FastAPI Server

```bash
# Basic usage
./run_fastapi.py

# With custom host and port
./run_fastapi.py --host 127.0.0.1 --port 8080

# With auto-reload for development
./run_fastapi.py --reload

# With multiple workers for production
./run_fastapi.py --workers 4
```

### Importing Chess Games

```bash
# Import a single PGN file
./import_games.py path/to/games.pgn

# Import multiple PGN files
./import_games.py path/to/games1.pgn path/to/games2.pgn

# Import all PGN files in a directory
./import_games.py "path/to/pgn_files/*.pgn"

# Set custom source and batch size
./import_games.py path/to/games.pgn --source "FIDE World Championship 2021" --batch-size 100
```

### Importing Chess Openings

```bash
# Import a single JSON file
./import_openings.py path/to/openings.json

# Import multiple JSON files
./import_openings.py path/to/openings1.json path/to/openings2.json

# Import all JSON files in a directory
./import_openings.py "path/to/json_files/*.json"
```

### Importing Chess Lessons

```bash
# Import a single document file
./import_lessons.py path/to/lessons.docx

# Import multiple document files
./import_lessons.py path/to/lessons1.docx path/to/lessons2.pdf

# Import all document files in a directory
./import_lessons.py "path/to/documents/*.docx" "path/to/documents/*.pdf"

# Custom output directory for extracted images
./import_lessons.py path/to/lessons.pdf --output-images-dir path/to/images_dir
```

### Running Health Checks

```bash
# Basic health check
./healthcheck.py

# With verbose output
./healthcheck.py --verbose

# With custom timeout
./healthcheck.py --timeout 5
```

## Position Database Safety (TWIC)

Target DB: `backend/data/twic/games_index.db`

### 1) Enable protection (default recommended)

```bash
./protect_position_db.sh
```

This sets Linux immutable flag (`chattr +i`) on:
- `games_index.db`
- `games_index.db-wal`
- `games_index.db-shm`
- `games_index.db-journal`

### 2) Controlled deletion (requires explicit confirmation)

```bash
./delete_position_db.sh
```

(Optionally pass a target path for safe testing: `./delete_position_db.sh /tmp/test_games_index.db`)

The script asks exactly:
`Are you sure you want to delete the position database?`

Deletion proceeds **only** if you type `YES` (case-sensitive).

### 3) Maintenance mode (temporary unprotect)

```bash
./unprotect_position_db.sh
# ... maintenance ...
./protect_position_db.sh
```

### Audit Log

All protect/unprotect/delete actions are appended to:
`backend/data/twic/position_db_delete_audit.log`

## Error Handling

All scripts return exit codes that can be used in automation:
- `0`: Success
- `1`: Error or unhealthy service

## Common Issues

- **Error connecting to vector store**: Ensure Weaviate is running and properly configured in `config.py`
- **PGN parsing errors**: Check that PGN files are properly formatted
- **Document extraction errors**: Ensure document files are valid and accessible 