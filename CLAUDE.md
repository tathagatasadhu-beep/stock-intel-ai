# Stock Intelligence Platform — Project Brief for Claude Code

Read this first. It's the context a new engineer (or Claude Code) needs to pick up where this project
left off.

## What this is

A personal/family-use stock research platform: S&P 500 screener, DCF/intrinsic-value engine, technical
analysis dashboard (candlesticks, RSI/MACD/Bollinger/VWAP/ATR/OBV/StochRSI), auto Fibonacci retracements,
AI-generated plain-English investment theses, and a news feed with sentiment. Full spec: `SPEC.md` in this
root — that's the original product spec verbatim.

This is a **separate product from EduQuestAI** (a different repo, `../eduquest-ai`) — it reuses the same
deploy pattern (Render + Vercel + Supabase) by owner preference, not because the two apps share any code.

## Status: Phase 1 MVP, live in production (2026-07-09)

- **Frontend**: https://stock-intel-ai-alpha.vercel.app
- **Backend**: https://stock-intel-ai-luk3.onrender.com — health check at `/api/health`
- **Database**: Supabase Postgres, project ref `rsixtlqjahqxwsbzgabf`
- **GitHub**: https://github.com/tathagatasadhu-beep/stock-intel-ai

## FMP API migration (discovered during first live deploy, 2026-07-09)

Built and locally tested against FMP's legacy `/api/v3/*` endpoints, which turned out to be
**403-Forbidden for any key without a subscription predating August 2025** — confirmed directly against
the live API the first time `scripts/refresh_universe.py` ran for real. `services/market_data.py` was
rewritten against FMP's current `/stable/*` API (different base URL, different field names — e.g.
`priceEarningsRatio` → `priceToEarningsRatio`, `debtEquityRatio` → `debtToEquityRatio`, fundamentals now
split across `/quote`, `/profile`, `/ratios`, `/key-metrics`, `/financial-growth`, `/financial-scores`,
`/balance-sheet-statement`, `/income-statement` instead of the old `/quote/{symbol}`-style path params).
`forward_pe` is now always `None` — the analyst-estimates endpoint needed for it errored during testing
and wasn't worth blocking on for an MVP-secondary field.

**The S&P 500 constituent list itself (`/stable/sp500-constituent`) is paid-tier-only** — also confirmed
live, not a guess. `services/sp500_universe.py` is a static, hand-curated list (expanded from ~168 to ~467
on 2026-09-06 after a user search for an uncovered ticker) of the largest S&P 500 constituents across all
11 GICS sectors instead — see that file's docstring for the reasoning and how to expand it further. This
means the screener currently covers a large *subset* of the S&P 500, not all ~503 names — a ticker search
that comes back "Not covered by this screener" (see `frontend/src/app/stock/[ticker]/page.tsx`) means
extend that list, not a bug.

### Scope decisions made against the spec (owner-approved, 2026-07-08)

The spec's own §8 recommends a Phase 1 MVP before the full feature set — this build follows that
recommendation:

- **Built**: S&P 500 screener with valuation/growth/financial-health/technical filters, DCF valuation
  (plus DDM/Owner Earnings/Comparable as secondary methods), candlestick chart with MA20/50/200 +
  Bollinger + VWAP overlays, RSI(14)/MACD(12,26,9)/Stochastic RSI/ATR/OBV panels, auto Fibonacci
  swing-detection + retracement levels, AI plain-English thesis + bullish/bearish + risk scoring via
  OpenAI, news feed with AI sentiment, composite investment score (§6 formula) → Strong Buy/Buy/Hold/Weak
  Hold/Avoid rating, email alerts (price-crosses-support, MACD bullish cross, RSI oversold, volume spike).
- **Deliberately deferred to a later phase** (owner chose "Phase 1 MVP only" over the broader options when
  scoping this build):
  - **Real-time WebSocket price streaming.** The spec's architecture section calls for it; the MVP instead
    polls the market-data provider on a schedule (ingestion script, see below) and the frontend re-fetches
    on an interval. A `/ws` endpoint is easy to add later on top of `services/market_data.py` once there's
    a reason to pay for streaming-tier API access.
  - **Push notifications and Telegram/Discord alert delivery.** Only email delivery is wired up
    (`services/email_alerts.py`). The `Alert.delivery_method` column and `AlertType` enum already model the
    other channels — only the delivery integration is missing.
  - **Reddit/X sentiment.** News sentiment currently covers Finnhub headlines only.
  - **§7 Future Features** (options flow, insider tracker, earnings prediction, portfolio optimization,
    chatbot, backtesting) — none of these exist yet, matching the spec's own "future" framing.
