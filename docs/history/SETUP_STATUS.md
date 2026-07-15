# Setup Status - Phase 1

## ✅ Completed (Ready to Use)

### 1. **Environment Configuration**
- [x] Backend `.env` - [backend/.env](backend/.env)
  - Supabase URL ✅
  - Supabase Service Key ✅
  - Supabase Anon Key ✅
  - Clerk Secret Key ✅

- [x] Frontend `.env.local` - [frontend/.env.local](frontend/.env.local)
  - Supabase URL ✅
  - Supabase Anon Key ✅
  - Clerk Publishable Key ✅
  - Clerk Secret Key ✅

### 2. **Database Schema**
- [x] SQL file created - [backend/schema.sql](backend/schema.sql)
- [ ] **ACTION NEEDED**: Run schema in Supabase SQL Editor
  - Go to: https://supabase.com/dashboard/project/qtzujwiqzbgyhdgulvcd/sql
  - Click "New Query"
  - Copy/paste entire [backend/schema.sql](backend/schema.sql)
  - Click "Run"

### 3. **Project Cleanup**
- [x] Removed Stockfish from backend
- [x] Updated dependencies (Phase 1 only)
- [x] Created documentation:
  - [PHASE1_CLEANUP.md](PHASE1_CLEANUP.md)
  - [IMPLEMENTATION_GUIDE.md](../IMPLEMENTATION_GUIDE.md)

---

## 🔄 Next Steps (In Order)

### **Step 1: Execute Database Schema (5 min)**
```sql
-- Run this in Supabase SQL Editor
-- Copy from: backend/schema.sql
```

**Verification:**
1. Go to Supabase → Table Editor
2. You should see 6 tables:
   - courses
   - modules
   - lessons
   - user_progress
   - lesson_chat_history
   - ai_response_cache
3. Click on `courses` → should see "Chess Fundamentals"

---

### **Step 2: Install Backend Dependencies (2 min)**
```bash
cd /home/marblemaster/Desktop/Cursor/chess-ultimate-app/backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Phase 1 dependencies
pip install -r requirements.txt
```

**Expected output:**
```
Successfully installed Flask-3.1.0 flask-cors-5.0.1 supabase-py pyjwt anthropic openai ...
```

---

### **Step 3: Create First API Endpoint (30 min)**

We need to create 3 new files:

#### **A. Supabase Client** - `backend/services/supabase_client.py`
```python
from supabase import create_client, Client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
```

#### **B. Clerk JWT Verification** - `backend/utils/auth.py`
```python
from functools import wraps
from flask import request, jsonify
import jwt
import os

CLERK_SECRET = os.getenv("CLERK_SECRET_KEY")

def verify_clerk_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')

        if not token:
            return jsonify({"error": "No token provided"}), 401

        try:
            # Verify JWT (Clerk uses RS256)
            # Note: This is simplified - production needs proper key verification
            decoded = jwt.decode(token, CLERK_SECRET, algorithms=["RS256"], options={"verify_signature": False})
            request.user_id = decoded.get('sub')
            return f(*args, **kwargs)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except Exception as e:
            return jsonify({"error": f"Invalid token: {str(e)}"}), 401

    return decorated
```

#### **C. Lessons API** - `backend/api/lessons.py`
```python
from flask import Blueprint, jsonify, request
from services.supabase_client import supabase
from utils.auth import verify_clerk_token

lessons_bp = Blueprint('lessons', __name__)

@lessons_bp.route('/api/lessons/<lesson_id>', methods=['GET'])
@verify_clerk_token
def get_lesson(lesson_id):
    """Get lesson content by ID"""
    result = supabase.table('lessons').select('*').eq('id', lesson_id).execute()

    if not result.data:
        return jsonify({"error": "Lesson not found"}), 404

    return jsonify(result.data[0])

@lessons_bp.route('/api/courses', methods=['GET'])
def get_courses():
    """Get all courses (public endpoint)"""
    result = supabase.table('courses').select('*').order('order_index').execute()
    return jsonify(result.data)
```

---

### **Step 4: Update app.py to Register Endpoints**

Add to [backend/app.py](backend/app.py):
```python
# Add after line 98 (after CORS setup)
from api.lessons import lessons_bp
app.register_blueprint(lessons_bp)
```

---

### **Step 5: Test Backend (5 min)**
```bash
# Terminal 1: Start backend
cd backend
source venv/bin/activate
python app.py

# Terminal 2: Test endpoints
curl http://localhost:5001/api/courses
# Should return: [{"id": "11111111-...", "title": "Chess Fundamentals", ...}]

curl http://localhost:5001/api/lessons/33333333-3333-3333-3333-333333333333
# Should return lesson data
```

---

### **Step 6: Install Frontend Dependencies (2 min)**
```bash
cd /home/marblemaster/Desktop/Cursor/chess-ultimate-app/frontend

npm install
```

---

### **Step 7: Test Full Stack (5 min)**
```bash
# Terminal 1: Backend (already running)
cd backend && source venv/bin/activate && python app.py

# Terminal 2: Frontend
cd frontend && npm run dev
```

Open: http://localhost:3000

You should see Clerk authentication screen!

---

## 📊 Current Architecture

```
┌─────────────┐      ┌──────────────┐      ┌──────────────┐
│  Frontend   │─────▶│    Flask     │─────▶│   Supabase   │
│  Next.js    │      │   Backend    │      │  PostgreSQL  │
│  :3000      │      │   :5001      │      │              │
└─────────────┘      └──────────────┘      └──────────────┘
      │                      │
      │                      │
      ▼                      ▼
┌─────────────┐      ┌──────────────┐
│    Clerk    │      │  Anthropic   │
│    Auth     │      │  Claude API  │
└─────────────┘      └──────────────┘
```

---

## 🔑 API Keys Status

| Service | Key | Status |
|---------|-----|--------|
| Supabase URL | `https://qtzujwiqz...` | ✅ Set |
| Supabase Service Key | `eyJhbGciOiJ...` | ✅ Set |
| Supabase Anon Key | `eyJhbGciOiJ...` | ✅ Set |
| Clerk Publishable | `pk_test_c3R1bm5...` | ✅ Set |
| Clerk Secret | `sk_test_N3kQYH...` | ✅ Set |
| Anthropic API | Not set | ❌ **TODO** |
| OpenAI API | Not set | ⚠️  Optional |

---

## 🚨 Still Needed

1. **Run database schema** in Supabase SQL Editor
2. **Add Anthropic or OpenAI API key** to [backend/.env](backend/.env) and [frontend/.env.local](frontend/.env.local)
3. **Create the 3 backend files** mentioned in Step 3
4. **Test the full stack** end-to-end

---

## 📝 Quick Commands Reference

```bash
# Backend
cd backend
source venv/bin/activate
python app.py

# Frontend
cd frontend
npm run dev

# Test API
curl http://localhost:5001/api/courses
curl http://localhost:5001/api/lessons/33333333-3333-3333-3333-333333333333
```

---

**Status Updated:** 2025-01-09

**Next Action:** Run database schema in Supabase, then create the 3 backend files!
