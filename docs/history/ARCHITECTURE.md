# Architecture Documentation - Ultimate Chess Learning Platform

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagrams](#architecture-diagrams)
3. [Frontend Architecture](#frontend-architecture)
4. [Backend Architecture](#backend-architecture)
5. [Data Flow](#data-flow)
6. [Infrastructure](#infrastructure)
7. [Security](#security)
8. [Scalability](#scalability)

## System Overview

The Ultimate Chess Learning Platform is a full-stack application built using a **microservices-inspired architecture** with a monolithic backend for simplicity.

### High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                         Client (Browser)                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │    Next.js 16 Frontend (SSR + Client Components)     │   │
│  │  - Material UI                                        │   │
│  │  - Stockfish WASM (client-side engine)              │   │
│  │  - Chess.js (game logic)                            │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓ ↑ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────┐
│                      Flask Backend (Python)                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           REST API + WebSocket Endpoints             │   │
│  │  - Chess Analysis API                                │   │
│  │  - Game Search API                                   │   │
│  │  - AI Chat API (RAG System)                         │   │
│  │  - User Management (Clerk JWT)                      │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │               Multi-Agent RAG System                 │   │
│  │  - Router Agent (classify queries)                   │   │
│  │  - Retriever Agent (search vector DB)               │   │
│  │  - Answer Agent (LLM generation)                    │   │
│  │  - Game Search Agent (specialized retrieval)        │   │
│  │  - Orchestrator (coordinate agents)                 │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    Core Services                     │   │
│  │  - Stockfish Engine (native)                        │   │
│  │  - Vector Store Service (Weaviate client)           │   │
│  │  - Conversation Memory (Redis + SQLite)             │   │
│  │  - Whisper STT / ElevenLabs TTS                     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓ ↑
┌─────────────────────────────────────────────────────────────┐
│                    External Services                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Weaviate │  │  Redis   │  │ Anthropic│  │  OpenAI  │   │
│  │ (Vector  │  │ (Cache)  │  │ (Claude) │  │ (GPT-4o) │   │
│  │   DB)    │  │          │  │          │  │          │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│  │  Clerk   │  │ Lichess  │  │Chess.com │                 │
│  │  (Auth)  │  │   API    │  │   API    │                 │
│  └──────────┘  └──────────┘  └──────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

## Architecture Diagrams

### Component Interaction Flow

```
User Request → Next.js Frontend → Flask API → Service Layer → External APIs
                     ↓                                ↓
              Stockfish WASM                   Weaviate / Redis
                     ↓                                ↓
              Direct Response              Multi-Agent RAG Response
```

### Multi-Agent RAG Pipeline

```
User Query (via WebSocket)
        ↓
┌───────────────┐
│ Router Agent  │ ← Classifies query type
└───────────────┘   (analysis, search, general)
        ↓
   ┌────────────────────┐
   │ Routing Decision   │
   └────────────────────┘
        ├─────────────────┬─────────────────┐
        ↓                 ↓                 ↓
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│Game Search   │  │ Retriever    │  │Direct Answer │
│   Agent      │  │   Agent      │  │   Agent      │
└──────────────┘  └──────────────┘  └──────────────┘
        ↓                 ↓                 ↓
   Search Weaviate   Vector Search     Claude API
   for games         for positions     (no context)
        ↓                 ↓                 ↓
   ┌──────────────────────────────────────────┐
   │        Answer Agent (Final LLM)          │
   │  - Synthesizes context from retrievers   │
   │  - Generates user-friendly response      │
   └──────────────────────────────────────────┘
        ↓
   User Response (via WebSocket)
```

## Frontend Architecture

### Technology Stack

- **Framework:** Next.js 16 (App Router with Server Components)
- **Language:** TypeScript 5.9
- **UI Library:** Material UI 7.1 (MUI)
- **Styling:** Tailwind CSS 4 + Emotion
- **State Management:** React hooks (useState, useContext, usehooks-ts)
- **Chess Logic:** chess.js 1.4.0
- **Chess UI:** react-chessboard 4.7.3
- **Chess Engine:** Stockfish.js (WASM versions 11, 16, 17, 17.1)
- **Authentication:** Clerk 6.34 (commented out)
- **Real-time:** Socket.IO client

### Directory Structure

```
frontend/src/
├── app/                    # Next.js App Router
│   ├── layout.tsx          # Root layout (Clerk provider)
│   ├── page.tsx            # Homepage
│   ├── analysis/           # Analysis board page
│   ├── database/           # Database search page
│   ├── learning/           # Learning platform pages
│   └── api/                # API routes (if needed)
├── components/             # React components
│   ├── ChessBoard.tsx      # Main chess board component
│   ├── MoveHistory.tsx     # Move list display
│   ├── EngineAnalysis.tsx  # Stockfish analysis panel
│   └── ChatWindow.tsx      # AI chat interface
├── hooks/                  # Custom React hooks
│   ├── useChesster.ts      # Main AI chat hook (47KB)
│   ├── useEngine.ts        # Stockfish integration
│   └── useChessGame.ts     # Game state management
├── stockfish/              # Stockfish WASM integration
│   ├── engine/
│   │   ├── engine.ts       # Engine interface
│   │   ├── UciEngine.ts    # UCI protocol implementation
│   │   └── Stockfish*.ts   # Version-specific engines
│   └── hooks/
│       └── useEngine.ts    # React hook for engine
├── theme/                  # Material UI theme
│   └── theme.ts
└── utils/                  # Utility functions
```

### Key Design Patterns

#### 1. Server-Side Rendering (SSR)

```typescript
// app/page.tsx
export default async function HomePage() {
  // Server component - runs on server
  const initialData = await fetchInitialData();

  return <ClientComponent data={initialData} />;
}
```

#### 2. Client Components for Interactivity

```typescript
'use client';  // Marks as client component

export function ChessBoard() {
  const [game, setGame] = useState(new Chess());
  // Client-side state and interactivity
}
```

#### 3. Custom Hooks for Logic Reuse

```typescript
// hooks/useChesster.ts
export function useChesster() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const sendMessage = async (text) => {
    // API call to backend
  };

  return { messages, isLoading, sendMessage };
}
```

#### 4. Context for Global State

```typescript
// contexts/GameContext.tsx
const GameContext = createContext<GameState>(initialState);

export function GameProvider({ children }) {
  const [game, setGame] = useState(new Chess());
  return (
    <GameContext.Provider value={{ game, setGame }}>
      {children}
    </GameContext.Provider>
  );
}
```

### Chess Analysis Flow

1. User makes move on board → `ChessBoard` component
2. `chess.js` validates move → updates game state
3. Optionally trigger Stockfish analysis → `useEngine` hook
4. Display engine evaluation → `EngineAnalysis` component
5. User can ask AI questions → `useChesster` hook → backend API

## Backend Architecture

### Technology Stack

- **Framework:** Flask 3.1.0
- **Language:** Python 3.9+
- **Vector Database:** Weaviate 1.28
- **Cache:** Redis 7
- **Persistence:** SQLite (conversations)
- **Chess Engine:** Stockfish (native binary)
- **LLM:** Anthropic Claude 3.5 Sonnet (primary), OpenAI GPT-4o (fallback)
- **Embeddings:** OpenAI text-embedding-3-small
- **Real-time:** Flask-SocketIO 5.3.7
- **Speech:** Whisper (STT), ElevenLabs (TTS)

### Directory Structure

```
backend/
├── app.py                  # Flask application entry point
├── api/                    # API endpoints
│   ├── chess.py            # Chess analysis endpoints
│   ├── chat.py             # AI chat endpoints
│   ├── database.py         # Game search endpoints
│   └── auth.py             # Authentication (Clerk JWT)
├── etl/                    # ETL pipeline and agents
│   ├── agents/
│   │   ├── router_agent.py         # Query classification
│   │   ├── retriever_agent.py      # Vector search
│   │   ├── answer_agent.py         # LLM generation
│   │   ├── game_search_agent.py    # Game retrieval
│   │   ├── orchestrator.py         # Coordinates agents
│   │   └── conversation_memory.py  # Memory management
│   └── loaders/
│       ├── twic_loader.py          # TWIC PGN ingestion
│       └── lichess_loader.py       # Lichess database
├── services/               # Core services
│   ├── stockfish_engine.py         # Stockfish integration
│   ├── vector_store_service.py     # Weaviate client
│   ├── whisper_service.py          # Speech-to-text
│   └── elevenlabs_tts.py           # Text-to-speech
├── utils/                  # Utilities
│   ├── logging.py
│   └── create_service.py
├── config/                 # Configuration
│   └── config.py
├── requirements.txt
└── .env.example
```

### Multi-Agent RAG System

The backend implements a **multi-agent Retrieval Augmented Generation (RAG)** system:

#### Agent Responsibilities

| Agent | Purpose | Tools |
|-------|---------|-------|
| **Router Agent** | Classifies user query type (analysis, search, general) | Claude Sonnet |
| **Game Search Agent** | Searches Weaviate for chess games by criteria | Weaviate query |
| **Retriever Agent** | Semantic search for similar positions/concepts | Vector search |
| **Answer Agent** | Generates final response with retrieved context | Claude/GPT-4o |
| **Orchestrator** | Coordinates agent workflow and manages conversation | Redis, SQLite |

#### Workflow Example

```python
# User: "Show me games where Kasparov played the Sicilian"

1. Router Agent → classifies as "game_search" query
2. Game Search Agent →
   - Queries Weaviate: player="Kasparov", opening ECO="B*" (Sicilian)
   - Returns top 10 matching games
3. Answer Agent →
   - Receives games as context
   - Generates response: "Here are 10 games where Garry Kasparov played the Sicilian Defense..."
   - Includes PGN snippets, analysis
4. Orchestrator →
   - Saves conversation to Redis (short-term) and SQLite (long-term)
   - Associates with user_id (Clerk) for future retrieval
```

### Conversation Memory System

**Two-tier storage:**

1. **Redis (Hot Cache)** - Last 20 messages, fast retrieval
2. **SQLite (Cold Storage)** - All history, searchable

```python
@dataclass
class ConversationSession:
    session_id: str
    user_id: Optional[str]  # Clerk user ID
    messages: List[ConversationMessage]
    created_at: datetime
    updated_at: datetime

# Save to Redis
redis_client.setex(
    f"conversation:{session_id}",
    ttl=3600,  # 1 hour
    value=json.dumps(session)
)

# Persist to SQLite
db.execute(
    "INSERT INTO conversations VALUES (?, ?, ?, ?)",
    (session_id, user_id, messages_json, timestamp)
)
```

## Data Flow

### Analysis Request Flow

```
User enters position on board
       ↓
Frontend validates with chess.js
       ↓
[Optional] Client-side Stockfish WASM analysis
       ↓
User clicks "Get AI Analysis"
       ↓
POST /api/chess/analyze_position
       ↓
Backend receives FEN string
       ↓
Stockfish (native) analyzes position (depth 20-24)
       ↓
Returns: evaluation, best move, principal variation
       ↓
Answer Agent generates explanation with context
       ↓
Response sent to frontend
       ↓
Display in EngineAnalysis component
```

### Chat Request Flow (RAG)

```
User types question in chat
       ↓
WebSocket emit('chat_message', { text, position? })
       ↓
Backend receives via Socket.IO
       ↓
Router Agent classifies query
       ├─ "game_search" → Game Search Agent
       ├─ "position_analysis" → Retriever Agent + Stockfish
       └─ "general_chess" → Answer Agent (no retrieval)
       ↓
Retrieved context (games, positions, etc.)
       ↓
Answer Agent synthesizes response
       ↓
Conversation saved to Redis + SQLite
       ↓
WebSocket emit('chat_response', { message })
       ↓
Frontend displays in ChatWindow
```

## Infrastructure

### Development Environment

```
Docker Compose (docker-compose.yml)
├── Redis (port 6379)
│   └── Purpose: Conversation cache, Socket.IO message queue
├── Weaviate (port 8080, 50051)
│   └── Purpose: Vector database for 6M+ chess games
└── [Optional] PostgreSQL (port 5432)
    └── Purpose: Future structured data (users, progress)
```

### Production Deployment

**Frontend (Vercel):**
- Next.js optimized build
- Edge caching for static assets
- Serverless functions for API routes (if any)

**Backend (Railway / DigitalOcean):**
- Docker container with Flask app
- Managed Redis (Redis Labs, Upstash)
- Managed Weaviate (Weaviate Cloud Services)
- Environment variables for secrets

**Database:**
- Weaviate Cloud Services (WCS) for vector DB
- PostgreSQL (managed) for relational data (future)
- SQLite embedded for conversations (or migrate to Postgres)

## Security

### Authentication Flow (Clerk)

```
User signs up/in via Clerk UI
       ↓
Clerk issues JWT token
       ↓
Frontend stores token in cookies (httpOnly, secure)
       ↓
API requests include token in Authorization header
       ↓
Backend verifies JWT with Clerk secret key
       ↓
Extracts user_id and associates with request
       ↓
Conversation/progress tied to authenticated user
```

### Security Best Practices

1. **API Keys** - Never commit to git, use environment variables
2. **CORS** - Restrict allowed origins to frontend domain
3. **JWT Verification** - Validate Clerk tokens on every protected endpoint
4. **Rate Limiting** - Implement on LLM endpoints to prevent abuse
5. **Input Validation** - Sanitize user input (FEN strings, chat messages)
6. **HTTPS** - Enforce in production

## Scalability

### Current Limitations

- **Single Backend Instance** - No horizontal scaling yet
- **In-Memory Stockfish** - One process per analysis request
- **Weaviate RAM** - 6M+ games require significant memory
- **LLM Rate Limits** - API provider quotas

### Future Scaling Strategies

1. **Horizontal Scaling**
   - Multiple Flask instances behind load balancer
   - Shared Redis for session state
   - Celery for background job processing

2. **Caching**
   - Cache Stockfish analyses by FEN (Redis)
   - Cache LLM responses for common queries
   - CDN for frontend assets

3. **Database Optimization**
   - Weaviate sharding for larger databases
   - Read replicas for Postgres
   - Partition conversations by user_id

4. **Microservices** (if needed)
   - Separate service for Stockfish analysis
   - Dedicated RAG service
   - Independent deployment and scaling

---

**Last Updated:** Phase 1 Foundation (2025-11-09)