- **Infra adapted from the spec's §4** (owner-approved): the spec calls for Docker + AWS/GCP/Azure +
  Celery + TimescaleDB. This build instead targets Render + Vercel + Supabase to match the owner's existing
  deploy pattern — see "Infra decisions" below for what that meant concretely.

## Infra decisions (spec → actual)

| Spec called for | This build uses | Why |
|---|---|---|
| Docker + AWS/GCP/Azure | Render (backend) + Vercel (frontend), no containers | Matches the owner's existing EduQuestAI deploy pattern; avoids standing up a new cloud account |
| Celery/RQ background workers | Render **background worker** service running `scripts/refresh_universe.py` on a schedule (Render cron job) | Same job (periodic data refresh), no message broker needed at this scale |
| TimescaleDB for market data | Plain Supabase Postgres, `PriceCandle` indexed on `(stock_id, date)` | Supabase doesn't offer the TimescaleDB extension; daily-candle volume for ~500 tickers doesn't need hypertables |
| Redis cache | Render managed Redis | Same role (screener result caching, provider rate-limit buffering), just provisioned via Render instead of self-hosted |
| CI/CD via GitHub Actions | Not set up yet | Deferred until the GitHub repo itself is created (see "Deploying") |

## Local dev machine is ARM64 Windows — same limitation as EduQuestAI

