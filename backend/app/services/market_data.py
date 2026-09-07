"""
Market data: fundamentals/ratios/quote from Finnhub, historical price candles from
Financial Modeling Prep's `/stable` API. Split across two providers deliberately (see
CLAUDE.md -> "Finnhub fundamentals migration", added 2026-09-07):

- FMP's free tier caps out around 250 requests/day total. The original design called it
  9 times per ticker (quote/profile/ratios/key-metrics/financial-growth/financial-scores/
  balance-sheet-statement/income-statement/historical-candles), so the ~467-ticker
  universe took ~19 days of quota to fully cover, and any real-world usage — including
  the on-demand refresh route — competed with the daily batch job for the same tiny
  budget and regularly hit "Limit Reach" (confirmed live).
- Finnhub's free tier (already have a key, used for news) has no comparable daily cap —
  just a per-minute rate limit — and its `/stock/metric?metric=all` endpoint covers
  nearly everything FMP's fundamentals did (confirmed live, field-by-field). The one
  thing Finnhub's free tier explicitly does NOT allow is historical OHLCV candles
  (`/stock/candle` → 403 "You don't have access to this resource", confirmed live) — so
  FMP is kept for exactly that one call per ticker instead of nine. At 1 call/ticker,
  the full universe fits in a single day's FMP quota with room to spare.

Two known accuracy trade-offs from this split, both intentional:
- `altman_z_score` is always None now — Finnhub's free tier doesn't expose it, and
  computing it from scratch needs balance-sheet detail (working capital, retained
  earnings, EBIT, total assets/liabilities) that isn't available either without a paid
  plan on either provider. Same graceful-degradation pattern as any other missing field.
- `total_debt` and `cash_and_equivalents` are derived (ratio × per-share-value ×
  shares-outstanding) rather than read directly off a balance sheet, since Finnhub's
  free tier only exposes per-share/ratio metrics, not raw dollar balance-sheet figures.
  Same category of approximation the code already made for `free_cash_flow` even under
  the old FMP-only design — not a new kind of imprecision, just one more field doing it.

Only the fields this app actually persists (app/db/orm.py::FundamentalSnapshot) are
mapped; both providers return much more per endpoint that we don't use.

All functions return None/empty on missing data rather than raising, so a partial
provider response degrades the app to "some fields missing" instead of an ingestion-run
failure.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import asyncio

import httpx

from app.core.config import settings
from app.services.sp500_universe import SP500_UNIVERSE


class MarketDataError(RuntimeError):
    pass


def _fmp_client() -> httpx.AsyncClient:
    if not settings.fmp_api_key:
        raise MarketDataError("FMP_API_KEY is not configured.")
    return httpx.AsyncClient(base_url=settings.fmp_base_url, timeout=30.0)


def _finnhub_client() -> httpx.AsyncClient:
    if not settings.finnhub_api_key:
        raise MarketDataError("FINNHUB_API_KEY is not configured.")
    return httpx.AsyncClient(base_url=settings.finnhub_base_url, timeout=30.0)


async def get_sp500_constituents() -> list[dict]:
    """Returns [{symbol, name, sector}] — see sp500_universe.py for why this is static."""
    return [{"symbol": row["symbol"], "name": row["name"], "sector": row["sector"]} for row in SP500_UNIVERSE]


@dataclass
class FundamentalsData:
    price: float
    market_cap: float | None
    exchange: str | None
    pe_ratio: float | None
    forward_pe: float | None
    peg_ratio: float | None
    price_to_book: float | None
    ev_ebitda: float | None
    revenue_growth_yoy: float | None
    eps_growth: float | None
    fcf_growth: float | None
    roe: float | None
    roic: float | None
    debt_equity: float | None
    current_ratio: float | None
    interest_coverage: float | None
    altman_z_score: float | None
    free_cash_flow: float | None
    shares_outstanding: float | None
    total_debt: float | None
    cash_and_equivalents: float | None
    dividend_per_share: float | None
    eps: float | None
    book_value_per_share: float | None
    week52_high: float | None
    week52_low: float | None
    avg_volume: float | None


def _pct_to_fraction(value: float | None) -> float | None:
    """Finnhub's growth/return metrics come back as percent numbers (15.77 meaning
    15.77%); the rest of this app (scoring percentiles, valuation inputs, the frontend's
    formatPercent helper) all treat these fields as fractions (0.1577) — this was FMP's
    convention and every stock already ingested under the old provider used it, so
    Finnhub's numbers get converted rather than the other way around."""
    return None if value is None else value / 100


