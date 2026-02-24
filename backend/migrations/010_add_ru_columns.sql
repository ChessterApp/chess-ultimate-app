-- Migration: Add Russian translation columns
-- Run this in the Supabase SQL Editor or via psql with the DB password

-- Add Russian translation columns to courses
ALTER TABLE courses ADD COLUMN IF NOT EXISTS title_ru TEXT;
ALTER TABLE courses ADD COLUMN IF NOT EXISTS description_ru TEXT;

-- Add Russian translation columns to modules  
ALTER TABLE modules ADD COLUMN IF NOT EXISTS title_ru TEXT;
ALTER TABLE modules ADD COLUMN IF NOT EXISTS description_ru TEXT;

-- Add Russian translation columns to lessons
ALTER TABLE lessons ADD COLUMN IF NOT EXISTS title_ru TEXT;
ALTER TABLE lessons ADD COLUMN IF NOT EXISTS content_ru TEXT;
ALTER TABLE lessons ADD COLUMN IF NOT EXISTS hint_text_ru TEXT;
ALTER TABLE lessons ADD COLUMN IF NOT EXISTS success_message_ru TEXT;
