"""
Financial Modeling Prep client — fundamentals, ratios, growth metrics, financial-health
scores, and historical price candles. Targets FMP's current `/stable` API
(https://site.financialmodelingprep.com/developer/docs/stable), NOT the legacy `/api/v3`
family — FMP retired `/api/v3` for anyone without a subscription predating August 2025
(confirmed directly against the live API: every v3 endpoint now 403s "Legacy Endpoint").
Only the fields this app actually persists (app/db/orm.py::FundamentalSnapshot) are
mapped; FMP returns much more per endpoint that we don't use.

The S&P 500 constituent list itself comes from services/sp500_universe.py (a static
list), not FMP — `/stable/sp500-constituent` is a paid-tier-only "Restricted Endpoint"
on a standard key (also confirmed live). See that module's docstring for why.

`forward_pe` is intentionally always None — FMP's forward P/E requires the
analyst-estimates endpoint, which needs a `period` parameter FMP's docs don't fully
specify and which returned errors during testing; not worth guessing at for an MVP
field that's secondary to trailing P/E.

All functions return None/empty on missing data rather than raising, so a partial provider
response degrades the app to "some fields missing" instead of an ingestion-run failure.
"""
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx

from app.core.config import settings
from app.services.sp500_universe import SP500_UNIVERSE


class MarketDataError(RuntimeError):
    pass


def _client() -> httpx.AsyncClient:
    if not settings.fmp_api_key:
        raise MarketDataError("FMP_API_KEY is not configured.")
    return httpx.AsyncClient(base_url=settings.fmp_base_url, timeout=30.0)


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


def _first(rows: list[dict] | None) -> dict:
    return rows[0] if rows else {}


async def get_fundamentals(ticker: str) -> FundamentalsData | None:
    """Fans out to FMP's quote/profile/ratios/key-metrics/financial-growth/
    financial-scores/balance-sheet-statement/income-statement endpoints (all under
    /stable) and merges them into one FundamentalsData record."""
    async with _client() as client:
        params = {"apikey": settings.fmp_api_key, "symbol": ticker}
        (
            quote_resp, profile_resp, ratios_resp, metrics_resp,
            growth_resp, score_resp, balance_resp, income_resp,
        ) = await _gather(
            client.get("/quote", params=params),
            client.get("/profile", params=params),
            client.get("/ratios", params={**params, "limit": 1}),
            client.get("/key-metrics", params={**params, "limit": 1}),
            client.get("/financial-growth", params={**params, "limit": 1}),
            client.get("/financial-scores", params=params),
            client.get("/balance-sheet-statement", params={**params, "limit": 1}),
            client.get("/income-statement", params={**params, "limit": 1}),
        )

    quote = _first(_safe_json(quote_resp))
    profile = _first(_safe_json(profile_resp))
    ratios = _first(_safe_json(ratios_resp))
    metrics = _first(_safe_json(metrics_resp))
    growth = _first(_safe_json(growth_resp))
    score = _first(_safe_json(score_resp))
    balance = _first(_safe_json(balance_resp))
    income = _first(_safe_json(income_resp))

    price = quote.get("price")
    if price is None:
        return None

    shares_out = income.get("weightedAverageShsOut")
    fcf_per_share = ratios.get("freeCashFlowPerShare")
    free_cash_flow = (fcf_per_share * shares_out) if (fcf_per_share and shares_out) else None

    return FundamentalsData(
        price=price,
        market_cap=quote.get("marketCap") or profile.get("marketCap"),
        exchange=quote.get("exchange") or profile.get("exchange"),
        pe_ratio=ratios.get("priceToEarningsRatio"),
        forward_pe=None,
        peg_ratio=ratios.get("priceToEarningsGrowthRatio"),
        price_to_book=ratios.get("priceToBookRatio"),
        ev_ebitda=metrics.get("evToEBITDA"),
        revenue_growth_yoy=growth.get("revenueGrowth"),
        eps_growth=growth.get("epsgrowth"),
        fcf_growth=growth.get("freeCashFlowGrowth"),
        roe=metrics.get("returnOnEquity"),
        roic=metrics.get("returnOnInvestedCapital"),
        debt_equity=ratios.get("debtToEquityRatio"),
        current_ratio=ratios.get("currentRatio"),
        interest_coverage=ratios.get("interestCoverageRatio"),
        altman_z_score=score.get("altmanZScore"),
        free_cash_flow=free_cash_flow,
        shares_outstanding=shares_out,
        total_debt=balance.get("totalDebt"),
        cash_and_equivalents=balance.get("cashAndCashEquivalents"),
        dividend_per_share=ratios.get("dividendPerShare"),
        eps=income.get("eps"),
        book_value_per_share=ratios.get("bookValuePerShare"),
        week52_high=quote.get("yearHigh"),
        week52_low=quote.get("yearLow"),
        avg_volume=profile.get("averageVolume"),
    )


async def get_historical_candles(ticker: str, days: int = 400) -> list[dict]:
    """Returns [{date, open, high, low, close, volume}] ascending by date."""
    to_date = date.today()
    from_date = to_date - timedelta(days=int(days * 1.6))  # padding for weekends/holidays
    async with _client() as client:
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


def _safe_json(resp: httpx.Response | BaseException) -> list[dict] | None:
    if isinstance(resp, BaseException):
        return None
    try:
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else [data]
    except (httpx.HTTPStatusError, ValueError):
        return None


async def _gather(*coros):
    # One endpoint failing (rate limit, 404 for a delisted ticker, transient network error)
    # shouldn't abort the whole fundamentals fetch — _safe_json treats an exception the
    # same as a missing field, so the caller just ends up with that field as None.
    return await asyncio.gather(*coros, return_exceptions=True)