async def get_fundamentals(ticker: str) -> FundamentalsData | None:
    """Quote + company profile + the full basic-financials metric set, all from
    Finnhub's free tier."""
    async with _finnhub_client() as client:
        params = {"symbol": ticker, "token": settings.finnhub_api_key}
        quote_resp, profile_resp, metric_resp = await asyncio.gather(
            client.get("/quote", params=params),
            client.get("/stock/profile2", params=params),
            client.get("/stock/metric", params={**params, "metric": "all"}),
            return_exceptions=True,
        )

    quote = _safe_json(quote_resp) or {}
    profile = _safe_json(profile_resp) or {}
    metrics = (_safe_json(metric_resp) or {}).get("metric", {})

    price = quote.get("c") if quote else None
    if not price:
        return None

    shares_out_millions = profile.get("shareOutstanding") if profile else None
    shares_out = shares_out_millions * 1_000_000 if shares_out_millions else None

    book_value_per_share = metrics.get("bookValuePerShareAnnual")
    book_equity = book_value_per_share * shares_out if (book_value_per_share and shares_out) else None
    debt_equity = metrics.get("totalDebt/totalEquityAnnual")
    total_debt = debt_equity * book_equity if (debt_equity is not None and book_equity) else None

    cash_per_share = metrics.get("cashPerSharePerShareAnnual")
    cash_and_equivalents = cash_per_share * shares_out if (cash_per_share and shares_out) else None

    price_to_fcf = metrics.get("pfcfShareTTM")
    fcf_per_share = price / price_to_fcf if price_to_fcf else None
    free_cash_flow = fcf_per_share * shares_out if (fcf_per_share and shares_out) else None

    exchange = None
    if profile and profile.get("exchange"):
        exchange = profile["exchange"].split(" ")[0]  # Finnhub: "NASDAQ NMS - GLOBAL MARKET" -> "NASDAQ"

    return FundamentalsData(
        price=price,
        market_cap=(profile.get("marketCapitalization") * 1_000_000) if profile and profile.get("marketCapitalization") else None,
        exchange=exchange,
        pe_ratio=metrics.get("peTTM") or metrics.get("peBasicExclExtraTTM"),
        forward_pe=metrics.get("forwardPE"),
        peg_ratio=metrics.get("pegTTM"),
        price_to_book=metrics.get("pbAnnual") or metrics.get("pb"),
        ev_ebitda=metrics.get("evEbitdaTTM"),
        revenue_growth_yoy=_pct_to_fraction(metrics.get("revenueGrowthTTMYoy")),
        eps_growth=_pct_to_fraction(metrics.get("epsGrowthTTMYoy")),
        fcf_growth=_pct_to_fraction(metrics.get("focfCagr5Y")),  # 5Y CAGR proxy — Finnhub has no direct YoY FCF growth field
        roe=_pct_to_fraction(metrics.get("roeTTM")),
        roic=_pct_to_fraction(metrics.get("roiTTM")),  # ROI, not ROIC specifically — closest free-tier equivalent
        debt_equity=debt_equity,
        current_ratio=metrics.get("currentRatioAnnual"),
        interest_coverage=metrics.get("netInterestCoverageAnnual"),
        altman_z_score=None,  # not available on Finnhub's free tier, see module docstring
        free_cash_flow=free_cash_flow,
        shares_outstanding=shares_out,
        total_debt=total_debt,
        cash_and_equivalents=cash_and_equivalents,
        dividend_per_share=metrics.get("dividendPerShareTTM"),
        eps=metrics.get("epsTTM"),
        book_value_per_share=book_value_per_share,
        week52_high=metrics.get("52WeekHigh"),
        week52_low=metrics.get("52WeekLow"),
        avg_volume=(metrics.get("10DayAverageTradingVolume") * 1_000_000) if metrics.get("10DayAverageTradingVolume") else None,
    )


async def get_historical_candles(ticker: str, days: int = 400) -> list[dict]:
    """Returns [{date, open, high, low, close, volume}] ascending by date. Stays on FMP —
    Finnhub's free tier doesn't allow historical candles (see module docstring)."""
    to_date = date.today()
    from_date = to_date - timedelta(days=int(days * 1.6))  # padding for weekends/holidays
    async with _fmp_client() as client:
        resp = await client.get(
            "/historical-price-eod/full",
            params={"symbol": ticker, "from": from_date.isoformat(), "to": to_date.isoformat(), "apikey": settings.fmp_api_key},
        )
        resp.raise_for_status()
        rows = resp.json()
    if not isinstance(rows, list):
        return []
    rows.sort(key=lambda r: r["date"])
    return [
        {
            "date": datetime.strptime(r["date"], "%Y-%m-%d").date(),
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
            "volume": r.get("volume", 0),
        }
        for r in rows[-days:]
    ]


def _safe_json(resp: httpx.Response | BaseException) -> dict | None:
    if isinstance(resp, BaseException):
        return None
    try:
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else None
    except (httpx.HTTPStatusError, ValueError):
        return None
