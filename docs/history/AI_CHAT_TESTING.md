# AI Chat Testing Guide

## Current Status ✅

The AI chat functionality has been configured with a valid Anthropic API key and is ready for testing.

### Services Running:
- **Backend:** Flask running on http://localhost:5001 (PID: 653518)
- **Frontend:** Next.js running on http://localhost:3000 (PID: 553367)
- **API Key:** Anthropic Claude 3.5 Sonnet configured and loaded

### Backend Configuration:
```
✅ Supabase client initialized: https://qtzujwiqzbgyhdgulvcd.supabase.co
✅ LLM client initialized successfully for provider: anthropic, model: claude-3-5-sonnet-20241022
✅ Lessons API registered
```

## How to Test AI Chat

### Step 1: Sign In
1. Open your browser to http://localhost:3000
2. If not already signed in, click "Sign In" or "Get Started"
3. Create an account or sign in with existing credentials

### Step 2: Navigate to Dashboard
1. After signing in, you should be automatically redirected to `/dashboard`
2. You'll see two sections:
   - **Chess Analysis Tools** (Position Analysis, Game Analysis, Puzzles)
   - **Your Learning Journey** (Available courses)

### Step 3: Start a Course
1. Click "Start Learning" on any available course (e.g., "Chess Fundamentals")
2. You'll see the course structure with modules and lessons
3. Click on the first unlocked lesson (usually "Introduction to Forks" or similar)

### Step 4: Test AI Chat
1. On the lesson page, you'll see:
   - **Left side:** Lesson content with markdown text and exercises
   - **Right side:** AI Chat sidebar

2. In the chat sidebar:
   - Type a question related to the lesson (e.g., "What is a fork?", "Can you explain this concept?")
   - Click "Send" or press Enter

3. **Expected Behavior:**
   - Your message appears in the chat immediately
   - A loading indicator appears
   - Within 2-5 seconds, the AI responds with a helpful, lesson-specific answer
   - The conversation history persists if you refresh the page

### Step 5: Test Edge Cases
1. **Empty messages:** Verify you can't send empty messages
2. **Multiple questions:** Ask follow-up questions to test conversation continuity
3. **Different lessons:** Try the chat on different lessons to ensure lesson-specific context
4. **Refresh:** Reload the page and verify chat history is preserved

## Troubleshooting

### If Chat Doesn't Respond:

**1. Check Browser Console (F12):**
```
Right-click → Inspect → Console tab
Look for errors like:
- "Failed to fetch"
- 401/403 authentication errors
- Network errors
```

**2. Check Backend Logs:**
```bash
cd /home/marblemaster/Desktop/Cursor/chess-ultimate-app/backend
tail -50 backend.log | grep -E "ERROR|chat|lesson"
```

**3. Verify Backend API:**
```bash
# Test health endpoint
curl http://localhost:5001/api/courses

# Should return JSON with courses
```

**4. Check Authentication:**
- Ensure you're signed in with Clerk
- Check that the JWT token is being sent in the Authorization header
- Verify Clerk secret key is configured in backend/.env

### Common Issues:

**Issue: "Failed to fetch" error**
- **Cause:** Backend not running or CORS misconfigured
- **Fix:** Restart backend with `cd backend && source venv/bin/activate && python app.py`

**Issue: Empty AI response**
- **Cause:** Anthropic API key invalid or rate limit exceeded
- **Fix:** Verify API key at https://console.anthropic.com

**Issue: Chat history not persisting**
- **Cause:** Database connection issue or user_id mismatch
- **Fix:** Check Supabase connection and verify user_id is being extracted from Clerk token

## API Endpoints Used

The AI chat uses these backend endpoints:

**GET /api/lessons/:id/chat**
- Fetches existing chat history for a lesson
- Returns: `{ messages: Array<{role, content}> }`

**POST /api/lessons/:id/chat**
- Sends a new message and gets AI response
- Body: `{ message: string }`
- Returns: `{ response: string, messages: Array<{role, content}> }`

**POST /api/lessons/:id/progress**
- Updates lesson progress status
- Body: `{ status: 'in_progress' | 'completed' }`
- Returns: Updated progress record

## Expected AI Behavior

The AI tutor should:
- ✅ Reference the specific lesson content in responses
- ✅ Be encouraging and patient with students
- ✅ Provide clear explanations appropriate to the lesson level
- ✅ Answer follow-up questions based on conversation history
- ✅ Stay focused on the current lesson topic

Example conversation:
```
User: "What is a fork?"

AI: "Great question! Based on the lesson you're studying, a fork is a tactical
move where one piece attacks two or more enemy pieces simultaneously. It's
one of the most powerful tactical patterns in chess because your opponent
can only save one of the attacked pieces on their next move.

In the example position from this lesson, can you spot the knight fork
opportunity? Take a look at where the white knight could move to attack
both the black queen and rook!"
```

## Next Steps After Successful Test

Once you've confirmed the AI chat is working:

1. **Test all analysis tools:**
   - Position Analysis page
   - Game Analysis page
   - Puzzle page

2. **Verify progress tracking:**
   - Complete a lesson
   - Check that next lesson unlocks
   - Verify progress persists across sessions

3. **Mobile testing:**
   - Test on mobile device
   - Verify responsive layout
   - Check chat interface on small screens

4. **Performance optimization:**
   - Add loading skeletons
   - Implement code splitting
   - Optimize API response times

---

**Ready to test!** Follow the steps above and report any issues you encounter.
