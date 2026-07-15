# Comprehensive Testing Guide - Phase 1: Multi-Tenant Server-Side LLM

## Overview

This guide provides step-by-step instructions for testing the newly implemented server-managed LLM architecture. The system now uses a centralized Anthropic API key managed by the backend, eliminating the need for users to configure their own API keys.

**Key Features Implemented:**
- ✅ Server-managed Claude 3.5 Sonnet integration
- ✅ Conversation context tracking across messages
- ✅ Rate limiting (50 requests/hour, 200 requests/day per user)
- ✅ Multi-user conversation isolation
- ✅ JWT-based authentication via Clerk
- ✅ Database-backed conversation history

---

## Prerequisites

Before testing, ensure you have:

1. **Database Migration Completed:**
   - Tables created: `analysis_conversations`, `analysis_chat_messages`, `api_usage`
   - Verify in Supabase SQL Editor:
   ```sql
   SELECT table_name,
          (SELECT COUNT(*) FROM information_schema.columns
           WHERE table_name = t.table_name) as column_count
   FROM information_schema.tables t
   WHERE table_schema = 'public'
     AND table_name IN ('analysis_conversations', 'analysis_chat_messages', 'api_usage')
   ORDER BY table_name;
   ```
   - Expected output:
   ```
   analysis_chat_messages    | 9
   analysis_conversations    | 6
   api_usage                | 10
   ```

2. **Environment Variables Configured:**

   **Backend** (`backend/.env`):
   ```bash
   ANTHROPIC_API_KEY=sk-ant-api03-...
   CLERK_SECRET_KEY=sk_test_...
   SUPABASE_URL=https://qtzujwiqzbgyhdgulvcd.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

   **Frontend** (`frontend/.env.local`):
   ```bash
   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
   CLERK_SECRET_KEY=sk_test_...
   NEXT_PUBLIC_BACKEND_URL=http://localhost:5001
   NEXT_PUBLIC_SUPABASE_URL=https://qtzujwiqzbgyhdgulvcd.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

3. **Dependencies Installed:**
   ```bash
   # Backend
   cd /home/marblemaster/Desktop/Cursor/chess-ultimate-app/backend
   pip install -r requirements.txt

   # Frontend
   cd /home/marblemaster/Desktop/Cursor/chess-ultimate-app/frontend
   npm install
   ```

---

## Part 1: Backend Service Testing

### 1.1 Start Backend Server

```bash
cd /home/marblemaster/Desktop/Cursor/chess-ultimate-app/backend
source venv/bin/activate
python app.py
```

**Expected Console Output:**
```
✅ Lessons API registered
✅ Chat API registered (server-managed LLM)
LLM Session Manager initialized: global_limit=50, user_limit=3
Conversation Manager initialized
Rate Limiter initialized (in-memory mode)
 * Running on http://localhost:5001
```

**Verify Backend is Running:**
```bash
ps aux | grep "python.*app.py" | grep -v grep
```

### 1.2 Test Health Endpoint

```bash
curl http://localhost:5001/api/chat/health | python3 -m json.tool
```

**Expected Response:**
```json
{
  "status": "healthy",
  "llm_stats": {
    "active_requests": 0,
    "total_processed": 0,
    "total_errors": 0,
    "active_users": 0,
    "model": "claude-3-5-sonnet-20241022"
  },
  "rate_limiter_stats": {
    "active_users": 0,
    "users_by_tier": {}
  }
}
```

**✅ Success Criteria:**
- Status code: 200
- `status` field: "healthy"
- `llm_stats` shows model name
- No errors in backend logs

### 1.3 Test Chat Endpoint (Authenticated)

**Step 1: Get Clerk JWT Token**

Open your browser console (F12) on http://localhost:3000 after signing in:
```javascript
await window.Clerk.session.getToken()
```

Copy the returned token.

**Step 2: Test Analysis Endpoint**

```bash
TOKEN="your_token_from_step_1"

curl -X POST http://localhost:5001/api/chat/analysis \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
    "query": "What is the best move in this position?",
    "context_type": "position"
  }' | python3 -m json.tool
```

**Expected Response:**
```json
{
  "success": true,
  "response": "In this position after 1.e4, Black has several strong options...",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "tokens_used": 150,
  "response_time_ms": 1250,
  "usage": {
    "hourly_remaining": 49,
    "daily_remaining": 199,
    "tier": "free"
  }
}
```

**✅ Success Criteria:**
- Status code: 200
- `success`: true
- `response` contains chess analysis
- `conversation_id` is a valid UUID
- `tokens_used` > 0
- `usage` shows remaining requests

**Step 3: Test Follow-up with Context**

