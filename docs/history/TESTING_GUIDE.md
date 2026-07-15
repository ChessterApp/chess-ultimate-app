# Chess Learning Platform - Testing Guide

## Phase 1 Implementation Complete! ✅

All major features have been implemented and both backend and frontend are running.

### Running Services

- **Backend API:** http://localhost:5001
- **Frontend:** http://localhost:3000
- **Database:** Supabase (configured)
- **Authentication:** Clerk (configured)
- **AI:** Anthropic Claude (configured)

---

## Complete User Flow Test

Follow these steps to test the entire application:

### 1. Authentication Flow

**Test Sign Up:**
1. Visit http://localhost:3000
2. Click "Sign Up" (or you'll be redirected automatically if not authenticated)
3. Create a new account with email
4. Verify email if required
5. Should redirect to dashboard

**Test Sign In:**
1. Sign out from Clerk menu
2. Visit http://localhost:3000/sign-in
3. Sign in with your credentials
4. Should redirect to dashboard

### 2. Dashboard Page

**URL:** http://localhost:3000/dashboard

**What to Test:**
- [ ] Page displays "Your Chess Learning Journey" heading
- [ ] Shows "Chess Fundamentals" course card
- [ ] Course card shows:
  - Title: "Chess Fundamentals"
  - Description: "Learn the basics of chess strategy"
  - Level badge: "beginner"
  - "Start Learning" button
- [ ] Click "Start Learning" navigates to course detail page

### 3. Course Detail Page

**URL:** http://localhost:3000/courses/11111111-1111-1111-1111-111111111111

**What to Test:**
- [ ] Page displays course title: "Chess Fundamentals"
- [ ] Shows course description
- [ ] Displays "Module 1: Basic Tactical Motifs" module
- [ ] Shows lessons under the module:
  - Lesson 1: "Introduction to Forks" (theory)
  - Lesson 2: "Fork Exercise 1" (exercise)
  - Lesson 3: "Introduction to Pins" (theory)
  - Lesson 4: "Pin Exercise 1" (exercise)
- [ ] First lesson is unlocked (no 🔒 icon)
- [ ] Subsequent lessons are locked (shows 🔒) until previous completed
- [ ] Lesson type badges show correct colors:
  - Theory = Blue
  - Exercise = Yellow
  - Quiz = Purple
- [ ] Click "Start" on first lesson

### 4. Lesson Detail Page

**URL:** http://localhost:3000/lessons/[lesson-id]

**What to Test:**

**Layout:**
- [ ] Two-column layout on desktop (lesson content + AI chat sidebar)
- [ ] Single column on mobile (stacked)
- [ ] "← Back to Course" button at top

**Lesson Content (Left Column):**
- [ ] Displays lesson title
- [ ] Shows lesson type badge (theory/exercise/quiz)
- [ ] Renders lesson content with markdown formatting
- [ ] For exercise lessons: displays FEN position
- [ ] "Complete Lesson" button at bottom

**AI Tutor Chat (Right Column):**
- [ ] Shows "AI Tutor" heading
- [ ] Empty state message: "Ask your AI tutor any questions about this lesson!"
- [ ] Text input field at bottom
- [ ] Send button

**Interactions:**
1. **Send a chat message:**
   - [ ] Type "What is a fork?" in the input
   - [ ] Click Send
   - [ ] User message appears (blue bubble, right-aligned)
   - [ ] "Thinking..." appears briefly
   - [ ] AI response appears (gray bubble, left-aligned)
   - [ ] Response is relevant to the lesson content
   - [ ] Input field clears after sending

2. **Complete the lesson:**
   - [ ] Click "Complete Lesson" button
   - [ ] Button shows "Completing..." state
   - [ ] Redirects back to course page
   - [ ] Lesson shows ✅ completed indicator
   - [ ] Next lesson is now unlocked

### 5. Progress Tracking

**Test Sequential Unlocking:**
1. Start with Lesson 1 (should be unlocked)
2. Complete Lesson 1
3. Return to course page
4. Verify Lesson 2 is now unlocked
5. Verify Lesson 3 is still locked
6. Complete Lesson 2
7. Verify Lesson 3 is now unlocked

**Test Status Persistence:**
1. Complete a lesson
2. Close browser tab
3. Open new tab and sign in again
4. Navigate to course page
5. Verify completed lessons show ✅
6. Verify progress is maintained

### 6. Chat History Persistence

**Test Chat Memory:**
1. Open Lesson 1
2. Send message: "What is a fork?"
3. Receive AI response
4. Send follow-up: "Can you give me an example?"
5. Verify AI has context from previous message
6. Navigate away from lesson
7. Return to same lesson
8. Verify chat history is preserved

---

## API Endpoints Testing

You can also test the backend directly:

### Get Courses
```bash
curl http://localhost:5001/api/courses
```

### Get Modules for Course
```bash
curl http://localhost:5001/api/courses/11111111-1111-1111-1111-111111111111/modules
```

### Get Lessons for Module (requires auth)
```bash
# Get a Clerk token from the frontend (check browser dev tools)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:5001/api/lessons/LESSON_ID
```

---

## Known Limitations (Phase 1)

These features are deferred to Phase 2:
- ❌ Interactive chess board (showing positions visually)
- ❌ Move validation and interactive exercises
- ❌ Stockfish engine integration
- ❌ Voice input/output
- ❌ Weaviate vector search
- ❌ Real-time multiplayer

---

## Troubleshooting

### Frontend won't start
```bash
cd frontend
source ~/.nvm/nvm.sh
nvm use 20
npm run dev
```

### Backend won't start
```bash
cd backend
source venv/bin/activate
python app.py
```

### Database connection issues
- Check Supabase credentials in `backend/.env`
- Verify `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`

### Authentication not working
- Check Clerk credentials in `frontend/.env.local`
- Verify `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY`

### AI chat not responding
- Check `backend/.env` has valid `ANTHROPIC_API_KEY`
- Check backend logs for errors: `tail -f backend/backend.log`

---

## Development URLs

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:5001
- **Supabase Dashboard:** https://supabase.com/dashboard/project/qtzujwiqzbgyhdgulvcd
- **Clerk Dashboard:** https://dashboard.clerk.com

---

## Next Steps (Optional Enhancements)

1. **UI Polish:**
   - Add loading skeletons
   - Improve error handling
   - Add animations/transitions
   - Responsive design improvements

2. **Features:**
   - Search lessons
   - Bookmarks/favorites
   - User profile page
   - Course progress visualization
   - Achievement badges

3. **Performance:**
   - Add caching
   - Optimize API calls
   - Lazy load components
   - Image optimization

4. **Testing:**
   - Unit tests
   - Integration tests
   - E2E tests with Playwright

---

## Success Criteria ✅

Your Phase 1 implementation is successful if:
- ✅ User can sign up and sign in with Clerk
- ✅ Dashboard displays available courses
- ✅ Course page shows modules and lessons
- ✅ Lessons unlock sequentially based on completion
- ✅ Lesson page displays content and AI chat
- ✅ AI tutor responds to questions about the lesson
- ✅ Progress is tracked and persisted
- ✅ Chat history is maintained per lesson

**All these features are now implemented and ready for testing!**
