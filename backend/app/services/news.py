"""
News feed client (spec section 2.6). Uses NewsAPI by default (NEWS_API_KEY). Swap the
`_fetch_newsapi` call for a Finnhub equivalent if you'd rather use that provider — the
NewsArticle shape returned to callers is provider-agnostic on purpose.

Sentiment analysis: a simple lexicon-based scorer, not a call out to a separate sentiment
model. Good enough for a "positive/neutral/negative" headline tag; the AI engine
(services/ai_engine.py) does the deeper qualitative analysis via OpenAI.
"""
from datetime import datetime, timezone

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


async def fetch_news_for_ticker(ticker: str, company_name: str, page_size: int = 10) -> list[dict]:
    if not settings.news_api_key:
        return []
    async with httpx.AsyncClient(base_url=settings.news_api_base_url, timeout=20.0) as client:
        resp = await client.get(
            "/everything",
            params={
                "q": f'"{ticker}" OR "{company_name}"',
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": page_size,
                "apiKey": settings.news_api_key,
            },
        )
        if resp.status_code != 200:
            return []
        data = resp.json()

    articles = []
    for row in data.get("articles", []):
        headline = row.get("title") or ""
        summary = row.get("description")
        sentiment_score, sentiment_label = score_sentiment(headline, summary)
        published_at_raw = row.get("publishedAt")
        try:
            published_at = datetime.fromisoformat(published_at_raw.replace("Z", "+00:00")) if published_at_raw else datetime.now(timezone.utc)
        except ValueError:
            published_at = datetime.now(timezone.utc)

        articles.append(
            {
                "source": (row.get("source") or {}).get("name") or "unknown",
                "headline": headline,
                "url": row.get("url"),
                "summary": summary,
                "published_at": published_at,
                "sentiment_score": sentiment_score,
                "sentiment_label": sentiment_label,
                "impact_score": estimate_impact((row.get("source") or {}).get("name") or "", sentiment_score),
            }
        )
    return [a for a in articles if a["url"]]