Use the `conversation_id` from previous response:

```bash
CONVERSATION_ID="uuid-from-previous-response"

curl -X POST http://localhost:5001/api/chat/analysis \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{
    \"fen\": \"rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1\",
    \"query\": \"Why is that move better than d5?\",
    \"conversation_id\": \"$CONVERSATION_ID\",
    \"context_type\": \"position\"
  }" | python3 -m json.tool
```

**✅ Success Criteria:**
- Response references previous context (e.g., "As I mentioned earlier...")
- Same `conversation_id` returned
- `usage.hourly_remaining` decreased by 1

### 1.4 Test Rate Limiting

```bash
# Send 51 requests rapidly (bash loop)
for i in {1..51}; do
  echo "Request $i:"
  curl -X POST http://localhost:5001/api/chat/analysis \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{
      "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
      "query": "Test rate limit",
      "context_type": "general"
    }' -w "\nStatus: %{http_code}\n\n" -s -o /dev/null
  sleep 0.5
done
```

**Expected Behavior:**
- Requests 1-50: Status 200
- Request 51: Status 429 (Too Many Requests)

**Expected 429 Response:**
```json
{
  "success": false,
  "error": "Rate limit exceeded. Please try again later.",
  "limits": {
    "hourly_limit": 50,
    "hourly_remaining": 0,
    "daily_limit": 200,
    "daily_remaining": 150
  }
}
```

**✅ Success Criteria:**
- 51st request returns 429
- Error message is user-friendly
- `hourly_remaining` = 0

### 1.5 Verify Database Storage

Check Supabase dashboard or run SQL query:

```sql
-- Check conversations created
SELECT id, user_id, conversation_type, created_at
FROM analysis_conversations
ORDER BY created_at DESC
LIMIT 5;

-- Check messages stored
SELECT conversation_id, role, LEFT(content, 50) as content_preview, tokens_used, timestamp
FROM analysis_chat_messages
ORDER BY timestamp DESC
LIMIT 10;

-- Check API usage tracking
SELECT user_id, endpoint, tokens_used, success, timestamp
FROM api_usage
ORDER BY timestamp DESC
LIMIT 10;
```

**✅ Success Criteria:**
- Conversations appear in `analysis_conversations`
- Messages stored in `analysis_chat_messages` with correct roles ('user', 'assistant')
- API usage logged in `api_usage` with token counts

---

## Part 2: Frontend Integration Testing

### 2.1 Start Frontend Server

```bash
cd /home/marblemaster/Desktop/Cursor/chess-ultimate-app/frontend
npm run dev
```

**Expected Console Output:**
```
> next dev
▲ Next.js 15.1.6
- Local:        http://localhost:3000
✓ Starting...
✓ Ready in 2.1s
```

**Verify Frontend is Running:**
Open http://localhost:3000 in your browser.

### 2.2 Test Authentication Flow

**Step 1: Sign In**
1. Navigate to http://localhost:3000
2. If not signed in, you should see Clerk authentication
3. Sign in with your Clerk account (or create one)
4. Verify you're redirected to the dashboard

**✅ Success Criteria:**
- Sign-in process completes without errors
- Redirected to `/dashboard` after sign-in
- User profile appears in the UI

### 2.3 Test AI Chat in Lesson Pages

**Step 1: Navigate to a Lesson**
1. From dashboard, click "Start Learning" on Chess Fundamentals
2. Click "Start" on the first lesson (Introduction to Forks)
3. Locate the AI Tutor chat interface (right sidebar on desktop)

**Step 2: Send First Message**
1. Type a question: "What is a fork in chess?"
2. Click Send or press Enter
3. Observe loading state

**Expected Behavior:**
- Loading indicator appears (typing animation or spinner)
- Response appears within 3-5 seconds
- Message appears in chat with AI avatar/icon
- No errors in browser console (F12)
- **NO "API key not configured" errors**

**✅ Success Criteria:**
- AI response displayed correctly
- Response is relevant to forks in chess
- No API key configuration errors
- Message persists after page refresh

**Step 3: Send Follow-up Message**
1. Type a follow-up question: "Can you give me an example of a fork?"
2. Send the message

**Expected Behavior:**
- AI response references previous context
- Conversation flows naturally
- Same conversation ID used (check Network tab in F12)

**✅ Success Criteria:**
- Follow-up response shows context awareness
- No repetition of previous explanations
- Conversation ID remains consistent

### 2.4 Test Conversation Persistence

**Step 1: Start Conversation**
1. Send 3 messages in a lesson's AI chat
2. Note the conversation content

