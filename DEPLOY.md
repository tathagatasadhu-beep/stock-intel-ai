# Deploying Stock Intelligence Platform

A concrete path from this repo to a live URL. Stack: **Vercel** (frontend) + **Supabase** (Postgres, Auth)
+ **Render** (FastAPI backend + scheduled data-refresh job). Mirrors the EduQuestAI deploy pattern — see
that project's `DEPLOY.md`/`CLAUDE.md` if you want the reasoning behind picking this stack over the spec's
original Docker/AWS proposal (also summarized in this repo's `CLAUDE.md` → "Infra decisions").

Not yet done for this project — this is the plan, to be executed once the owner has reviewed the code.

## 0. Prerequisites

- GitHub account
- Accounts on [supabase.com](https://supabase.com), [vercel.com](https://vercel.com),
  [render.com](https://render.com)
- API keys: OpenAI, Financial Modeling Prep, Finnhub — see `backend/.env.example`
- `git`, `node`, `python3` installed locally

## 1. Push this repo to GitHub

```bash
cd stock-intel-ai
git init
git add .
git commit -m "Initial MVP scaffold"
git branch -M main
gh repo create stock-intel-ai --private --source=. --push
# no gh CLI? create an empty repo on github.com, then:
# git remote add origin https://github.com/<you>/stock-intel-ai.git
# git push -u origin main
```

## 2. Database — Supabase

1. Create a new Supabase project.
2. Get the schema created — no Alembic migrations exist yet (first deploy), so the simplest path is a
   one-off run of `python -c "import asyncio; from app.db.session import engine; from app.db.orm import Base; asyncio.run(engine.begin().__aenter__()); ..."`-style
   `Base.metadata.create_all`, or hand-translate `app/db/orm.py`'s models to SQL and paste into the SQL
   Editor. Do this once real Postgres is reachable (i.e., after step 3 gives you the pooler URL).
3. Project Settings → Database → get the **connection pooler** string (transaction mode, port 6543) —
   region-specific, copy it fresh from the dashboard, don't reuse EduQuestAI's. This is your `DATABASE_URL`.
4. Project Settings → API → grab `Project URL` and the JWKS is derived from it automatically
   (`SUPABASE_URL` env var is all the backend needs for JWT verification).

## 3. Backend — Render

1. New → Web Service → connect the GitHub repo, root directory `backend/`.
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add env vars from `backend/.env.example`: `DATABASE_URL`, `SUPABASE_URL`, `APP_JWT_SECRET`,
   `OPENAI_API_KEY`, `FMP_API_KEY`, `FINNHUB_API_KEY`, `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`ALERT_FROM_EMAIL`.
5. Deploy. Note the resulting URL, e.g. `https://stock-intel-api.onrender.com`.
6. New → Cron Job (or Background Worker), same repo/root directory, command:
   `python scripts/refresh_universe.py`. Schedule daily (S&P 500 fundamentals don't move intraday; re-run
   more often only if you upgrade to intraday technicals). This job needs the same env vars as the web
   service.
7. If using Render managed Redis for screener-result caching: New → Redis, then add `REDIS_URL` to both
   the web service and the cron job.

## 4. Frontend — Vercel

1. Import the repo into Vercel, root directory `frontend/`.
2. Add environment variable `BACKEND_URL` = the Render backend URL from step 3. That's the *only* env var
   Vercel needs — same BFF architecture as EduQuestAI (browser never talks to the backend or Supabase
   directly).
3. Deploy. Vercel gives a `*.vercel.app` URL immediately; add a custom domain under Project → Domains later.

## 5. Ongoing costs (separate from any Claude/Anthropic subscription)

| Item | Approx. cost |
|---|---|
| Vercel (frontend) | Free tier likely sufficient |
| Supabase (DB/auth) | Free tier, then ~$25/mo if outgrown |
| Render (backend + cron job) | Free tier sleeps when idle; ~$7/mo each for always-on |
| Financial Modeling Prep | Free tier is rate-limited (~250 req/day) — a daily full S&P 500 refresh needs a paid tier (~$20–30/mo range) |
| OpenAI | Pay-per-use, driven by how many AI theses get (re)generated |
| Finnhub | Free tier available, rate-limited |
| Domain | ~$12/year |

None of these depend on keeping a Claude subscription active — they bill independently through each
provider.

## 6. Handing this to Claude Code

Open a terminal in the repo root and run `claude`. It reads `CLAUDE.md` automatically. Suggested first
prompt once you're ready to actually deploy:

> Read CLAUDE.md and walk me through DEPLOY.md step by step — I have Supabase/Render/Vercel accounts ready.
