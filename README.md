# ♟️ Chesster — AI-Powered Chess Learning Platform

<p align="center">
  <strong>https://chesster.io</strong>
</p>

<p align="center">
  An intelligent chess learning platform combining Stockfish engine analysis, multi-LLM AI coaching, a 4.35M-game database, opening repertoire builder, interactive puzzles, and structured courses — all in one place.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Next.js-16-black?logo=next.js" alt="Next.js 16" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react" alt="React 19" />
  <img src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript" alt="TypeScript 5.9" />
  <img src="https://img.shields.io/badge/Flask-3.1-000000?logo=flask" alt="Flask 3.1" />
  <img src="https://img.shields.io/badge/Stockfish-WASM-8BC34A" alt="Stockfish WASM" />
  <img src="https://img.shields.io/badge/License-Private-red" alt="Private" />
</p>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [AI Architecture](#-ai-architecture)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
- [Environment Variables](#-environment-variables)
- [Deployment](#-deployment)
- [API Reference](#-api-reference)
- [Database](#-database)
- [Scripts & Utilities](#-scripts--utilities)
- [Internationalization](#-internationalization)
- [Piece Themes](#-piece-themes)

---

## 🌐 Overview

Chesster is a full-stack chess learning platform live at **chesster.io**, deployed on a DigitalOcean droplet behind nginx with SSL. It combines:

- **Client-side Stockfish WASM** for instant position evaluation
- **Three AI providers** (Mastra/Gemini, Claude Sonnet 4.0, OpenRouter) intelligently routed for coaching, analysis, and conversation
- **4.35 million master games** (TWIC archive) with instant position search across 290M indexed positions
- **Opening repertoire builder** with tree visualization, spaced repetition training, PGN import/export, and arrow annotations
- **Interactive puzzles**, structured courses, game review, opponent profiling, and voice input

The platform supports **English, Russian, and Kazakh** with full i18n coverage across 27 translation namespaces.

---

## ✨ Features

### 🔬 Position Analysis
- Real-time Stockfish WASM evaluation with eval bar and multi-PV lines
- AI-powered natural language position explanations
- Positional theme detection and radar analysis
- FEN/PGN input, board editor, and image-to-FEN conversion

### 📖 Opening Repertoire (Debut)
- Build and manage White/Black repertoires with interactive opening tree
- Search 4.35M master games by position, player, ECO code, or Elo range
- PGN import/export with drag-and-drop support
- Arrow annotations for move explanations
- Spaced repetition training mode
- Game linking to specific repertoire nodes

### 🧩 Interactive Puzzles
- AI-generated tactical puzzles from positions
- Move sequence validation with animated feedback
- Lottie celebration animations on solve
- Progress tracking per user

### 📚 Structured Learning
- Course → Module → Lesson hierarchy
- Embedded interactive boards in lessons
- Lesson-specific puzzles
- Progress tracking with completion states

### 🤖 AI Chess Coach
- Multi-session chat with conversation history
- Voice input via speech-to-text (faster-whisper)
- Intelligent routing: quick analysis → Gemini, deep coaching → Claude, fallback → OpenRouter
- SSE streaming responses
- Cached LLM responses for repeated queries

### 🎮 Game Viewer & Review
- Full PGN game viewer with move navigation
- AI-powered game review with move-by-move commentary
- Theme scoring and classification
- Chess.com and Lichess game import

### 👤 Opponent Analysis
- Chess.com and Lichess profile analysis
- Opening tendency detection
- Performance statistics and patterns

### 🌍 Internationalization
- English, Russian, Kazakh
- 27 translation namespaces covering every UI surface
- Runtime language switching

---

## 🛠 Tech Stack

### Frontend
| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 16 | App Router + Pages API routes |
| React | 19 | UI framework |
| TypeScript | 5.9 | Type safety |
| MUI | 7.1 | Component library |
| Tailwind CSS | 4 | Utility-first styling |
| chess.js | — | Chess logic & move validation |
| react-chessboard | — | Interactive board rendering |
| Chessground | — | Alternative board renderer |
| Stockfish WASM | — | Client-side engine evaluation |
| Clerk | — | Authentication (sign-in/sign-up, user management) |
| Mastra | — | AI agent framework (Gemini 2.5 Flash) |
| next-intl | — | i18n (en/ru/kk) |
| SWR | — | Data fetching & caching |
| Lottie | — | Animations |

### Backend
| Technology | Version | Purpose |
|------------|---------|---------|
| Flask | 3.1 | REST API + SSE streaming |
| Python | 3.11 | Runtime |
| python-chess | — | Chess logic, PGN parsing, board operations |
| Supabase | — | PostgreSQL database + auth |
| SQLite | — | TWIC game index (43 GB) |
| OpenRouter | — | Multi-LLM gateway (Claude, GPT, Gemini) |
| faster-whisper | tiny | Speech-to-text transcription |
| Docker | — | Backend containerization |

### Infrastructure
| Component | Details |
|-----------|---------|
| Server | DigitalOcean droplet (104.248.190.155) |
| Domain | chesster.io |
| Reverse Proxy | nginx with SSL (certbot / Let's Encrypt) |
| Process Manager | PM2 (frontend) |
| Containers | Docker Compose (backend) |

---

## 🧠 AI Architecture

Chesster uses a **hybrid 3-way AI routing** system. An intelligent router in the frontend decides which provider handles each request based on message content, keywords, and context:

```
┌─────────────────────────────────────────────────┐
│                   User Message                   │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│          Intelligent Router                      │
│       (src/lib/router/index.ts)                  │
│                                                  │
│  Analyzes: keywords, message type, context       │
└──────┬──────────────┬───────────────┬───────────┘
       │              │               │
       ▼              ▼               ▼
┌─────────────┐ ┌───────────┐ ┌──────────────────┐
│   Mastra    │ │ Clawdbot  │ │  Python Backend   │
│  (Gemini    │ │ (Claude   │ │  (OpenRouter      │
│  2.5 Flash) │ │ Sonnet 4) │ │   auto)           │
│             │ │           │ │                    │
│ Fast pos.   │ │ Deep      │ │ Fallback analysis  │
│ analysis    │ │ coaching, │ │ with SSE streaming │
│             │ │ memory,   │ │                    │
│             │ │ personal- │ │                    │
│             │ │ ization   │ │                    │
└─────────────┘ └───────────┘ └──────────────────┘
  Port 3000       Port 19789      Port 5001
  (Next.js)       (Gateway)       (Flask/Docker)
```

| Provider | Model | Strengths | Route Triggers |
|----------|-------|-----------|----------------|
| **Mastra** | Gemini 2.5 Flash via OpenRouter | Fast, low-cost position analysis | Quick questions, eval requests |
| **Clawdbot** | Claude Sonnet 4.0 | Deep coaching, memory, personalization | Coaching, study plans, deep analysis |
| **Python Backend** | OpenRouter auto-select | Reliable fallback, SSE streaming | Fallback, analysis streams |

### Voice Input Pipeline
```
Browser MediaRecorder → WebM/Opus blob
    → POST /api/chat/transcribe
        → faster-whisper (tiny model)
            → Transcribed text → Chat input
```

---

## 📁 Project Structure

```
chess-ultimate-app/
├── frontend/                     # Next.js application
│   ├── src/
│   │   ├── app/                  # App Router pages
│   │   │   ├── page.tsx          # Landing page
│   │   │   ├── dashboard/        # User dashboard
│   │   │   ├── position/         # Analysis board
│   │   │   ├── game/             # Game viewer
│   │   │   ├── debut/            # Opening repertoire builder
│   │   │   ├── editor/           # Board editor
│   │   │   ├── learn/            # Course platform
│   │   │   │   └── [courseSlug]/ # Individual course view
│   │   │   ├── puzzle/           # Interactive puzzles
│   │   │   ├── opponent/         # Opponent analysis
│   │   │   ├── profile/          # User profile
│   │   │   ├── sign-in/          # Clerk sign-in
│   │   │   └── sign-up/          # Clerk sign-up
│   │   │
│   │   ├── components/           # React components
│   │   │   ├── analysis/         # AiChessboard, ChessterAnalysisView, EvalBar
│   │   │   ├── editor/           # BoardEditor, EditorControls, SparePieces
│   │   │   ├── openings/         # DebutBoard, OpeningTree, GameSearchPanel,
│   │   │   │                     # NodeDetailsPanel, PgnImporter, RepertoireSelector
│   │   │   ├── chess/            # AnimatedChessBoard, ArrowOverlay, BoardControls,
│   │   │   │                     # FeedbackDisplay, LottieCelebration, PuzzleSequence
│   │   │   ├── tabs/             # ChaptersTab, ChatTab, Chessdb, EvalGraph,
│   │   │   │                     # GameInfoTab, GameReviewDialog, GameReviewTab,
│   │   │   │                     # LegalMoveTab, ModelSetting, OpeningTab, PgnView,
│   │   │   │                     # PlayerInfoTab, PositionRadarAnalysis, StockfishTab
│   │   │   ├── ui/               # Shared UI primitives
│   │   │   ├── ChatSidebar.tsx   # Multi-session chat sidebar
│   │   │   ├── ClientShell.tsx   # App shell wrapper
│   │   │   ├── LanguageSwitcher.tsx
│   │   │   ├── LoadingScreen.tsx
│   │   │   └── Navbar.tsx
│   │   │
│   │   ├── hooks/                # Custom React hooks
│   │   │   ├── useChesster.ts          # Main analysis hook (56K)
│   │   │   ├── useOpeningRepertoire.ts # Repertoire management
│   │   │   ├── useGameReview.ts        # Game review logic
│   │   │   ├── useChatSessions.ts      # Multi-session chat
│   │   │   ├── useVoiceRecorder.ts     # Voice recording
│   │   │   ├── useRepertoire.ts
│   │   │   ├── useReplayStockfish.ts
│   │   │   ├── useGameTheme.ts
│   │   │   └── useThemeScore.ts
│   │   │
│   │   ├── lib/
│   │   │   └── router/
│   │   │       └── index.ts      # AI provider routing logic
│   │   │
│   │   └── i18n/                 # Translation files (en/ru/kk)
│   │
│   ├── src/pages/api/            # Pages Router API routes
│   │   ├── chat/
│   │   │   ├── stream.ts         # SSE chat orchestrator
│   │   │   └── transcribe.ts     # Voice STT endpoint
│   │   ├── puzzle.ts             # Puzzle generation
│   │   ├── agent.ts              # Mastra agent endpoint
│   │   ├── convert-image.ts      # Image processing
│   │   ├── gametheme.ts          # Theme detection
│   │   └── themescore.ts         # Theme scoring
│   │
│   ├── next.config.ts            # COEP/COOP headers, i18n, cache busting
│   ├── ecosystem.config.js       # PM2 configuration
│   ├── .env.local                # Frontend environment variables
│   └── Dockerfile
│
├── backend/                      # Flask API (Docker)
│   ├── app.py                    # Flask application entry point
│   ├── api/                      # API blueprints
│   │   ├── chat.py               # AI chat with conversation history
│   │   ├── lessons.py            # Course/module/lesson CRUD
│   │   ├── openings.py           # Opening repertoire (1928 lines)
│   │   ├── puzzles.py            # Puzzle generation & tracking
│   │   ├── opponent_analysis.py  # Chess.com/Lichess profiling
│   │   ├── photo_to_fen.py       # Image → FEN conversion
│   │   └── repertoire.py         # Repertoire service
│   │
│   ├── services/
│   │   ├── supabase_client.py
│   │   ├── conversation_manager.py
│   │   ├── llm_session_manager.py
│   │   ├── rate_limiter.py
│   │   └── repertoire_service.py
│   │
│   ├── llm/                      # LLM provider implementations
│   │   ├── anthropic_llm.py
│   │   ├── openai_llm.py
│   │   └── openrouter_llm.py
│   │
│   ├── scripts/                  # Database & maintenance scripts
│   │   ├── add_position_index.py
│   │   ├── index_pgn_database.py
│   │   ├── index_positions_chunked.py
│   │   ├── download_twic_updates.py
│   │   ├── import_games.py
│   │   ├── import_lessons.py
│   │   ├── import_openings.py
│   │   ├── import_lichess_study.py
│   │   └── healthcheck.py
│   │
│   ├── .env                      # Backend environment variables
│   └── Dockerfile                # python:3.11-slim, non-root, port 5001
│
├── docker-compose.yml            # Backend (Flask) + Frontend (Next.js)
├── .env                          # Docker Compose build args
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites

- **Node.js** ≥ 22
- **Python** 3.11+
- **Docker** & Docker Compose
- **PM2** (`npm install -g pm2`)
- **Supabase** project with PostgreSQL
- **Clerk** account for authentication
- **OpenRouter** API key for LLM access

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/chess-ultimate-app.git
cd chess-ultimate-app
```

### 2. Configure Environment Variables

```bash
# Frontend
cp frontend/.env.local.example frontend/.env.local
# Edit with your Clerk, Supabase, OpenRouter, and Mastra keys

# Backend
cp backend/.env.example backend/.env
# Edit with your Supabase, OpenRouter, and LLM API keys

# Docker Compose
cp .env.example .env
# Edit build args if needed
```

See [Environment Variables](#-environment-variables) for the full list.

### 3. Start the Backend (Docker)

```bash
docker compose up -d backend
```

The Flask API starts on port **5002** (mapped to **5001** inside the container).

### 4. Start the Frontend

```bash
cd frontend
npm install
npm run build
pm2 start ecosystem.config.js
```

The Next.js app runs on port **3000**.

### 5. Configure Nginx (Production)

Set up nginx as a reverse proxy with SSL:

```nginx
server {
    listen 443 ssl;
    server_name chesster.io;

    ssl_certificate /etc/letsencrypt/live/chesster.io/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/chesster.io/privkey.pem;

    # Default: Next.js frontend
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
    }

    # SSE chat stream (special buffering)
    location /api/chat/stream {
        proxy_pass http://127.0.0.1:3000;
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
    }

    # Voice transcription (25MB upload limit)
    location /api/chat/transcribe {
        proxy_pass http://127.0.0.1:3000;
        client_max_body_size 25M;
    }

    # Flask backend API routes
    location ~ ^/api/(courses|learn|chat|puzzles|opponent|openings|convert-image|health) {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
    }

    # Flask SSE analysis stream
    location /api/chat/analysis/stream {
        proxy_pass http://127.0.0.1:5001;
        proxy_buffering off;
        proxy_cache off;
    }

    # Health check
    location /health {
        return 200 'OK';
    }
}
```

Install SSL with certbot:
```bash
sudo certbot --nginx -d chesster.io
```

---

## 🔐 Environment Variables

### Frontend (`frontend/.env.local`)

```env
# Clerk Authentication
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
CLERK_SECRET_KEY=sk_live_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/dashboard
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/dashboard

# Supabase
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# Backend URLs
NEXT_PUBLIC_BACKEND_URL=https://chesster.io
NEXT_PUBLIC_API_URL=https://chesster.io/api

# Mastra AI Framework
MASTRA_OPENROUTER_API_KEY=sk-or-v1-...
MASTRA_MODEL=google/gemini-2.5-flash

# Clawdbot Gateway
CLAWDBOT_GATEWAY_URL=http://localhost:19789
CLAWDBOT_GATEWAY_TOKEN=your_gateway_token

# OpenRouter (for frontend API routes)
OPENROUTER_API_KEY=sk-or-v1-...
```

### Backend (`backend/.env`)

```env
# Supabase
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# LLM Providers
OPENROUTER_API_KEY=sk-or-v1-...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Flask
FLASK_ENV=production
FLASK_PORT=5001
```

### Docker Compose (`.env`)

```env
BACKEND_PORT=5002
FRONTEND_PORT=3000
```

---

## 🚢 Deployment

### Production Stack (chesster.io)

```
Internet → nginx (443/SSL) → ┬→ Next.js (PM2, port 3000)   ← Frontend + API routes
                              ├→ Flask (Docker, port 5001)   ← Backend API
                              └→ Clawdbot (port 19789)       ← AI coaching gateway
```

### Deploy Updates

```bash
# Pull latest code
cd /root/chess-app
git pull origin main

# Rebuild & restart backend
docker compose up -d --build backend

# Rebuild & restart frontend
cd frontend
npm run build
pm2 restart all
```

### Health Checks

```bash
# Nginx health
curl https://chesster.io/health

# Backend health
curl http://localhost:5001/api/health

# Frontend (Next.js)
pm2 status

# Backend (Docker)
docker compose ps
```

### Stockfish WASM Headers

The frontend requires Cross-Origin headers for SharedArrayBuffer (Stockfish WASM):

```
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Opener-Policy: same-origin
```

These are configured in `frontend/next.config.ts`.

---

## 📡 API Reference

### Frontend API Routes (Next.js — port 3000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat/stream` | POST | SSE chat orchestrator — routes to Mastra, Clawdbot, or Python backend |
| `/api/chat/transcribe` | POST | Voice message STT via faster-whisper (accepts WebM/Opus, max 25MB) |
| `/api/puzzle` | POST | AI puzzle generation from position |
| `/api/agent` | POST | Direct Mastra agent endpoint |
| `/api/convert-image` | POST | Image processing / photo-to-FEN |
| `/api/gametheme` | POST | Detect positional themes from FEN |
| `/api/themescore` | POST | Score a position across theme dimensions |

### Backend API Routes (Flask — port 5001)

| Endpoint | Method | Description |
|----------|--------|-------------|
| **Chat** | | |
| `/api/chat` | POST | AI chat with conversation history & cached responses |
| `/api/chat/analysis/stream` | POST | SSE streaming position analysis |
| **Courses & Learning** | | |
| `/api/courses` | GET | List all courses |
| `/api/courses/<id>` | GET | Get course with modules & lessons |
| `/api/learn/progress` | GET/POST | User learning progress |
| **Opening Repertoire** | | |
| `/api/openings/repertoires` | GET/POST | List/create repertoires |
| `/api/openings/repertoires/<id>` | GET/PUT/DELETE | Repertoire CRUD |
| `/api/openings/repertoires/<id>/nodes` | GET/POST | Opening tree nodes |
| `/api/openings/repertoires/<id>/nodes/<nid>` | PUT/DELETE | Node CRUD |
| `/api/openings/repertoires/<id>/nodes/<nid>/arrows` | GET/POST/DELETE | Arrow annotations |
| `/api/openings/repertoires/<id>/game-links` | GET/POST/DELETE | Game links |
| `/api/openings/repertoires/<id>/export` | GET | Export repertoire as PGN |
| `/api/openings/repertoires/<id>/import` | POST | Import PGN into repertoire |
| `/api/openings/repertoires/<id>/training` | GET/POST | Spaced repetition training |
| `/api/openings/games/search` | GET | Search TWIC games (player, ECO, Elo, position) |
| `/api/openings/games/<id>` | GET | Get full game PGN |
| `/api/openings/positions/search` | GET | Search by FEN position hash |
| `/api/openings/players/search` | GET | FTS player search |
| **Puzzles** | | |
| `/api/puzzles` | GET/POST | List/generate puzzles |
| `/api/puzzles/<id>/solve` | POST | Submit puzzle solution |
| **Opponent Analysis** | | |
| `/api/opponent/analyze` | POST | Analyze Chess.com/Lichess profile |
| **Utilities** | | |
| `/api/convert-image` | POST | Photo → FEN conversion |
| `/api/health` | GET | Backend health check |

---

## 🗄 Database

### Supabase PostgreSQL (Application Data)

#### Learning Content
```sql
courses          -- id, title, description, slug, image_url, order
modules          -- id, course_id, title, description, order
lessons          -- id, module_id, title, content, fen, pgn, order
lesson_puzzles   -- id, lesson_id, fen, moves, theme
```

#### User Data
```sql
user_progress    -- id, user_id, lesson_id, completed, score, updated_at
user_sessions    -- id, user_id, session_data, created_at
chat_history     -- id, user_id, session_id, role, content, created_at
```

#### Opening Repertoire (Debut)
```sql
opening_repertoires   -- id, user_id, name, color, description, created_at
opening_nodes         -- id, repertoire_id, parent_id, fen, move, comment, nag, sort_order
opening_game_links    -- id, node_id, game_source, game_id, metadata
opening_arrows        -- id, node_id, from_square, to_square, color, comment
```

All tables use **Row Level Security (RLS)** policies scoped to `user_id`.

### TWIC SQLite Database (`games_index.db` — 43 GB)

A comprehensive master games index built from The Week in Chess (TWIC) archives.

| Table | Rows | Description |
|-------|------|-------------|
| `games` | **4,350,122** | White/Black names, Elo, titles, FIDE IDs, result, date, ECO, opening, variation, event, site |
| `players` | **116,718** | Player directory with FTS (full-text search) |
| `game_positions` | **290,731,871** | game_id, ply number, board_hash (position fingerprint) |
| `metadata` | — | Database version, build info |

#### Key Indexes
| Index | Column(s) | Purpose |
|-------|-----------|---------|
| `idx_positions_hash` | `board_hash` | **Instant FEN position search** across 290M positions |
| `idx_games_white` | `white_name` | Player name search |
| `idx_games_black` | `black_name` | Player name search |
| `idx_games_eco` | `eco` | ECO code filtering |
| `idx_games_elo` | `white_elo`, `black_elo` | Elo range filtering |
| `idx_games_date` | `date` | Date range queries |
| `idx_games_year` | `year` | Year filtering |
| `idx_games_result` | `result` | Result filtering |
| `idx_games_fide` | `white_fide_id`, `black_fide_id` | FIDE ID lookup |
| `idx_positions_game` | `game_id` | Game → positions join |

#### Position Search Flow
```
User FEN → python-chess board_hash → SELECT game_id FROM game_positions
WHERE board_hash = ? → JOIN games → Return matching master games
```

---

## 🔧 Scripts & Utilities

### Database Management (`backend/scripts/`)

| Script | Description |
|--------|-------------|
| `download_twic_updates.py` | Download latest TWIC PGN archives |
| `import_games.py` | Import PGN files into SQLite games table |
| `index_pgn_database.py` | Build the PGN database index |
| `add_position_index.py` | Add position hash index to games_index.db |
| `index_positions_chunked.py` | Chunked position indexing (for large datasets) |
| `import_lessons.py` | Import course/lesson content into Supabase |
| `import_openings.py` | Import opening data |
| `import_lichess_study.py` | Import Lichess studies as courses |
| `healthcheck.py` | Backend health check script |

### Common Operations

```bash
# Download latest TWIC games
python backend/scripts/download_twic_updates.py

# Index new positions (chunked for memory efficiency)
python backend/scripts/index_positions_chunked.py

# Import a Lichess study as a course
python backend/scripts/import_lichess_study.py --study-id STUDY_ID

# Check backend health
python backend/scripts/healthcheck.py
```

---

## 🌍 Internationalization

Chesster supports **3 languages** with **27 translation namespaces**:

| Language | Code | Coverage |
|----------|------|----------|
| English | `en` | Full |
| Russian | `ru` | Full |
| Kazakh | `kk` | Full |

### Translation Namespaces

```
common        landing       auth          dashboard
gamification  mascot        navigation    learn
profile       lesson        course        navbar
puzzle        opponent      editor        analysis
game          database      chat          puzzles
lichess       modelSettings review        board
playerSearch  errors        debut
```

Translations are managed via `next-intl` with runtime language switching through the `LanguageSwitcher` component.

---

## 🎨 Piece Themes

Chesster ships with **16 custom piece themes**:

| | | | |
|---|---|---|---|
| Anime | Apollo | Artemis | Attack |
| Cburnett | Clash | Cyborg | Fritz |
| Fritz2 | Hades | Halloween | Hera |
| Juno | Jupiter | Mars | Minerva |

Themes are selectable per-user and persist across sessions.

---

## 📐 Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| **Stockfish WASM (client-side)** | Zero-latency evaluation, no server load for engine analysis |
| **3-way AI routing** | Cost optimization: cheap model for quick queries, premium model for deep coaching |
| **SQLite for TWIC** | Single-file 43GB database with custom indexes outperforms PostgreSQL for read-heavy position search |
| **SSE over WebSocket** | Simpler infrastructure, works through nginx without upgrades, sufficient for streaming responses |
| **Next.js Pages API + App Router** | API routes in Pages for SSE compatibility, UI in App Router for RSC benefits |
| **PM2 + Docker** | PM2 for Node.js process management with auto-restart; Docker for Python isolation |
| **Clerk for auth** | Zero-config auth with social login, webhook support, and Supabase integration |

---

## 📄 License

Private repository. All rights reserved.

---

<p align="center">
  Built with ♟️ by the Chesster team
</p>