**Step 2: Refresh Page**
1. Press F5 or Cmd/Ctrl+R to reload the page
2. Check if conversation history appears

**Expected Behavior:**
- Chat history loads automatically
- All previous messages visible
- Can continue conversation from where it left off

**✅ Success Criteria:**
- Conversation history persists across page reloads
- Message order preserved
- Can send new messages and maintain context

### 2.5 Test Multiple Conversations

**Step 1: Start Chat in Lesson 1**
1. Navigate to first lesson
2. Send a message: "What is a fork?"
3. Note the conversation

**Step 2: Navigate to Different Lesson**
1. Go back to course page
2. Open second lesson (Fork Exercise 1)
3. Check the AI chat

**Expected Behavior:**
- New conversation started (different conversation_id)
- Messages from Lesson 1 don't appear in Lesson 2 chat
- Each lesson has separate conversation history

**✅ Success Criteria:**
- Conversations isolated by lesson
- No cross-contamination between different lessons
- Can switch between lessons without data loss

### 2.6 Verify No API Key Configuration UI

**Step 1: Check Chat Interface**
1. Look for any "API Settings" or "Configure API Key" options in the chat sidebar
2. Check for ModelSetting component or similar

**Expected Behavior:**
- No API key input fields visible
- Info box displays: "🤖 AI Model: Claude 3.5 Sonnet"
- Message states: "Powered by server-managed Anthropic API. No configuration required!"

**✅ Success Criteria:**
- API key configuration completely removed
- Users cannot enter API keys
- Clear messaging about server-managed AI

---

## Part 3: Multi-User Testing

### 3.1 Test User Isolation

**Step 1: User A Signs In**
1. Sign in as User A (your primary account)
2. Navigate to a lesson
3. Send 3 messages in AI chat
4. Note the conversation ID (check Network tab → POST request → Response)

**Step 2: User B Signs In**
1. Open incognito/private browser window
2. Navigate to http://localhost:3000
3. Sign in as User B (different Clerk account)
4. Navigate to the same lesson
5. Check AI chat interface

**Expected Behavior:**
- User B sees empty chat (no history)
- User B cannot see User A's conversations

**Step 3: User B Starts Conversation**
1. Send a message as User B
2. Note the conversation ID

**Step 4: Verify Database Isolation**
Query Supabase:
```sql
SELECT id, user_id, conversation_type
FROM analysis_conversations
WHERE user_id IN ('user_a_clerk_id', 'user_b_clerk_id');
```

**✅ Success Criteria:**
- Each user has separate conversation records
- User A's conversations not visible to User B
- Conversation IDs are different
- Database shows correct user_id for each conversation

### 3.2 Test Concurrent Usage

**Step 1: Simultaneous Requests**
1. Have User A and User B both send messages at the same time
2. Both should receive responses

**Expected Behavior:**
- Both users get responses within 3-5 seconds
- No interference between requests
- Rate limits applied per-user (not global)

**✅ Success Criteria:**
- Both requests succeed
- Response times remain reasonable (< 5 seconds)
- No "too many requests" errors for either user

---

## Part 4: Error Handling Testing

### 4.1 Test Backend Unavailable

**Step 1: Stop Backend**
```bash
# Find backend process
ps aux | grep "python.*app.py" | grep -v grep

# Kill the process (use PID from above)
kill -9 <PID>
```

**Step 2: Try to Send Chat Message**
1. In frontend, try to send a chat message

**Expected Behavior:**
- Error message appears: "Failed to connect to AI service" or similar
- No infinite loading state
- User-friendly error message (not raw network error)

**✅ Success Criteria:**
- Clear error message displayed
- UI remains functional (can try again)
- No browser console errors about undefined responses

**Step 3: Restart Backend and Retry**
```bash
cd /home/marblemaster/Desktop/Cursor/chess-ultimate-app/backend
source venv/bin/activate
python app.py > backend.log 2>&1 &
```

Wait 5 seconds, then send chat message again.

**✅ Success Criteria:**
- Chat works again after backend restart
- Previous conversation history still available

### 4.2 Test Invalid JWT Token

**Step 1: Manually Send Request with Invalid Token**
```bash
curl -X POST http://localhost:5001/api/chat/analysis \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer invalid_token_12345" \
  -d '{
    "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "query": "Test",
    "context_type": "general"
  }'
```

**Expected Response:**
```json
{
  "error": "Invalid token: ..."
}
```
Status code: 401

**✅ Success Criteria:**
- Returns 401 Unauthorized
- Error message is clear
- Backend logs the authentication failure

### 4.3 Test Missing Required Fields

