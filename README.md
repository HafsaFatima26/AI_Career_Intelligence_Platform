# AI Career Intelligence Platform

Autonomous multi-agent system that reads the job market and generates dynamic, week-by-week career roadmaps.

## Stack
| Layer | Technology |
|---|---|
| Frontend | React + Vite, Tailwind CSS, D3.js |
| Backend | Python + FastAPI |
| AI / Agents | LangGraph + Google Gemini Pro |
| Embeddings | Gemini text-embedding-004 (768-dim) |
| Database | Supabase (PostgreSQL + pgvector) |
| Scraping | httpx + BeautifulSoup4 |

## Sitting 1 Checklist
- [x] Backend scaffold (FastAPI, routes, services, agents, orchestrator)
- [x] Supabase SQL schema (`supabase_setup.sql`)
- [x] requirements.txt
- [x] .env.example
- [x] Frontend component stubs

## Quick Start

### Backend
```bash
cd backend
cp .env.example .env          # fill in your keys
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Supabase
1. Create a project at https://supabase.com
2. Open SQL Editor → New Query
3. Paste & run `supabase_setup.sql`

### Frontend (Sitting 9)
```bash
cd frontend
npm create vite@latest . -- --template react
npm install
npm run dev
```

## Build Plan
| Sitting | Goal |
|---|---|
| 1 (✅) | Scaffold + Supabase DB setup |
| 2 | Scraping Service |
| 3 | Job Market Agent (extract + embed) |
| 4 | User Profiling Agent |
| 5 | Gap Analysis (pgvector similarity) |
| 6 | Career Strategist Agent |
| 7 | LangGraph Orchestration |
| 8 | API Routes & Async tasks |
| 9 | React Core UI |
| 10 | D3.js Skill Graph |
| 11 | Deployment (Render + Vercel) |
