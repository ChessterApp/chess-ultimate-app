import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

// Server-side client with service role (full access) — use in API routes only
export const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey);

// Client-side client with anon key — use in browser
export const supabase = createClient(supabaseUrl, supabaseAnonKey);