**Step 1: Send Request Without FEN**
```bash
TOKEN="your_valid_token"

curl -X POST http://localhost:5001/api/chat/analysis \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "What is the best move?"
  }'
```

**Expected Response:**
```json
{
  "success": false,
  "error": "Missing required field: fen"
}
```
Status code: 400

**✅ Success Criteria:**
- Returns 400 Bad Request
- Clear validation error message
- Request not processed by LLM

---

## Part 5: Performance Testing

### 5.1 Test Response Times

**Step 1: Measure Average Response Time**
```bash
TOKEN="your_valid_token"

# Send 10 requests and measure time
for i in {1..10}; do
  echo "Request $i:"
  /usr/bin/time -f "Time: %E" curl -X POST http://localhost:5001/api/chat/analysis \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{
      "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
      "query": "What is the best move?",
      "context_type": "position"
    }' -s -o /dev/null -w "\nHTTP Status: %{http_code}\n"
  echo "---"
done
```

**Expected Performance:**
- Average response time: 2-4 seconds
- No timeouts (30-second backend timeout should never trigger)
- Consistent performance across requests

**✅ Success Criteria:**
- 95% of requests complete in < 5 seconds
- No 504 Gateway Timeout errors
- Response times logged in `api_usage` table match actual times

### 5.2 Test Concurrent Load

**Step 1: Simulate 10 Concurrent Users**
```bash
TOKEN="your_valid_token"

# Run 10 requests in parallel
for i in {1..10}; do
  (curl -X POST http://localhost:5001/api/chat/analysis \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d "{
      \"fen\": \"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1\",
      \"query\": \"Request $i\",
      \"context_type\": \"general\"
    }" -s -o /tmp/response_$i.json -w "Request $i: %{http_code}\n") &
done

wait
echo "All requests completed"
```

**Expected Behavior:**
- All 10 requests succeed (status 200)
- No request exceeds 10 seconds
- Backend logs show concurrent processing

**✅ Success Criteria:**
- All requests return 200
- No "too many concurrent requests" errors (global limit is 50)
- LLM session manager stats show multiple active requests

---

## Success Criteria Summary

Phase 1 is **100% COMPLETE** when all of the following are true:

### Backend
- ✅ Database migration run successfully (3 tables created)
- ✅ Backend health check returns "healthy"
- ✅ Chat endpoint responds to authenticated requests
- ✅ Rate limiting enforces 50 req/hour limit
- ✅ Conversations stored in database
- ✅ Messages associated with correct conversation_id
- ✅ API usage tracked with token counts
- ✅ Error responses return appropriate status codes

### Frontend
- ✅ useChesster hook calls new `/api/chat/analysis` endpoint
- ✅ Clerk JWT authentication working
- ✅ API key configuration UI removed/hidden
- ✅ Chat interface functional in lesson pages
- ✅ Conversation history persists across page reloads
- ✅ Loading states display correctly
- ✅ Error messages are user-friendly

### Integration
- ✅ End-to-end chat flow works (sign in → navigate → ask → receive response)
- ✅ Conversation context maintained across follow-up messages
- ✅ Multi-user isolation verified (User A can't see User B's chats)
- ✅ Rate limiting applied per-user (not globally)
- ✅ Performance acceptable (< 5 second avg response time)
- ✅ No errors in browser console during normal usage
- ✅ No errors in backend logs during normal usage

---

## Troubleshooting Guide

### Issue 1: Backend Won't Start

**Symptom:** `ModuleNotFoundError: No module named 'X'`

**Solution:**
```bash
cd /home/marblemaster/Desktop/Cursor/chess-ultimate-app/backend
source venv/bin/activate
pip install -r requirements.txt
```

**Verify imports:**
```bash
python -c "from services.llm_session_manager import get_session_manager"
python -c "from services.conversation_manager import get_conversation_manager"
python -c "from services.rate_limiter import get_rate_limiter"
python -c "from api.chat import chat_bp"
```

### Issue 2: Chat Endpoint Returns 500

**Symptom:** Status 500 with generic error message

**Check backend logs:**
```bash
tail -50 /home/marblemaster/Desktop/Cursor/chess-ultimate-app/backend/backend.log | grep ERROR
```

**Common causes:**
1. **Missing ANTHROPIC_API_KEY:**
   ```bash
   grep ANTHROPIC_API_KEY backend/.env
   ```
   Verify key starts with `sk-ant-api03-`

2. **Supabase connection failed:**
   ```bash
   python -c "from supabase import create_client; import os; from dotenv import load_dotenv; load_dotenv(); client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY')); print('Connected:', client.table('analysis_conversations').select('id').limit(1).execute())"
   ```

