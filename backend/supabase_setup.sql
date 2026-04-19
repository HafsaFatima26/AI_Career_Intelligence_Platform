-- ============================================================
-- AI Career Intelligence Platform — Supabase Schema (Sitting 1)
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. jobs table — raw scraped postings
CREATE TABLE IF NOT EXISTS jobs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title       TEXT NOT NULL,
  company     TEXT,
  description TEXT,
  raw_skills  JSONB,
  source_url  TEXT,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- 3. extracted_skills — with 768-dim Gemini embedding
CREATE TABLE IF NOT EXISTS extracted_skills (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name       TEXT NOT NULL,
  category   TEXT,                        -- Language, Framework, Tool, Cloud, Soft
  seniority  TEXT,                        -- Junior, Mid, Senior
  source     TEXT,                        -- 'market' | 'user:<job_id>'
  embedding  vector(768),                 -- Gemini text-embedding-004 output
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(name, source)
);

-- 4. users — job-level workflow state & output
CREATE TABLE IF NOT EXISTS users (
  id          UUID PRIMARY KEY,           -- job_id from /analyze-profile
  github_url  TEXT,
  resume_text TEXT,
  status      TEXT DEFAULT 'queued',      -- queued | profiling | gap_analysis | done | error
  roadmap_md  TEXT,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- 5. Index for fast vector similarity search
CREATE INDEX IF NOT EXISTS skills_embedding_idx
  ON extracted_skills
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- 6. RPC function used by similarity_search() in dbService.py
CREATE OR REPLACE FUNCTION match_skills(
  query_embedding vector(768),
  match_count     int DEFAULT 20
)
RETURNS TABLE (
  id        UUID,
  name      TEXT,
  category  TEXT,
  seniority TEXT,
  source    TEXT,
  similarity FLOAT
)
LANGUAGE SQL STABLE
AS $$
  SELECT
    id, name, category, seniority, source,
    1 - (embedding <=> query_embedding) AS similarity
  FROM extracted_skills
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;
