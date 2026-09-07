"""GET /stocks/{ticker} — fundamentals + recent candles for a single stock (spec section 5).
POST /stocks/{ticker}/refresh — on-demand ingestion for a covered-but-not-yet-refreshed
ticker, so a user doesn't have to wait for the next scheduled batch run (see CLAUDE.md ->
"On-demand refresh")."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.orm import AIAnalysis, FundamentalSnapshot, PriceCandle, Stock
from app.db.session import get_db
from app.models.schemas import AIAnalysisOut, CandleOut, FundamentalsOut, StockSummary
from app.services import ingest
from app.services.sp500_universe import SP500_UNIVERSE

router = APIRouter()

_UNIVERSE_SYMBOLS = {row["symbol"] for row in SP500_UNIVERSE}
_UNIVERSE_BY_SYMBOL = {row["symbol"]: row for row in SP500_UNIVERSE}


async def _get_stock_or_404(ticker: str, db: AsyncSession) -> Stock:
    result = await db.execute(select(Stock).where(Stock.ticker == ticker.upper()))
    stock = result.scalar_one_or_none()
    if stock is None:
        # A missing `Stock` row means one of two different things, and the frontend
        # (see stock/[ticker]/page.tsx) needs to tell them apart: genuinely outside our
        # curated universe (services/sp500_universe.py) vs. in the universe but not yet
        # ingested by scripts/refresh_universe.py (e.g. this week's FMP-quota rotation
        # hasn't reached it yet). Same underlying condition (no row), different message.
        if ticker.upper() in _UNIVERSE_SYMBOLS:
            raise HTTPException(status_code=404, detail=f"{ticker.upper()} is in our coverage universe but hasn't been refreshed yet — check back after the next data refresh.")
        raise HTTPException(status_code=404, detail=f"Unknown ticker: {ticker} — not part of this screener's coverage universe.")
    return stock


async def _latest_fundamentals(stock_id, db: AsyncSession) -> FundamentalSnapshot | None:
    result = await db.execute(
        select(FundamentalSnapshot)
        .where(FundamentalSnapshot.stock_id == stock_id)
        .order_by(FundamentalSnapshot.as_of_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("", response_model=list[StockSummary])
async def list_stocks(q: str | None = None, limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Ticker/company-name search — used by the frontend's search box."""
    stmt = select(Stock).where(Stock.is_sp500.is_(True)).limit(limit)
    if q:
        like = f"%{q.upper()}%"
        stmt = select(Stock).where(Stock.ticker.like(like) | Stock.company_name.ilike(f"%{q}%")).limit(limit)
    result = await db.execute(stmt)
    stocks = result.scalars().all()

    out = []
    for stock in stocks:
        fundamentals = await _latest_fundamentals(stock.id, db)
        out.append(
            StockSummary(
                ticker=stock.ticker,
                company_name=stock.company_name,
                sector=stock.sector,
                industry=stock.industry,
                market_cap=stock.market_cap,
                price=fundamentals.price if fundamentals else None,
            )
        )
    return out


@router.get("/{ticker}", response_model=FundamentalsOut)
async def get_stock_fundamentals(ticker: str, db: AsyncSession = Depends(get_db)):
    stock = await _get_stock_or_404(ticker, db)
    fundamentals = await _latest_fundamentals(stock.id, db)
    if fundamentals is None:
        raise HTTPException(status_code=404, detail=f"No fundamentals data for {ticker} yet — run the ingestion script.")
    return fundamentals


@router.get("/{ticker}/candles", response_model=list[CandleOut])
async def get_stock_candles(ticker: str, days: int = 400, db: AsyncSession = Depends(get_db)):
    stock = await _get_stock_or_404(ticker, db)
    result = await db.execute(
        select(PriceCandle).where(PriceCandle.stock_id == stock.id).order_by(PriceCandle.date.desc()).limit(days)
    )
    candles = list(reversed(result.scalars().all()))
    return candles


@router.get("/{ticker}/ai-analysis", response_model=AIAnalysisOut)
async def get_ai_analysis(ticker: str, db: AsyncSession = Depends(get_db)):
    stock = await _get_stock_or_404(ticker, db)
    result = await db.execute(
        select(AIAnalysis).where(AIAnalysis.stock_id == stock.id).order_by(AIAnalysis.generated_at.desc()).limit(1)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"No AI analysis for {ticker} yet — run the ingestion script.")
    return AIAnalysisOut(
        generated_at=analysis.generated_at,
        bullish_bearish_score=analysis.bullish_bearish_score,
        risk_score=analysis.risk_score,
        investment_thesis=analysis.investment_thesis,
        technical_thesis=analysis.technical_thesis,
        key_risks=[line for line in analysis.key_risks.split("\n") if line.strip()],
        entry_zone_low=analysis.entry_zone_low,
        entry_zone_high=analysis.entry_zone_high,
        stop_loss=analysis.stop_loss,
        target_3m=analysis.target_3m,
        target_6m=analysis.target_6m,
        target_1y=analysis.target_1y,
    )


@router.post("/{ticker}/refresh")
async def refresh_stock_now(ticker: str, db: AsyncSession = Depends(get_db)):
    """Fetches live data for one ticker right now instead of waiting for the next
    scheduled batch run — for a ticker that's in our coverage universe but hasn't been
    ingested yet (e.g. this week's FMP-quota rotation hasn't reached it). Takes several
    seconds (real FMP/OpenAI/Finnhub calls); the frontend shows a loading state while
    this runs (see components/RefreshNowButton.tsx).

    Idempotent per day: if this ticker already has today's snapshot, returns
    immediately without spending any provider quota — this is also what makes it safe
    to expose without auth or extra rate-limiting of its own; the worst case is one
    real ingestion per ticker per day, same cost as that ticker being covered by the
    batch job."""
    ticker = ticker.upper()
    universe_row = _UNIVERSE_BY_SYMBOL.get(ticker)
    if universe_row is None:
        raise HTTPException(status_code=400, detail=f"{ticker} is not part of this screener's coverage universe.")

    today = date.today()

    existing_stock = (await db.execute(select(Stock).where(Stock.ticker == ticker))).scalar_one_or_none()
    if existing_stock is not None:
        already_current = (
            await db.execute(
                select(FundamentalSnapshot).where(FundamentalSnapshot.stock_id == existing_stock.id, FundamentalSnapshot.as_of_date == today)
            )
        ).scalar_one_or_none()
        if already_current is not None:
            return {"status": "already_current", "ticker": ticker}

    try:
        result = await ingest.ingest_ticker(db, ticker, universe_row["name"], universe_row["sector"], today)
    except Exception as exc:  # noqa: BLE001 - surface as a clean 502, not a 500 traceback
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"Failed to fetch live data for {ticker}: {exc}") from exc

    if result is None:
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"The market data provider had no data for {ticker} right now — try again shortly.")

    pop = await ingest.build_population_from_db(db, today)
    await ingest.score_and_analyze_one(db, result, pop, today)
    await db.commit()

    return {"status": "refreshed", "ticker": ticker}
