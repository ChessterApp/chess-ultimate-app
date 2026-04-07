-- ============================================
-- Chess Ultimate App - Phase 1 Database Schema
-- ============================================
-- Run this in Supabase SQL Editor or via Supabase MCP

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- COURSES & LESSONS
-- ============================================

CREATE TABLE courses (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  title TEXT NOT NULL,
  description TEXT,
  level TEXT CHECK (level IN ('beginner', 'intermediate', 'advanced', 'master')),
  order_index INT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE modules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  course_id UUID REFERENCES courses(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT,
  order_index INT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE lessons (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  module_id UUID REFERENCES modules(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  content TEXT, -- Markdown or HTML
  lesson_type TEXT CHECK (lesson_type IN ('theory', 'exercise', 'quiz', 'practice')),
  order_index INT NOT NULL,

  -- Exercise data (if lesson_type = 'exercise')
  exercise_fen TEXT,
  exercise_solution JSONB, -- [{move: "Nf3", explanation: "..."}]

  -- Quiz data (if lesson_type = 'quiz')
  quiz_questions JSONB, -- [{question: "...", options: [...], correct: 0}]

  -- Unlocking (NULL = unlocked by default)
  requires_lesson_id UUID REFERENCES lessons(id),

  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- USER PROGRESS
-- ============================================

CREATE TABLE user_progress (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id TEXT NOT NULL, -- Clerk user ID
  lesson_id UUID REFERENCES lessons(id) ON DELETE CASCADE,

  status TEXT DEFAULT 'not_started' CHECK (status IN ('not_started', 'in_progress', 'completed')),

  -- Progress metrics
  started_at TIMESTAMP WITH TIME ZONE,
  completed_at TIMESTAMP WITH TIME ZONE,
  time_spent_seconds INT DEFAULT 0,

  -- Quiz/exercise results
  score INT CHECK (score >= 0 AND score <= 100),
  attempts INT DEFAULT 0,

  -- Last position (for resuming)
  last_fen TEXT,
  last_notes TEXT,

  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

  UNIQUE(user_id, lesson_id)
);

-- ============================================
-- AI CHAT HISTORY (per lesson)
-- ============================================

CREATE TABLE lesson_chat_history (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id TEXT NOT NULL, -- Clerk user ID
  lesson_id UUID REFERENCES lessons(id) ON DELETE CASCADE,

  messages JSONB NOT NULL DEFAULT '[]', -- [{role: 'user', content: '...'}, ...]

  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

  UNIQUE(user_id, lesson_id)
);

-- ============================================
-- LLM RESPONSE CACHE
-- ============================================

CREATE TABLE ai_response_cache (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  query_hash TEXT UNIQUE NOT NULL,
  lesson_id UUID REFERENCES lessons(id) ON DELETE CASCADE,
  user_query TEXT NOT NULL,
  ai_response TEXT NOT NULL,

  cached_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  hit_count INT DEFAULT 0
);

-- ============================================
-- INDEXES
-- ============================================

CREATE INDEX idx_cache_hash ON ai_response_cache(query_hash);
CREATE INDEX idx_cache_expires ON ai_response_cache(expires_at);
CREATE INDEX idx_user_progress ON user_progress(user_id, lesson_id);
CREATE INDEX idx_chat_history ON lesson_chat_history(user_id, lesson_id);

-- ============================================
-- SEED DATA (Sample Course)
-- ============================================

-- Insert a sample course
INSERT INTO courses (id, title, description, level, order_index)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'Chess Fundamentals', 'Learn the basics of chess strategy', 'beginner', 1);

-- Insert a sample module
INSERT INTO modules (id, course_id, title, description, order_index)
VALUES
  ('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111', 'Tactical Motifs', 'Learn basic tactical patterns', 1);

-- Insert sample lessons
INSERT INTO lessons (id, module_id, title, content, lesson_type, order_index, exercise_fen, exercise_solution)
VALUES
  (
    '33333333-3333-3333-3333-333333333333',
    '22222222-2222-2222-2222-222222222222',
    'Introduction to Forks',
    '# What is a Fork?

A **fork** is a tactical move where a single piece attacks two or more opponent pieces simultaneously.

## Example
In the position below, the white knight on f7 attacks both the black queen on d8 and the black rook on h8.

## Key Points
- Forks force your opponent to lose material
- Knights are the most common forking pieces
- Look for forks in every position!',
    'theory',
    1,
    'r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 1',
    NULL
  ),
  (
    '44444444-4444-4444-4444-444444444444',
    '22222222-2222-2222-2222-222222222222',
    'Fork Exercise 1',
    '# Find the Fork

White to move. Find the knight fork that wins material.

**Hint:** Look for squares where the knight can attack two pieces at once.',
    'exercise',
    2,
    'r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 1',
    '[{"move": "Nxe5", "explanation": "The knight forks the king on e8 and the rook on h8!"}]'
  );

-- Set up lesson dependency (exercise requires theory lesson)
UPDATE lessons
SET requires_lesson_id = '33333333-3333-3333-3333-333333333333'
WHERE id = '44444444-4444-4444-4444-444444444444';
