# Product Specification — AI-Powered Stock Intelligence Platform

Version 1.0 · Web Application · AI + Finance

Preserved as provided by the product owner. See `CLAUDE.md` for what's actually built vs. deferred to a
later phase, and for infra decisions that adapt this spec's "Deployment" section to the owner's existing
Render/Vercel/Supabase stack.

## 1. Product Overview

**Product Name:** Stock Intelligence Platform
**Goal:** Build a professional stock screening, valuation, technical analysis, and real-time news
intelligence platform that helps users identify high-potential investment and trading opportunities.

## 2. Core Features

### 2.1 Stock Screener

**Universe:** S&P 500 (Phase 1); expandable to NASDAQ, NYSE, global markets.

**Filters:**

- *Valuation* — P/E Ratio, Forward P/E, PEG Ratio, Price/Book, EV/EBITDA, Intrinsic Value vs Current Price,
  Margin of Safety %
- *Growth* — Revenue Growth (YoY), EPS Growth, Free Cash Flow Growth, ROE, ROIC
- *Financial Health* — Debt/Equity, Current Ratio, Interest Coverage, Altman Z-Score
- *Technical* — RSI, MACD, Moving Average Crossovers, 52-Week High/Low, Volume Breakout

### 2.2 Intrinsic Value Engine

**Methods:** Discounted Cash Flow (DCF), Dividend Discount Model, Owner Earnings Valuation, Comparable
Valuation.

**User Inputs:**

| Input | Default |
|---|---|
| Discount Rate (WACC) | 8% |
| FCF Growth Rate | 5% |
| Terminal Growth | 2.5% |
| Projection Years | 5 |

### 2.3 Technical Analysis Dashboard

**Charts:** Candlestick Chart, Volume Bars, MA20/MA50/MA200, Bollinger Bands, VWAP
**Indicators:** RSI (14), MACD (12,26,9), Stochastic RSI, ATR, OBV

### 2.4 Fibonacci & Support/Resistance

- Auto-detect swing high/low
- Draw Fib levels: 23.6, 38.2, 50, 61.8, 78.6
- Highlight support zones
- Highlight resistance zones
- Show breakout probability

### 2.5 AI Trading Assistant

Plain-English analysis, e.g.:

> "Apple is trading 18% below estimated intrinsic value. Revenue growth remains positive, debt is
> manageable, RSI is neutral, and MACD has turned bullish. A potential accumulation zone exists near the
> 61.8% Fibonacci level."

AI should generate: Bullish/Bearish score (0–100), Risk score, Investment thesis, Technical thesis, Key
risks, Recommended entry zone, Stop-loss, 3M/6M/1Y targets.

### 2.6 Real-Time News Intelligence

**Data Sources:** Finnhub, NewsAPI, Alpha Vantage News, Reddit sentiment, X/Twitter sentiment
**Features:** Live news feed per stock, sector news, breaking news alerts, AI sentiment analysis, impact
score (Low/Medium/High)

## 3. Alert System

User can create alerts for: price crosses support, MACD bullish crossover, RSI < 30, volume spike,
breaking news, analyst upgrades/downgrades.

**Delivery:** Email, Push notification, Telegram/Discord webhook.

## 4. System Architecture

- **Frontend:** Next.js + TypeScript, Tailwind CSS, TradingView Lightweight Charts, Recharts/Plotly
- **Backend:** Python FastAPI, REST + WebSocket APIs, background workers (Celery/RQ)
- **Database:** PostgreSQL, Redis cache, TimescaleDB for market data
- **Deployment:** Docker, AWS/GCP/Azure, CI/CD via GitHub Actions

## 5. API Requirements

| Endpoint | Purpose |
|---|---|
| `GET /stocks/{ticker}` | Fundamentals |
| `GET /technicals/{ticker}` | Indicators |
| `GET /valuation/{ticker}` | DCF |
| `GET /screener` | Ranked stocks |
| `GET /news/{ticker}` | News feed |
| `POST /alerts` | Create alerts |

## 6. AI Scoring Formula

**Composite Score:** Investment Score = 30% Valuation + 25% Growth + 20% Financial Health + 15% Technicals
+ 10% News Sentiment

**Output:** 90–100 Strong Buy · 75–89 Buy · 60–74 Hold · 40–59 Weak Hold · <40 Avoid

## 7. Future Features

Options flow analysis, insider trading tracker, earnings prediction model, portfolio optimization, AI
chatbot for stock questions, backtesting engine.

## 8. Recommended MVP (Build First)

Phase 1 MVP: S&P 500 screener, DCF valuation, candlestick + Fib chart, RSI + MACD, AI plain-English
analysis, news feed, email alerts.
