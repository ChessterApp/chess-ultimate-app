import { column, Schema, Table } from '@powersync/web';

/**
 * PowerSync schema matching Supabase tables for offline-first sync.
 *
 * Column types map to SQLite types:
 * - column.text   → TEXT  (string | null)
 * - column.integer → INTEGER (number | null)
 * - column.real   → REAL  (number | null)
 *
 * Every table implicitly has an `id` TEXT primary key.
 *
 * Table names MUST match Supabase table names exactly — PowerSync
 * local SQLite uses the same names as the sync rules.
 */

const user_games = new Table({
  user_id: column.text,
  title: column.text,
  white: column.text,
  black: column.text,
  white_elo: column.integer,
  black_elo: column.integer,
  result: column.text,
  date: column.text,
  event: column.text,
  eco: column.text,
  opening_name: column.text,
  pgn: column.text,
  notes: column.text,
  tags: column.text, // JSON-serialized string[]
  is_favorite: column.integer, // SQLite boolean: 0 | 1
  source: column.text,
  created_at: column.text,
  updated_at: column.text,
});

const opening_repertoires = new Table({
  user_id: column.text,
  name: column.text,
  color: column.text, // 'w' | 'b'
  description: column.text,
  is_primary: column.integer,
  starting_fen: column.text,
  starting_move_line: column.text,
  created_at: column.text,
  updated_at: column.text,
});

const opening_nodes = new Table({
  repertoire_id: column.text,
  parent_id: column.text,
  fen: column.text,
  move_san: column.text,
  move_uci: column.text,
  move_number: column.integer,
  is_white_move: column.integer,
  opening_name: column.text,
  eco_code: column.text,
  notes: column.text,
  priority: column.integer,
  is_critical: column.integer,
  times_trained: column.integer,
  times_correct: column.integer,
  last_trained_at: column.text,
  next_review_at: column.text,
  ease_factor: column.real,
  interval_days: column.integer,
  created_at: column.text,
  updated_at: column.text,
});

const analysis_conversations = new Table({
  user_id: column.text,
  title: column.text,
  messages: column.text, // JSON-serialized ChatMessage[]
  is_active: column.integer,
  current_fen: column.text,
  current_pgn: column.text,
  created_at: column.text,
  updated_at: column.text,
});

const user_progress = new Table({
  user_id: column.text,
  course_id: column.text,
  lesson_id: column.text,
  completed: column.integer,
  score: column.integer,
  attempts: column.integer,
  last_attempt_at: column.text,
  created_at: column.text,
  updated_at: column.text,
});

const courses = new Table({
  title: column.text,
  description: column.text,
  level: column.text,
  category: column.text,
  order_num: column.integer,
  is_published: column.integer,
  created_at: column.text,
  updated_at: column.text,
});

const lesson_puzzles = new Table({
  fen: column.text,
  moves: column.text,
  rating: column.integer,
  themes: column.text, // JSON-serialized string[]
  game_url: column.text,
  created_at: column.text,
});

const subscriptions = new Table({
  user_id: column.text,
  clerk_user_id: column.text,
  active: column.integer, // SQLite boolean: 0 | 1
  plan: column.text,
  status: column.text,
  trial_end: column.text,
  created_at: column.text,
  updated_at: column.text,
});

const lessons = new Table({
  course_id: column.text,
  title: column.text,
  content: column.text,
  lesson_type: column.text,
  order_num: column.integer,
  exercise_fen: column.text,
  solution_move: column.text,
  exercise_type: column.text,
  hint_text: column.text,
  success_message: column.text,
  created_at: column.text,
  updated_at: column.text,
});

export const AppSchema = new Schema({
  user_games,
  opening_repertoires,
  opening_nodes,
  analysis_conversations,
  user_progress,
  subscriptions,
  courses,
  lesson_puzzles,
  lessons,
});

export type AppDatabase = (typeof AppSchema)['types'];
export type UserGameRow = AppDatabase['user_games'];
export type RepertoireRow = AppDatabase['opening_repertoires'];
export type RepertoireNodeRow = AppDatabase['opening_nodes'];
export type ChatSessionRow = AppDatabase['analysis_conversations'];
export type UserProgressRow = AppDatabase['user_progress'];
export type SubscriptionRow = AppDatabase['subscriptions'];
export type CourseRow = AppDatabase['courses'];
export type PuzzleRow = AppDatabase['lesson_puzzles'];
export type LessonRow = AppDatabase['lessons'];