3. **Anthropic API key invalid:**
   ```bash
   python -c "from anthropic import Anthropic; import os; from dotenv import load_dotenv; load_dotenv(); client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY')); print('API key valid')"
   ```

### Issue 3: Frontend Can't Connect to Backend

**Symptom:** "Failed to fetch" or network errors in browser console

**Check CORS settings:**
Verify [backend/app.py](backend/app.py) has CORS configured:
```python
CORS(app, resources={r"/api/*": {"origins": "*"}})
```

**Check environment variable:**
```bash
cat frontend/.env.local | grep NEXT_PUBLIC_BACKEND_URL
```
Should show: `NEXT_PUBLIC_BACKEND_URL=http://localhost:5001`

**Verify backend is accessible:**
```bash
curl http://localhost:5001/api/chat/health
```

**Check browser Network tab:**
1. Open Developer Tools (F12)
2. Go to Network tab
3. Try sending a chat message
4. Check the request to `/api/chat/analysis`
5. Look at Request Headers → Authorization → Should have "Bearer ey..."

### Issue 4: Rate Limit Triggered Immediately

**Symptom:** First request returns 429

**Check if rate limiter persisted from previous session:**
Rate limiter is in-memory, so restart backend to reset:
```bash
# Kill backend
ps aux | grep "python.*app.py" | awk '{print $2}' | xargs kill -9

# Restart backend
cd /home/marblemaster/Desktop/Cursor/chess-ultimate-app/backend
source venv/bin/activate
python app.py > backend.log 2>&1 &
```

**Or use different user account:**
Sign out and sign in with different Clerk account.

### Issue 5: Conversation Context Not Maintained

**Symptom:** Follow-up questions don't reference previous context

**Check conversation ID tracking:**
1. Open browser Developer Tools (F12)
2. Go to Network tab
3. Send first message, check Response → `conversation_id`
4. Send follow-up message, check Request → should include same `conversation_id`

**If conversation_id is null/missing:**
Check [frontend/src/hooks/useChesster.ts:152](frontend/src/hooks/useChesster.ts#L152):
```typescript
const conversationIdRef = useRef<string | null>(null);
```

Verify line ~270 saves conversation ID:
```typescript
if (data.conversation_id) {
  conversationIdRef.current = data.conversation_id;
}
```

**Check backend context retrieval:**
Query database:
```sql
SELECT conversation_id, role, content, timestamp
FROM analysis_chat_messages
WHERE conversation_id = 'your-conversation-id-here'
ORDER BY timestamp;
```
Should show alternating user/assistant messages.

---

## Monitoring Commands

### Check Backend Health
```bash
curl http://localhost:5001/api/chat/health | python3 -m json.tool
```

### View Recent Backend Logs
```bash
tail -50 /home/marblemaster/Desktop/Cursor/chess-ultimate-app/backend/backend.log
```

### View Live Backend Logs
```bash
tail -f /home/marblemaster/Desktop/Cursor/chess-ultimate-app/backend/backend.log
```

### Check Database Usage Statistics
```sql
-- Conversation count by user
SELECT user_id, COUNT(*) as conversation_count
FROM analysis_conversations
GROUP BY user_id
ORDER BY conversation_count DESC;

-- Message count by conversation
SELECT conversation_id, COUNT(*) as message_count, SUM(tokens_used) as total_tokens
FROM analysis_chat_messages
GROUP BY conversation_id
ORDER BY total_tokens DESC
LIMIT 10;

-- API usage by endpoint
SELECT endpoint, COUNT(*) as requests, SUM(tokens_used) as total_tokens, AVG(response_time_ms) as avg_response_time
FROM api_usage
GROUP BY endpoint
ORDER BY requests DESC;

-- Today's usage
SELECT user_id, COUNT(*) as requests, SUM(tokens_used) as tokens
FROM api_usage
WHERE DATE(timestamp) = CURRENT_DATE
GROUP BY user_id
ORDER BY requests DESC;
```

---

## Reference Documentation

For more information, see:

- **Architecture Details:** [ARCHITECTURE_ANALYSIS_MULTI_TENANT_LLM.md](ARCHITECTURE_ANALYSIS_MULTI_TENANT_LLM.md)
- **Implementation Summary:** [PHASE1_IMPLEMENTATION_SUMMARY.md](PHASE1_IMPLEMENTATION_SUMMARY.md)
- **Setup Guide:** [NEXT_STEPS.md](NEXT_STEPS.md)
- **Migration Guide:** [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)

---

**Testing Guide Complete!** 🎉

This guide covers comprehensive testing procedures for the Phase 1 server-managed LLM implementation. Follow each section sequentially to verify all features are working correctly.
