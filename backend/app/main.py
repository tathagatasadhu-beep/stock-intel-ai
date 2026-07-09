"""
Stock Intelligence Platform backend entrypoint.

Run locally (against Postgres): uvicorn app.main:app --reload --port 8000
Run locally on this ARM64 Windows machine (SQLite, no asyncpg build needed):
    python dev_server_sqlite.py
"""
from dotenv import load_dotenv

load_dotenv()  # local dev only — Render sets real env vars directly in production

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import alerts, auth, news, screener, stocks, technicals, valuation

app = FastAPI(
    title="Stock Intelligence Platform API",
    version="0.1.0",
    description="Backend for the AI-powered stock screening, valuation, and technical analysis platform.",
)

# Irrelevant in production: the browser never talks to this API directly (see CLAUDE.md ->
# Conventions, same BFF architecture as EduQuestAI). Only Next.js's server-side Route
# Handlers call this, so CORS never needs to allow the deployed frontend's origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # 3001: this machine's stock-intel-ai dev port, see dev_server_sqlite.py
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router, prefix="/api/stocks", tags=["stocks"])
app.include_router(technicals.router, prefix="/api/technicals", tags=["technicals"])
app.include_router(valuation.router, prefix="/api/valuation", tags=["valuation"])
app.include_router(screener.router, prefix="/api/screener", tags=["screener"])
app.include_router(news.router, prefix="/api/news", tags=["news"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