`asyncpg` has no prebuilt wheel for win-arm64 on this machine, and this project pulled in more packages
than EduQuestAI that hit the same wall. `backend/requirements.txt` is the **production** dependency list
(installs cleanly on Render's Linux x86_64) — installing it verbatim locally will fail. The working local
install (already done once in `backend/venv/`, re-run if the venv is ever recreated):

```powershell
python -m venv venv
./venv/Scripts/python.exe -m pip install --only-binary=:all: cryptography "pyjwt[crypto]==2.10.1"
./venv/Scripts/python.exe -m pip install fastapi==0.115.0 httpx==0.27.2 openai==1.51.0 "pydantic[email]==2.13.4" `
  python-dotenv==1.0.1 python-multipart==0.0.9 sqlalchemy==2.0.51 uvicorn==0.30.6 aiosqlite==0.20.0 greenlet numpy
```

What's different from a plain `pip install -r requirements.txt` and why:
- **Skip `asyncpg`** entirely (no win-arm64 wheel, no local Postgres anyway — SQLite dev mode doesn't need it).
- **`cryptography` (pulled in by `pyjwt[crypto]`) needs `--only-binary=:all:`.** Left unpinned/source-build,
  pip tries to compile it via `maturin`, which fails with `could not determine version from interpreter
  name 'python.exe'` — a maturin/venv-naming quirk on this machine, not a real incompatibility. Forcing a
  wheel-only install sidesteps it (works because *some* pinned-nearby cryptography version does ship a
  win-arm64 wheel on PyPI).
- **Plain `uvicorn`, not `uvicorn[standard]`.** The `[standard]` extra pulls in `httptools`, which has no
  win-arm64 wheel and needs the MSVC C++ Build Tools (not installed) to compile. Plain `uvicorn` runs the
  dev server fine; production on Render still uses the full `uvicorn[standard]` from `requirements.txt`.
- **`numpy` unpinned, not `numpy==2.1.2`.** The pinned version has no win-arm64 wheel either and its build
  needs a C/Fortran toolchain this machine doesn't have; an unpinned `pip install numpy` resolves to a
  newer release that does ship one.
- **`greenlet` installed explicitly.** SQLAlchemy's async engine (`create_async_engine`, used by every
  request) needs it at runtime, but it's not always pulled in transitively without `asyncpg` in the mix —
  without it you get `ValueError: the greenlet library is required to use this function` the first time any
  route touches the DB. It's a normal wheel-installable package, no build issues.

With that installed:

- **Local backend testing**: `backend/dev_server_sqlite.py` swaps `DATABASE_URL` to
  `sqlite+aiosqlite:///...` *before* `app.db.session` creates its engine, creates the schema, and seeds a
  handful of demo stocks (with fake but realistic-shaped fundamentals/candles/technicals) so the frontend
  has something to render without a live FMP/OpenAI key. Real provider keys still work if present in
  `backend/.env` — the seed only fills gaps.
- Production (Render, Linux x86_64) installs `asyncpg` from a wheel with zero issues — don't "fix" the
  local workaround in a way that changes production behavior.
- Node.js + npm: same as EduQuestAI, prepend `$env:Path = "C:\Program Files\nodejs;$env:Path"` in
  PowerShell if `npm`/`node` aren't found, or use `frontend/dev.cmd`.

## API keys this project needs

All live only in `backend/.env` (gitignored) locally and in Render/Vercel environment variables in
production — never in this repo. See `backend/.env.example` for the full list. Summary:

- `OPENAI_API_KEY` — AI thesis generation (`services/ai_engine.py`)
- `FMP_API_KEY` — Financial Modeling Prep: historical price candles only (`services/market_data.py`)
- `FINNHUB_API_KEY` — Finnhub: company-news headline feed (`services/news.py`) **and**, since 2026-09-07,
  fundamentals/ratios/quote (`services/market_data.py`) — see "Finnhub fundamentals migration" below
- `DATABASE_URL` — Supabase pooler connection string (see EduQuestAI's `CLAUDE.md` for the exact pooler
  gotcha — identical requirement here: use the **pooler** host, port 6543, with
  `connect_args={"statement_cache_size": 0}` on the async engine, already wired in
  `backend/app/db/session.py`)
- `SUPABASE_URL` / Supabase JWKS — parent/user auth, same pattern as EduQuestAI
  (`app/core/security.py::decode_supabase_jwt`)
- `SMTP_*` — outbound email for alerts (`services/email_alerts.py`)

## Conventions

- Money/ratio values are stored and returned as plain floats (not cents-as-int) — this is a research tool,
  not a ledger; the extra precision of fixed-point isn't needed and would complicate every calculation in
  `services/technicals.py` and `services/valuation.py` for no benefit.
- **Frontend never calls the backend directly** — same BFF pattern as EduQuestAI: Server Components read
  session cookies and call the backend server-to-server; client components go through same-origin Route
  Handlers (`frontend/src/app/api/**/route.ts`). Only `BACKEND_URL` (no `NEXT_PUBLIC_` prefix) is needed on
  Vercel.
- All computed analytics (technicals, valuation, composite score, AI thesis) are **persisted**, not
  computed on every request — `scripts/refresh_universe.py` computes and stores a snapshot per ticker on
  each run; API routers read the latest stored snapshot. This keeps the screener fast (no live FMP/OpenAI
  calls in the request path) and keeps provider API usage bounded and predictable. The one exception is
  **on-demand refresh** (`POST /api/stocks/{ticker}/refresh`, added 2026-09-07): a user viewing a
  covered-but-not-yet-ingested ticker can trigger a real, synchronous fetch for just
  that one ticker instead of waiting for the batch job to rotate around to it (see "Finnhub fundamentals
  migration" below for why this is now cheap enough to leave unauthenticated and un-rate-limited). The fetch/compute/score
  pipeline itself lives in `app/services/ingest.py`, shared by both the batch script and this route so
  there's exactly one implementation of "how to ingest a ticker" — see that module's docstring. Idempotent
  per day (checks for today's snapshot before spending any provider quota), which is also what makes it
  safe to leave unauthenticated: worst case is one real ingestion per ticker per day, the same cost as that
  ticker being covered by the batch job.
- Every table that could ever be scoped to a signed-in user (currently just `Alert`, since screener/stock
  data is shared/public within this app) is scoped by `user_id` — same "app-layer filter, don't rely on RLS
  alone" pattern as EduQuestAI's `parent_id` convention.

## Deploying — already done once; gotchas hit along the way

Actual deploy sequence used (see git log for the exact commits): GitHub repo → Supabase project → Render
web service (`backend/`, root directory **must** be set to `backend` at import time, not fixed after —
see gotcha below) → Render cron job (`scripts/refresh_universe.py`, same root-directory requirement,
separately) → Vercel project (`frontend/`, root directory **must** be `frontend`).

Gotchas hit deploying this for real, in case any of this needs redoing:

- **Vercel/Render "Root Directory" must be set correctly at project-creation time.** Changing it after the
  fact in Settings and clicking Redeploy did **not** reliably pick up the change — the Vercel project kept
  serving the FastAPI backend's 404 response (`{"detail":"Not Found"}`, distinguishable from Next.js's own
  404 by the exact body shape and by `/api/health`/`/docs` responding 200 on what should've been the
  frontend domain) until a fresh commit was pushed to force a truly new build. If a Root Directory ever
  looks wrong post-deploy, don't trust "Redeploy" on an old deployment — push a new commit or re-import the
  project from scratch. This actually happened here — the Vercel project ended up re-imported from scratch,
  which is why the live URL is `stock-intel-ai-alpha.vercel.app` and not whatever it was originally.
- **A brand-new Supabase project's connection pooler can briefly `ConnectionRefusedError` (`errno 111`)
  even though the hostname resolves and the port is genuinely open** (verified independently during
  debugging) and even with Network Restrictions correctly set to "allow all" and Connection Pooling shown
  healthy in the dashboard. It self-resolved after a bit of time (likely Supavisor finishing tenant
  registration for the new project) — no config change actually fixed it. If this happens again on a fresh
  project, the fix is patience + retrying, not more config changes.
- **Schema creation isn't a separate step** — `scripts/refresh_universe.py` runs `Base.metadata.create_all`
  itself at the top of `main()` before touching any provider API, so the very first Cron Job run creates
  every table. No Alembic migrations exist; if the schema ever changes, either hand-write `ALTER TABLE`s or
  add Alembic at that point.
- **FMP quota** (mostly resolved 2026-09-07, see "Finnhub fundamentals migration" below): the original
  design called FMP 9 times per ticker, so the ~467-ticker universe needed ~4,200 calls for one full
  refresh against a ~250/day free-tier key — it also meant the on-demand refresh route
  (`POST /api/stocks/{ticker}/refresh`) competed with the batch job for the same tiny budget and regularly
  got "Limit Reach" 429s (confirmed live in production). FMP now handles only historical candles (1 call/
  ticker), so a full refresh needs ~467 FMP calls — about 2 days of free-tier quota instead of ~19, with
  plenty of headroom left for on-demand fetches too. `scripts/refresh_universe.py` still rotates its
  starting point through the universe by one ticker per calendar day (see the comment above the `offset`
  calculation in `main()`) so a quota-limited run keeps making cumulative progress either way — that safety
  net didn't stop being worth keeping just because the math got better.

## Finnhub fundamentals migration (2026-09-07)

Fundamentals/ratios/quote (everything in `FundamentalSnapshot` except price history) moved from FMP to
Finnhub — same key already used for news, no new signup or cost. Reasoning and the exact endpoint mapping
live in `services/market_data.py`'s module docstring; the short version: Finnhub's free tier has no
comparable daily cap (just a per-minute rate limit) and its `/stock/metric?metric=all` covers nearly
everything FMP's fundamentals did, confirmed field-by-field against the live API before building this —
including `forward_pe`, which FMP's free tier never provided at all. The one thing Finnhub's free tier
won't do is historical OHLCV candles (confirmed live: 403 on `/stock/candle`), so FMP stays for exactly
that one call per ticker.

Two accuracy trade-offs worth knowing about if fundamentals ever look off for a Finnhub-sourced ticker:
- `altman_z_score` is always `None` now (not available on Finnhub's free tier, and computing it from
  scratch needs balance-sheet detail neither free tier exposes).
- `total_debt` and `cash_and_equivalents` are derived (ratio × per-share metric × shares outstanding)
  rather than read directly off a balance sheet, since Finnhub's free tier only exposes ratios/per-share
  figures, not raw dollar balance-sheet lines. This is the same category of approximation the code already
  made for `free_cash_flow` under the old FMP-only design, not a new kind of imprecision.

Tickers ingested before this migration have FMP-sourced snapshots already in the DB — nothing retroactively
changes them; the difference only shows up the next time each ticker gets refreshed.

## Core-tickers-first batch prioritization (2026-09-08)

Even after the Finnhub migration above cut FMP calls 9x, the batch job still attempts all ~467 tickers
every run, so a full pass still costs ~467 FMP calls (candles) against a ~250/day free-tier cap — meaning
most of the universe is stale most of the time, and on-demand refreshes (`POST /api/stocks/{ticker}/
refresh`) still had to compete with the batch job for whatever quota was left.

`scripts/refresh_universe.py` now processes `services/sp500_universe.py::CORE_TICKERS` — a small,
hand-picked, fixed set of ~10 well-known megacaps (AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, JPM, WMT,
XOM) — as its own fully-awaited batch *before* the rotated long-tail pass even starts, guaranteeing they
get first claim on the day's FMP quota rather than just a statistical edge from list order. `ScreenerFilters
.limit` (`app/models/schemas.py`) also defaults to 10 instead of 50, matching product intent: the screener
is a small always-fresh view plus whatever else users have explicitly searched, not an attempt at ranking
the full index. Verified locally (mocked providers, real batch-ordering logic): all 10 core tickers were
the first 10 processed regardless of their position in the underlying list.

Deliberately a **fixed** list, not "top N by market cap" or "top N by current score" — both of those are
circular (a ticker that's never refreshed can never earn a market cap or score figure to enter the set).
To change which tickers are always-fresh, just edit `CORE_TICKERS` directly.

Note: viewing the screener page itself never spends API quota — it only reads already-persisted DB rows
(`app/routers/screener.py`). All the quota cost is in `scripts/refresh_universe.py` (batch) and the
on-demand refresh route; a smaller screener `limit` doesn't save quota by itself, it just matches the UI
to what's realistically kept fresh.
