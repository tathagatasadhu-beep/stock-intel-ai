"""
Single-ticker ingestion pipeline: fetch fundamentals/candles from FMP, compute
technicals/Fibonacci/valuation, fetch news, score against a peer population, and
generate an AI analysis — then persist all of it.

This is the shared core that both `scripts/refresh_universe.py` (batch, all ~467
tickers, once a day) and the on-demand `POST /api/stocks/{ticker}/refresh` route
(one ticker, whenever a user asks for a ticker that hasn't been ingested yet — see
CLAUDE.md -> "On-demand refresh") call. It used to live only in refresh_universe.py;
pulled out here once the on-demand endpoint needed the exact same steps instead of
duplicating them.

Callers own the AsyncSession and the commit — this module only flushes, so a caller
processing many tickers concurrently (the batch script) can keep one session per
ticker, while a caller processing one ticker (the on-demand route) can commit once
at the end.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.orm import (
    AIAnalysis,
    FibonacciLevel,
    FundamentalSnapshot,
    NewsArticle,
    PortfolioHolding,
    PriceCandle,
    ScreenerScore,
    Stock,
    TechnicalSnapshot,
    ValuationResult,
)
from app.services import ai_engine, fibonacci as fib_service, market_data, news as news_service
from app.services import scoring, technicals as tech_service, valuation as valuation_service


@dataclass
class IngestResult:
    stock: Stock
    fundamentals: FundamentalSnapshot
    technicals: TechnicalSnapshot | None
    fibonacci: FibonacciLevel | None
    valuation: ValuationResult | None
    news: list[NewsArticle]


async def upsert_stock(
    db: AsyncSession, symbol: str, name: str, sector: str | None, asset_type: str = "stock", is_sp500: bool = True
) -> Stock:
    result = await db.execute(select(Stock).where(Stock.ticker == symbol))
    stock = result.scalar_one_or_none()
    if stock is None:
        stock = Stock(ticker=symbol, company_name=name, sector=sector, is_sp500=is_sp500, asset_type=asset_type)
        db.add(stock)
    else:
        stock.company_name = name
        stock.sector = sector
        # is_sp500/asset_type intentionally NOT overwritten on existing rows — a stock
        # already classified (e.g. by the static universe) shouldn't flip because a
        # portfolio holding happened to reference it too; see refresh_universe.py's
        # constituent-merging logic, which is what keeps this from being ambiguous.
    stock.last_refreshed_at = datetime.now(timezone.utc)
    await db.flush()
    return stock


async def refresh_fundamentals(db: AsyncSession, stock: Stock, as_of: date) -> FundamentalSnapshot | None:
    data = await market_data.get_fundamentals(stock.ticker)
    if data is None:
        return None
    stock.market_cap = data.market_cap
    stock.exchange = data.exchange

    result = await db.execute(
        select(FundamentalSnapshot).where(FundamentalSnapshot.stock_id == stock.id, FundamentalSnapshot.as_of_date == as_of)
    )
    snapshot = result.scalar_one_or_none() or FundamentalSnapshot(stock_id=stock.id, as_of_date=as_of)
    for field in (
        "price", "pe_ratio", "forward_pe", "peg_ratio", "price_to_book", "ev_ebitda", "revenue_growth_yoy",
        "eps_growth", "fcf_growth", "roe", "roic", "debt_equity", "current_ratio", "interest_coverage",
        "altman_z_score", "free_cash_flow", "shares_outstanding", "total_debt", "cash_and_equivalents",
        "dividend_per_share", "eps", "book_value_per_share", "week52_high", "week52_low", "avg_volume",
    ):
        setattr(snapshot, field, getattr(data, field))
    db.add(snapshot)
    await db.flush()
    return snapshot


async def refresh_candles(db: AsyncSession, stock: Stock) -> dict | None:
    rows = await market_data.get_historical_candles(stock.ticker)
    if not rows:
        return None

    existing = await db.execute(select(PriceCandle.date).where(PriceCandle.stock_id == stock.id))
    existing_dates = {r[0] for r in existing.all()}
    for row in rows:
        if row["date"] in existing_dates:
            continue
        db.add(PriceCandle(stock_id=stock.id, **row))
    await db.flush()

    return {
        "dates": [r["date"] for r in rows],
        "open": np.array([r["open"] for r in rows], dtype=float),
        "high": np.array([r["high"] for r in rows], dtype=float),
        "low": np.array([r["low"] for r in rows], dtype=float),
        "close": np.array([r["close"] for r in rows], dtype=float),
        "volume": np.array([r["volume"] for r in rows], dtype=float),
    }


async def compute_technicals(db: AsyncSession, stock: Stock, candles: dict, as_of: date) -> TechnicalSnapshot | None:
    closes, highs, lows, volumes = candles["close"], candles["high"], candles["low"], candles["volume"]
    if len(closes) < 20:
        return None

    sma20, sma50, sma200 = tech_service.sma(closes, 20), tech_service.sma(closes, 50), tech_service.sma(closes, 200)
    bb = tech_service.bollinger_bands(closes, 20)
    vwap = tech_service.rolling_vwap(highs, lows, closes, volumes)
    rsi = tech_service.rsi(closes)
    macd = tech_service.macd(closes)
    atr = tech_service.atr(highs, lows, closes)
    obv = tech_service.obv(closes, volumes)
    stoch_rsi = tech_service.stochastic_rsi(closes)

    def last(arr: np.ndarray) -> float | None:
        v = arr[-1]
        return None if np.isnan(v) else round(float(v), 4)

    result = await db.execute(
        select(TechnicalSnapshot).where(TechnicalSnapshot.stock_id == stock.id, TechnicalSnapshot.as_of_date == as_of)
    )
    snapshot = result.scalar_one_or_none() or TechnicalSnapshot(stock_id=stock.id, as_of_date=as_of)
    snapshot.rsi14 = last(rsi)
    snapshot.macd, snapshot.macd_signal, snapshot.macd_hist = last(macd.macd), last(macd.signal), last(macd.hist)
    snapshot.sma20, snapshot.sma50, snapshot.sma200 = last(sma20), last(sma50), last(sma200)
    snapshot.bollinger_upper, snapshot.bollinger_mid, snapshot.bollinger_lower = last(bb.upper), last(bb.mid), last(bb.lower)
    snapshot.vwap = last(vwap)
    snapshot.atr14 = last(atr)
    snapshot.obv = last(obv)
    snapshot.stoch_rsi = last(stoch_rsi)
    snapshot.ma_crossover_signal = tech_service.ma_crossover_signal(sma50, sma200)
    snapshot.volume_breakout = tech_service.volume_breakout(volumes)
    snapshot.week52_breakout = tech_service.week52_breakout(closes, highs, lows)
    db.add(snapshot)
    await db.flush()
    return snapshot


async def compute_fibonacci(db: AsyncSession, stock: Stock, candles: dict, as_of: date) -> FibonacciLevel | None:
    result = fib_service.compute_fibonacci(candles["high"], candles["low"], candles["close"], candles["volume"])
    if result is None:
        return None
    row = FibonacciLevel(
        stock_id=stock.id,
        as_of_date=as_of,
        trend_direction=result.trend_direction,
        swing_high=result.swing_high,
        swing_low=result.swing_low,
        level_0=result.levels["0"],
        level_236=result.levels["236"],
        level_382=result.levels["382"],
        level_500=result.levels["500"],
        level_618=result.levels["618"],
        level_786=result.levels["786"],
        level_100=result.levels["100"],
        nearest_support=result.nearest_support,
        nearest_resistance=result.nearest_resistance,
        breakout_probability=result.breakout_probability,
    )
    db.add(row)
    await db.flush()
    return row


async def compute_valuation(db: AsyncSession, stock: Stock, fundamentals: FundamentalSnapshot, as_of: date) -> ValuationResult | None:
    # Best-effort peer average — see refresh_universe.py's original comment on this same
    # logic for why this can be a partial sector sample rather than the full sector.
    peer_result = await db.execute(
        select(FundamentalSnapshot.pe_ratio)
        .join(Stock, Stock.id == FundamentalSnapshot.stock_id)
        .where(Stock.sector == stock.sector, Stock.id != stock.id, FundamentalSnapshot.pe_ratio.is_not(None))
    )
    pes = [r[0] for r in peer_result.all() if r[0] and r[0] > 0]
    peer_avg_pe = round(sum(pes) / len(pes), 2) if pes else None

    methods = [
        valuation_service.dcf_valuation(
            fundamentals.free_cash_flow, fundamentals.shares_outstanding, fundamentals.total_debt,
            fundamentals.cash_and_equivalents, settings.default_wacc, settings.default_fcf_growth_rate,
            settings.default_terminal_growth_rate, settings.default_projection_years,
        ),
        valuation_service.ddm_valuation(fundamentals.dividend_per_share, settings.default_wacc, settings.default_fcf_growth_rate),
        valuation_service.owner_earnings_valuation(fundamentals.eps, settings.default_wacc, settings.default_fcf_growth_rate),
        valuation_service.comparable_valuation(fundamentals.eps, peer_avg_pe),
    ]
    for m in methods:
        db.add(
            ValuationResult(
                stock_id=stock.id, as_of_date=as_of, method=m.method,
                wacc=settings.default_wacc, fcf_growth_rate=settings.default_fcf_growth_rate,
                terminal_growth_rate=settings.default_terminal_growth_rate, projection_years=settings.default_projection_years,
                intrinsic_value=m.intrinsic_value or 0.0, current_price=fundamentals.price,
                margin_of_safety_pct=valuation_service.margin_of_safety_pct(m.intrinsic_value, fundamentals.price) or 0.0,
            )
        )

    blended_value = valuation_service.blended_intrinsic_value(methods)
    blended = ValuationResult(
        stock_id=stock.id, as_of_date=as_of, method="blended",
        wacc=settings.default_wacc, fcf_growth_rate=settings.default_fcf_growth_rate,
        terminal_growth_rate=settings.default_terminal_growth_rate, projection_years=settings.default_projection_years,
        intrinsic_value=blended_value or 0.0, current_price=fundamentals.price,
        margin_of_safety_pct=valuation_service.margin_of_safety_pct(blended_value, fundamentals.price) or 0.0,
    )
    db.add(blended)
    await db.flush()
    return blended


async def refresh_news(db: AsyncSession, stock: Stock) -> list[NewsArticle]:
    articles = await news_service.fetch_news_for_ticker(stock.ticker, stock.company_name)
    existing = await db.execute(select(NewsArticle.url).where(NewsArticle.stock_id == stock.id))
    existing_urls = {r[0] for r in existing.all()}
    persisted = []
    for a in articles:
        if a["url"] in existing_urls:
            continue
        row = NewsArticle(stock_id=stock.id, **a)
        db.add(row)
        persisted.append(row)
    await db.flush()
    return persisted


async def ingest_ticker(
    db: AsyncSession, symbol: str, name: str, sector: str | None, as_of: date,
    asset_type: str = "stock", is_sp500: bool = True,
) -> IngestResult | None:
    """Runs the full fetch+compute pipeline for one ticker. Returns None (without
    raising) if the provider had no fundamentals/candles for it — a bad ticker or a
    provider hiccup shouldn't be indistinguishable from a crash to the caller.

    ETFs (asset_type="etf") skip the valuation step — P/E-style intrinsic-value
    methods don't meaningfully apply to a fund — but still get candles/technicals/
    Fibonacci/news/AI-analysis, since price action and news sentiment are just as
    relevant to a fund as a stock. See score_and_analyze_one for the scoring-side
    equivalent (skips the composite screener score, not just valuation)."""
    stock = await upsert_stock(db, symbol, name, sector, asset_type=asset_type, is_sp500=is_sp500)
    fundamentals = await refresh_fundamentals(db, stock, as_of)
    candles = await refresh_candles(db, stock)
    if fundamentals is None or candles is None:
        return None

    technicals = await compute_technicals(db, stock, candles, as_of)
    fib = await compute_fibonacci(db, stock, candles, as_of)
    blended_valuation = None if stock.asset_type == "etf" else await compute_valuation(db, stock, fundamentals, as_of)
    news_articles = await refresh_news(db, stock)

    return IngestResult(
        stock=stock, fundamentals=fundamentals, technicals=technicals,
        fibonacci=fib, valuation=blended_valuation, news=news_articles,
    )


async def build_population_from_db(db: AsyncSession, as_of: date) -> scoring.Population:
    """Builds a scoring Population from every stock's latest-as-of-today snapshot
    already in the DB — used by the on-demand refresh route, which scores one new
    ticker against whatever peer set has been ingested so far rather than the full
    (mostly-not-yet-ingested) universe. Gets more representative as coverage grows;
    the batch script builds a tighter Population directly from its own run's results
    instead (see refresh_universe.py::score_and_analyze) since it has all of them in
    memory already."""
    pop = scoring.Population()
    fundamentals_rows = (await db.execute(select(FundamentalSnapshot).where(FundamentalSnapshot.as_of_date == as_of))).scalars().all()
    for f in fundamentals_rows:
        pop.pe_ratio.append(f.pe_ratio)
        pop.forward_pe.append(f.forward_pe)
        pop.peg_ratio.append(f.peg_ratio)
        pop.price_to_book.append(f.price_to_book)
        pop.ev_ebitda.append(f.ev_ebitda)
        pop.revenue_growth_yoy.append(f.revenue_growth_yoy)
        pop.eps_growth.append(f.eps_growth)
        pop.fcf_growth.append(f.fcf_growth)
        pop.roe.append(f.roe)
        pop.roic.append(f.roic)
        pop.debt_equity.append(f.debt_equity)
        pop.current_ratio.append(f.current_ratio)
        pop.interest_coverage.append(f.interest_coverage)
        pop.altman_z_score.append(f.altman_z_score)

        valuation_row = (
            await db.execute(
                select(ValuationResult).where(
                    ValuationResult.stock_id == f.stock_id, ValuationResult.as_of_date == as_of, ValuationResult.method == "blended"
                )
            )
        ).scalar_one_or_none()
        pop.margin_of_safety_pct.append(valuation_row.margin_of_safety_pct if valuation_row else None)

        technical_row = (
            await db.execute(select(TechnicalSnapshot).where(TechnicalSnapshot.stock_id == f.stock_id, TechnicalSnapshot.as_of_date == as_of))
        ).scalar_one_or_none()
        pop.macd_hist.append(technical_row.macd_hist if technical_row else None)
    return pop


async def get_portfolio_ticker_symbols(db: AsyncSession) -> set[str]:
    """All distinct tickers referenced by ANY user's portfolio holdings — used by
    scripts/refresh_universe.py to widen the batch job's always-fresh priority tier
    beyond CORE_TICKERS, since a user's real positions should stay fresh regardless of
    whether they're in the static universe or one of the fixed core tickers."""
    result = await db.execute(select(Stock.ticker).join(PortfolioHolding, PortfolioHolding.stock_id == Stock.id).distinct())
    return {r[0] for r in result.all()}


