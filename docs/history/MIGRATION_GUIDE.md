# Database Migration Guide - Analysis Chat Tables

## Migration: 002_create_analysis_chat_tables.sql

This migration creates the database schema for server-managed multi-tenant LLM chat.

### Tables Created:
1. `analysis_conversations` - Chat sessions
2. `analysis_chat_messages` - Individual messages
3. `api_usage` - Usage tracking for cost control

---

## How to Run the Migration

### Option 1: Supabase SQL Editor (Recommended)

1. **Open Supabase Dashboard:**
   - Go to https://supabase.com/dashboard
   - Navigate to your project: `qtzujwiqzbgyhdgulvcd`

2. **Open SQL Editor:**
   - Click "SQL Editor" in the left sidebar
   - Click "New query"

3. **Copy and Execute SQL:**
   - Open `backend/migrations/002_create_analysis_chat_tables.sql`
   - Copy the entire contents
   - Paste into the SQL Editor
   - Click "Run" (or Cmd/Ctrl + Enter)

4. **Verify Tables:**
   Run this query to confirm tables were created:
   ```sql
   SELECT table_name,
          (SELECT COUNT(*) FROM information_schema.columns
           WHERE table_name = t.table_name) as column_count
   FROM information_schema.tables t
   WHERE table_schema = 'public'
     AND table_name IN ('analysis_conversations', 'analysis_chat_messages', 'api_usage')
   ORDER BY table_name;
   ```

   Expected output:
   ```
   analysis_chat_messages    | 9
   analysis_conversations    | 6
   api_usage                | 9
   ```

### Option 2: Supabase CLI (If Installed)

```bash
cd chess-ultimate-app/backend

# Login to Supabase
supabase login

# Link to your project
supabase link --project-ref qtzujwiqzbgyhdgulvcd

# Run migration
supabase db push --file migrations/002_create_analysis_chat_tables.sql
```

### Option 3: psql Command Line

If you have PostgreSQL client installed:

```bash
# Get your database connection string from Supabase Dashboard
# Settings → Database → Connection string (Direct connection)

psql "postgresql://postgres:[YOUR-PASSWORD]@[HOST]:5432/postgres" \
  -f backend/migrations/002_create_analysis_chat_tables.sql
```

---

## Post-Migration Verification

### 1. Check Tables Exist

```sql
\dt analysis_*
\dt api_usage
```

### 2. Check Indexes

```sql
SELECT tablename, indexname
FROM pg_indexes
WHERE tablename LIKE 'analysis_%' OR tablename = 'api_usage'
ORDER BY tablename, indexname;
```

Expected indexes:
- `idx_conversations_user_id`
- `idx_conversations_type`
- `idx_conversations_updated`
- `idx_messages_conversation`
- `idx_messages_user`
- `idx_messages_timestamp`
- `idx_usage_user`
- `idx_usage_timestamp`
- `idx_usage_endpoint`
- `idx_usage_success`

### 3. Test Insert

```sql
-- Test conversation insert
INSERT INTO analysis_conversations (id, user_id, conversation_type, context)
VALUES (
  'test-uuid-12345',
  'test_user_123',
  'position',
  '{"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"}'::jsonb
);

-- Test message insert
INSERT INTO analysis_chat_messages (conversation_id, user_id, role, content, fen, tokens_used)
VALUES (
  'test-uuid-12345',
  'test_user_123',
  'user',
  'What is the best opening move?',
  'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
  50
);

-- Verify inserts
SELECT * FROM analysis_conversations WHERE user_id = 'test_user_123';
SELECT * FROM analysis_chat_messages WHERE user_id = 'test_user_123';

-- Clean up test data
DELETE FROM analysis_conversations WHERE user_id = 'test_user_123';
```

### 4. Test Foreign Key Cascade

```sql
-- Insert test conversation
INSERT INTO analysis_conversations (id, user_id, conversation_type)
VALUES ('cascade-test-uuid', 'test_user_cascade', 'general');

-- Insert test messages
INSERT INTO analysis_chat_messages (conversation_id, user_id, role, content)
VALUES
  ('cascade-test-uuid', 'test_user_cascade', 'user', 'Test message 1'),
  ('cascade-test-uuid', 'test_user_cascade', 'assistant', 'Test response 1');

-- Verify 2 messages exist
SELECT COUNT(*) FROM analysis_chat_messages WHERE conversation_id = 'cascade-test-uuid';
-- Expected: 2

-- Delete conversation (should cascade delete messages)
DELETE FROM analysis_conversations WHERE id = 'cascade-test-uuid';

-- Verify messages were deleted
SELECT COUNT(*) FROM analysis_chat_messages WHERE conversation_id = 'cascade-test-uuid';
-- Expected: 0
```

---

## Rollback (If Needed)

If you need to rollback this migration:

```sql
-- Drop tables (CASCADE will remove dependent objects)
DROP TABLE IF EXISTS api_usage CASCADE;
DROP TABLE IF EXISTS analysis_chat_messages CASCADE;
DROP TABLE IF EXISTS analysis_conversations CASCADE;

-- Drop function
DROP FUNCTION IF EXISTS update_updated_at_column CASCADE;
```

---

## Next Steps After Migration

Once the migration is complete:

1. **Restart Backend:**
   ```bash
   cd chess-ultimate-app/backend
   pkill -f "python.*app.py"
   python app.py
   ```

2. **Verify Chat API Endpoints:**
   ```bash
   # Check health endpoint
   curl http://localhost:5001/api/chat/health

   # Expected response:
   # {
   #   "status": "healthy",
   #   "llm_stats": { ... },
   #   "rate_limiter_stats": { ... }
   # }
   ```

3. **Test Chat Endpoint (with Clerk JWT):**
   ```bash
   # Get JWT token from frontend (localStorage or Clerk session)
   TOKEN="your_clerk_jwt_token_here"

   curl -X POST http://localhost:5001/api/chat/analysis \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer $TOKEN" \
     -d '{
       "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
       "query": "What is the best move here?",
       "context_type": "position"
     }'
   ```

4. **Monitor Logs:**
   ```bash
   tail -f chess-ultimate-app/backend.log
   ```

---

## Troubleshooting

### Error: "relation already exists"

The tables were already created. Either:
- Drop existing tables first (see Rollback section)
- Or skip this migration

### Error: "permission denied"

You may need database admin privileges. Contact your Supabase project owner.

### Error: "syntax error at or near"

Make sure you copied the entire SQL file contents, including all statements.

### Connection Timeout

Check your Supabase project is active and connection credentials are correct.

---

## Migration Complete! ✅

After successful migration, your database will have:
- ✅ 3 new tables for chat functionality
- ✅ 10 indexes for query performance
- ✅ Foreign key constraints with CASCADE delete
- ✅ Automatic timestamp updates via trigger

You can now proceed with frontend integration!
