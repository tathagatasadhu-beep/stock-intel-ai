# Stock Intelligence Platform

AI-powered stock screening, valuation, technical analysis, and news-intelligence platform for the
S&P 500 — a professional research tool in the spirit of TradingView/Finviz, built for personal/family
investment research use.

Full product spec: see `SPEC.md`. Current build status, architecture decisions, and conventions: see
`CLAUDE.md` — read that first if you're picking this project up.

## Stack

- **Frontend**: Next.js 16 (TypeScript, Tailwind CSS, TradingView Lightweight Charts) — deploys to Vercel
- **Backend**: FastAPI (Python) — deploys to Render
- **Database**: PostgreSQL via Supabase (also provides Auth)
- **Cache**: Redis (Render managed Redis) — screener result caching, rate-limit buffering for the market
  data provider
- **Market data**: Financial Modeling Prep (fundamentals, ratios, price candles)
- **News**: Finnhub (headlines + sentiment)
- **AI**: OpenAI (plain-English investment thesis, bullish/bearish + risk scoring)

## Live

- Frontend: https://stock-intel-ai-liart.vercel.app
- Backend: https://stock-intel-ai-luk3.onrender.com (health check at `/api/health`)

## Repo layout

```
backend/    FastAPI app, services (technicals/valuation/AI/screener), ingestion scripts
frontend/   Next.js app — Server Components + BFF route handlers, browser never calls backend directly
```

## Local development

See `CLAUDE.md` → "Local dev machine is ARM64 Windows" for why the backend runs against SQLite locally
instead of Postgres, and how to start both servers.

## Status

Phase 1 MVP scaffold — see `CLAUDE.md` for exactly what's built vs. still a stub, and what the spec's
Phase 2+ features (real-time WebSocket price streaming, Telegram/Discord alerts, options flow, portfolio
optimization, backtesting) intentionally left out of this pass look like.
