"""
Financial Modeling Prep client — fundamentals, ratios, growth metrics, financial-health
scores, and historical price candles. See https://site.financialmodelingprep.com/developer/docs
Only the fields this app actually persists (app/db/orm.py::FundamentalSnapshot) are mapped;
FMP returns much more per endpoint that we don't use.

All functions return None/empty on missing data rather than raising, so a partial provider
response degrades the app to "some fields missing" instead of an ingestion-run failure.
"""
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from app.core.config import settings


class MarketDataError(RuntimeError):
    pass


def _client() -> httpx.AsyncClient:
    if not settings.fmp_api_key:
        raise MarketDataError("FMP_API_KEY is not configured.")
    return httpx.AsyncClient(base_url=settings.fmp_base_url, timeout=30.0)


async def get_sp500_constituents() -> list[dict]:
    """Returns [{symbol, name, sector, industry}] for the current S&P 500."""
    async with _client() as client:
        resp = await client.get("/sp500_constituent", params={"apikey": settings.fmp_api_key})
        resp.raise_for_status()
        data = resp.json()
    return [
        {
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "sector": row.get("sector"),
            "sub_sector": row.get("subSector"),
        }
        for row in data
        if row.get("symbol")
    ]


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
    """Fans out to FMP's quote/ratios/key-metrics/financial-growth/score endpoints and
    merges them into one FundamentalsData record."""
    async with _client() as client:
        params = {"apikey": settings.fmp_api_key}
        quote_resp, profile_resp, ratios_resp, metrics_resp, growth_resp, score_resp = await _gather(
            client.get(f"/quote/{ticker}", params=params),
            client.get(f"/profile/{ticker}", params=params),
            client.get(f"/ratios/{ticker}", params={**params, "limit": 1}),
            client.get(f"/key-metrics/{ticker}", params={**params, "limit": 1}),
            client.get(f"/financial-growth/{ticker}", params={**params, "limit": 1}),
            client.get(f"/score", params={**params, "symbol": ticker}),
        )

    quote = _first(_safe_json(quote_resp))
    profile = _first(_safe_json(profile_resp))
    ratios = _first(_safe_json(ratios_resp))
    metrics = _first(_safe_json(metrics_resp))
    growth = _first(_safe_json(growth_resp))
    score = _first(_safe_json(score_resp))

    price = quote.get("price")
    if price is None:
        return None

    fcf_per_share = metrics.get("freeCashFlowPerShare") or 0
    shares_out = quote.get("sharesOutstanding") or 0
    free_cash_flow = (fcf_per_share * shares_out) or None

    dividend_yield = metrics.get("dividendYield") or 0
    dividend_per_share = (dividend_yield * price) or None

    return FundamentalsData(
        price=price,
        market_cap=quote.get("marketCap"),
        exchange=quote.get("exchange") or profile.get("exchangeShortName"),
        pe_ratio=quote.get("pe") or ratios.get("priceEarningsRatio"),
        forward_pe=metrics.get("peRatio"),
        peg_ratio=ratios.get("priceEarningsToGrowthRatio"),
        price_to_book=ratios.get("priceToBookRatio"),
        ev_ebitda=ratios.get("enterpriseValueMultiple"),
        revenue_growth_yoy=growth.get("revenueGrowth"),
        eps_growth=growth.get("epsgrowth"),
        fcf_growth=growth.get("freeCashFlowGrowth"),
        roe=ratios.get("returnOnEquity"),
        roic=metrics.get("roic"),
        debt_equity=ratios.get("debtEquityRatio"),
        current_ratio=ratios.get("currentRatio"),
        interest_coverage=ratios.get("interestCoverage"),
        altman_z_score=score.get("altmanZScore"),
        free_cash_flow=free_cash_flow,
        shares_outstanding=quote.get("sharesOutstanding"),
        total_debt=metrics.get("totalDebt"),
        cash_and_equivalents=metrics.get("cashAndCashEquivalents"),
        dividend_per_share=dividend_per_share,
        eps=quote.get("eps"),
        book_value_per_share=metrics.get("bookValuePerShare"),
        week52_high=quote.get("yearHigh"),
        week52_low=quote.get("yearLow"),
        avg_volume=quote.get("avgVolume"),
    )


async def get_historical_candles(ticker: str, days: int = 400) -> list[dict]:
    """Returns [{date, open, high, low, close, volume}] ascending by date."""
    async with _client() as client:
        resp = await client.get(f"/historical-price-full/{ticker}", params={"apikey": settings.fmp_api_key, "timeseries": days})
        resp.raise_for_status()
        data = resp.json()
    rows = data.get("historical", [])
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
        for r in rows
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
    import asyncio

    # One endpoint failing (rate limit, 404 for a delisted ticker, transient network error)
    # shouldn't abort the whole fundamentals fetch — _safe_json treats an exception the
    # same as a missing field, so the caller just ends up with that field as None.
    return await asyncio.gather(*coros, return_exceptions=True)
