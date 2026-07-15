# Setup Guide - Ultimate Chess Learning Platform

This guide provides detailed instructions for setting up the chess learning platform locally.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Project Setup](#project-setup)
3. [Docker Services](#docker-services)
4. [Backend Setup](#backend-setup)
5. [Frontend Setup](#frontend-setup)
6. [API Keys Configuration](#api-keys-configuration)
7. [Enabling Clerk Authentication](#enabling-clerk-authentication)
8. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Software

| Software | Minimum Version | Installation |
|----------|----------------|--------------|
| Node.js | 20.9.0 | [nodejs.org](https://nodejs.org) or use nvm |
| Python | 3.9 | [python.org](https://python.org) |
| Docker | 24.0 | [docker.com](https://docs.docker.com/get-docker/) |
| Docker Compose | 2.20 | Included with Docker Desktop |
| Git | 2.40 | [git-scm.com](https://git-scm.com) |

### Optional

- **Stockfish** - Native binary for server-side analysis (auto-downloaded by backend)
- **ffmpeg** - For audio processing if using voice features

### System Requirements

- **RAM**: 8GB minimum (16GB recommended for vector database)
- **Storage**: 10GB minimum (100GB+ if loading full TWIC database)
- **CPU**: Multi-core processor recommended for Stockfish analysis

## Project Setup

### 1. Navigate to Project Directory

```bash
cd /home/marblemaster/Desktop/Cursor/chess-ultimate-app
```

### 2. Verify Directory Structure

```bash
ls -la
```

You should see:
- `frontend/` - Next.js frontend
- `backend/` - Flask backend
- `docker-compose.yml` - Docker services configuration
- `.gitignore`
- `README.md`

## Docker Services

The application requires Redis and Weaviate running via Docker.

### Start Services

```bash
# Start in detached mode
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove volumes (fresh start)
docker-compose down -v
```

### Verify Services

```bash
docker-compose ps
```

Expected output:
```
NAME              IMAGE                                         STATUS
chess-redis       redis:7-alpine                                Up
chess-weaviate    cr.weaviate.io/semitechnologies/weaviate:1.28 Up (healthy)
```

### Service Health Checks

**Redis:**
```bash
docker exec -it chess-redis redis-cli ping
# Expected: PONG
```

**Weaviate:**
```bash
curl http://localhost:8080/v1/.well-known/ready
# Expected: {"class":[],"meta":{"hostname":"...","version":"1.28.0"}}
```

## Backend Setup

### 1. Create Virtual Environment

```bash
cd backend

python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Upgrade pip

```bash
pip install --upgrade pip
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**Note:** This may take 5-10 minutes due to large packages (PyTorch, Transformers).

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and configure (see [API Keys Configuration](#api-keys-configuration)):
- ANTHROPIC_API_KEY (required for AI features)
- OPENAI_API_KEY (required for embeddings)
- CLERK_SECRET_KEY (optional, for Phase 2)

### 5. Create Data Directories

```bash
mkdir -p data/twic data/lichess data/chess_com logs
```

### 6. Test Backend

```bash
python app.py
```

Expected output:
```
INFO:werkzeug:WARNING: This is a development server.
INFO:app:Starting Flask application...
INFO:app:Redis connected: True
INFO:app:Weaviate connected: True
INFO:app:Stockfish initialized
INFO:werkzeug: * Running on http://0.0.0.0:5001
```

Access: [http://localhost:5001/api/health](http://localhost:5001/api/health)

## Frontend Setup

### 1. Install Dependencies

```bash
cd frontend
npm install
```

**Note:** May show warnings about peer dependencies or Node version - these are usually safe to ignore for development.

### 2. Configure Environment

```bash
cp .env.example .env.local
```

Edit `.env.local`:
```env
NEXT_PUBLIC_API_URL=http://localhost:5001
```

For production, set to your deployed backend URL.

### 3. Start Development Server

```bash
npm run dev
```

Expected output:
```
▲ Next.js 16.0.0
- Local:        http://localhost:3000
- Network:      http://192.168.x.x:3000

✓ Ready in Xms
```

Access: [http://localhost:3000](http://localhost:3000)

### 4. Build for Production

```bash
npm run build
npm start
```

## API Keys Configuration

### Required Keys

#### 1. Anthropic API Key (Primary LLM)

**Get Key:**
1. Sign up at [console.anthropic.com](https://console.anthropic.com)
2. Navigate to "API Keys"
3. Create new key
4. Copy key (starts with `sk-ant-`)

**Configure:**
```env
# backend/.env
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here

# frontend/.env.local (optional, for client-side features)
NEXT_PUBLIC_ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

#### 2. OpenAI API Key (Embeddings + Fallback)

**Get Key:**
1. Sign up at [platform.openai.com](https://platform.openai.com)
2. Go to "API keys"
3. Create new secret key
4. Copy key (starts with `sk-`)

**Configure:**
```env
# backend/.env
OPENAI_API_KEY=sk-your-openai-key-here

# frontend/.env.local (optional)
NEXT_PUBLIC_OPENAI_API_KEY=sk-your-openai-key-here
```

### Optional Keys

#### ElevenLabs (Text-to-Speech)

1. Sign up at [elevenlabs.io](https://elevenlabs.io)
2. Get API key from settings
3. Choose voice ID from voice library

```env
# backend/.env
ELEVENLABS_API_KEY=your-elevenlabs-key
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # Example: Rachel
```

## Enabling Clerk Authentication

**Status:** Currently disabled for easier development. Enable in Phase 2.

### 1. Create Clerk Account

1. Sign up at [clerk.com](https://clerk.com)
2. Create new application
3. Choose authentication methods (Email, Google, etc.)

### 2. Get Clerk Keys

From Clerk Dashboard → API Keys:
- **Publishable Key** (starts with `pk_test_`)
- **Secret Key** (starts with `sk_test_`)

### 3. Configure Environment

**Frontend** (`frontend/.env.local`):
```env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_your_key_here
CLERK_SECRET_KEY=sk_test_your_key_here
```

**Backend** (`backend/.env`):
```env
CLERK_SECRET_KEY=sk_test_your_key_here
```

### 4. Uncomment Clerk Code

**File:** [frontend/src/app/layout.tsx](frontend/src/app/layout.tsx)

Find and uncomment:
```typescript
// ClerkProvider disabled for local development without authentication
// import {
//   ClerkProvider,
// } from '@clerk/nextjs'
```

Becomes:
```typescript
import {
  ClerkProvider,
} from '@clerk/nextjs'
```

Then wrap the app with `<ClerkProvider>`:
```typescript
export default function RootLayout({ children }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body>{children}</body>
      </html>
    </ClerkProvider>
  )
}
```

### 5. Update Component Auth Checks

**File:** [frontend/src/app/page.tsx](frontend/src/app/page.tsx) and other pages

Replace simulated auth:
```typescript
// Simulated for no-auth mode
const isSignedIn = true;
const user = { firstName: "Chess Player" };
```

With real Clerk hooks:
```typescript
import { useUser } from "@clerk/nextjs";
const { isSignedIn, user } = useUser();
```

### 6. Restart Frontend

```bash
cd frontend
npm run dev
```

You should now see Clerk sign-in UI when accessing protected routes.

## Troubleshooting

### Backend Issues

#### Port 5001 Already in Use

```bash
# Find process using port 5001
lsof -i :5001

# Kill process
kill -9 <PID>
```

#### Redis Connection Failed

```bash
# Check Redis is running
docker ps | grep chess-redis

# Restart Redis
docker-compose restart redis
```

#### Weaviate Connection Failed

```bash
# Check Weaviate health
curl http://localhost:8080/v1/.well-known/ready

# View logs
docker-compose logs weaviate

# Restart Weaviate
docker-compose restart weaviate
```

#### Import Errors (Python)

```bash
# Ensure virtual environment is activated
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### Frontend Issues

#### Node Version Error

```bash
# Check current version
node --version

# Install Node 20+ using nvm
nvm install 20
nvm use 20
```

#### Module Not Found

```bash
# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install
```

#### Build Fails

```bash
# Check for TypeScript errors
npm run lint

# Clear Next.js cache
rm -rf .next
npm run build
```

### Docker Issues

#### Services Won't Start

```bash
# Check Docker is running
docker info

# Remove all containers and volumes (CAUTION: data loss)
docker-compose down -v
docker-compose up -d
```

#### Out of Disk Space

```bash
# Check Docker disk usage
docker system df

# Clean up unused images and containers
docker system prune -a
```

### API Key Issues

#### 401 Unauthorized from LLM APIs

- Verify API keys are correct (no extra spaces)
- Check API key has credits/usage available
- Ensure `.env` file is in correct location
- Restart backend after updating `.env`

## Next Steps

After successful setup:

1. **Test the Application**
   - Open [http://localhost:3000](http://localhost:3000)
   - Try basic chess analysis
   - Test AI chat functionality

2. **Load Chess Database** (Optional, Phase 4)
   - See [backend/etl/TWIC_EXPANSION_README.md](backend/etl/TWIC_EXPANSION_README.md)
   - Download TWIC games
   - Run ingestion scripts

3. **Enable Authentication** (Phase 2)
   - Follow [Enabling Clerk Authentication](#enabling-clerk-authentication)
   - Test sign-up and sign-in flows

4. **Deploy to Production**
   - See [README.md Deployment](README.md#-deployment) section

## Getting Help

- **Project Issues:** Create GitHub issue
- **Clerk Help:** [clerk.com/docs](https://clerk.com/docs)
- **Weaviate Help:** [weaviate.io/developers/weaviate](https://weaviate.io/developers/weaviate)
- **Next.js Help:** [nextjs.org/docs](https://nextjs.org/docs)