async def get_non_universe_portfolio_stocks(db: AsyncSession, universe_symbols: set[str]) -> list[Stock]:
    """Stocks referenced by a portfolio holding whose ticker ISN'T in the static S&P 500
    universe (services/sp500_universe.py) — ETFs, or a stock outside the curated list.
    These need their own constituent-dict entries in the batch job's priority tier since
    the static-universe pass will never reach them otherwise. Their name/sector/asset_type
    were already set when the holding was created (see routers/portfolio.py), so no
    provider call is needed just to enumerate them."""
    holding_stock_ids = select(PortfolioHolding.stock_id).distinct()
    result = await db.execute(select(Stock).where(Stock.id.in_(holding_stock_ids)))
    return [s for s in result.scalars().all() if s.ticker not in universe_symbols]


async def score_and_analyze_one(db: AsyncSession, result: IngestResult, pop: scoring.Population, as_of: date) -> None:
    """The scoring + AI-analysis half of the pipeline for a single already-ingested
    ticker — shared by both callers, same as the fetch/compute half above.

    ETFs skip the composite screener score entirely (not just valuation) — funds don't
    have the fundamentals-based fields the score is built from (P/E, ROE, debt/equity
    are all meaningless for a fund), so a composite number would be misleading rather
    than just incomplete. They still get an AI analysis (technical/thesis framing, not
    valuation-based) since that's useful for portfolio monitoring regardless of asset
    type — see the `is_etf` context flag below."""
    stock, f, t, v, fib, articles = result.stock, result.fundamentals, result.technicals, result.valuation, result.fibonacci, result.news
    is_etf = stock.asset_type == "etf"

    composite = None
    rating = None
    if not is_etf:
        valuation_score = scoring.compute_valuation_score(
            f.pe_ratio, f.forward_pe, f.peg_ratio, f.price_to_book, f.ev_ebitda, v.margin_of_safety_pct if v else None, pop,
        )
        growth_score = scoring.compute_growth_score(f.revenue_growth_yoy, f.eps_growth, f.fcf_growth, f.roe, f.roic, pop)
        health_score = scoring.compute_financial_health_score(f.debt_equity, f.current_ratio, f.interest_coverage, f.altman_z_score, pop)
        technical_score = scoring.compute_technical_score(
            t.rsi14 if t else None, t.macd_hist if t else None, t.ma_crossover_signal if t else None,
            t.volume_breakout if t else False, t.week52_breakout if t else None, pop,
        )
        news_score = scoring.compute_news_sentiment_score(
            [a.sentiment_score for a in articles if a.sentiment_score is not None],
            [a.impact_score for a in articles if a.impact_score],
        )
        composite = scoring.compute_composite_score(valuation_score, growth_score, health_score, technical_score, news_score)
        rating = scoring.rating_for_score(composite)

        existing_score = (
            await db.execute(select(ScreenerScore).where(ScreenerScore.stock_id == stock.id, ScreenerScore.as_of_date == as_of))
        ).scalar_one_or_none()
        score_row = existing_score or ScreenerScore(stock_id=stock.id, as_of_date=as_of)
        score_row.valuation_score = valuation_score
        score_row.growth_score = growth_score
        score_row.financial_health_score = health_score
        score_row.technical_score = technical_score
        score_row.news_sentiment_score = news_score
        score_row.composite_score = composite
        score_row.rating = rating
        db.add(score_row)

    context = {
        "ticker": stock.ticker, "company_name": stock.company_name, "sector": stock.sector, "is_etf": is_etf,
        "price": f.price, "pe_ratio": f.pe_ratio, "peg_ratio": f.peg_ratio, "roe": f.roe,
        "revenue_growth_yoy": f.revenue_growth_yoy, "debt_equity": f.debt_equity, "altman_z_score": f.altman_z_score,
        "margin_of_safety_pct": v.margin_of_safety_pct if v else None,
        "rsi14": t.rsi14 if t else None, "macd_hist": t.macd_hist if t else None,
        "nearest_support": fib.nearest_support if fib else None, "nearest_resistance": fib.nearest_resistance if fib else None,
        "composite_score": composite, "rating": rating,
    }
    ai_result = await ai_engine.generate_ai_analysis(context)
    db.add(
        AIAnalysis(
            stock_id=stock.id, bullish_bearish_score=ai_result.bullish_bearish_score, risk_score=ai_result.risk_score,
            investment_thesis=ai_result.investment_thesis, technical_thesis=ai_result.technical_thesis,
            key_risks="\n".join(ai_result.key_risks), entry_zone_low=ai_result.entry_zone_low,
            entry_zone_high=ai_result.entry_zone_high, stop_loss=ai_result.stop_loss, target_3m=ai_result.target_3m,
            target_6m=ai_result.target_6m, target_1y=ai_result.target_1y, raw_model_output=ai_result.raw_model_output,
        )
    )
