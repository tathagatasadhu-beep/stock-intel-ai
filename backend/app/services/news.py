"""
News feed client (spec section 2.6). Uses Finnhub's company-news endpoint
(https://finnhub.io/docs/api/company-news) — free tier covers this. The NewsArticle
shape returned to callers is provider-agnostic on purpose; swap `_fetch_finnhub` for
another provider (NewsAPI, Alpha Vantage News) without touching any caller.

Sentiment analysis: a simple lexicon-based scorer, not a call out to a separate sentiment
model. Good enough for a "positive/neutral/negative" headline tag; the AI engine
(services/ai_engine.py) does the deeper qualitative analysis via OpenAI.
"""
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings

_POSITIVE_WORDS = {
    "beat", "beats", "surge", "surges", "soar", "soars", "rally", "rallies", "upgrade", "upgrades",
    "record", "growth", "profit", "profits", "gain", "gains", "outperform", "bullish", "strong",
    "exceeds", "expansion", "buyback", "raise", "raises", "positive", "wins", "win",
}
_NEGATIVE_WORDS = {
    "miss", "misses", "plunge", "plunges", "slump", "slumps", "downgrade", "downgrades", "loss",
    "losses", "decline", "declines", "layoff", "layoffs", "lawsuit", "recall", "bearish", "weak",
    "cuts", "cut", "warns", "warning", "investigation", "fraud", "bankruptcy", "negative", "fall", "falls",
}


def score_sentiment(headline: str, summary: str | None = None) -> tuple[float, str]:
    text = f"{headline} {summary or ''}".lower()
    words = set(text.replace(",", " ").replace(".", " ").split())
    pos = len(words & _POSITIVE_WORDS)
    neg = len(words & _NEGATIVE_WORDS)
    if pos == 0 and neg == 0:
        return 0.0, "neutral"
    score = (pos - neg) / max(pos + neg, 1)
    label = "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"
    return round(score, 2), label


def estimate_impact(source: str, sentiment_score: float) -> str:
    """Heuristic: strong sentiment (positive or negative) from a headline = higher impact."""
    magnitude = abs(sentiment_score)
    if magnitude >= 0.6:
        return "high"
    if magnitude >= 0.25:
        return "medium"
    return "low"


async def fetch_news_for_ticker(ticker: str, company_name: str, days_back: int = 7, limit: int = 10) -> list[dict]:
    if not settings.finnhub_api_key:
        return []

    today = datetime.now(timezone.utc).date()
    async with httpx.AsyncClient(base_url=settings.finnhub_base_url, timeout=20.0) as client:
        resp = await client.get(
            "/company-news",
            params={
                "symbol": ticker,
                "from": (today - timedelta(days=days_back)).isoformat(),
                "to": today.isoformat(),
                "token": settings.finnhub_api_key,
            },
        )
        if resp.status_code != 200:
            return []
        data = resp.json()

    articles = []
    for row in data[:limit] if isinstance(data, list) else []:
        headline = row.get("headline") or ""
        summary = row.get("summary")
        sentiment_score, sentiment_label = score_sentiment(headline, summary)
        unix_ts = row.get("datetime")
        published_at = datetime.fromtimestamp(unix_ts, tz=timezone.utc) if unix_ts else datetime.now(timezone.utc)

        articles.append(
            {
                "source": row.get("source") or "unknown",
                "headline": headline,
                "url": row.get("url"),
                "summary": summary,
                "published_at": published_at,
                "sentiment_score": sentiment_score,
                "sentiment_label": sentiment_label,
                "impact_score": estimate_impact(row.get("source") or "", sentiment_score),
            }
        )
    return [a for a in articles if a["url"] and a["headline"]]
